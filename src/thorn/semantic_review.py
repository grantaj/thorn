from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.dependencies import (
    DependencyNode,
    DependencyResolution,
    ExtractedProject,
)
from thorn.evidence import InferenceStatus
from thorn.frontend import SourceSpan
from thorn.review_selection import SelectedSymbolContext, select_symbol_context, span_key
from thorn.semantic_dependencies import (
    ProjectSourceSortKey,
    dependency_node_sort_key,
    project_source_sort_key,
    result_project_symbol_dependency_ids,
)
from thorn.support import Claim, SupportEdge
from thorn.symbols import (
    Constraint,
    Definition,
    Symbol,
    SymbolIntroductionCandidate,
)


class ReviewTargetKind(StrEnum):
    """Policy that selected a bounded Thorn review projection."""

    RESULT = "result"
    SUPPORT_RELATION = "support_relation"


class ReviewSourceContext(BaseModel):
    """Compact source wording retained because it contributed structural evidence."""

    text: str
    source: SourceSpan


class SemanticReviewItem(BaseModel):
    """One bounded Thorn-owned mathematical review projection.

    ``RESULT`` items are the canonical normal-review view for a requested result.
    ``SUPPORT_RELATION`` items are uncertainty-focused diagnostic/evaluation views.
    ``trigger_relation_identifiers`` therefore records uncertainty present in a
    result-level item, but records the actual selection reason for a targeted item.
    """

    identifier: str
    target_kind: ReviewTargetKind
    result: DependencyNode
    claims: list[Claim] = Field(default_factory=list)
    trigger_relation_identifiers: list[str] = Field(default_factory=list)
    support_relations: list[SupportEdge] = Field(default_factory=list)
    hypotheses: list[Constraint] = Field(default_factory=list)
    local_constraints: list[Constraint] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    symbol_candidates: list[SymbolIntroductionCandidate] = Field(default_factory=list)
    dependencies: list[DependencyNode] = Field(default_factory=list)
    nearby_context: list[ReviewSourceContext] = Field(default_factory=list)

    def canonical_json(self) -> str:
        """Serialize deterministically for tests and future fingerprinting."""

        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class ReviewContext(BaseModel):
    """Provider-neutral review context projected from canonical Thorn IR."""

    items: list[SemanticReviewItem] = Field(default_factory=list)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def _spans_overlap(left: SourceSpan, right: SourceSpan) -> bool:
    return (
        left.file == right.file
        and left.start_offset < right.end_offset
        and right.start_offset < left.end_offset
    )


def _edge_claim_ids(edge: SupportEdge) -> set[str]:
    identifiers = {edge.target_claim_identifier}
    if edge.source_claim_identifier is not None:
        identifiers.add(edge.source_claim_identifier)
    return identifiers


def _edge_sort_key(
    project: ExtractedProject,
    edge: SupportEdge,
) -> ProjectSourceSortKey:
    return project_source_sort_key(project, edge.source, edge.identifier)


def _claim_sort_key(
    project: ExtractedProject,
    claim: Claim,
) -> ProjectSourceSortKey:
    return project_source_sort_key(project, claim.source, claim.identifier)


def _trigger_edges(project: ExtractedProject) -> list[SupportEdge]:
    return sorted(
        (
            edge
            for edge in project.proof_support_graph.edges
            if edge.status in {InferenceStatus.AMBIGUOUS, InferenceStatus.UNRESOLVED}
        ),
        key=lambda edge: _edge_sort_key(project, edge),
    )


def _locally_related(
    left: SupportEdge,
    right: SupportEdge,
    *,
    claim_order: dict[str, int],
    confident_edges: list[SupportEdge],
) -> bool:
    left_ids = _edge_claim_ids(left)
    right_ids = _edge_claim_ids(right)
    if left_ids & right_ids:
        return True

    for edge in confident_edges:
        bridge_ids = _edge_claim_ids(edge)
        if bridge_ids & left_ids and bridge_ids & right_ids:
            return True

    left_positions = [claim_order[item] for item in left_ids if item in claim_order]
    right_positions = [claim_order[item] for item in right_ids if item in claim_order]
    if not left_positions or not right_positions:
        return False
    distance = min(
        abs(left_pos - right_pos)
        for left_pos in left_positions
        for right_pos in right_positions
    )
    return distance <= 1


def _group_trigger_edges(
    project: ExtractedProject,
    result_identifier: str,
    edges: list[SupportEdge],
) -> list[list[SupportEdge]]:
    graph = project.proof_support_graph
    result_claims = sorted(
        graph.claims_for_result(result_identifier),
        key=lambda claim: _claim_sort_key(project, claim),
    )
    claim_order = {claim.identifier: index for index, claim in enumerate(result_claims)}
    result_claim_ids = set(claim_order)
    confident_edges = [
        edge
        for edge in graph.edges
        if edge.status == InferenceStatus.CONFIDENT
        and edge.target_claim_identifier in result_claim_ids
        and (
            edge.source_claim_identifier is None
            or edge.source_claim_identifier in result_claim_ids
        )
    ]

    groups: list[list[SupportEdge]] = []
    remaining = set(range(len(edges)))
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        component = {seed}
        pending = [seed]
        while pending:
            current = pending.pop()
            neighbours = [
                candidate
                for candidate in sorted(remaining)
                if _locally_related(
                    edges[current],
                    edges[candidate],
                    claim_order=claim_order,
                    confident_edges=confident_edges,
                )
            ]
            for neighbour in neighbours:
                remaining.remove(neighbour)
                component.add(neighbour)
                pending.append(neighbour)
        groups.append(
            sorted(
                (edges[index] for index in component),
                key=lambda edge: _edge_sort_key(project, edge),
            )
        )

    return sorted(groups, key=lambda group: _edge_sort_key(project, group[0]))


def _relevant_spans(
    claims: list[Claim],
    relations: list[SupportEdge],
) -> list[SourceSpan]:
    spans: list[SourceSpan] = []
    for claim in claims:
        spans.append(claim.source)
        for qualifier in claim.qualifiers:
            spans.append(qualifier.source)
            spans.extend(bound.source for bound in qualifier.bound_names)
            for evidence in qualifier.evidence:
                spans.append(evidence.source)
                if evidence.target is not None:
                    spans.append(evidence.target)
    for relation in relations:
        spans.append(relation.source)
        for evidence in relation.evidence:
            spans.append(evidence.source)
            if evidence.target is not None:
                spans.append(evidence.target)
    return spans


def _select_symbol_context(
    project: ExtractedProject,
    result_identifier: str,
    spans: list[SourceSpan],
) -> SelectedSymbolContext:
    table = project.symbol_table

    # Targeted breadth is trigger-relative. Mathematical identity and transitive
    # authority closure still come from the same canonical Symbol IR as normal review.
    selected_ids = set(result_project_symbol_dependency_ids(project, result_identifier))

    for use in table.uses:
        if use.resolved_symbol_identifier is None:
            continue
        if any(_spans_overlap(use.source, span) for span in spans):
            selected_ids.add(use.resolved_symbol_identifier)

    for symbol in table.symbols:
        if symbol.result_identifier != result_identifier:
            continue
        if any(
            _spans_overlap(symbol.source, span)
            or _spans_overlap(symbol.introduction_source, span)
            for span in spans
        ):
            selected_ids.add(symbol.identifier)

    for definition in table.definitions:
        if any(_spans_overlap(definition.source, span) for span in spans):
            selected_ids.add(definition.symbol_identifier)
    for constraint in table.constraints:
        if any(_spans_overlap(constraint.source, span) for span in spans):
            selected_ids.add(constraint.symbol_identifier)

    candidates = (
        candidate
        for candidate in table.candidates
        if candidate.result_identifier == result_identifier
        and any(
            _spans_overlap(candidate.source, span)
            or _spans_overlap(candidate.math_source, span)
            for span in spans
        )
    )
    return select_symbol_context(project, selected_ids, candidates)


def _select_dependencies(
    project: ExtractedProject,
    result_identifier: str,
    relations: list[SupportEdge],
) -> list[DependencyNode]:
    labels = {edge.target_label for edge in relations if edge.target_label is not None}
    identifiers = {
        edge.target_identifier
        for edge in project.dependency_graph.edges
        if edge.source_identifier == result_identifier
        and edge.target_label in labels
        and edge.resolution == DependencyResolution.RESOLVED
        and edge.target_identifier is not None
    }
    nodes = [
        node
        for node in project.dependency_graph.nodes
        if node.identifier in identifiers
    ]
    return sorted(nodes, key=lambda node: dependency_node_sort_key(project, node))


def _nearby_context(
    project: ExtractedProject,
    relations: list[SupportEdge],
) -> list[ReviewSourceContext]:
    contexts: dict[
        tuple[str, tuple[str, int, int, int, int, int, int]], ReviewSourceContext
    ] = {}
    for relation in relations:
        for evidence in relation.evidence:
            text = evidence.context.strip()
            if not text:
                continue
            key = (text, span_key(evidence.source))
            contexts[key] = ReviewSourceContext(text=text, source=evidence.source)
    return sorted(
        contexts.values(),
        key=lambda context: project_source_sort_key(
            project,
            context.source,
            context.text,
        ),
    )


def _item_identifier(result_identifier: str, trigger_edges: list[SupportEdge]) -> str:
    # Identity is intentionally order-insensitive: presentation order must not
    # create a distinct review item for the same trigger set.
    trigger_ids = sorted(edge.identifier for edge in trigger_edges)
    payload = "\0".join([result_identifier, *trigger_ids]).encode()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"semantic-review:{result_identifier}:{digest}"


def _build_item(
    project: ExtractedProject,
    result_identifier: str,
    trigger_edges: list[SupportEdge],
) -> SemanticReviewItem:
    graph = project.proof_support_graph
    core_claim_ids: set[str] = set()
    for edge in trigger_edges:
        core_claim_ids.update(_edge_claim_ids(edge))
    claims = sorted(
        (claim for claim in graph.claims if claim.identifier in core_claim_ids),
        key=lambda claim: _claim_sort_key(project, claim),
    )

    contextual_relations = [
        edge
        for edge in graph.edges
        if edge.status == InferenceStatus.CONFIDENT
        and edge.target_claim_identifier in core_claim_ids
        and (
            edge.source_claim_identifier is None
            or edge.source_claim_identifier in core_claim_ids
        )
    ]
    relations_by_id = {
        edge.identifier: edge for edge in [*trigger_edges, *contextual_relations]
    }
    relations = sorted(
        relations_by_id.values(),
        key=lambda edge: _edge_sort_key(project, edge),
    )
    spans = _relevant_spans(claims, relations)
    symbol_context = _select_symbol_context(project, result_identifier, spans)

    try:
        result = project.dependency_graph.node(result_identifier)
    except KeyError:
        result = DependencyNode.from_unit(project.unit(result_identifier))

    return SemanticReviewItem(
        identifier=_item_identifier(result_identifier, trigger_edges),
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=result,
        claims=claims,
        trigger_relation_identifiers=[edge.identifier for edge in trigger_edges],
        support_relations=relations,
        hypotheses=symbol_context.hypotheses,
        local_constraints=symbol_context.local_constraints,
        symbols=symbol_context.symbols,
        definitions=symbol_context.definitions,
        symbol_candidates=symbol_context.candidates,
        dependencies=_select_dependencies(project, result_identifier, relations),
        nearby_context=_nearby_context(project, trigger_edges),
    )


def build_review_context(project: ExtractedProject) -> ReviewContext:
    """Build Thorn's uncertainty-focused diagnostic/evaluation review projection.

    This selector is retained for the explicit ``thorn-eval --targeted-preflight``
    and ``--review-context targeted`` use cases. It is not the canonical normal
    review policy and never gates ``review_workflow``; normal review always uses
    the result-level projection from ``build_result_review_context``.

    Ambiguous or unresolved support relations are the only diagnostic triggers.
    Ambiguous symbol candidates never create an item by themselves; they may be
    selected as local context after a support item already exists.
    """

    triggers_by_result: dict[str, list[SupportEdge]] = defaultdict(list)
    graph = project.proof_support_graph
    for edge in _trigger_edges(project):
        target = graph.claim(edge.target_claim_identifier)
        triggers_by_result[target.result_identifier].append(edge)

    items: list[SemanticReviewItem] = []
    for unit in project.units:
        result_identifier = unit.identifier
        if result_identifier not in triggers_by_result:
            continue
        groups = _group_trigger_edges(
            project,
            result_identifier,
            triggers_by_result[result_identifier],
        )
        items.extend(_build_item(project, result_identifier, group) for group in groups)

    return ReviewContext(items=items)
