from __future__ import annotations

import re
from dataclasses import dataclass

from thorn.frontend import FrontendFile, FrontendMath, ParsedProject, SourceSpan
from thorn.symbol_extract import _span
from thorn.symbols import (
    Constraint,
    Definition,
    IntroductionKind,
    ResultRegion,
    ScopeKind,
    Symbol,
    SymbolRole,
    SymbolTable,
    SymbolUse,
)

# This module recognizes declaration *grammar*, never mathematical vocabulary.
# A candidate becomes review context only when a theorem statement or proof has
# a concrete lexical use of the declared term. Proximity alone is not an edge.
_STYLE_TERM = (
    r"(?:\\[A-Za-z]+\{[^{}]+\}|"
    r"[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3})"
)

_CALLED_RE = re.compile(
    rf"\b(?:is|are|will\s+be|shall\s+be)\s+called\s+"
    rf"(?P<term>{_STYLE_TERM})\s+"
    r"(?:when|if|whenever|provided\s+that)\b",
    re.IGNORECASE,
)
_SAID_TO_BE_RE = re.compile(
    rf"\b(?:is|are)\s+said\s+to\s+be\s+(?P<term>{_STYLE_TERM})\s+"
    r"(?:when|if|whenever|provided\s+that)\b",
    re.IGNORECASE,
)
_WE_SAY_RE = re.compile(
    rf"\bwe\s+say\s+that\b[^.!?\n]{{1,160}}?\b(?:is|are)\s+"
    rf"(?P<term>{_STYLE_TERM})\s+"
    r"(?:when|if|whenever|provided\s+that)\b",
    re.IGNORECASE,
)
_BY_MEAN_RE = re.compile(
    rf"\bby\s+(?:an?\s+)?(?P<term>{_STYLE_TERM})\s+we\s+mean\b",
    re.IGNORECASE,
)
_AMBIENT_RE = re.compile(
    r"(?:^|(?<=[.!?])\s+)"
    r"(?:throughout|in\s+what\s+follows|henceforth|from\s+now\s+on|"
    r"unless\s+otherwise\s+stated|unless\s+specified\s+otherwise)\s*,?\s*"
    r"(?:(?:the|all|every|each)\s+)?"
    r"(?P<term>[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,5}?)\s+"
    r"(?:is|are|means?|denotes?|refers\s+to)\b",
    re.IGNORECASE | re.MULTILINE,
)
_STYLE_WRAPPER_RE = re.compile(r"\\[A-Za-z]+\{(?P<inner>[^{}]+)\}\Z")
_DOCUMENT_BEGIN = r"\begin{document}"


@dataclass(frozen=True)
class _Declaration:
    kind: str
    term: str
    term_start: int
    term_end: int
    source_start: int
    source_end: int


def _math_containing(file: FrontendFile, offset: int) -> FrontendMath | None:
    for math in file.math:
        if math.span.start_offset <= offset < math.span.end_offset:
            return math
    return None


def _math_ends_sentence(raw: str) -> bool:
    return (
        re.search(r"[.!?]\s*(?:\\\]|\\\)|\$\$|\$)\s*\Z", raw, re.DOTALL)
        is not None
    )


def _document_body_floor(raw: str, cue_offset: int) -> int:
    start = raw.rfind(_DOCUMENT_BEGIN, 0, cue_offset)
    return start + len(_DOCUMENT_BEGIN) if start >= 0 else 0


def _sentence_bounds(file: FrontendFile, cue_offset: int) -> tuple[int, int]:
    raw = file.raw
    body_floor = _document_body_floor(raw, cue_offset)
    paragraph_marker = raw.rfind("\n\n", body_floor, cue_offset)
    paragraph_start = paragraph_marker + 2 if paragraph_marker >= body_floor else body_floor
    paragraph_end = raw.find("\n\n", cue_offset)
    if paragraph_end < 0:
        paragraph_end = len(raw)

    start = cue_offset
    cursor = cue_offset - 1
    while cursor >= paragraph_start:
        math = _math_containing(file, cursor)
        if math is not None:
            if _math_ends_sentence(math.raw):
                start = math.span.end_offset
                break
            cursor = math.span.start_offset - 1
            continue
        if raw[cursor] in ".!?":
            start = cursor + 1
            break
        cursor -= 1
    else:
        start = paragraph_start
    while start < cue_offset and raw[start].isspace():
        start += 1

    cursor = cue_offset
    end = paragraph_end
    while cursor < paragraph_end:
        math = _math_containing(file, cursor)
        if math is not None:
            cursor = math.span.end_offset
            if _math_ends_sentence(math.raw):
                end = cursor
                break
            continue
        if raw[cursor] in ".!?":
            end = cursor + 1
            break
        cursor += 1
    while end > start and raw[end - 1].isspace():
        end -= 1
    return start, end


def _unwrap_term(raw_term: str, absolute_start: int) -> tuple[str, int, int]:
    wrapper = _STYLE_WRAPPER_RE.fullmatch(raw_term.strip())
    if wrapper is None:
        leading = len(raw_term) - len(raw_term.lstrip())
        term = raw_term.strip()
        start = absolute_start + leading
        return term, start, start + len(term)
    inner = wrapper.group("inner").strip()
    inner_start = raw_term.find(wrapper.group("inner")) + (
        len(wrapper.group("inner")) - len(wrapper.group("inner").lstrip())
    )
    start = absolute_start + inner_start
    return inner, start, start + len(inner)


def _overlaps_result(start: int, end: int, regions: list[ResultRegion]) -> bool:
    for region in regions:
        spans = [region.statement_span]
        if region.proof_span is not None:
            spans.append(region.proof_span)
        for span in spans:
            if start < span.end_offset and span.start_offset < end:
                return True
    return False


def _declarations(file: FrontendFile, regions: list[ResultRegion]) -> list[_Declaration]:
    candidates: list[_Declaration] = []
    patterns = (
        ("definition", _CALLED_RE),
        ("definition", _SAID_TO_BE_RE),
        ("definition", _WE_SAY_RE),
        ("definition", _BY_MEAN_RE),
        ("ambient", _AMBIENT_RE),
    )
    for kind, pattern in patterns:
        for match in pattern.finditer(file.raw):
            source_start, source_end = _sentence_bounds(file, match.start())
            if _overlaps_result(source_start, source_end, regions):
                continue
            raw_term = match.group("term")
            term, term_start, term_end = _unwrap_term(raw_term, match.start("term"))
            if not term:
                continue
            candidates.append(
                _Declaration(
                    kind=kind,
                    term=term,
                    term_start=term_start,
                    term_end=term_end,
                    source_start=source_start,
                    source_end=source_end,
                )
            )

    unique: dict[tuple[int, int, str], _Declaration] = {}
    for candidate in candidates:
        key = (candidate.source_start, candidate.source_end, candidate.term.casefold())
        unique[key] = candidate
    return sorted(unique.values(), key=lambda item: (item.source_start, item.term.casefold()))


def _term_variants(term: str) -> tuple[str, ...]:
    """Return mechanically related lexical forms without mathematical vocabulary."""

    variants = [term]
    words = term.split()
    if not words:
        return tuple(variants)
    final = words[-1]
    singular: str | None = None
    if final.lower().endswith("ies") and len(final) > 3:
        singular = final[:-3] + "y"
    elif final.lower().endswith("s") and not final.lower().endswith("ss") and len(final) > 1:
        singular = final[:-1]
    if singular is not None:
        variants.append(" ".join([*words[:-1], singular]))
    return tuple(dict.fromkeys(variants))


def _term_pattern(term: str) -> re.Pattern[str]:
    alternatives: list[str] = []
    for variant in _term_variants(term):
        pieces = [re.escape(piece) for piece in variant.split()]
        alternatives.append(r"\s+".join(pieces))
    body = "(?:" + "|".join(alternatives) + ")"
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _result_occurrences(
    file: FrontendFile,
    regions: list[ResultRegion],
    declaration: _Declaration,
) -> list[tuple[ResultRegion, ScopeKind, int, int]]:
    pattern = _term_pattern(declaration.term)
    occurrences: list[tuple[ResultRegion, ScopeKind, int, int]] = []
    for region in regions:
        spans = [(region.statement_span, ScopeKind.STATEMENT)]
        if region.proof_span is not None:
            spans.append((region.proof_span, ScopeKind.PROOF))
        for span, kind in spans:
            if span.start_offset <= declaration.source_start:
                # Project prose declarations only govern later source in the same file.
                continue
            text = span.text(file.raw)
            for match in pattern.finditer(text):
                start = span.start_offset + match.start()
                end = span.start_offset + match.end()
                if start > declaration.source_end:
                    occurrences.append((region, kind, start, end))
    return occurrences


def _scope_for_use(
    table: SymbolTable,
    *,
    result_identifier: str,
    kind: ScopeKind,
    source: SourceSpan,
) -> str | None:
    locals_ = [
        scope
        for scope in table.scopes
        if scope.result_identifier == result_identifier
        and scope.kind == ScopeKind.LOCAL
        and scope.source is not None
        and scope.source.file == source.file
        and scope.source.start_offset <= source.start_offset
        and source.end_offset <= scope.source.end_offset
    ]
    if locals_:
        locals_.sort(
            key=lambda scope: (
                scope.source.end_offset - scope.source.start_offset
                if scope.source is not None
                else 0
            )
        )
        return locals_[0].identifier
    for scope in table.scopes:
        if scope.result_identifier == result_identifier and scope.kind == kind:
            return scope.identifier
    return None


def _append_declaration(
    file: FrontendFile,
    table: SymbolTable,
    declaration: _Declaration,
) -> Symbol:
    source = _span(
        file.path,
        file.raw,
        declaration.term_start,
        declaration.term_end,
    )
    introduction = _span(
        file.path,
        file.raw,
        declaration.source_start,
        declaration.source_end,
    )
    identifier = f"semantic:{file.path}:{declaration.term_start}"
    symbol = Symbol(
        identifier=identifier,
        name=declaration.term,
        role=SymbolRole.UNKNOWN,
        introduction_kind=(
            IntroductionKind.DEFINE
            if declaration.kind == "definition"
            else IntroductionKind.FOR
        ),
        scope_identifier="project",
        source=source,
        introduction_source=introduction,
        raw_introduction=introduction.text(file.raw),
    )
    table.symbols.append(symbol)
    if declaration.kind == "definition":
        table.definitions.append(
            Definition(
                identifier=f"{identifier}:definition",
                symbol_identifier=identifier,
                operator=":=",
                # The authoritative meaning is ordinary prose. Deliberately do
                # not fabricate a formula; the canonical source handle is the
                # semantic payload and thorn-proof/1 may request it.
                expression_latex="",
                source=introduction,
                raw=introduction.text(file.raw),
            )
        )
    else:
        table.constraints.append(
            Constraint(
                identifier=f"{identifier}:convention",
                symbol_identifier=identifier,
                relation=":",
                expression_latex="",
                source=introduction,
                raw=introduction.text(file.raw),
            )
        )
    return symbol


def _resolve_semantic_term(
    table: SymbolTable,
    *,
    name: str,
    source: SourceSpan,
) -> Symbol | None:
    variants = {variant.casefold() for variant in _term_variants(name)}
    candidates = [
        symbol
        for symbol in table.symbols
        if symbol.identifier.startswith("semantic:")
        and symbol.source.file == source.file
        and symbol.source.start_offset < source.start_offset
        and symbol.name.casefold() in variants
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.source.start_offset)


def add_project_semantic_context(
    project: ParsedProject,
    regions: list[ResultRegion],
    table: SymbolTable,
) -> None:
    """Recover explicit prose semantics as ordinary project-scope symbol edges.

    Only declaration-shaped prose is eligible, and eligibility is not enough:
    the declared lexical term must be concretely used by a later theorem
    statement or proof. This creates a normal resolved SymbolUse dependency,
    so existing result selection, canonical Proof-IR provenance, source rescue,
    replay, and report navigation remain the sole production path.
    """

    regions_by_file: dict[str, list[ResultRegion]] = {}
    for region in regions:
        regions_by_file.setdefault(region.file, []).append(region)

    existing_symbols = {
        (symbol.name.casefold(), symbol.source.file, symbol.source.start_offset)
        for symbol in table.symbols
    }
    pending_uses: list[
        tuple[FrontendFile, Symbol, list[tuple[ResultRegion, ScopeKind, int, int]]]
    ] = []

    # Register all eligible declarations before resolving uses. This preserves
    # ordinary lexical shadowing when the same term is redefined later.
    for file in project.files:
        file_regions = regions_by_file.get(file.path, [])
        for declaration in _declarations(file, file_regions):
            occurrences = _result_occurrences(file, file_regions, declaration)
            if not occurrences:
                continue
            key = (declaration.term.casefold(), file.path, declaration.term_start)
            if key in existing_symbols:
                continue
            symbol = _append_declaration(file, table, declaration)
            existing_symbols.add(key)
            pending_uses.append((file, symbol, occurrences))

    existing_uses = {
        (use.name.casefold(), use.source.file, use.source.start_offset, use.source.end_offset)
        for use in table.uses
    }
    for file, symbol, occurrences in pending_uses:
        for region, kind, start, end in occurrences:
            source = _span(file.path, file.raw, start, end)
            use_key = (symbol.name.casefold(), source.file, source.start_offset, source.end_offset)
            if use_key in existing_uses:
                continue
            scope = _scope_for_use(
                table,
                result_identifier=region.identifier,
                kind=kind,
                source=source,
            )
            if scope is None:
                continue
            resolved = _resolve_semantic_term(table, name=symbol.name, source=source)
            table.uses.append(
                SymbolUse(
                    name=symbol.name,
                    scope_identifier=scope,
                    source=source,
                    raw=source.text(file.raw),
                    resolved_symbol_identifier=(
                        resolved.identifier if resolved is not None else None
                    ),
                )
            )
            existing_uses.add(use_key)

    table.symbols.sort(key=lambda item: (item.source.file, item.source.start_offset))
    table.definitions.sort(key=lambda item: (item.source.file, item.source.start_offset))
    table.constraints.sort(key=lambda item: (item.source.file, item.source.start_offset))
    table.uses.sort(key=lambda item: (item.source.file, item.source.start_offset, item.name))
