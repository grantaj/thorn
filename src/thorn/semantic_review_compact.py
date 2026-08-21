from __future__ import annotations

from thorn.evidence import InferenceStatus
from thorn.semantic_review import ReviewTargetKind
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.support import Claim, SupportEdge


def _claim_key(claim: Claim) -> tuple[str, int, int, str]:
    return (
        claim.source.file,
        claim.source.start_offset,
        claim.source.end_offset,
        claim.identifier,
    )


def _relation_key(edge: SupportEdge) -> tuple[str, int, int, str]:
    return (
        edge.source.file,
        edge.source.start_offset,
        edge.source.end_offset,
        edge.identifier,
    )


def _compact_text(text: str) -> str:
    return " ".join(text.strip().split())


def _append_relations(
    lines: list[str],
    relations: list[SupportEdge],
    *,
    claim_labels: dict[str, str],
) -> None:
    for index, relation in enumerate(sorted(relations, key=_relation_key), start=1):
        source = (
            claim_labels.get(relation.source_claim_identifier, relation.source_claim_identifier)
            if relation.source_claim_identifier is not None
            else "external"
        )
        target = claim_labels.get(
            relation.target_claim_identifier,
            relation.target_claim_identifier,
        )
        parts = [
            f"R{index}: {source} -> {target}",
            f"kind={relation.kind.value}",
        ]
        cue = _compact_text(relation.raw_justification)
        if cue:
            parts.append(f"wording={cue}")
        if relation.target_label:
            parts.append(f"reference={relation.target_label}")
        if relation.named_property:
            parts.append(f"property={relation.named_property}")
        lines.append("; ".join(parts))


def render_compact_semantic_review_request(request: SemanticReviewRequest) -> str:
    """Render only mathematical content useful to a semantic reviewer.

    The canonical ``SemanticReviewItem`` remains unchanged and retains full Thorn
    provenance. This renderer is intentionally lossy at the provider boundary: it
    removes machine-facing identifiers, source coordinates, frontend evidence,
    confidence metadata, symbol bookkeeping, and repeated instructions while
    preserving the theorem, proof claims, support structure, explicit constraints,
    definitions, and referenced mathematical results.
    """

    item = request.item
    claims = sorted(item.claims, key=_claim_key)
    claim_labels = {claim.identifier: f"C{index}" for index, claim in enumerate(claims, start=1)}
    trigger_ids = set(item.trigger_relation_identifiers)
    trigger_relations = [
        relation for relation in item.support_relations if relation.identifier in trigger_ids
    ]
    context_relations = [
        relation
        for relation in item.support_relations
        if relation.identifier not in trigger_ids
        and relation.status == InferenceStatus.CONFIDENT
    ]

    lines = [
        "# Theorem",
        item.result.statement.strip(),
    ]

    lines.extend(["", "# Proof claims"])
    if claims:
        for claim in claims:
            label = claim_labels[claim.identifier]
            lines.append(f"{label}: {_compact_text(claim.raw)}")
            qualifiers = [
                _compact_text(qualifier.raw)
                for qualifier in claim.qualifiers
                if _compact_text(qualifier.raw)
            ]
            if qualifiers:
                lines.append(f"  qualifiers: {'; '.join(qualifiers)}")
    else:
        lines.append("(none extracted)")

    if trigger_relations:
        heading = (
            "# Escalated support questions"
            if item.target_kind == ReviewTargetKind.SUPPORT_RELATION
            else "# Uncertain support relations"
        )
        lines.extend(["", heading])
        _append_relations(lines, trigger_relations, claim_labels=claim_labels)

    if context_relations:
        lines.extend(["", "# Other support context"])
        _append_relations(lines, context_relations, claim_labels=claim_labels)

    hypotheses = [_compact_text(item.raw) for item in item.hypotheses if _compact_text(item.raw)]
    if hypotheses:
        lines.extend(["", "# Explicit hypotheses"])
        lines.extend(f"- {text}" for text in hypotheses)

    local_constraints = [
        _compact_text(item.raw)
        for item in item.local_constraints
        if _compact_text(item.raw)
    ]
    if local_constraints:
        lines.extend(["", "# Local constraints"])
        lines.extend(f"- {text}" for text in local_constraints)

    definitions = [_compact_text(item.raw) for item in item.definitions if _compact_text(item.raw)]
    if definitions:
        lines.extend(["", "# Definitions"])
        lines.extend(f"- {text}" for text in definitions)

    if item.dependencies:
        lines.extend(["", "# Referenced results"])
        for dependency in item.dependencies:
            label = dependency.label or dependency.identifier
            lines.append(f"- {label}: {_compact_text(dependency.statement)}")

    return "\n".join(lines) + "\n"
