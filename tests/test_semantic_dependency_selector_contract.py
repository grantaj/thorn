"""Contract observations for Thorn's two current review-context selectors."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import pytest
from test_semantic_dependency_contract import (
    PROSE_AUTHORITY_CONFIGURATIONS,
    ContractConfiguration,
    _write_project,
)
from test_semantic_review import make_project

from thorn.eval_review import build_result_review_context
from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import SourceSpan
from thorn.semantic_review import SemanticReviewItem, build_review_context
from thorn.support import SupportEdge, SupportKind


class _Identified(Protocol):
    identifier: str


def _canonical_by_identifier(items: Iterable[_Identified]) -> dict[str, _Identified]:
    return {item.identifier: item for item in items}


def _source_key(span: SourceSpan) -> tuple[str, int, int, int, int, int, int]:
    return (
        span.file,
        span.start_offset,
        span.end_offset,
        span.start_line,
        span.start_column,
        span.end_line,
        span.end_column,
    )


def _assert_canonical_selector_projection(project: object, item: SemanticReviewItem) -> None:
    """Assert selector output is a bounded projection of canonical Thorn-owned state."""

    graph = project.dependency_graph
    support = project.proof_support_graph
    table = project.symbol_table

    # Result and dependency identity come from the canonical dependency graph. A
    # selector may prune that graph, but it may not manufacture a shadow target.
    assert item.result == graph.node(item.result.identifier)
    canonical_direct = {
        dependency.identifier: dependency
        for dependency in graph.direct_dependencies(item.result.identifier)
    }
    canonical_closure = set(graph.transitive_dependency_ids(item.result.identifier))
    for dependency in item.dependencies:
        assert dependency == canonical_direct[dependency.identifier]
        assert dependency.identifier in canonical_closure

    # Support uncertainty and its exact provenance survive selection unchanged.
    canonical_relations = _canonical_by_identifier(support.edges)
    for relation in item.support_relations:
        assert relation == canonical_relations[relation.identifier]
    for trigger_identifier in item.trigger_relation_identifiers:
        trigger = canonical_relations[trigger_identifier]
        assert trigger.status in {InferenceStatus.AMBIGUOUS, InferenceStatus.UNRESOLVED}

    # Selector-visible mathematical context must correspond to canonical Symbol
    # IR objects. This comparison intentionally derives identifiers from the item
    # rather than freezing any private identifier spelling.
    canonical_symbols = _canonical_by_identifier(table.symbols)
    canonical_definitions = _canonical_by_identifier(table.definitions)
    canonical_constraints = _canonical_by_identifier(table.constraints)
    canonical_candidates = _canonical_by_identifier(table.candidates)
    for symbol in item.symbols:
        assert symbol == canonical_symbols[symbol.identifier]
    for definition in item.definitions:
        assert definition == canonical_definitions[definition.identifier]
    for constraint in [*item.hypotheses, *item.local_constraints]:
        assert constraint == canonical_constraints[constraint.identifier]
    for candidate in item.symbol_candidates:
        assert candidate == canonical_candidates[candidate.identifier]
        assert candidate.status != InferenceStatus.CONFIDENT

    # Nearby prose is admitted only through exact evidence already attached to a
    # selected canonical support relation. There is no whole-paper fallback here.
    canonical_context = {
        (evidence.context.strip(), _source_key(evidence.source))
        for relation in item.support_relations
        for evidence in relation.evidence
        if evidence.context.strip()
    }
    assert {
        (context.text, _source_key(context.source)) for context in item.nearby_context
    } <= canonical_context


def _item_with_dependency_statement(
    items: list[SemanticReviewItem],
    statement: str,
) -> SemanticReviewItem:
    return next(
        item
        for item in items
        if any(dependency.statement == statement for dependency in item.dependencies)
    )


def _item_with_trigger(
    items: list[SemanticReviewItem],
    trigger_identifier: str,
) -> SemanticReviewItem:
    return next(
        item for item in items if trigger_identifier in item.trigger_relation_identifiers
    )


def _selected_declarations(item: SemanticReviewItem) -> list[object]:
    return [*item.definitions, *item.hypotheses, *item.local_constraints]


def _assert_exact_canonical_declaration(
    project: object,
    item: SemanticReviewItem,
    source_text: str,
) -> object:
    canonical = [
        declaration
        for declaration in [
            *project.symbol_table.definitions,
            *project.symbol_table.constraints,
        ]
        if declaration.raw == source_text
    ]
    assert len(canonical) == 1
    declaration = canonical[0]
    assert declaration in _selected_declarations(item)
    raw_file = Path(declaration.source.file).read_text(encoding="utf-8")
    assert declaration.source.text(raw_file) == source_text
    return declaration


def test_current_selectors_project_canonical_authority_and_uncertainty() -> None:
    project = make_project()
    result_item = build_result_review_context(project, project.units[0].identifier).items[0]
    targeted_items = build_review_context(project).items
    targeted_item = _item_with_dependency_statement(
        targeted_items,
        "The needed local estimate is valid.",
    )

    for item in (result_item, targeted_item):
        _assert_canonical_selector_projection(project, item)

        # Structured result dependency and local semantic context compose inside
        # the same Thorn-owned item; neither selector gets a private authority graph.
        assert any(
            dependency.statement == "The needed local estimate is valid."
            for dependency in item.dependencies
        )
        assert any(definition.raw == "Define $f(x)=x$." for definition in item.definitions)
        assert any(constraint.raw == "$x>0$" for constraint in item.hypotheses)

        # Ambiguous candidate evidence remains candidate evidence after projection.
        candidate = next(candidate for candidate in item.symbol_candidates if candidate.name == "z")
        assert candidate.status == InferenceStatus.AMBIGUOUS
        assert all(symbol.name != candidate.name for symbol in item.symbols)


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_both_selectors_preserve_transitive_project_semantic_closure(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    convention = r"Throughout, the base field is $K=\mathbb R$."
    definition = "A matrix is called regular when its determinant is nonzero over the base field."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{convention}
{definition}

\begin{{lemma}}\label{{lem:criterion}}
A matrix with nonzero determinant is invertible.
\end{{lemma}}
\begin{{proof}}Use the adjugate formula.\end{{proof}}

\begin{{lemma}}\label{{lem:aside}}
The identity matrix is invertible.
\end{{lemma}}
\begin{{proof}}Its inverse is itself.\end{{proof}}

\begin{{theorem}}\label{{thm:main}}
Every regular matrix is invertible; compare Lemma~\ref{{lem:aside}}.
\end{{theorem}}
\begin{{proof}}
Apply Lemma~\ref{{lem:criterion}}.
\end{{proof}}
""",
    )
    project = run.project

    # Use a real extracted project-scope declaration chain, but inject only the
    # uncertainty trigger needed to exercise targeted policy. This characterizes
    # selector behavior without extending prose recognition or choosing a policy.
    claims = project.proof_support_graph.claims_for_result("thm:main")
    assert claims
    trigger_claim = claims[0]
    trigger_identifier = "selector-contract:criterion-support"
    project.proof_support_graph.edges.append(
        SupportEdge(
            identifier=trigger_identifier,
            target_claim_identifier=trigger_claim.identifier,
            kind=SupportKind.RESULT_REFERENCE,
            source=trigger_claim.source,
            raw_justification=r"Lemma~\ref{lem:criterion}",
            target_label="lem:criterion",
            status=InferenceStatus.UNRESOLVED,
            confidence=None,
            evidence=[
                StructuralEvidence(
                    reason="contract-only uncertain support role",
                    source=trigger_claim.source,
                    context=trigger_claim.raw,
                    frontend="selector-contract-fixture",
                )
            ],
        )
    )

    result_item = build_result_review_context(project, "thm:main").items[0]
    targeted_item = _item_with_trigger(build_review_context(project).items, trigger_identifier)
    criterion = project.dependency_graph.node("lem:criterion")
    aside = project.dependency_graph.node("lem:aside")

    regular_declaration = next(
        declaration
        for declaration in [
            *project.symbol_table.definitions,
            *project.symbol_table.constraints,
        ]
        if declaration.raw == definition
    )
    base_field_declaration = next(
        declaration
        for declaration in [
            *project.symbol_table.definitions,
            *project.symbol_table.constraints,
        ]
        if declaration.raw == convention
    )
    regular_symbol = project.symbol_table.symbol(regular_declaration.symbol_identifier)
    assert any(
        use.scope_identifier == "project"
        and use.resolved_symbol_identifier == base_field_declaration.symbol_identifier
        and use.source.file == regular_symbol.introduction_source.file
        and regular_symbol.introduction_source.start_offset <= use.source.start_offset
        and use.source.end_offset <= regular_symbol.introduction_source.end_offset
        for use in project.symbol_table.uses
    )

    for item in (result_item, targeted_item):
        _assert_canonical_selector_projection(project, item)
        assert criterion in item.dependencies
        _assert_exact_canonical_declaration(project, item, definition)
        _assert_exact_canonical_declaration(project, item, convention)

    # The shared mathematical closure is canonical, while dependency breadth is
    # still selector policy: result-wide selection keeps both direct references;
    # the targeted item keeps only the dependency implicated by its trigger.
    assert aside in result_item.dependencies
    assert aside not in targeted_item.dependencies
    assert trigger_identifier in targeted_item.trigger_relation_identifiers


def test_selector_policy_differences_remain_observations_not_shared_authority() -> None:
    project = make_project()
    result_item = build_result_review_context(project, project.units[0].identifier).items[0]
    targeted_items = build_review_context(project).items
    targeted_item = _item_with_dependency_statement(
        targeted_items,
        "The needed local estimate is valid.",
    )

    # Result-level selection is result-wide and includes deterministic context and
    # all direct structured dependencies for the selected result.
    result_claims = {claim.raw for claim in result_item.claims}
    assert "A separate argument begins." in result_claims
    assert "Its separate conclusion follows." in result_claims
    assert {dependency.statement for dependency in result_item.dependencies} == {
        "The needed local estimate is valid.",
        "An unrelated fact.",
    }
    assert any(definition.raw == "Set $y=2$." for definition in result_item.definitions)

    # Targeted selection is trigger-relative. It prunes the local item to the
    # uncertainty-bearing region and the structured dependency implicated there.
    targeted_claims = {claim.raw for claim in targeted_item.claims}
    assert "A separate argument begins." not in targeted_claims
    assert "Its separate conclusion follows." not in targeted_claims
    assert {dependency.statement for dependency in targeted_item.dependencies} == {
        "The needed local estimate is valid."
    }
    assert all(definition.raw != "Set $y=2$." for definition in targeted_item.definitions)

    # Lack of an uncertainty trigger is a policy difference: targeted selection
    # emits nothing, while result-level selection remains available to its callers.
    confident_project = make_project(include_uncertain=False)
    assert build_review_context(confident_project).items == []
    confident_result = build_result_review_context(
        confident_project,
        confident_project.units[0].identifier,
    )
    assert len(confident_result.items) == 1
    assert confident_result.items[0].trigger_relation_identifiers == []
