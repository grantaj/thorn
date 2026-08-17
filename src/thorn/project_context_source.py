from __future__ import annotations

import re

from thorn.frontend import FrontendFile, ParsedProject, SourceSpan
from thorn.symbols import Constraint, ScopeKind, SymbolRole, SymbolTable

_PROJECT_PROSE_CUE_RE = re.compile(
    r"(?is)^\s*(?:let|define|set|for(?:\s+(?:each|every|all))?)\b"
)
_START_BOUNDARY_RE = re.compile(
    r"(?:\n\s*\n|[.!?](?=\s|$)|\\begin\{document\}\s*|\\end\{[^{}]+\}\s*)"
)
_END_BOUNDARY_RE = re.compile(r"(?:[.!?](?=\s|$)|\n\s*\n|(?=\\begin\{))")


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _span(file: FrontendFile, start: int, end: int) -> SourceSpan:
    start_line, start_column = _line_column(file.raw, start)
    end_line, end_column = _line_column(file.raw, end)
    return SourceSpan(
        file=file.path,
        start_offset=start,
        end_offset=end,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _sentence_start(file: FrontendFile, offset: int) -> int:
    window_start = max(0, offset - 256)
    prefix = file.raw[window_start:offset]
    matches = list(_START_BOUNDARY_RE.finditer(prefix))
    start = window_start + (matches[-1].end() if matches else 0)
    while start < offset and file.raw[start].isspace():
        start += 1
    return start


def _sentence_end(file: FrontendFile, offset: int) -> int:
    window_end = min(len(file.raw), offset + 256)
    suffix = file.raw[offset:window_end]
    match = _END_BOUNDARY_RE.search(suffix)
    if match is None:
        return offset
    end = offset + match.end()
    # A blank-line/environment boundary marks the end of the prose block rather
    # than source belonging to the declaration. Trim boundary whitespace while
    # retaining ordinary sentence punctuation when present.
    while end > offset and file.raw[end - 1].isspace():
        end -= 1
    return end


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
    This function changes provenance only: symbol identity and recovered semantic
    content remain untouched.
    """

    files = {file.path: file for file in project.files}
    expanded_by_symbol: dict[str, tuple[SourceSpan, SourceSpan]] = {}

    for index, symbol in enumerate(table.symbols):
        if table.scope(symbol.scope_identifier).kind != ScopeKind.PROJECT:
            continue
        if not _PROJECT_PROSE_CUE_RE.match(symbol.raw_introduction):
            continue
        file = files.get(symbol.introduction_source.file)
        if file is None:
            continue
        expanded = _span(
            file,
            _sentence_start(file, symbol.introduction_source.start_offset),
            _sentence_end(file, symbol.introduction_source.end_offset),
        )
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
