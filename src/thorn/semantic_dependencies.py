from __future__ import annotations

from collections.abc import Iterable

from thorn.dependencies import ExtractedProject
from thorn.frontend import SourceSpan
from thorn.symbols import ScopeKind, Symbol
from thorn.workspace import ProjectPositionLookup


def _span_contains(outer: SourceSpan, inner: SourceSpan) -> bool:
    return (
        outer.file == inner.file
        and outer.start_offset <= inner.start_offset
        and inner.end_offset <= outer.end_offset
    )


def semantic_symbol_sort_key(
    project: ExtractedProject,
    symbol: Symbol,
) -> tuple[int, ...]:
    """Order a canonical symbol by normalized workspace position when available."""

    workspace = project.workspace
    if workspace is not None:
        try:
            return (0, *ProjectPositionLookup(workspace).sort_key(
                symbol.source.file,
                symbol.source.start_offset,
            ))
        except KeyError:
            pass

    table_order = {
        item.identifier: index for index, item in enumerate(project.symbol_table.symbols)
    }
    return (1, table_order[symbol.identifier])


def _ordered_project_symbol_ids(
    project: ExtractedProject,
    identifiers: Iterable[str],
) -> list[str]:
    table = project.symbol_table
    unique = set(identifiers)
    return [
        symbol.identifier
        for symbol in sorted(
            (symbol for symbol in table.symbols if symbol.identifier in unique),
            key=lambda symbol: (*semantic_symbol_sort_key(project, symbol), symbol.identifier),
        )
    ]


def result_project_symbol_dependency_ids(
    project: ExtractedProject,
    result_identifier: str,
) -> list[str]:
    """Return canonical project-symbol targets used by one result.

    Result-to-declaration edges are read from already-resolved ``SymbolUse``
    identities and result-owned scopes. Source overlap is provenance, not edge
    identity, so callers do not need to reconstruct these dependencies from text.
    """

    table = project.symbol_table
    result_scope_ids = {
        scope.identifier
        for scope in table.scopes
        if scope.result_identifier == result_identifier
    }
    targets: set[str] = set()
    for use in table.uses:
        target_identifier = use.resolved_symbol_identifier
        if target_identifier is None or use.scope_identifier not in result_scope_ids:
            continue
        target = table.symbol(target_identifier)
        if table.scope(target.scope_identifier).kind != ScopeKind.PROJECT:
            continue
        targets.add(target_identifier)
    return _ordered_project_symbol_ids(project, targets)


def project_symbol_dependency_ids(
    project: ExtractedProject,
    owner_identifier: str,
) -> list[str]:
    """Return canonical project declaration dependencies of one project symbol."""

    table = project.symbol_table
    owner = table.symbol(owner_identifier)
    if table.scope(owner.scope_identifier).kind != ScopeKind.PROJECT:
        return []

    targets: set[str] = set()
    for use in table.uses:
        target_identifier = use.resolved_symbol_identifier
        if target_identifier is None or use.scope_identifier != "project":
            continue
        if not _span_contains(owner.introduction_source, use.source):
            continue
        target = table.symbol(target_identifier)
        if table.scope(target.scope_identifier).kind != ScopeKind.PROJECT:
            continue
        targets.add(target_identifier)
    return _ordered_project_symbol_ids(project, targets)


def close_project_symbol_dependencies(
    project: ExtractedProject,
    selected_ids: Iterable[str],
) -> set[str]:
    """Transitively close canonical project-symbol dependencies for review.

    This is selection over canonical ``SymbolTable`` state, not a second semantic
    graph. ``SymbolUse.resolved_symbol_identifier`` remains the edge authority.
    """

    closed = set(selected_ids)
    pending = list(closed)
    while pending:
        owner_identifier = pending.pop()
        for target_identifier in project_symbol_dependency_ids(project, owner_identifier):
            if target_identifier in closed:
                continue
            closed.add(target_identifier)
            pending.append(target_identifier)
    return closed
