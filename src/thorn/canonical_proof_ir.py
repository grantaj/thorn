from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.evidence import InferenceStatus
from thorn.frontend import SourceSpan
from thorn.models import SourceRange, TheoremUnit
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.support import (
    Claim,
    ClaimForm,
    ClaimQualifier,
    QualifierKind,
    SupportEdge,
    SupportKind,
)
from thorn.symbols import Constraint, Definition, Symbol


class CanonicalNodeKind(StrEnum):
    RESULT = "result"
    HYPOTHESIS = "hypothesis"
    LOCAL_CONSTRAINT = "local_constraint"
    DEFINITION = "definition"
    DEPENDENCY = "dependency"
    CLAIM = "claim"
    OPAQUE_PROSE = "opaque_prose"


class CanonicalEdgeKind(StrEnum):
    RESULT_REFERENCE = "result_reference"
    EQUATION_REFERENCE = "equation_reference"
    DEFINITION = "definition"
    NAMED_PROPERTY = "named_property"
    PRIOR_CLAIM = "prior_claim"
    EXPLICIT_REASON = "explicit_reason"
    QUANTIFIER = "quantifier"
    QUALIFIER = "qualifier"


class CanonicalProofSource(BaseModel):
    """Exact Thorn-side source payload for one canonical proof address."""

    address: str
    ir_identifier: str
    text: str
    source_span: SourceSpan | None = None
    source_range: SourceRange | None = None
    referenced_result_identifier: str | None = None


class CanonicalProofNode(BaseModel):
    address: str
    kind: CanonicalNodeKind
    atom: str
    opaque: bool = False


class CanonicalProofEdge(BaseModel):
    address: str
    kind: CanonicalEdgeKind
    source: str | None = None
    target: str
    status: InferenceStatus = InferenceStatus.CONFIDENT
    atom: str | None = None


class CanonicalProofIR(BaseModel):
    """Graph-derived model-facing proof language with exact source recovery."""

    result_identifier: str
    nodes: list[CanonicalProofNode] = Field(default_factory=list)
    edges: list[CanonicalProofEdge] = Field(default_factory=list)
    sources: list[CanonicalProofSource] = Field(default_factory=list)
    pruned_claims: int = 0

    def render_initial(self) -> str:
        lines = [f"{node.address}:{node.atom}" for node in self.nodes]
        for edge in self.edges:
            marker = _status_marker(edge.status)
            if edge.kind == CanonicalEdgeKind.QUANTIFIER:
                lines.append(f"{edge.address}:{edge.atom or '~'}{marker}>{edge.target}")
                continue
            source = edge.source or "_"
            code = _EDGE_CODES[edge.kind]
            suffix = f":{edge.atom}" if edge.atom else ""
            lines.append(
                f"{edge.address}:{source}>{edge.target}:{code}{marker}{suffix}"
            )
        return "\n".join(lines) + "\n"

    def source(self, address: str) -> CanonicalProofSource:
        for item in self.sources:
            if item.address == address:
                return item
        raise KeyError(f"unknown canonical-proof source address {address!r}")

    @property
    def opaque_nodes(self) -> int:
        return sum(node.opaque for node in self.nodes)


_MATH_RE = re.compile(
    r"(?s)(\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\$)\$(?!\$).*?(?<!\\)\$)"
)
_LABEL_RE = re.compile(r"\\label\s*\{[^{}]*\}")

_LATEX_SYMBOLS: tuple[tuple[str, str], ...] = (
    (r"\\Leftrightarrow(?![A-Za-z])", "⇔"),
    (r"\\Longleftrightarrow(?![A-Za-z])", "⇔"),
    (r"\\Rightarrow(?![A-Za-z])", "⇒"),
    (r"\\Longrightarrow(?![A-Za-z])", "⇒"),
    (r"\\leftrightarrow(?![A-Za-z])", "↔"),
    (r"\\rightarrow(?![A-Za-z])", "→"),
    (r"\\subseteq(?![A-Za-z])", "⊆"),
    (r"\\notin(?![A-Za-z])", "∉"),
    (r"\\forall(?![A-Za-z])", "∀"),
    (r"\\exists(?![A-Za-z])", "∃"),
    (r"\\implies(?![A-Za-z])", "⇒"),
    (r"\\iff(?![A-Za-z])", "⇔"),
    (r"\\wedge(?![A-Za-z])", "∧"),
    (r"\\land(?![A-Za-z])", "∧"),
    (r"\\vee(?![A-Za-z])", "∨"),
    (r"\\lor(?![A-Za-z])", "∨"),
    (r"\\lnot(?![A-Za-z])", "¬"),
    (r"\\neg(?![A-Za-z])", "¬"),
    (r"\\neq(?![A-Za-z])", "≠"),
    (r"\\ne(?![A-Za-z])", "≠"),
    (r"\\leq(?![A-Za-z])", "≤"),
    (r"\\le(?![A-Za-z])", "≤"),
    (r"\\geq(?![A-Za-z])", "≥"),
    (r"\\ge(?![A-Za-z])", "≥"),
    (r"\\in(?![A-Za-z])", "∈"),
    (r"\\subset(?![A-Za-z])", "⊂"),
    (r"\\to(?![A-Za-z])", "→"),
)

_EDGE_CODES: dict[CanonicalEdgeKind, str] = {
    CanonicalEdgeKind.RESULT_REFERENCE: "r",
    CanonicalEdgeKind.EQUATION_REFERENCE: "q",
    CanonicalEdgeKind.DEFINITION: "d",
    CanonicalEdgeKind.NAMED_PROPERTY: "p",
    CanonicalEdgeKind.PRIOR_CLAIM: "c",
    CanonicalEdgeKind.EXPLICIT_REASON: "x",
    CanonicalEdgeKind.QUALIFIER: "u",
    CanonicalEdgeKind.QUANTIFIER: "∀",
}

_SUPPORT_EDGE_KINDS: dict[SupportKind, CanonicalEdgeKind] = {
    SupportKind.RESULT_REFERENCE: CanonicalEdgeKind.RESULT_REFERENCE,
    SupportKind.EQUATION_REFERENCE: CanonicalEdgeKind.EQUATION_REFERENCE,
    SupportKind.DEFINITION: CanonicalEdgeKind.DEFINITION,
    SupportKind.NAMED_PROPERTY: CanonicalEdgeKind.NAMED_PROPERTY,
    SupportKind.PRIOR_CLAIM: CanonicalEdgeKind.PRIOR_CLAIM,
    SupportKind.EXPLICIT_REASON: CanonicalEdgeKind.EXPLICIT_REASON,
}


def _compact(text: str) -> str:
    return " ".join(text.strip().split())


def _semantic_text(text: str) -> str:
    """Remove source-only markup that carries no mathematical semantics."""

    return _compact(_LABEL_RE.sub("", text))


def _strip_math_delimiters(text: str) -> str:
    text = text.strip()
    if text.startswith("$$") and text.endswith("$$"):
        return text[2:-2]
    if text.startswith("\\[") and text.endswith("\\]"):
        return text[2:-2]
    if text.startswith("\\(") and text.endswith("\\)"):
        return text[2:-2]
    if text.startswith("$") and text.endswith("$"):
        return text[1:-1]
    return text


def normalize_latex_math(text: str) -> str:
    """Normalize only exact, semantically fixed TeX logical/operator spellings."""

    result = _compact(text)
    for pattern, replacement in _LATEX_SYMBOLS:
        result = re.sub(pattern, replacement, result)
    result = re.sub(r"\\(?:,|;|!|quad|qquad)(?![A-Za-z])", "", result)
    return _compact(result)


def _placeholderize(text: str) -> tuple[str, list[str]]:
    fragments: list[str] = []

    def replace(match: re.Match[str]) -> str:
        fragment = normalize_latex_math(_strip_math_delimiters(match.group(0)))
        token = f"@{len(fragments)}@"
        fragments.append(fragment)
        return token

    template = _compact(_MATH_RE.sub(replace, _semantic_text(text))).rstrip(". ;")
    return template, fragments


def _restore(expression: str, fragments: list[str]) -> str:
    result = expression
    for index, fragment in enumerate(fragments):
        result = result.replace(f"@{index}@", fragment)
    return result


def canonicalize_mathematical_text(text: str) -> str | None:
    """Canonicalize only fully matched mathematical phrases; never guess prose."""

    template, fragments = _placeholderize(text)
    if not fragments:
        return None

    token = r"(@\d+@)"
    patterns: tuple[tuple[str, str], ...] = (
        (
            rf"(?:for all|for every|for each)\s+{token}\s*,?\s*if\s+{token}\s*,?\s*then\s+{token}",
            "∀\\1.(\\2⇒\\3)",
        ),
        (
            rf"(?:for all|for every|for each)\s+{token}\s*,?\s*{token}",
            "∀\\1.\\2",
        ),
        (
            rf"there exists\s+{token}\s+(?:such that|with)\s+{token}",
            "∃\\1.\\2",
        ),
        (rf"if\s+{token}\s*,?\s*then\s+{token}", "\\1⇒\\2"),
        (rf"{token}\s+(?:if and only if|iff)\s+{token}", "\\1⇔\\2"),
        (rf"{token}\s+and\s+{token}", "\\1∧\\2"),
        (rf"{token}\s+or\s+{token}", "\\1∨\\2"),
        (rf"not\s+{token}", "¬\\1"),
        (rf"{token}\s+(?:is in|belongs to)\s+{token}", "\\1∈\\2"),
        (rf"{token}\s+(?:is not equal to|does not equal)\s+{token}", "\\1≠\\2"),
        (rf"{token}\s+(?:equals|is equal to)\s+{token}", "\\1=\\2"),
        (token, "\\1"),
    )
    for pattern, replacement in patterns:
        if re.fullmatch(pattern, template, flags=re.IGNORECASE) is not None:
            normalized = re.sub(pattern, replacement, template, flags=re.IGNORECASE)
            return _restore(normalized, fragments)
    return None


def _has_math(claim: Claim) -> bool:
    return claim.form == ClaimForm.DISPLAY or _MATH_RE.search(claim.raw) is not None


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


def _status_marker(status: InferenceStatus) -> str:
    if status == InferenceStatus.AMBIGUOUS:
        return "?"
    if status == InferenceStatus.UNRESOLVED:
        return "!"
    return ""


def _constraint_atom(constraint: Constraint, symbols: dict[str, Symbol]) -> str:
    symbol = symbols.get(constraint.symbol_identifier)
    name = symbol.name if symbol is not None else "?"
    return normalize_latex_math(
        f"{name}{constraint.relation}{constraint.expression_latex}"
    )


def _definition_atom(definition: Definition, symbols: dict[str, Symbol]) -> str:
    symbol = symbols.get(definition.symbol_identifier)
    name = symbol.name if symbol is not None else "?"
    return normalize_latex_math(
        f"{name}{definition.operator}{definition.expression_latex}"
    )


def _incoming_edges(
    claim_identifier: str,
    edges: list[SupportEdge],
) -> list[SupportEdge]:
    return [edge for edge in edges if edge.target_claim_identifier == claim_identifier]


def _slice_claim_identifiers(
    claims: list[Claim],
    edges: list[SupportEdge],
) -> set[str]:
    if not claims:
        return set()

    claim_ids = {claim.identifier for claim in claims}
    all_sources = {
        edge.source_claim_identifier
        for edge in edges
        if edge.source_claim_identifier in claim_ids
    }
    seeds = {claim.identifier for claim in claims if _has_math(claim)}
    seeds.update(
        edge.target_claim_identifier
        for edge in edges
        if edge.status == InferenceStatus.CONFIDENT
        and edge.target_claim_identifier in claim_ids
        and edge.target_claim_identifier not in all_sources
    )

    last = claims[-1]
    if _incoming_edges(last.identifier, edges):
        seeds.add(last.identifier)
    if not seeds:
        seeds.add(last.identifier)

    incoming: dict[str, list[SupportEdge]] = {}
    for edge in edges:
        incoming.setdefault(edge.target_claim_identifier, []).append(edge)

    keep = set(seeds)
    pending = list(seeds)
    while pending:
        target = pending.pop()
        for edge in incoming.get(target, []):
            source = edge.source_claim_identifier
            if source is None or source not in claim_ids or source in keep:
                continue
            keep.add(source)
            pending.append(source)
    return keep


def _claim_atom(claim: Claim, incoming: list[SupportEdge]) -> str | None:
    if claim.form == ClaimForm.DISPLAY:
        return normalize_latex_math(_strip_math_delimiters(claim.raw))

    direct = canonicalize_mathematical_text(claim.raw)
    if direct is not None:
        return direct

    template, fragments = _placeholderize(claim.raw)
    if len(fragments) != 1:
        return None

    if (
        any(edge.kind == SupportKind.PRIOR_CLAIM for edge in incoming)
        and re.fullmatch(
            r"(?:therefore|hence|thus|consequently)\s*,?\s*@0@",
            template,
            flags=re.IGNORECASE,
        )
        is not None
    ):
        return fragments[0]

    structural_prefix = any(
        edge.kind
        in {
            SupportKind.RESULT_REFERENCE,
            SupportKind.EQUATION_REFERENCE,
            SupportKind.DEFINITION,
            SupportKind.NAMED_PROPERTY,
        }
        for edge in incoming
    )
    if structural_prefix and re.fullmatch(
        r"(?:by|from|using|applying|apply|invoking|invoke)\b.+?,\s*@0@",
        template,
        flags=re.IGNORECASE,
    ):
        return fragments[0]
    return None


def _qualifier_atom(qualifier: ClaimQualifier) -> tuple[CanonicalEdgeKind, str]:
    if qualifier.kind == QualifierKind.TRAILING_BINDER and qualifier.bound_names:
        names = ",".join(bound.name for bound in qualifier.bound_names)
        return CanonicalEdgeKind.QUANTIFIER, f"∀{names}"
    canonical = canonicalize_mathematical_text(qualifier.raw)
    if canonical is not None:
        return CanonicalEdgeKind.QUALIFIER, canonical
    return CanonicalEdgeKind.QUALIFIER, _semantic_text(qualifier.raw)


def _support_payload(edge: SupportEdge) -> str | None:
    if edge.named_property:
        return _compact(edge.named_property)
    if edge.kind == SupportKind.EXPLICIT_REASON:
        return canonicalize_mathematical_text(edge.raw_justification) or _semantic_text(
            edge.raw_justification
        )
    return None


def build_canonical_proof_ir(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
) -> CanonicalProofIR:
    """Build a conservative backward proof slice and canonical mathematical language."""

    item = request.item
    if item.result.identifier != unit.identifier:
        raise ValueError(
            "canonical proof unit/result mismatch: "
            f"{unit.identifier!r} != {item.result.identifier!r}"
        )

    nodes: list[CanonicalProofNode] = []
    canonical_edges: list[CanonicalProofEdge] = []
    sources: list[CanonicalProofSource] = []
    symbols = {symbol.identifier: symbol for symbol in item.symbols}

    statement_text = _semantic_text(unit.statement)
    statement_atom = canonicalize_mathematical_text(statement_text)
    statement_opaque = statement_atom is None
    if statement_atom is None:
        statement_atom = statement_text
    nodes.append(
        CanonicalProofNode(
            address="T0",
            kind=CanonicalNodeKind.RESULT,
            atom=statement_atom,
            opaque=statement_opaque,
        )
    )
    sources.append(
        CanonicalProofSource(
            address="T0",
            ir_identifier=unit.identifier,
            text=unit.statement,
            source_range=unit.statement_range,
        )
    )

    for index, hypothesis in enumerate(
        sorted(item.hypotheses, key=_constraint_key), start=1
    ):
        address = f"H{index}"
        nodes.append(
            CanonicalProofNode(
                address=address,
                kind=CanonicalNodeKind.HYPOTHESIS,
                atom=_constraint_atom(hypothesis, symbols),
            )
        )
        sources.append(
            CanonicalProofSource(
                address=address,
                ir_identifier=hypothesis.identifier,
                text=hypothesis.raw,
                source_span=hypothesis.source,
            )
        )

    for index, constraint in enumerate(
        sorted(item.local_constraints, key=_constraint_key), start=1
    ):
        address = f"L{index}"
        nodes.append(
            CanonicalProofNode(
                address=address,
                kind=CanonicalNodeKind.LOCAL_CONSTRAINT,
                atom=_constraint_atom(constraint, symbols),
            )
        )
        sources.append(
            CanonicalProofSource(
                address=address,
                ir_identifier=constraint.identifier,
                text=constraint.raw,
                source_span=constraint.source,
            )
        )

    for index, definition in enumerate(
        sorted(item.definitions, key=_definition_key), start=1
    ):
        address = f"D{index}"
        nodes.append(
            CanonicalProofNode(
                address=address,
                kind=CanonicalNodeKind.DEFINITION,
                atom=_definition_atom(definition, symbols),
            )
        )
        sources.append(
            CanonicalProofSource(
                address=address,
                ir_identifier=definition.identifier,
                text=definition.raw,
                source_span=definition.source,
            )
        )

    claims = sorted(item.claims, key=_claim_key)
    support_edges = sorted(item.support_relations, key=_edge_key)
    keep_ids = _slice_claim_identifiers(claims, support_edges)
    kept_claims = [claim for claim in claims if claim.identifier in keep_ids]
    included_support = [
        edge
        for edge in support_edges
        if edge.target_claim_identifier in keep_ids
        and (
            edge.source_claim_identifier is None
            or edge.source_claim_identifier in keep_ids
        )
    ]

    used_dependency_labels = {
        edge.target_label
        for edge in included_support
        if edge.kind == SupportKind.RESULT_REFERENCE and edge.target_label is not None
    }
    dependencies = [
        dependency
        for dependency in item.dependencies
        if dependency.label in used_dependency_labels
    ]
    dependency_labels: dict[str, str] = {}
    for index, dependency in enumerate(dependencies, start=1):
        address = f"R{index}"
        if dependency.label is not None:
            dependency_labels[dependency.label] = address
        dependency_text = _semantic_text(dependency.statement)
        atom = canonicalize_mathematical_text(dependency_text)
        opaque = atom is None
        if atom is None:
            atom = dependency_text
        label = dependency.label or dependency.identifier
        nodes.append(
            CanonicalProofNode(
                address=address,
                kind=CanonicalNodeKind.DEPENDENCY,
                atom=f"{label}:{atom}",
                opaque=opaque,
            )
        )
        sources.append(
            CanonicalProofSource(
                address=address,
                ir_identifier=dependency.identifier,
                text=dependency.statement,
                source_range=dependency.source,
                referenced_result_identifier=dependency.identifier,
            )
        )

    claim_addresses: dict[str, str] = {}
    math_index = 0
    prose_index = 0
    qualifier_index = 0
    for claim in kept_claims:
        incoming = _incoming_edges(claim.identifier, included_support)
        atom = _claim_atom(claim, incoming)
        opaque = atom is None
        if opaque:
            prose_index += 1
            address = f"P{prose_index}"
            atom = _semantic_text(claim.raw)
            kind = CanonicalNodeKind.OPAQUE_PROSE
        else:
            math_index += 1
            address = f"C{math_index}"
            kind = CanonicalNodeKind.CLAIM
        assert atom is not None
        claim_addresses[claim.identifier] = address
        nodes.append(
            CanonicalProofNode(address=address, kind=kind, atom=atom, opaque=opaque)
        )
        sources.append(
            CanonicalProofSource(
                address=address,
                ir_identifier=claim.identifier,
                text=claim.raw,
                source_span=claim.source,
            )
        )

        for qualifier in claim.qualifiers:
            qualifier_index += 1
            edge_kind, qualifier_atom = _qualifier_atom(qualifier)
            qualifier_address = f"Q{qualifier_index}"
            canonical_edges.append(
                CanonicalProofEdge(
                    address=qualifier_address,
                    kind=edge_kind,
                    target=address,
                    status=qualifier.status,
                    atom=qualifier_atom,
                )
            )
            sources.append(
                CanonicalProofSource(
                    address=qualifier_address,
                    ir_identifier=qualifier.identifier,
                    text=qualifier.raw,
                    source_span=qualifier.source,
                )
            )

    dependency_by_label = {
        dependency.label: dependency
        for dependency in dependencies
        if dependency.label is not None
    }
    for index, edge in enumerate(included_support, start=1):
        source: str | None = None
        if edge.source_claim_identifier is not None:
            source = claim_addresses.get(edge.source_claim_identifier)
        elif edge.target_label is not None:
            source = dependency_labels.get(edge.target_label, f"@{edge.target_label}")
        target = claim_addresses[edge.target_claim_identifier]
        address = f"E{index}"
        canonical_edges.append(
            CanonicalProofEdge(
                address=address,
                kind=_SUPPORT_EDGE_KINDS[edge.kind],
                source=source,
                target=target,
                status=edge.status,
                atom=_support_payload(edge),
            )
        )
        referenced = (
            dependency_by_label.get(edge.target_label)
            if edge.target_label is not None
            else None
        )
        sources.append(
            CanonicalProofSource(
                address=address,
                ir_identifier=edge.identifier,
                text=edge.raw_justification,
                source_span=edge.source,
                referenced_result_identifier=(
                    referenced.identifier if referenced is not None else None
                ),
            )
        )

    return CanonicalProofIR(
        result_identifier=unit.identifier,
        nodes=nodes,
        edges=canonical_edges,
        sources=sources,
        pruned_claims=len(claims) - len(kept_claims),
    )
