from __future__ import annotations

from thorn.dependencies import DependencyNode, ExtractedProject
from thorn.evidence import InferenceStatus
from thorn.linguistic_statements import StatementScopeKind
from thorn.review_selection import SelectedSymbolContext, select_symbol_context, span_key
from thorn.semantic_dependencies import (
    ProjectSourceSortKey,
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
from thorn.workspace import ProjectPositionLookup, WorkspaceResolution


def _claim_key(project: ExtractedProject, claim: Claim) -> ProjectSourceSortKey:
    return project_source_sort_key(project, claim.source, claim.identifier)


def _relation_key(project: ExtractedProject, edge: SupportEdge) -> ProjectSourceSortKey:
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


def _source_overlap(left: object, right: object) -> bool:
    return (
        left.file == right.file
        and left.start_offset < right.end_offset
        and right.start_offset < left.end_offset
    )


def _statement_context(
    project: ExtractedProject,
    result_identifier: str,
) -> list[ReviewSourceContext]:
    """Select prior statements by generic linguistic relevance, not declaration grammar."""

    inventory = project.linguistic_statements
    workspace = project.workspace
    if (
        inventory is None
        or not inventory.complete
        or workspace is None
        or workspace.resolution != WorkspaceResolution.RESOLVED
    ):
        return []

    target_statements = [
        statement
        for statement in inventory.statements
        if statement.result_identifier == result_identifier
        and statement.scope_kind
        in {StatementScopeKind.RESULT_STATEMENT, StatementScopeKind.RESULT_PROOF}
    ]
    if not target_statements:
        return []

    seed_terms = {
        term
        for statement in target_statements
        for term in statement.content_terms
    }
    if not seed_terms:
        return []

    lookup = ProjectPositionLookup(workspace)
    target_positions = [
        position
        for statement in target_statements
        for position in lookup.positions(statement.source.file, statement.source.start_offset)
    ]
    if not target_positions:
        return []

    selected: list[ReviewSourceContext] = []
    for statement in inventory.statements:
        if statement.scope_kind != StatementScopeKind.PROJECT:
            continue
        if not seed_terms.intersection(statement.content_terms):
            continue
        candidate_positions = lookup.positions(
            statement.source.file,
            statement.source.end_offset,
        )
        if not candidate_positions:
            continue
        # A path-level result may represent repeated project occurrences. Make a
        # prior statement reachable only when every target occurrence has a prior
        # occurrence of that exact source statement; disagreement fails closed.
        if not all(
            any(candidate < target for candidate in candidate_positions)
            for target in target_positions
        ):
            continue
        selected.append(
            ReviewSourceContext(text=statement.text, source=statement.source)
        )

    return sorted(
        selected,
        key=lambda context: project_source_sort_key(
            project,
            context.source,
            context.text,
        ),
    )


def _without_overlapping_prose_classification(
    project: ExtractedProject,
    context: SelectedSymbolContext,
    statements: list[ReviewSourceContext],
) -> SelectedSymbolContext:
    """Prefer exact generic statement source over overlapping prose-role guesses.

    The old declaration classifier remains available to other production consumers
    during this bounded tranche. It is deliberately removed from this review view
    only where the new source-mapped statement path independently selected the same
    source, so #198 can test review reachability without depending on phrase lists.
    """

    inventory = project.prose_declarations
    if inventory is None or not statements:
        return context
    classified = [candidate.source for candidate in inventory.candidates]

    def replaced(source: object) -> bool:
        return any(_source_overlap(source, prose) for prose in classified) and any(
            _source_overlap(source, statement.source) for statement in statements
        )

    return SelectedSymbolContext(
        hypotheses=[item for item in context.hypotheses if not replaced(item.source)],
        local_constraints=[
            item for item in context.local_constraints if not replaced(item.source)
        ],
        symbols=context.symbols,
        definitions=[item for item in context.definitions if not replaced(item.source)],
        candidates=context.candidates,
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
    statement_context = _statement_context(project, result_identifier)
    symbol_context = _without_overlapping_prose_classification(
        project,
        _result_symbol_context(project, result_identifier),
        statement_context,
    )
    uncertain_relation_ids = sorted(
        edge.identifier
        for edge in relations
        if edge.status in {InferenceStatus.AMBIGUOUS, InferenceStatus.UNRESOLVED}
    )
    dependencies = sorted(
        project.dependency_graph.direct_dependencies(result_identifier),
        key=lambda node: dependency_node_sort_key(project, node),
    )

    nearby_context = {
        (context.text, span_key(context.source)): context
        for context in [*_nearby_context(project, relations), *statement_context]
    }
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
        nearby_context=sorted(
            nearby_context.values(),
            key=lambda context: project_source_sort_key(
                project,
                context.source,
                context.text,
            ),
        ),
    )
    return ReviewContext(items=[item])
