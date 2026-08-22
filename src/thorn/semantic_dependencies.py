from __future__ import annotations

from collections.abc import Iterable

from thorn.dependencies import DependencyNode, ExtractedProject
from thorn.frontend import SourceSpan
from thorn.symbols import ScopeKind, Symbol
from thorn.workspace import ProjectPositionLookup

ProjectSourceSortKey = tuple[
    int,
    tuple[int, ...],
    str,
    int,
    int,
    int,
    int,
    int,
    int,
    str,
]
SemanticSymbolSortKey = ProjectSourceSortKey
DependencyNodeSortKey = tuple[int, int, str, int, int, str]


def _span_contains(outer: SourceSpan, inner: SourceSpan) -> bool:
    return (
        outer.file == inner.file
        and outer.start_offset <= inner.start_offset
        and inner.end_offset <= outer.end_offset
    )


def project_source_sort_key(
    project: ExtractedProject,
    span: SourceSpan,
    stable_identifier: str = "",
) -> ProjectSourceSortKey:
    """Order source-backed IR by expanded workspace position when available.

    The exact physical source provenance remains a deterministic tie-break and is
    the fallback for synthetic/no-workspace projects. Source-backed IR does not
    invent occurrence identity: repeated physical files retain the established
    earliest-occurrence collapse used by ``ProjectPositionLookup.sort_key``.
    """

    workspace = project.workspace
    if workspace is not None:
        try:
            return (
                0,
                ProjectPositionLookup(workspace).sort_key(
                    span.file,
                    span.start_offset,
                ),
                span.file,
                span.start_offset,
                span.end_offset,
                span.start_line,
                span.start_column,
                span.end_line,
                span.end_column,
                stable_identifier,
            )
        except KeyError:
            pass

    return (
        1,
        (),
        span.file,
        span.start_offset,
        span.end_offset,
        span.start_line,
        span.start_column,
        span.end_line,
        span.end_column,
        stable_identifier,
    )


def semantic_symbol_sort_key(
    project: ExtractedProject,
    symbol: Symbol,
) -> SemanticSymbolSortKey:
    """Order a canonical symbol by workspace position, then stable provenance."""

    return project_source_sort_key(project, symbol.source, symbol.identifier)


def dependency_node_sort_key(
    project: ExtractedProject,
    node: DependencyNode,
) -> DependencyNodeSortKey:
    """Order result/dependency nodes by canonical extracted project order."""

    unit_order = {unit.identifier: index for index, unit in enumerate(project.units)}
    index = unit_order.get(node.identifier)
    if index is not None:
        return (0, index, "", 0, 0, node.identifier)
    return (
        1,
        0,
        node.source.file,
        node.source.start_line,
        node.source.end_line,
        node.identifier,
    )


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
            key=lambda symbol: semantic_symbol_sort_key(project, symbol),
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
