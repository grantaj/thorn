from __future__ import annotations

import json
import re
from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.evidence import InferenceStatus
from thorn.frontend import SourceSpan
from thorn.models import SourceRange, TheoremUnit
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.support import Claim, ClaimForm, SupportEdge, SupportKind
from thorn.symbols import Constraint, Definition, Symbol


class SkeletonSourceKind(StrEnum):
    RESULT = "result"
    HYPOTHESIS = "hypothesis"
    LOCAL_CONSTRAINT = "local_constraint"
    DEFINITION = "definition"
    DEPENDENCY = "dependency"
    CLAIM = "claim"
    QUALIFIER = "qualifier"
    SUPPORT = "support"


class SkeletonSourceAddress(BaseModel):
    """One local skeleton address and its exact Thorn-side source payload."""

    address: str
    kind: SkeletonSourceKind
    ir_identifier: str
    text: str
    source_span: SourceSpan | None = None
    source_range: SourceRange | None = None
    referenced_result_identifier: str | None = None


class ProofSkeleton(BaseModel):
    """Tiny model-facing proof graph plus a local, non-rendered source address map."""

    result_identifier: str
    lines: list[str] = Field(default_factory=list)
    sources: list[SkeletonSourceAddress] = Field(default_factory=list)

    def render_initial(self) -> str:
        """Render only the initial skeleton; source-map payloads stay Thorn-side."""

        return "\n".join(self.lines) + "\n"

    def source(self, address: str) -> SkeletonSourceAddress:
        for item in self.sources:
            if item.address == address:
                return item
        raise KeyError(f"unknown proof-skeleton source address {address!r}")

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


_MATH_RE = re.compile(
    r"(?s)(\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\$)\$(?!\$).*?(?<!\\)\$)"
)

_SUPPORT_CODES: dict[SupportKind, str] = {
    SupportKind.RESULT_REFERENCE: "r",
    SupportKind.EQUATION_REFERENCE: "q",
    SupportKind.DEFINITION: "d",
    SupportKind.NAMED_PROPERTY: "p",
    SupportKind.PRIOR_CLAIM: "c",
    SupportKind.EXPLICIT_REASON: "x",
}


def _compact(text: str) -> str:
    return " ".join(text.strip().split())


def _strip_math_delimiters(text: str) -> str:
    if text.startswith("$$") and text.endswith("$$"):
        return text[2:-2]
    if text.startswith("\\[") and text.endswith("\\]"):
        return text[2:-2]
    if text.startswith("\\(") and text.endswith("\\)"):
        return text[2:-2]
    if text.startswith("$") and text.endswith("$"):
        return text[1:-1]
    return text


def _math_fragments(text: str, *, whole_if_display: bool = False) -> list[str]:
    fragments: list[str] = []
    for match in _MATH_RE.finditer(text):
        fragment = _compact(_strip_math_delimiters(match.group(0)))
        if fragment and fragment not in fragments:
            fragments.append(fragment)
    if not fragments and whole_if_display:
        fragment = _compact(text)
        if fragment:
            fragments.append(fragment)
    return fragments


def _render_fragments(fragments: list[str]) -> str:
    return "|".join(fragments) if fragments else "~"


def _span_key(span: SourceSpan) -> tuple[str, int, int, str]:
    return (span.file, span.start_offset, span.end_offset, "")


def _claim_key(claim: Claim) -> tuple[str, int, int, str]:
    return (*_span_key(claim.source)[:3], claim.identifier)


def _constraint_key(constraint: Constraint) -> tuple[str, int, int, str]:
    return (*_span_key(constraint.source)[:3], constraint.identifier)


def _definition_key(definition: Definition) -> tuple[str, int, int, str]:
    return (*_span_key(definition.source)[:3], definition.identifier)


def _edge_key(edge: SupportEdge) -> tuple[str, int, int, str]:
    return (*_span_key(edge.source)[:3], edge.identifier)


def _constraint_atom(constraint: Constraint, symbols: dict[str, Symbol]) -> str:
    symbol = symbols.get(constraint.symbol_identifier)
    name = symbol.name if symbol is not None else "?"
    return _compact(f"{name}{constraint.relation}{constraint.expression_latex}")


def _definition_atom(definition: Definition, symbols: dict[str, Symbol]) -> str:
    symbol = symbols.get(definition.symbol_identifier)
    name = symbol.name if symbol is not None else "?"
    return _compact(f"{name}{definition.operator}{definition.expression_latex}")


def _status_marker(status: InferenceStatus) -> str:
    if status == InferenceStatus.AMBIGUOUS:
        return "?"
    if status == InferenceStatus.UNRESOLVED:
        return "!"
    return ""


def _source_endpoint(
    edge: SupportEdge,
    *,
    claim_labels: dict[str, str],
    dependency_labels: dict[str, str],
) -> str:
    if edge.source_claim_identifier is not None:
        return claim_labels.get(edge.source_claim_identifier, "X")
    if edge.target_label is not None and edge.target_label in dependency_labels:
        return dependency_labels[edge.target_label]
    return "X"


def build_proof_skeleton(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
) -> ProofSkeleton:
    """Project one result-level review item into a source-addressable proof skeleton.

    The initial packet deliberately keeps only formula fragments, compact constraints,
    dependency labels and graph topology. Prose that cannot be represented safely by
    those local atoms is rendered as ``~`` and remains exactly recoverable from
    ``sources`` by the same short address.
    """

    item = request.item
    if item.result.identifier != unit.identifier:
        raise ValueError(
            "proof skeleton unit/result mismatch: "
            f"{unit.identifier!r} != {item.result.identifier!r}"
        )

    lines: list[str] = []
    sources: list[SkeletonSourceAddress] = []
    symbols = {symbol.identifier: symbol for symbol in item.symbols}

    statement_fragments = _math_fragments(unit.statement)
    lines.append(f"T0:{_render_fragments(statement_fragments)}")
    sources.append(
        SkeletonSourceAddress(
            address="T0",
            kind=SkeletonSourceKind.RESULT,
            ir_identifier=unit.identifier,
            text=unit.statement,
            source_range=unit.statement_range,
        )
    )

    for index, hypothesis in enumerate(sorted(item.hypotheses, key=_constraint_key), start=1):
        address = f"H{index}"
        lines.append(f"{address}:{_constraint_atom(hypothesis, symbols)}")
        sources.append(
            SkeletonSourceAddress(
                address=address,
                kind=SkeletonSourceKind.HYPOTHESIS,
                ir_identifier=hypothesis.identifier,
                text=hypothesis.raw,
                source_span=hypothesis.source,
            )
        )

    for index, constraint in enumerate(
        sorted(item.local_constraints, key=_constraint_key), start=1
    ):
        address = f"L{index}"
        lines.append(f"{address}:{_constraint_atom(constraint, symbols)}")
        sources.append(
            SkeletonSourceAddress(
                address=address,
                kind=SkeletonSourceKind.LOCAL_CONSTRAINT,
                ir_identifier=constraint.identifier,
                text=constraint.raw,
                source_span=constraint.source,
            )
        )

    for index, definition in enumerate(sorted(item.definitions, key=_definition_key), start=1):
        address = f"D{index}"
        lines.append(f"{address}:{_definition_atom(definition, symbols)}")
        sources.append(
            SkeletonSourceAddress(
                address=address,
                kind=SkeletonSourceKind.DEFINITION,
                ir_identifier=definition.identifier,
                text=definition.raw,
                source_span=definition.source,
            )
        )

    dependency_labels: dict[str, str] = {}
    for index, dependency in enumerate(item.dependencies, start=1):
        address = f"R{index}"
        if dependency.label is not None:
            dependency_labels[dependency.label] = address
        statement = _render_fragments(_math_fragments(dependency.statement))
        label = dependency.label or dependency.identifier
        lines.append(f"{address}:{label}:{statement}")
        sources.append(
            SkeletonSourceAddress(
                address=address,
                kind=SkeletonSourceKind.DEPENDENCY,
                ir_identifier=dependency.identifier,
                text=dependency.statement,
                source_range=dependency.source,
                referenced_result_identifier=dependency.identifier,
            )
        )

    claims = sorted(item.claims, key=_claim_key)
    claim_labels = {
        claim.identifier: f"C{index}" for index, claim in enumerate(claims, start=1)
    }
    qualifier_index = 0
    for claim in claims:
        address = claim_labels[claim.identifier]
        fragments = _math_fragments(
            claim.raw,
            whole_if_display=claim.form == ClaimForm.DISPLAY,
        )
        lines.append(f"{address}:{_render_fragments(fragments)}")
        sources.append(
            SkeletonSourceAddress(
                address=address,
                kind=SkeletonSourceKind.CLAIM,
                ir_identifier=claim.identifier,
                text=claim.raw,
                source_span=claim.source,
            )
        )
        for qualifier in claim.qualifiers:
            qualifier_index += 1
            qualifier_address = f"Q{qualifier_index}"
            qualifier_fragments = _math_fragments(qualifier.raw)
            lines.append(
                f"{qualifier_address}>{address}:"
                f"{_render_fragments(qualifier_fragments)}"
            )
            sources.append(
                SkeletonSourceAddress(
                    address=qualifier_address,
                    kind=SkeletonSourceKind.QUALIFIER,
                    ir_identifier=qualifier.identifier,
                    text=qualifier.raw,
                    source_span=qualifier.source,
                )
            )

    for index, edge in enumerate(sorted(item.support_relations, key=_edge_key), start=1):
        address = f"E{index}"
        source = _source_endpoint(
            edge,
            claim_labels=claim_labels,
            dependency_labels=dependency_labels,
        )
        target = claim_labels.get(edge.target_claim_identifier, "X")
        code = _SUPPORT_CODES[edge.kind]
        marker = _status_marker(edge.status)
        payload: list[str] = []
        if edge.named_property:
            payload.append(_compact(edge.named_property))
        payload.extend(_math_fragments(edge.raw_justification))
        suffix = f":{'|'.join(payload)}" if payload else ""
        lines.append(f"{address}:{source}>{target}:{code}{marker}{suffix}")
        sources.append(
            SkeletonSourceAddress(
                address=address,
                kind=SkeletonSourceKind.SUPPORT,
                ir_identifier=edge.identifier,
                text=edge.raw_justification,
                source_span=edge.source,
                referenced_result_identifier=(
                    next(
                        (
                            dependency.identifier
                            for dependency in item.dependencies
                            if dependency.label == edge.target_label
                        ),
                        None,
                    )
                    if edge.target_label is not None
                    else None
                ),
            )
        )

    return ProofSkeleton(
        result_identifier=unit.identifier,
        lines=lines,
        sources=sources,
    )
