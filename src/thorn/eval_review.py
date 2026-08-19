from __future__ import annotations

from thorn.dependencies import DependencyNode, ExtractedProject
from thorn.evidence import InferenceStatus
from thorn.frontend import SourceSpan
from thorn.semantic_review import (
    ReviewContext,
    ReviewSourceContext,
    ReviewTargetKind,
    SemanticReviewItem,
    _close_project_symbol_dependencies,
)
from thorn.support import Claim, SupportEdge
from thorn.symbols import (
    Constraint,
    Definition,
    ScopeKind,
    Symbol,
    SymbolIntroductionCandidate,
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


def _claim_key(claim: Claim) -> tuple[str, int, int, int, int, int, int, str]:
    return (*_span_key(claim.source), claim.identifier)


def _relation_key(edge: SupportEdge) -> tuple[str, int, int, int, int, int, int, str]:
    return (*_span_key(edge.source), edge.identifier)


def _symbol_key(symbol: Symbol) -> tuple[str, int, int, int, int, int, int, str]:
    return (*_span_key(symbol.source), symbol.identifier)


def _definition_key(
    definition: Definition,
) -> tuple[str, int, int, int, int, int, int, str]:
    return (*_span_key(definition.source), definition.identifier)


def _constraint_key(
    constraint: Constraint,
) -> tuple[str, int, int, int, int, int, int, str]:
    return (*_span_key(constraint.source), constraint.identifier)


def _candidate_key(
    candidate: SymbolIntroductionCandidate,
) -> tuple[str, int, int, int, int, int, int, str]:
    return (*_span_key(candidate.source), candidate.identifier)


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
        key=_relation_key,
    )


def _result_symbol_context(
    project: ExtractedProject,
    result_identifier: str,
    claims: list[Claim],
) -> tuple[
    list[Constraint],
    list[Constraint],
    list[Symbol],
    list[Definition],
    list[SymbolIntroductionCandidate],
]:
    table = project.symbol_table
    result = _result_node(project, result_identifier)

    def is_target_use(source: SourceSpan) -> bool:
        if (
            source.file == result.source.file
            and result.source.start_line <= source.start_line <= result.source.end_line
        ):
            return True
        return any(
            source.file == claim.source.file
            and claim.source.start_offset <= source.start_offset
            and source.end_offset <= claim.source.end_offset
            for claim in claims
        )

    # Keep result-owned symbols, then close selectively over actually resolved
    # symbol uses in the target statement/proof. This admits an outer/global
    # definition only when the target really uses that symbol; it is not a
    # whole-paper symbol-table dump.
    symbol_ids = {
        symbol.identifier
        for symbol in table.symbols
        if symbol.result_identifier == result_identifier
    }
    symbol_ids.update(
        use.resolved_symbol_identifier
        for use in table.uses
        if use.resolved_symbol_identifier is not None and is_target_use(use.source)
    )
    _close_project_symbol_dependencies(table, symbol_ids)

    symbols = sorted(
        (symbol for symbol in table.symbols if symbol.identifier in symbol_ids),
        key=_symbol_key,
    )
    definitions = sorted(
        (
            definition
            for definition in table.definitions
            if definition.symbol_identifier in symbol_ids
        ),
        key=_definition_key,
    )

    symbol_by_id = {symbol.identifier: symbol for symbol in symbols}
    hypotheses: list[Constraint] = []
    local_constraints: list[Constraint] = []
    for constraint in table.constraints:
        symbol = symbol_by_id.get(constraint.symbol_identifier)
        if symbol is None:
            continue
        scope_kind = table.scope(symbol.scope_identifier).kind
        if scope_kind in {ScopeKind.RESULT, ScopeKind.STATEMENT}:
            hypotheses.append(constraint)
        else:
            local_constraints.append(constraint)
    hypotheses.sort(key=_constraint_key)
    local_constraints.sort(key=_constraint_key)

    candidates = sorted(
        (
            candidate
            for candidate in table.candidates
            if candidate.result_identifier == result_identifier
        ),
        key=_candidate_key,
    )
    return hypotheses, local_constraints, symbols, definitions, candidates


def _nearby_context(relations: list[SupportEdge]) -> list[ReviewSourceContext]:
    contexts: dict[
        tuple[str, tuple[str, int, int, int, int, int, int]],
        ReviewSourceContext,
    ] = {}
    for relation in relations:
        for evidence in relation.evidence:
            text = evidence.context.strip()
            if not text:
                continue
            key = (text, _span_key(evidence.source))
            contexts[key] = ReviewSourceContext(text=text, source=evidence.source)
    return [contexts[key] for key in sorted(contexts)]


def build_result_review_context(
    project: ExtractedProject,
    result_identifier: str,
) -> ReviewContext:
    """Build one bounded, result-level IR item for a controlled context A/B run.

    Unlike ``build_review_context``, this evaluation seam does not decide whether
    semantic escalation is warranted. It always returns exactly one item for the
    selected result so explicit ``raw`` and ``ir`` runs perform comparable
    attack-only semantic work. The normal targeted selector remains the sole
    authority for deciding which uncertainty-bearing local items deserve review.

    The item contains only Thorn-owned IR. Provider adapters still receive a
    ``SemanticReviewRequest`` and never receive or traverse the project graph.
    """

    project.unit(result_identifier)
    claims = sorted(
        project.proof_support_graph.claims_for_result(result_identifier),
        key=_claim_key,
    )
    relations = _result_relations(project, claims)
    (
        hypotheses,
        local_constraints,
        symbols,
        definitions,
        candidates,
    ) = _result_symbol_context(
        project,
        result_identifier,
        claims,
    )
    trigger_ids = sorted(
        edge.identifier
        for edge in relations
        if edge.status in {InferenceStatus.AMBIGUOUS, InferenceStatus.UNRESOLVED}
    )
    dependencies = sorted(
        project.dependency_graph.direct_dependencies(result_identifier),
        key=lambda node: (
            node.source.file,
            node.source.start_line,
            node.source.end_line,
            node.identifier,
        ),
    )

    item = SemanticReviewItem(
        identifier=f"semantic-review-eval:{result_identifier}",
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=_result_node(project, result_identifier),
        claims=claims,
        trigger_relation_identifiers=trigger_ids,
        support_relations=relations,
        hypotheses=hypotheses,
        local_constraints=local_constraints,
        symbols=symbols,
        definitions=definitions,
        symbol_candidates=candidates,
        dependencies=dependencies,
        nearby_context=_nearby_context(relations),
    )
    return ReviewContext(items=[item])
