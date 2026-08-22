from __future__ import annotations

from thorn.frontend import ParsedProject, SourceSpan
from thorn.source_projection import LinguisticProjection, build_linguistic_projection
from thorn.symbols import Symbol, SymbolTable, SymbolUse, canonical_symbol_name
from thorn.workspace import (
    ProjectPositionLookup,
    ProjectWorkspaceFacts,
    WorkspaceResolution,
)


def _source_sort_key(
    lookup: ProjectPositionLookup | None,
    source: SourceSpan,
) -> tuple[tuple[int, ...], str, int, int]:
    if lookup is not None:
        try:
            return (
                lookup.sort_key(source.file, source.start_offset),
                source.file,
                source.start_offset,
                source.end_offset,
            )
        except KeyError:
            pass
    return ((10**12, source.start_offset), source.file, source.start_offset, source.end_offset)


def _span_eligible(
    projections: dict[str, LinguisticProjection],
    source: SourceSpan,
) -> bool:
    projection = projections.get(source.file)
    return projection is not None and projection.source_span_eligible(source)


def _source_eligible(
    projections: dict[str, LinguisticProjection],
    symbol: Symbol,
) -> bool:
    return _span_eligible(projections, symbol.introduction_source)


def _project_symbol_key(symbol: Symbol) -> tuple[str, int, int]:
    return (symbol.source.file, symbol.source.start_offset, symbol.source.end_offset)


def _disambiguate_project_symbol_identifiers(table: SymbolTable) -> None:
    """Make distinct physical project declarations distinct Symbol-IR identities."""

    groups: dict[str, list[Symbol]] = {}
    for symbol in table.symbols:
        if symbol.scope_identifier == "project":
            groups.setdefault(symbol.identifier, []).append(symbol)
    collisions = {
        identifier: symbols
        for identifier, symbols in groups.items()
        if len({_project_symbol_key(symbol) for symbol in symbols}) > 1
    }
    if not collisions:
        return

    replacements: dict[tuple[str, str], str] = {}
    rewritten: list[Symbol] = []
    for symbol in table.symbols:
        if symbol.identifier not in collisions:
            rewritten.append(symbol)
            continue
        new_identifier = (
            f"{symbol.identifier}:{symbol.source.file}:"
            f"{symbol.source.start_offset}:{symbol.source.end_offset}"
        )
        replacements[(symbol.identifier, symbol.source.file)] = new_identifier
        rewritten.append(symbol.model_copy(update={"identifier": new_identifier}))
    table.symbols = rewritten

    for index, definition in enumerate(table.definitions):
        replacement = replacements.get((definition.symbol_identifier, definition.source.file))
        if replacement is None:
            continue
        table.definitions[index] = definition.model_copy(
            update={
                "identifier": definition.identifier.replace(
                    definition.symbol_identifier, replacement, 1
                ),
                "symbol_identifier": replacement,
            }
        )
    for index, constraint in enumerate(table.constraints):
        replacement = replacements.get((constraint.symbol_identifier, constraint.source.file))
        if replacement is None:
            continue
        table.constraints[index] = constraint.model_copy(
            update={
                "identifier": constraint.identifier.replace(
                    constraint.symbol_identifier, replacement, 1
                ),
                "symbol_identifier": replacement,
            }
        )
    table.uses = [
        use.model_copy(update={"resolved_symbol_identifier": None})
        if use.resolved_symbol_identifier in collisions
        else use
        for use in table.uses
    ]


def enforce_structured_authority_boundary(
    project: ParsedProject,
    table: SymbolTable,
    *,
    workspace: ProjectWorkspaceFacts | None,
) -> None:
    """Apply normalized source/workspace facts to structured Symbol-IR authority.

    ``symbol_extract`` and ``project_context`` recognize Thorn-owned mathematical
    declaration syntax. This function is the authority boundary for those structured
    candidates: parser-owned source roles decide eligibility, workspace facts decide
    project-order availability, and every retained use is resolved again through the
    occurrence-aware resolver. No TeX or include structure is rediscovered here.
    """

    _disambiguate_project_symbol_identifiers(table)

    projections = {
        file.path: build_linguistic_projection(file)
        for file in project.files
    }
    project_authority_available = (
        workspace is not None
        and workspace.resolution == WorkspaceResolution.RESOLVED
        and all(projection.complete for projection in projections.values())
    )

    retained_symbols: list[Symbol] = []
    removed_ids: set[str] = set()
    for symbol in table.symbols:
        eligible = _source_eligible(projections, symbol)
        if symbol.scope_identifier == "project":
            eligible = eligible and project_authority_available
        if eligible:
            retained_symbols.append(symbol)
        else:
            removed_ids.add(symbol.identifier)
    table.symbols = retained_symbols

    if removed_ids:
        table.definitions = [
            definition
            for definition in table.definitions
            if definition.symbol_identifier not in removed_ids
        ]
        table.constraints = [
            constraint
            for constraint in table.constraints
            if constraint.symbol_identifier not in removed_ids
        ]

    known_names = {
        canonical_symbol_name(symbol.name)
        for symbol in table.symbols
    }
    retained_uses = [
        use
        for use in table.uses
        if canonical_symbol_name(use.name) in known_names
        and _span_eligible(projections, use.source)
    ]
    resolved_uses: list[SymbolUse] = []
    for use in retained_uses:
        resolved = table.resolve(
            use.name,
            use.scope_identifier,
            use.source,
            workspace=workspace,
        )
        resolved_uses.append(
            use.model_copy(
                update={
                    "resolved_symbol_identifier": (
                        resolved.identifier if resolved is not None else None
                    )
                }
            )
        )
    table.uses = resolved_uses

    lookup = (
        ProjectPositionLookup(workspace)
        if workspace is not None and workspace.resolution == WorkspaceResolution.RESOLVED
        else None
    )
    table.symbols.sort(key=lambda item: _source_sort_key(lookup, item.source))
    table.definitions.sort(key=lambda item: _source_sort_key(lookup, item.source))
    table.constraints.sort(key=lambda item: _source_sort_key(lookup, item.source))
    table.uses.sort(
        key=lambda item: (*_source_sort_key(lookup, item.source), item.name)
    )
