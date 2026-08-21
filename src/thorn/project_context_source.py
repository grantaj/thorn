from __future__ import annotations

import re

from thorn.frontend import ParsedProject, SourceSpan
from thorn.source_projection import build_linguistic_projection
from thorn.symbols import Constraint, ScopeKind, SymbolRole, SymbolTable

_PROJECT_PROSE_CUE_RE = re.compile(
    r"(?is)^\s*(?:let|define|set|for(?:\s+(?:each|every|all))?)\b"
)


def _same_span(left: SourceSpan, right: SourceSpan) -> bool:
    return (
        left.file == right.file
        and left.start_offset == right.start_offset
        and left.end_offset == right.end_offset
    )


def preserve_project_authoritative_source(
    project: ParsedProject,
    table: SymbolTable,
) -> None:
    """Expand recovered project declarations to their exact authoritative sentence.

    Deterministic symbol recovery often needs only the mathematical token and its
    cue. Review rescue needs the complete local statement that gives that token
    authority, including ambient-domain wording and trailing local conventions.
    Sentence provenance comes from the same reversible frontend-derived projection
    used by semantic extraction; this layer does not reconstruct TeX boundaries.
    """

    files = {file.path: file for file in project.files}
    projections = {
        file.path: build_linguistic_projection(file)
        for file in project.files
    }
    expanded_by_symbol: dict[str, tuple[SourceSpan, SourceSpan]] = {}

    for index, symbol in enumerate(table.symbols):
        if table.scope(symbol.scope_identifier).kind != ScopeKind.PROJECT:
            continue
        if not _PROJECT_PROSE_CUE_RE.match(symbol.raw_introduction):
            continue
        file = files.get(symbol.introduction_source.file)
        projection = projections.get(symbol.introduction_source.file)
        if file is None or projection is None or not projection.complete:
            continue
        expanded = projection.sentence_span(symbol.introduction_source.start_offset)
        if _same_span(expanded, symbol.introduction_source):
            continue
        expanded_by_symbol[symbol.identifier] = (symbol.introduction_source, expanded)
        table.symbols[index] = symbol.model_copy(
            update={
                "introduction_source": expanded,
                "raw_introduction": expanded.text(file.raw),
            }
        )

    for index, definition in enumerate(table.definitions):
        pair = expanded_by_symbol.get(definition.symbol_identifier)
        if pair is None:
            continue
        old, expanded = pair
        if not _same_span(definition.source, old):
            continue
        file = files[expanded.file]
        table.definitions[index] = definition.model_copy(
            update={"source": expanded, "raw": expanded.text(file.raw)}
        )

    for index, constraint in enumerate(table.constraints):
        pair = expanded_by_symbol.get(constraint.symbol_identifier)
        if pair is None:
            continue
        old, expanded = pair
        if not _same_span(constraint.source, old):
            continue
        file = files[expanded.file]
        table.constraints[index] = constraint.model_copy(
            update={"source": expanded, "raw": expanded.text(file.raw)}
        )

    # A map declaration is authoritative mathematical context even when it is
    # not a definition. Reuse the existing Constraint path so its domain and
    # codomain are represented in canonical Proof IR and keep the exact sentence
    # available as source when lowering is incomplete.
    constrained = {constraint.symbol_identifier for constraint in table.constraints}
    for symbol in table.symbols:
        if table.scope(symbol.scope_identifier).kind != ScopeKind.PROJECT:
            continue
        if symbol.role != SymbolRole.MAP or symbol.identifier in constrained:
            continue
        if symbol.domain_latex is None or symbol.codomain_latex is None:
            continue
        table.constraints.append(
            Constraint(
                identifier=f"constraint:{symbol.identifier}:mapping",
                symbol_identifier=symbol.identifier,
                relation=":",
                expression_latex=(
                    f"{symbol.domain_latex}\\to {symbol.codomain_latex}"
                ),
                source=symbol.introduction_source,
                raw=symbol.raw_introduction,
            )
        )

    table.constraints.sort(key=lambda item: (item.source.file, item.source.start_offset))
