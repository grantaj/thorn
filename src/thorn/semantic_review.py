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
from thorn.semantic_dependencies import (
    close_project_symbol_dependencies,
    result_project_symbol_dependency_ids,
    semantic_symbol_sort_key,
)
from thorn.support import Claim, SupportEdge
from thorn.symbols import (
    Constraint,
    Definition,
    ScopeKind,
    Symbol,
    SymbolIntroductionCandidate,
)


class ReviewTargetKind(StrEnum):
    """Kinds of Thorn IR relations that can become semantic review targets."""

    SUPPORT_RELATION = "support_relation"


class ReviewSourceContext(BaseModel):
    """Compact source wording retained because it contributed structural evidence."""

    text: str
    source: SourceSpan


class SemanticReviewItem(BaseModel):
    """One bounded mathematical neighbourhood worth later semantic attention.

    The representation is provider-independent and contains only Thorn-owned IR
    objects. ``trigger_relation_identifiers`` records why the item exists;
    confident support relations may be present in ``support_relations`` without
    becoming escalation reasons themselves.
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
    """Provider-neutral semantic-review context distilled from a project Math IR."""

    items: list[SemanticReviewItem] = Field(default_factory=list)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


def _span_key(span: SourceSpan) -> tuple[str, int, int, int, int, int, int]:
    return (
        span.file,
        span.start_offset,
        span.end_offset,
        span.start_line,
        span.start_column,
        span.end_line,
        span.end_column,
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


def _edge_sort_key(edge: SupportEdge) -> tuple[str, int, int, str]:
    return (
        edge.source.file,
        edge.source.start_offset,
        edge.source.end_offset,
        edge.identifier,
    )


def _claim_sort_key(claim: Claim) -> tuple[str, int, int, str]:
    return (
        claim.source.file,
        claim.source.start_offset,
        claim.source.end_offset,
        claim.identifier,
    )


def _trigger_edges(project: ExtractedProject) -> list[SupportEdge]:
    return sorted(
        (
            edge
            for edge in project.proof_support_graph.edges
            if edge.status in {InferenceStatus.AMBIGUOUS, InferenceStatus.UNRESOLVED}
        ),
        key=_edge_sort_key,
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
        key=_claim_sort_key,
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
        groups.append(sorted((edges[index] for index in component), key=_edge_sort_key))

    return sorted(groups, key=lambda group: _edge_sort_key(group[0]))


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
) -> tuple[
    list[Constraint],
    list[Constraint],
    list[Symbol],
    list[Definition],
    list[SymbolIntroductionCandidate],
]:
    table = project.symbol_table

    # Result-to-project-declaration identity comes from canonical resolved uses.
    # The uncertainty-focused selector may narrow local context below, but it does
    # not reconstruct semantic project edges from source text or file ordering.
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

    # NEED_SOURCE is deliberately bounded to one round. Any authoritative
    # project prose needed to interpret an already-selected declaration must
    # therefore be selected before the packet advertises its closed-world
    # handles, not discovered only after rescuing the outer declaration.
    selected_ids = close_project_symbol_dependencies(project, selected_ids)

    symbols = sorted(
        (symbol for symbol in table.symbols if symbol.identifier in selected_ids),
        key=lambda symbol: (*semantic_symbol_sort_key(project, symbol), symbol.identifier),
    )
    definitions = sorted(
        (
            definition
            for definition in table.definitions
            if definition.symbol_identifier in selected_ids
        ),
        key=lambda definition: (*_span_key(definition.source), definition.identifier),
    )

    hypotheses: list[Constraint] = []
    local_constraints: list[Constraint] = []
    symbol_by_id = {symbol.identifier: symbol for symbol in symbols}
    for constraint in table.constraints:
        selected_symbol = symbol_by_id.get(constraint.symbol_identifier)
        if selected_symbol is None:
            continue
        scope_kind = table.scope(selected_symbol.scope_identifier).kind
        if scope_kind in {ScopeKind.RESULT, ScopeKind.STATEMENT}:
            hypotheses.append(constraint)
        else:
            local_constraints.append(constraint)
    hypotheses.sort(key=lambda item: (*_span_key(item.source), item.identifier))
    local_constraints.sort(key=lambda item: (*_span_key(item.source), item.identifier))

    candidates = sorted(
        (
            candidate
            for candidate in table.candidates
            if candidate.result_identifier == result_identifier
            and any(
                _spans_overlap(candidate.source, span)
                or _spans_overlap(candidate.math_source, span)
                for span in spans
            )
        ),
        key=lambda candidate: (*_span_key(candidate.source), candidate.identifier),
    )
    return hypotheses, local_constraints, symbols, definitions, candidates


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
    # DependencyGraph node order is already normalized workspace order.
    return [
        node
        for node in project.dependency_graph.nodes
        if node.identifier in identifiers
    ]


def _nearby_context(relations: list[SupportEdge]) -> list[ReviewSourceContext]:
    contexts: dict[
        tuple[str, tuple[str, int, int, int, int, int, int]], ReviewSourceContext
    ] = {}
    for relation in relations:
        for evidence in relation.evidence:
            text = evidence.context.strip()
            if not text:
                continue
            key = (text, _span_key(evidence.source))
            contexts[key] = ReviewSourceContext(text=text, source=evidence.source)
    return [contexts[key] for key in sorted(contexts)]


def _item_identifier(result_identifier: str, trigger_edges: list[SupportEdge]) -> str:
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
        key=_claim_sort_key,
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
    relations = sorted(relations_by_id.values(), key=_edge_sort_key)
    spans = _relevant_spans(claims, relations)
    (
        hypotheses,
        local_constraints,
        symbols,
        definitions,
        candidates,
    ) = _select_symbol_context(
        project,
        result_identifier,
        spans,
    )

    try:
        result = project.dependency_graph.node(result_identifier)
    except KeyError:
        result = DependencyNode.from_unit(project.unit(result_identifier))

    return SemanticReviewItem(
        identifier=_item_identifier(result_identifier, trigger_edges),
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=result,
        claims=claims,
        trigger_relation_identifiers=sorted(edge.identifier for edge in trigger_edges),
        support_relations=relations,
        hypotheses=hypotheses,
        local_constraints=local_constraints,
        symbols=symbols,
        definitions=definitions,
        symbol_candidates=candidates,
        dependencies=_select_dependencies(project, result_identifier, relations),
        nearby_context=_nearby_context(trigger_edges),
    )


def build_review_context(project: ExtractedProject) -> ReviewContext:
    """Distill uncertain support relations into bounded semantic-review items.

    Ambiguous or unresolved support relations are the only triggers in this
    tranche. Ambiguous symbol candidates never create an item by themselves;
    they may be selected as local context after a support item already exists.
    """

    triggers_by_result: dict[str, list[SupportEdge]] = defaultdict(list)
    graph = project.proof_support_graph
    for edge in _trigger_edges(project):
        target = graph.claim(edge.target_claim_identifier)
        triggers_by_result[target.result_identifier].append(edge)

    items: list[SemanticReviewItem] = []
    # ExtractedProject.units is already normalized workspace order. Preserve it
    # rather than re-sorting result identifiers lexically.
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
