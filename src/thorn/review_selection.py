from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from thorn.dependencies import ExtractedProject
from thorn.frontend import SourceSpan
from thorn.semantic_dependencies import (
    close_project_symbol_dependencies,
    semantic_symbol_sort_key,
)
from thorn.symbols import (
    Constraint,
    Definition,
    ScopeKind,
    Symbol,
    SymbolIntroductionCandidate,
)


@dataclass(frozen=True)
class SelectedSymbolContext:
    """Canonical Symbol-IR projection shared by result and diagnostic review views."""

    hypotheses: list[Constraint]
    local_constraints: list[Constraint]
    symbols: list[Symbol]
    definitions: list[Definition]
    candidates: list[SymbolIntroductionCandidate]


def span_key(span: SourceSpan) -> tuple[str, int, int, int, int, int, int]:
    return (
        span.file,
        span.start_offset,
        span.end_offset,
        span.start_line,
        span.start_column,
        span.end_line,
        span.end_column,
    )


def select_symbol_context(
    project: ExtractedProject,
    symbol_identifiers: Iterable[str],
    candidates: Iterable[SymbolIntroductionCandidate],
) -> SelectedSymbolContext:
    """Materialize one bounded review projection from canonical Symbol IR.

    Callers own only the breadth policy that seeds ``symbol_identifiers`` and
    ``candidates``. Transitive authoritative declaration closure, ordering, and
    constraint classification are shared so result-level and targeted review do
    not grow separate semantic-selection machinery.
    """

    table = project.symbol_table
    selected_ids = close_project_symbol_dependencies(project, symbol_identifiers)

    symbols = sorted(
        (symbol for symbol in table.symbols if symbol.identifier in selected_ids),
        key=lambda symbol: semantic_symbol_sort_key(project, symbol),
    )
    definitions = sorted(
        (
            definition
            for definition in table.definitions
            if definition.symbol_identifier in selected_ids
        ),
        key=lambda definition: (*span_key(definition.source), definition.identifier),
    )

    symbol_by_id = {symbol.identifier: symbol for symbol in symbols}
    hypotheses: list[Constraint] = []
    local_constraints: list[Constraint] = []
    for constraint in table.constraints:
        selected_symbol = symbol_by_id.get(constraint.symbol_identifier)
        if selected_symbol is None:
            continue
        scope_kind = table.scope(selected_symbol.scope_identifier).kind
        if scope_kind in {ScopeKind.RESULT, ScopeKind.STATEMENT}:
            hypotheses.append(constraint)
        else:
            local_constraints.append(constraint)
    hypotheses.sort(key=lambda item: (*span_key(item.source), item.identifier))
    local_constraints.sort(key=lambda item: (*span_key(item.source), item.identifier))

    selected_candidates = sorted(
        candidates,
        key=lambda candidate: (*span_key(candidate.source), candidate.identifier),
    )
    return SelectedSymbolContext(
        hypotheses=hypotheses,
        local_constraints=local_constraints,
        symbols=symbols,
        definitions=definitions,
        candidates=selected_candidates,
    )
