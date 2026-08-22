from __future__ import annotations

from thorn.dependencies import DependencyNode, ExtractedProject
from thorn.evidence import InferenceStatus
from thorn.review_selection import SelectedSymbolContext, select_symbol_context, span_key
from thorn.semantic_dependencies import (
    dependency_node_sort_key,
    project_source_sort_key,
    result_project_symbol_dependency_ids,
)
from thorn.semantic_review import (
    ReviewContext,
    ReviewSourceContext,
    ReviewTargetKind,
    SemanticReviewItem,
)
from thorn.support import Claim, SupportEdge


def _claim_key(project: ExtractedProject, claim: Claim):
    return project_source_sort_key(project, claim.source, claim.identifier)


def _relation_key(project: ExtractedProject, edge: SupportEdge):
    return project_source_sort_key(project, edge.source, edge.identifier)


def _result_node(project: ExtractedProject, result_identifier: str) -> DependencyNode:
    try:
        return project.dependency_graph.node(result_identifier)
    except KeyError:
        return DependencyNode.from_unit(project.unit(result_identifier))


def _result_relations(
    project: ExtractedProject,
    claims: list[Claim],
) -> list[SupportEdge]:
    claim_ids = {claim.identifier for claim in claims}
    return sorted(
        (
            edge
            for edge in project.proof_support_graph.edges
            if edge.target_claim_identifier in claim_ids
            and (
                edge.source_claim_identifier is None
                or edge.source_claim_identifier in claim_ids
            )
        ),
        key=lambda edge: _relation_key(project, edge),
    )


def _result_symbol_context(
    project: ExtractedProject,
    result_identifier: str,
) -> SelectedSymbolContext:
    table = project.symbol_table

    # Result-wide breadth is policy here. Canonical project declaration closure,
    # ordering, and constraint classification live in the shared selector primitive.
    symbol_ids = {
        symbol.identifier
        for symbol in table.symbols
        if symbol.result_identifier == result_identifier
    }
    symbol_ids.update(result_project_symbol_dependency_ids(project, result_identifier))
    candidates = (
        candidate
        for candidate in table.candidates
        if candidate.result_identifier == result_identifier
    )
    return select_symbol_context(project, symbol_ids, candidates)


def _nearby_context(
    project: ExtractedProject,
    relations: list[SupportEdge],
) -> list[ReviewSourceContext]:
    contexts: dict[
        tuple[str, tuple[str, int, int, int, int, int, int]],
        ReviewSourceContext,
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


def build_result_review_context(
    project: ExtractedProject,
    result_identifier: str,
) -> ReviewContext:
    """Build the canonical bounded result-level review item for one result.

    Normal Thorn review is result-level and always returns exactly one item for a
    requested result, whether or not deterministic support extraction contains an
    uncertainty marker. The uncertainty-focused selector in ``semantic_review``
    is a separate diagnostic/evaluation projection and never gates this path.

    The item contains only Thorn-owned canonical IR. Provider adapters receive a
    ``SemanticReviewRequest`` and never receive or traverse the project graph.
    """

    project.unit(result_identifier)
    claims = sorted(
        project.proof_support_graph.claims_for_result(result_identifier),
        key=lambda claim: _claim_key(project, claim),
    )
    relations = _result_relations(project, claims)
    symbol_context = _result_symbol_context(project, result_identifier)
    uncertain_relation_ids = sorted(
        edge.identifier
        for edge in relations
        if edge.status in {InferenceStatus.AMBIGUOUS, InferenceStatus.UNRESOLVED}
    )
    dependencies = sorted(
        project.dependency_graph.direct_dependencies(result_identifier),
        key=lambda node: dependency_node_sort_key(project, node),
    )

    item = SemanticReviewItem(
        identifier=f"semantic-review-eval:{result_identifier}",
        target_kind=ReviewTargetKind.RESULT,
        result=_result_node(project, result_identifier),
        claims=claims,
        trigger_relation_identifiers=uncertain_relation_ids,
        support_relations=relations,
        hypotheses=symbol_context.hypotheses,
        local_constraints=symbol_context.local_constraints,
        symbols=symbol_context.symbols,
        definitions=symbol_context.definitions,
        symbol_candidates=symbol_context.candidates,
        dependencies=dependencies,
        nearby_context=_nearby_context(project, relations),
    )
    return ReviewContext(items=[item])
