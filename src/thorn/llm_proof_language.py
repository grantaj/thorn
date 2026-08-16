from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from thorn.dependencies import DependencyGraph
from thorn.evidence import InferenceStatus
from thorn.formula_ir import ExprLoweringStatus, MathExpr, render_math_expr
from thorn.frontend import SourceSpan
from thorn.higher_proof_structure import ProofBranch, ProofControlStructure, ProofStructureKind
from thorn.models import SourceRange, TheoremUnit
from thorn.proof_obligations import (
    ObligationStatus,
    ProofObligation,
    ProofProposition,
    ProofRuleKind,
    ProofStepEdge,
    PropositionRole,
)
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.semantic_transformations import (
    SemanticApplicationObligation,
    SemanticSupportAtom,
    SemanticSupportKind,
    SemanticTransformation,
    SemanticTransformationIR,
    SemanticTransformationKind,
    build_semantic_transformation_ir,
)
from thorn.symbol_resolution_ir import ExpressionRef
from thorn.symbols import SymbolTable

FORMAT_VERSION = "thorn-proof/1"
DEFAULT_MAX_SOURCE_REQUESTS = 8


class ProofLanguageStyle(StrEnum):
    """Keyless rendering candidates over the same canonical semantic payload."""

    COMPACT = "compact"
    EXPLICIT = "explicit"


class ProofLanguageSourceHandle(BaseModel):
    """Thorn-side exact source payload addressable from the model-facing language."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    ir_identifier: str
    text: str
    source_span: SourceSpan | None = None
    source_range: SourceRange | None = None
    referenced_result_identifier: str | None = None


class LLMProofLanguage(BaseModel):
    """Stable issue-65 delaboration plus a non-rendered exact source map."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: Literal["thorn-proof/1"] = "thorn-proof/1"
    result_identifier: str
    lines: tuple[str, ...] = ()
    sources: tuple[ProofLanguageSourceHandle, ...] = ()

    def render_initial(self) -> str:
        return "\n".join(self.lines) + "\n"

    def fingerprint(self) -> str:
        payload = f"{self.format_version}\n{self.render_initial()}".encode()
        return hashlib.sha256(payload).hexdigest()

    def source(self, address: str) -> ProofLanguageSourceHandle:
        for item in self.sources:
            if item.address == address:
                return item
        raise KeyError(f"unknown proof-language source address {address!r}")

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class SourceRescueRequest(BaseModel):
    """One bounded source-on-demand request tied to an exact initial packet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_fingerprint: str
    addresses: tuple[str, ...]
    round_number: Literal[1] = 1


class SourceRescueResponse(BaseModel):
    """Exact requested source for the single supported rescue round."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_fingerprint: str
    addresses: tuple[str, ...]
    round_number: Literal[1] = 1
    text: str


_NEED_SOURCE_RE = re.compile(
    r"^\s*NEED_SOURCE\s+([A-Za-z][A-Za-z0-9:._-]*(?:\s*,\s*[A-Za-z][A-Za-z0-9:._-]*)*)\s*$"
)

_CONTROL_WORDS: dict[ProofStructureKind, str] = {
    ProofStructureKind.CASE_SPLIT: "CASES",
    ProofStructureKind.CONTRADICTION: "CONTRADICTION",
    ProofStructureKind.CONTRAPOSITION: "CONTRAPOSITION",
    ProofStructureKind.INDUCTION: "INDUCTION",
    ProofStructureKind.WLOG: "WLOG",
    ProofStructureKind.SUBPROOF: "SUBPROOF",
    ProofStructureKind.WITNESS_BRANCH: "WITNESS",
}


def _compact_text(text: str) -> str:
    return " ".join(text.strip().split())


def _status_marker(status: InferenceStatus) -> str:
    if status == InferenceStatus.AMBIGUOUS:
        return " ~"
    if status == InferenceStatus.UNRESOLVED:
        return " ?"
    return ""


def _source_suffix(addresses: tuple[str, ...] | list[str]) -> str:
    unique = tuple(dict.fromkeys(addresses))
    return f" @{','.join(unique)}" if unique else ""


def _render_expression(expression: MathExpr | None) -> str:
    return render_math_expr(expression) if expression is not None else "?"


def _render_ref(ir: SemanticTransformationIR, ref: ExpressionRef | None) -> str:
    if ref is None:
        return "?"
    try:
        expression = ir.higher.resolved.expression(ref)
    except KeyError:
        return "?"
    return render_math_expr(expression)


def _proposition_expression(proposition: ProofProposition) -> str:
    return _render_expression(proposition.expression)


def _proposition_needs_source(proposition: ProofProposition) -> bool:
    return (
        proposition.role == PropositionRole.UNRESOLVED
        or proposition.expression is None
        or proposition.expression_status
        in {
            ExprLoweringStatus.PARTIAL,
            ExprLoweringStatus.OPAQUE,
        }
    )


def _binding_text(ir: SemanticTransformationIR, transformation: SemanticTransformation) -> str:
    items: list[str] = []
    for binding in transformation.parameter_bindings:
        parameter = _render_ref(ir, binding.parameter_ref)
        argument = _render_ref(ir, binding.argument_ref)
        marker = _status_marker(binding.status).strip()
        value = f"{parameter}:={argument}"
        if marker:
            value += marker
        items.append(value)
    return ",".join(items)


def _support_atoms(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
    kind: SemanticSupportKind | None = None,
) -> list[SemanticSupportAtom]:
    result: list[SemanticSupportAtom] = []
    for address in transformation.support_atom_addresses:
        try:
            atom = ir.support_atom(address)
        except KeyError:
            continue
        if kind is None or atom.kind == kind:
            result.append(atom)
    return result


def _atom_token(atom: SemanticSupportAtom | None) -> str:
    if atom is None:
        return "?"
    if atom.proposition_address is not None:
        return atom.proposition_address
    if atom.kind == SemanticSupportKind.NAMED_PROPERTY and atom.name:
        return f"property({json.dumps(_compact_text(atom.name), ensure_ascii=False)})"
    return atom.address


def _input_tokens(transformation: SemanticTransformation) -> list[str]:
    return list(dict.fromkeys(ref.owner_address for ref in transformation.input_refs))


def _obligation_piece(
    ir: SemanticTransformationIR,
    obligation: SemanticApplicationObligation,
) -> str:
    expected = _render_expression(obligation.expected)
    if obligation.status == ObligationStatus.DISCHARGED:
        if obligation.satisfied_by:
            return ",".join(obligation.satisfied_by)
        return expected
    return f"?{obligation.address}:{expected}"


def _transformation_sources(transformation: SemanticTransformation) -> tuple[str, ...]:
    if transformation.status == InferenceStatus.CONFIDENT:
        return ()
    return transformation.opaque_source_addresses or transformation.source_addresses


def _render_result_transformation(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
    *,
    style: ProofLanguageStyle,
) -> str:
    atom = next(iter(_support_atoms(ir, transformation, SemanticSupportKind.RESULT)), None)
    support = _atom_token(atom)
    bindings = _binding_text(ir, transformation)
    if bindings:
        support += f"[{bindings}]"

    inputs = _input_tokens(transformation)
    pieces = [support, *inputs]
    for address in transformation.obligation_addresses:
        try:
            obligation = ir.obligation(address)
        except KeyError:
            continue
        piece = _obligation_piece(ir, obligation)
        if piece not in pieces:
            pieces.append(piece)

    marker = _status_marker(transformation.status)
    source = _source_suffix(_transformation_sources(transformation))
    if style == ProofLanguageStyle.COMPACT:
        return ",".join(pieces) + marker + source

    action = (
        "specialize"
        if transformation.kind == SemanticTransformationKind.RESULT_SPECIALIZATION
        else "apply"
    )
    details = f"{action} {support}"
    if inputs:
        details += f"; inputs={','.join(inputs)}"
    missing = [piece for piece in pieces if piece.startswith("?")]
    if missing:
        details += f"; need={','.join(missing)}"
    return details + marker + source


def _render_rewrite_transformation(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
    *,
    style: ProofLanguageStyle,
) -> str:
    atom = next(iter(_support_atoms(ir, transformation, SemanticSupportKind.EQUALITY)), None)
    equality = _atom_token(atom)
    direction = (
        f"{_render_ref(ir, transformation.rewrite_from_ref)}"
        f"→{_render_ref(ir, transformation.rewrite_to_ref)}"
    )
    inputs = _input_tokens(transformation)
    marker = _status_marker(transformation.status)
    source = _source_suffix(_transformation_sources(transformation))
    if style == ProofLanguageStyle.COMPACT:
        pieces = [*inputs, f"rewrite({equality}:{direction})"]
        return ",".join(pieces) + marker + source
    details = f"rewrite {equality} {direction}"
    if inputs:
        details += f"; inputs={','.join(inputs)}"
    return details + marker + source


def _render_definition_transformation(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
    *,
    style: ProofLanguageStyle,
) -> str:
    atom = next(iter(_support_atoms(ir, transformation, SemanticSupportKind.DEFINITION)), None)
    definition = _atom_token(atom)
    inputs = _input_tokens(transformation)
    marker = _status_marker(transformation.status)
    source = _source_suffix(_transformation_sources(transformation))
    action = (
        "unfold"
        if transformation.kind == SemanticTransformationKind.DEFINITION_UNFOLD
        else "definition"
    )
    if style == ProofLanguageStyle.COMPACT:
        pieces = [*inputs, f"{action}({definition})"]
        return ",".join(pieces) + marker + source
    details = f"{action} {definition}"
    if inputs:
        details += f"; inputs={','.join(inputs)}"
    return details + marker + source


def _render_property_transformation(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
    *,
    style: ProofLanguageStyle,
) -> str:
    atom = next(
        iter(_support_atoms(ir, transformation, SemanticSupportKind.NAMED_PROPERTY)),
        None,
    )
    property_token = _atom_token(atom)
    inputs = _input_tokens(transformation)
    marker = _status_marker(transformation.status)
    source = _source_suffix(_transformation_sources(transformation))
    if style == ProofLanguageStyle.COMPACT:
        return ",".join([*inputs, property_token]) + marker + source
    details = property_token
    if inputs:
        details += f"; inputs={','.join(inputs)}"
    return details + marker + source


def _render_transformation(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
    *,
    style: ProofLanguageStyle,
) -> str:
    if transformation.kind in {
        SemanticTransformationKind.RESULT_APPLICATION,
        SemanticTransformationKind.RESULT_SPECIALIZATION,
    }:
        return _render_result_transformation(ir, transformation, style=style)
    if transformation.kind == SemanticTransformationKind.EQUALITY_REWRITE:
        return _render_rewrite_transformation(ir, transformation, style=style)
    if transformation.kind in {
        SemanticTransformationKind.DEFINITION_USE,
        SemanticTransformationKind.DEFINITION_UNFOLD,
    }:
        return _render_definition_transformation(ir, transformation, style=style)
    if transformation.kind == SemanticTransformationKind.NAMED_PROPERTY_APPLICATION:
        return _render_property_transformation(ir, transformation, style=style)
    raise ValueError(f"unsupported semantic transformation {transformation.kind!r}")


def _render_fallback_step(
    step_rule: ProofRuleKind,
    premises: tuple[str, ...],
    status: InferenceStatus,
    sources: tuple[str, ...],
    *,
    style: ProofLanguageStyle,
) -> str:
    premise_text = ",".join(premises) if premises else "?"
    marker = _status_marker(status)
    source = _source_suffix(sources if status != InferenceStatus.CONFIDENT else ())
    if style == ProofLanguageStyle.COMPACT:
        if step_rule not in {ProofRuleKind.UNKNOWN, ProofRuleKind.EXACT}:
            premise_text += f"{{{step_rule.value}}}"
        return premise_text + marker + source
    details = f"premises={premise_text}; rule={step_rule.value}"
    return details + marker + source


def _transformations_by_target(
    ir: SemanticTransformationIR,
) -> dict[str, list[SemanticTransformation]]:
    result: dict[str, list[SemanticTransformation]] = {}
    for transformation in ir.transformations:
        result.setdefault(transformation.target_ref.owner_address, []).append(transformation)
    return result


def _steps_by_target(
    ir: SemanticTransformationIR,
) -> dict[str, list[ProofStepEdge]]:
    result: dict[str, list[ProofStepEdge]] = {}
    for step in ir.higher.resolved.proof.steps:
        result.setdefault(step.conclusion, []).append(step)
    return result


def _render_proposition_lines(
    ir: SemanticTransformationIR,
    *,
    style: ProofLanguageStyle,
) -> list[str]:
    transformations = _transformations_by_target(ir)
    steps = _steps_by_target(ir)
    lines: list[str] = []

    for proposition in ir.higher.resolved.proof.propositions:
        expression = _proposition_expression(proposition)
        source = (
            _source_suffix((proposition.source_address,))
            if _proposition_needs_source(proposition)
            else ""
        )
        derivations: list[str] = []
        for transformation in transformations.get(proposition.address, []):
            derivations.append(_render_transformation(ir, transformation, style=style))
        if not derivations:
            for step in steps.get(proposition.address, []):
                derivations.append(
                    _render_fallback_step(
                        step.rule,
                        step.premises,
                        step.status,
                        step.source_addresses,
                        style=style,
                    )
                )

        if style == ProofLanguageStyle.EXPLICIT:
            line = (
                f"PROPOSITION {proposition.address} role={proposition.role.value} expr={expression}"
            )
            if derivations:
                line += f" FROM {' OR '.join(derivations)}"
            elif proposition.role in {PropositionRole.DERIVED, PropositionRole.UNRESOLVED}:
                line += " FROM ?"
            lines.append(line + source)
            continue

        line = f"{proposition.address} {expression}"
        if derivations:
            line += f" <- {' || '.join(derivations)}"
        elif proposition.role in {PropositionRole.DERIVED, PropositionRole.UNRESOLVED}:
            line += " <- ?"
        lines.append(line + source)
    return lines


def _dependency_lines(
    ir: SemanticTransformationIR,
    *,
    style: ProofLanguageStyle,
) -> list[str]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    lines: list[str] = []
    for atom in ir.support_atoms:
        if atom.kind != SemanticSupportKind.RESULT or not atom.dependency_path:
            continue
        token = atom.proposition_address or atom.address
        key = (token, atom.dependency_path)
        if key in seen:
            continue
        seen.add(key)
        path = ">".join(atom.dependency_path)
        if style == ProofLanguageStyle.COMPACT:
            lines.append(f"DEP {token} {path}")
        else:
            lines.append(f"DEPENDENCY support={token} path={path}")
    return lines


def _branch_compact(ir: SemanticTransformationIR, branch: ProofBranch) -> str:
    assumptions = list(branch.local_assumptions)
    if not assumptions and branch.assumption_refs:
        assumptions = [_render_ref(ir, ref) for ref in branch.assumption_refs]
    prefix = branch.kind.value
    if assumptions:
        prefix += f"[{','.join(assumptions)}]"
    conclusion = branch.conclusion_address or _render_ref(ir, branch.conclusion_ref)
    piece = f"{prefix}=>{conclusion}"
    if branch.witness_ref is not None:
        piece += f" witness={_render_ref(ir, branch.witness_ref)}"
    return piece + _status_marker(branch.status)


def _control_source(structure: ProofControlStructure) -> tuple[str, ...]:
    if structure.support_status == InferenceStatus.CONFIDENT:
        return structure.opaque_source_addresses
    return structure.opaque_source_addresses or structure.source_addresses


def _render_control_lines(
    ir: SemanticTransformationIR,
    *,
    style: ProofLanguageStyle,
) -> list[str]:
    higher = ir.higher
    structure_ids = {
        structure.address: f"F{index}" for index, structure in enumerate(higher.structures, start=1)
    }
    branches_by_parent: dict[str, list[ProofBranch]] = {}
    for branch in higher.branches:
        branches_by_parent.setdefault(branch.parent_structure_address, []).append(branch)

    lines: list[str] = []
    for structure in higher.structures:
        local_id = structure_ids[structure.address]
        word = _CONTROL_WORDS[structure.kind]
        conclusion = structure.conclusion_address or "?"
        premises = ",".join(structure.premise_addresses)
        branches = branches_by_parent.get(structure.address, [])
        source = _source_suffix(_control_source(structure))
        parent = (
            structure_ids.get(structure.parent_structure_address)
            if structure.parent_structure_address is not None
            else None
        )

        if style == ProofLanguageStyle.EXPLICIT:
            details = [
                f"CONTROL {local_id} kind={structure.kind.value}",
                f"conclusion={conclusion}",
                f"assertion={structure.assertion_status.value}",
                f"support={structure.support_status.value}",
            ]
            if premises:
                details.append(f"premises={premises}")
            if parent:
                details.append(f"parent={parent}")
            if structure.subject_ref is not None:
                details.append(f"subject={_render_ref(ir, structure.subject_ref)}")
            if structure.transformed_goal_ref is not None:
                details.append(
                    f"transformed_goal={_render_ref(ir, structure.transformed_goal_ref)}"
                )
            if structure.witness_ref is not None:
                details.append(f"witness={_render_ref(ir, structure.witness_ref)}")
            if branches:
                details.append(
                    "branches=" + ";".join(_branch_compact(ir, branch) for branch in branches)
                )
            lines.append(" ".join(details) + source)
            continue

        line = f"FLOW {local_id} {word} -> {conclusion}"
        if premises:
            line += f" from {premises}"
        if parent:
            line += f" parent={parent}"
        if structure.subject_ref is not None:
            line += f" subject={_render_ref(ir, structure.subject_ref)}"
        if structure.transformed_goal_ref is not None:
            line += f" goal={_render_ref(ir, structure.transformed_goal_ref)}"
        if structure.witness_ref is not None:
            line += f" witness={_render_ref(ir, structure.witness_ref)}"
        if branches:
            line += " {" + ";".join(_branch_compact(ir, branch) for branch in branches) + "}"
        line += _status_marker(structure.support_status)
        if structure.assertion_status != InferenceStatus.CONFIDENT:
            line += " inferred"
        lines.append(line + source)
    return lines


def _obligation_expected(ir: SemanticTransformationIR, obligation: ProofObligation) -> str:
    if obligation.expected is not None:
        return render_math_expr(obligation.expected)
    try:
        proposition = ir.higher.resolved.proof.proposition(obligation.proposition_address)
    except KeyError:
        return "?"
    return _proposition_expression(proposition)


def _proof_obligation_lines(
    ir: SemanticTransformationIR,
    *,
    style: ProofLanguageStyle,
) -> list[str]:
    lines: list[str] = []
    for obligation in ir.higher.resolved.proof.obligations:
        if not obligation.terminal and obligation.status != ObligationStatus.UNRESOLVED:
            continue
        noun = "GOAL" if obligation.terminal else "HOLE"
        expected = _obligation_expected(ir, obligation)
        context = ",".join(obligation.local_context) or "-"
        state = "open" if obligation.status == ObligationStatus.UNRESOLVED else "structural"
        source = (
            _source_suffix((obligation.source_address,))
            if obligation.status == ObligationStatus.UNRESOLVED
            else ""
        )
        if style == ProofLanguageStyle.COMPACT:
            lines.append(
                f"{noun} {obligation.address} {obligation.proposition_address}: "
                f"{expected} | ctx {context} | {state}{source}"
            )
        else:
            lines.append(
                f"{noun} {obligation.address} proposition={obligation.proposition_address} "
                f"expected={expected} context={context} status={state}{source}"
            )
    return lines


def _application_obligation_lines(
    ir: SemanticTransformationIR,
    *,
    style: ProofLanguageStyle,
) -> list[str]:
    lines: list[str] = []
    for obligation in ir.obligations:
        if obligation.status != ObligationStatus.UNRESOLVED:
            continue
        expected = _render_expression(obligation.expected)
        context = ",".join(obligation.local_context) or "-"
        source = _source_suffix(obligation.source_addresses)
        if style == ProofLanguageStyle.COMPACT:
            lines.append(f"NEED {obligation.address}: {expected} | ctx {context}{source}")
        else:
            lines.append(
                f"PRECONDITION {obligation.address} expected={expected} "
                f"context={context} status=open{source}"
            )
    return lines


def render_llm_proof_language(
    ir: SemanticTransformationIR,
    *,
    style: ProofLanguageStyle = ProofLanguageStyle.COMPACT,
) -> str:
    """Delaborate canonical Proof IR into one deterministic model-facing language."""

    header = "THORN-PROOF 1" if style == ProofLanguageStyle.COMPACT else "THORN PROOF LANGUAGE 1"
    lines = [header]
    lines.extend(_render_proposition_lines(ir, style=style))
    lines.extend(_dependency_lines(ir, style=style))
    lines.extend(_render_control_lines(ir, style=style))
    lines.extend(_proof_obligation_lines(ir, style=style))
    lines.extend(_application_obligation_lines(ir, style=style))
    return "\n".join(lines) + "\n"


def _source_handles(ir: SemanticTransformationIR) -> tuple[ProofLanguageSourceHandle, ...]:
    handles: list[ProofLanguageSourceHandle] = []
    seen: set[str] = set()
    for source in ir.higher.resolved.proof.sources:
        if source.address in seen:
            continue
        seen.add(source.address)
        handles.append(
            ProofLanguageSourceHandle(
                address=source.address,
                ir_identifier=source.ir_identifier,
                text=source.text,
                source_span=source.source_span,
                source_range=source.source_range,
                referenced_result_identifier=source.referenced_result_identifier,
            )
        )
    return tuple(handles)


def project_llm_proof_language(ir: SemanticTransformationIR) -> LLMProofLanguage:
    """Freeze the compact issue-65 rendering while retaining source Thorn-side."""

    rendered = render_llm_proof_language(ir, style=ProofLanguageStyle.COMPACT)
    return LLMProofLanguage(
        result_identifier=ir.result_identifier,
        lines=tuple(rendered.rstrip("\n").split("\n")),
        sources=_source_handles(ir),
    )


def build_llm_proof_language(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
    *,
    symbol_table: SymbolTable | None = None,
    dependency_graph: DependencyGraph | None = None,
) -> LLMProofLanguage:
    """Build the stable model-facing projection from the complete #60-#64 stack."""

    semantic = build_semantic_transformation_ir(
        unit,
        request,
        symbol_table=symbol_table,
        dependency_graph=dependency_graph,
    )
    return project_llm_proof_language(semantic)


def proof_language_inventory(ir: SemanticTransformationIR) -> dict[str, int]:
    """Keyless semantic counts shared by both candidate text renderings."""

    proof = ir.higher.resolved.proof
    return {
        "propositions": len(proof.propositions),
        "proof_obligations": len(proof.obligations),
        "open_proof_obligations": sum(
            item.status == ObligationStatus.UNRESOLVED for item in proof.obligations
        ),
        "support_atoms": len(ir.support_atoms),
        "transformations": len(ir.transformations),
        "application_obligations": len(ir.obligations),
        "open_application_obligations": sum(
            item.status == ObligationStatus.UNRESOLVED for item in ir.obligations
        ),
        "control_structures": len(ir.higher.structures),
        "control_branches": len(ir.higher.branches),
        "source_handles": len(proof.sources),
    }


def parse_source_rescue_request(
    document: LLMProofLanguage,
    command: str,
    *,
    max_addresses: int = DEFAULT_MAX_SOURCE_REQUESTS,
    round_number: int = 1,
) -> SourceRescueRequest:
    """Parse exactly one batched ``NEED_SOURCE`` rescue command.

    ``round_number`` is intentionally constrained to one so a caller cannot silently
    turn source rescue into an unbounded conversational side channel.
    """

    if round_number != 1:
        raise ValueError("Thorn proof language supports exactly one source rescue round")
    if max_addresses < 1:
        raise ValueError("max_addresses must be positive")
    match = _NEED_SOURCE_RE.fullmatch(command)
    if match is None:
        raise ValueError("expected NEED_SOURCE address[,address...]")
    addresses = tuple(dict.fromkeys(part.strip() for part in match.group(1).split(",")))
    if len(addresses) > max_addresses:
        raise ValueError(
            f"source rescue requests at most {max_addresses} addresses, got {len(addresses)}"
        )
    known = {item.address for item in document.sources}
    unknown = [address for address in addresses if address not in known]
    if unknown:
        raise KeyError(f"unknown proof-language source addresses: {', '.join(unknown)}")
    return SourceRescueRequest(
        document_fingerprint=document.fingerprint(),
        addresses=addresses,
    )


def render_source_rescue(
    document: LLMProofLanguage,
    request: SourceRescueRequest,
) -> SourceRescueResponse:
    """Return only the requested exact source, preserving request order."""

    if request.document_fingerprint != document.fingerprint():
        raise ValueError("source rescue request does not match this proof-language packet")
    lines = [f"THORN-SOURCE 1 {request.document_fingerprint}"]
    for address in request.addresses:
        source = document.source(address)
        lines.append(f"SOURCE @{address}")
        if source.referenced_result_identifier is not None:
            lines.append(f"RESULT_ID {source.referenced_result_identifier}")
        lines.append(source.text)
        lines.append(f"END_SOURCE @{address}")
    return SourceRescueResponse(
        document_fingerprint=request.document_fingerprint,
        addresses=request.addresses,
        text="\n".join(lines) + "\n",
    )
