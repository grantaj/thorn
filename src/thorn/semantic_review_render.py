from __future__ import annotations

import json

from pydantic import BaseModel

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import SourceSpan
from thorn.models import SourceRange
from thorn.semantic_review import ReviewTargetKind, SemanticReviewItem
from thorn.support import Claim, SupportEdge
from thorn.symbols import Constraint


class SemanticReviewRequest(BaseModel):
    """Provider-neutral request for one already-bounded semantic review item.

    The canonical item remains the source of truth. Provider adapters may render
    this request for their transport, but provider-specific message or prompt
    schemas do not belong here.
    """

    item: SemanticReviewItem

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def build_semantic_review_request(item: SemanticReviewItem) -> SemanticReviewRequest:
    """Create a provider-neutral request without re-selecting or regrouping Math IR."""

    return SemanticReviewRequest(item=item.model_copy(deep=True))


def _format_span(span: SourceSpan) -> str:
    return (
        f"{span.file}:{span.start_line}:{span.start_column}-"
        f"{span.end_line}:{span.end_column} "
        f"[offsets {span.start_offset}:{span.end_offset}]"
    )


def _format_range(source: SourceRange) -> str:
    return f"{source.file}:{source.start_line}-{source.end_line}"


def _append_evidence(lines: list[str], evidence: list[StructuralEvidence]) -> None:
    if not evidence:
        lines.append("Evidence: (none retained)")
        return
    lines.append("Evidence:")
    for item in evidence:
        lines.append(f"- Reason: {item.reason}")
        lines.append(f"  Source: {_format_span(item.source)}")
        lines.append(
            "  Target: "
            + (_format_span(item.target) if item.target is not None else "(none)")
        )
        lines.append(f"  Context: {item.context}")
        lines.append(
            "  Dependency path: "
            + (" -> ".join(item.dependency_path) if item.dependency_path else "(none)")
        )
        lines.append(f"  Frontend: {item.frontend or '(not recorded)'}")


def _append_relation(lines: list[str], relation: SupportEdge, *, role: str) -> None:
    lines.append(f"### Relation ID: {relation.identifier}")
    lines.append(f"Review role: {role}")
    lines.append(f"Kind: {relation.kind.value}")
    lines.append(f"Status: {relation.status.value.upper()}")
    lines.append(f"Source: {_format_span(relation.source)}")
    lines.append(f"Source claim: {relation.source_claim_identifier or '(none)'}")
    lines.append(f"Target claim: {relation.target_claim_identifier}")
    lines.append(f"Target label: {relation.target_label or '(none)'}")
    lines.append(f"Named property: {relation.named_property or '(none)'}")
    lines.append(f"Raw support wording: {relation.raw_justification}")
    lines.append(
        "Front-end confidence: "
        + (f"{relation.confidence:.3f}" if relation.confidence is not None else "(not assigned)")
    )
    _append_evidence(lines, relation.evidence)
    lines.append("")


def _append_claim(lines: list[str], claim: Claim) -> None:
    lines.append(f"### Claim ID: {claim.identifier}")
    lines.append(f"Form: {claim.form.value}")
    lines.append(f"Source: {_format_span(claim.source)}")
    lines.append("Exact wording:")
    lines.append(claim.raw)
    if claim.qualifiers:
        lines.append("Qualifiers:")
        for qualifier in claim.qualifiers:
            lines.append(f"- ID: {qualifier.identifier}")
            lines.append(f"  Kind: {qualifier.kind.value}")
            lines.append(f"  Status: {qualifier.status.value.upper()}")
            lines.append(f"  Source: {_format_span(qualifier.source)}")
            lines.append(f"  Wording: {qualifier.raw}")
    lines.append("")


def _append_constraints(lines: list[str], constraints: list[Constraint], *, noun: str) -> None:
    if not constraints:
        lines.append(f"(no {noun} selected)")
        lines.append("")
        return
    for item in constraints:
        lines.append(f"- {noun.title()} ID: {item.identifier}")
        lines.append(f"  Symbol ID: {item.symbol_identifier}")
        lines.append(f"  Relation: {item.relation} {item.expression_latex}")
        lines.append(f"  Source: {_format_span(item.source)}")
        lines.append(f"  Wording: {item.raw}")
    lines.append("")


def render_semantic_review_request(request: SemanticReviewRequest) -> str:
    """Render one semantic request deterministically for a mathematical reviewer.

    The review selector owns collection ordering. This rendering boundary preserves
    that canonical order rather than inventing a physical-filename order that can
    disagree with expanded workspace/manuscript order.
    """

    item = request.item
    targeted = item.target_kind == ReviewTargetKind.SUPPORT_RELATION
    trigger_ids = set(item.trigger_relation_identifiers)
    trigger_relations = [
        relation for relation in item.support_relations if relation.identifier in trigger_ids
    ]
    confident_relations = [
        relation
        for relation in item.support_relations
        if relation.identifier not in trigger_ids
        and relation.status == InferenceStatus.CONFIDENT
    ]

    if targeted:
        selection_explanation = (
            "Relations under semantic escalation are the reason this targeted view was selected. "
            "CONFIDENT relations are interpretation context only; they are not assertions that the "
            "mathematics is correct."
        )
        trigger_heading = "## Relations that caused semantic escalation"
        trigger_role = "semantic escalation reason"
    else:
        selection_explanation = (
            "This is the canonical result-level review view. AMBIGUOUS and UNRESOLVED relations "
            "are highlighted because uncertainty is present, but they did not gate or cause the "
            "review request. CONFIDENT relations are interpretation context only."
        )
        trigger_heading = "## Uncertain support relations in this result"
        trigger_role = "uncertain result context"

    lines = [
        "# Thorn semantic review request",
        f"Review item: {item.identifier}",
        f"Target kind: {item.target_kind.value}",
        "",
        "## Review task",
        (
            "Judge the mathematics in this bounded Thorn-owned view: determine whether the audited "
            "claims and proposed support relations are valid, invalid, insufficiently supported, "
            "or genuinely unresolved from the supplied context."
        ),
        (
            "Thorn's relation statuses record deterministic front-end extraction certainty. "
            "AMBIGUOUS and UNRESOLVED are uncertainty states, not correctness defects. Do not "
            "report a finding merely because a relation has one of those statuses."
        ),
        selection_explanation,
        "Use the retained source wording and provenance when wording matters. Do not assume that "
        "Thorn's parser conclusion is mathematically correct.",
        "",
        "## Containing result",
        f"Result ID: {item.result.identifier}",
        f"Environment: {item.result.environment}",
        f"Label: {item.result.label or '(none)'}",
        f"Source: {_format_range(item.result.source)}",
        "Statement:",
        item.result.statement,
        "",
        "## Audited claims",
    ]

    if item.claims:
        for claim in item.claims:
            _append_claim(lines, claim)
    else:
        lines.extend(["(no claims selected)", ""])

    lines.append(trigger_heading)
    if trigger_relations:
        for relation in trigger_relations:
            _append_relation(lines, relation, role=trigger_role)
    else:
        lines.extend(["(no uncertain relation present in request)", ""])

    lines.append("## Confident support context")
    if confident_relations:
        for relation in confident_relations:
            _append_relation(lines, relation, role="confident interpretation context")
    else:
        lines.extend(["(no confident support context selected)", ""])

    lines.append("## Explicit hypotheses")
    _append_constraints(lines, item.hypotheses, noun="hypothesis")

    lines.append("## Relevant local constraints")
    _append_constraints(lines, item.local_constraints, noun="local constraint")

    lines.append("## Relevant definitions")
    if item.definitions:
        for definition in item.definitions:
            lines.append(f"- Definition ID: {definition.identifier}")
            lines.append(f"  Symbol ID: {definition.symbol_identifier}")
            lines.append(f"  Operator: {definition.operator}")
            lines.append(f"  Expression: {definition.expression_latex}")
            lines.append(f"  Source: {_format_span(definition.source)}")
            lines.append(f"  Wording: {definition.raw}")
    else:
        lines.append("(no definitions selected)")
    lines.append("")

    lines.append("## Relevant symbols")
    if item.symbols:
        for symbol in item.symbols:
            lines.append(f"- Symbol ID: {symbol.identifier}")
            lines.append(f"  Name: {symbol.name}")
            lines.append(f"  Role: {symbol.role.value}")
            lines.append(f"  Introduction kind: {symbol.introduction_kind.value}")
            lines.append(f"  Source: {_format_span(symbol.source)}")
            lines.append(f"  Introduction source: {_format_span(symbol.introduction_source)}")
            lines.append(f"  Wording: {symbol.raw_introduction}")
    else:
        lines.append("(no symbols selected)")
    lines.append("")

    lines.append("## Uncertain symbol candidates supplied as context only")
    if item.symbol_candidates:
        lines.append(
            "These candidates did not trigger semantic review; they are retained only to help "
            "interpret nearby notation."
        )
        for candidate in item.symbol_candidates:
            lines.append(f"- Candidate ID: {candidate.identifier}")
            lines.append(f"  Name: {candidate.name}")
            lines.append(f"  Kind: {candidate.kind.value}")
            lines.append(f"  Status: {candidate.status.value.upper()}")
            lines.append(f"  Source: {_format_span(candidate.source)}")
            lines.append(f"  Math source: {_format_span(candidate.math_source)}")
            lines.append(f"  Wording: {candidate.raw_context}")
            _append_evidence(lines, candidate.evidence)
    else:
        lines.append("(no symbol candidates selected)")
    lines.append("")

    lines.append("## Relevant result dependencies")
    if item.dependencies:
        for dependency in item.dependencies:
            lines.append(f"- Dependency ID: {dependency.identifier}")
            lines.append(f"  Environment: {dependency.environment}")
            lines.append(f"  Label: {dependency.label or '(none)'}")
            lines.append(f"  Source: {_format_range(dependency.source)}")
            lines.append(f"  Statement: {dependency.statement}")
    else:
        lines.append("(no dependency results selected)")
    lines.append("")

    lines.append("## Nearby source wording retained by the deterministic front-end")
    if item.nearby_context:
        for context in item.nearby_context:
            lines.append(f"- Source: {_format_span(context.source)}")
            lines.append(f"  Wording: {context.text}")
    else:
        lines.append("(no nearby source wording retained)")
    lines.append("")

    return "\n".join(lines)
