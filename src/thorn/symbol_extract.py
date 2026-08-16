from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from thorn.frontend import FrontendFile, FrontendMath, ParsedProject, SourceSpan
from thorn.symbols import (
    Constraint,
    Definition,
    IntroductionKind,
    ResultRegion,
    Scope,
    ScopeKind,
    Symbol,
    SymbolRole,
    SymbolTable,
    SymbolUse,
)

_SIMPLE_SYMBOL = (
    r"(?:\\[A-Za-z]+|[A-Za-z])"
    r"(?:_(?:\{[^{}]+\}|\\[A-Za-z]+|[A-Za-z0-9]+))?"
)
_SIMPLE_SYMBOL_RE = re.compile(rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*$")
_MULTI_SYMBOL_RE = re.compile(rf"^\s*{_SIMPLE_SYMBOL}(?:\s*,\s*{_SIMPLE_SYMBOL})+\s*$")
_MAP_RE = re.compile(
    rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*:\s*(?P<domain>.+?)\s*"
    r"\\(?:to|rightarrow|longrightarrow)\s*(?P<codomain>.+?)\s*$"
)
_FUNCTION_DEF_RE = re.compile(
    rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*\((?P<args>[^()]*)\)\s*"
    r"(?P<operator>:=|=|\\coloneqq)\s*(?P<rhs>.+?)\s*$"
)
_SIMPLE_DEF_RE = re.compile(
    rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*(?P<operator>:=|=|\\coloneqq)\s*"
    r"(?P<rhs>.+?)\s*$"
)
_PROJECT_COLON_DEF_RE = re.compile(
    rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*(?::=|\\coloneqq)\s*"
    r"(?P<rhs>.+?)\s*$",
    re.DOTALL,
)
_PROJECT_STACKED_DEF_PREFIX_RE = re.compile(
    rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*\\(?:stackrel|overset)",
    re.IGNORECASE,
)
_DEF_ANNOTATION_RE = re.compile(
    r"(?<![A-Za-z])def(?:inition)?(?![A-Za-z])",
    re.IGNORECASE,
)
_RELATION_RE = re.compile(
    rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*"
    r"(?P<relation>>|<|\\geq?|\\leq?|\\in)\s*(?P<rhs>.+?)\s*$"
)
_QUANTIFIER_RE = re.compile(
    rf"(?P<quantifier>\\forall|\\exists)\s*(?P<name>{_SIMPLE_SYMBOL})"
    r"(?:\s*(?P<relation>\\in)\s*(?P<rhs>[^,;]+))?"
)
_CUE_PATTERNS: tuple[tuple[IntroductionKind, re.Pattern[str]], ...] = (
    (IntroductionKind.LET, re.compile(r"(?i)\blet\s*$")),
    (IntroductionKind.FOR, re.compile(r"(?i)\bfor(?:\s+(?:each|every))?\s*$")),
    (IntroductionKind.DEFINE, re.compile(r"(?i)\bdefine\s*$")),
    (IntroductionKind.SET, re.compile(r"(?i)\bset\s*$")),
)
_STANDARD_WRAPPER_RE = re.compile(
    r"\\(?:mathbb|mathbf|mathrm|mathcal|mathfrak|operatorname)\s*(?:\{[^{}]*\}|[A-Za-z])"
)


@dataclass(frozen=True)
class _Candidate:
    name: str
    name_start: int
    name_end: int
    role: SymbolRole = SymbolRole.UNKNOWN
    arity: int | None = None
    domain_latex: str | None = None
    codomain_latex: str | None = None
    definition_operator: str | None = None
    definition_rhs: str | None = None
    constraint_relation: str | None = None
    constraint_rhs: str | None = None


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _span(file: str, text: str, start: int, end: int) -> SourceSpan:
    start_line, start_column = _line_column(text, start)
    end_line, end_column = _line_column(text, end)
    return SourceSpan(
        file=file,
        start_offset=start,
        end_offset=end,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _math_inner(math: FrontendMath) -> tuple[str, int]:
    raw = math.raw
    if raw.startswith("$$") and raw.endswith("$$"):
        return raw[2:-2], math.span.start_offset + 2
    if raw.startswith("$") and raw.endswith("$"):
        return raw[1:-1], math.span.start_offset + 1
    if raw.startswith(r"\[") and raw.endswith(r"\]"):
        return raw[2:-2], math.span.start_offset + 2
    if raw.startswith(r"\(") and raw.endswith(r"\)"):
        return raw[2:-2], math.span.start_offset + 2
    return raw, math.span.start_offset


def _math_in_span(file: FrontendFile, span: SourceSpan) -> list[FrontendMath]:
    return [
        math
        for math in file.math
        if math.span.start_offset >= span.start_offset and math.span.end_offset <= span.end_offset
    ]


def _scope_id(kind: ScopeKind, region: ResultRegion, span: SourceSpan) -> str:
    return f"{kind.value}:{region.identifier}@{Path(span.file).name}:{span.start_offset}"


def _symbol_id(scope_identifier: str, name: str, source: SourceSpan) -> str:
    return f"symbol:{name}@{scope_identifier}:{source.start_offset}"


def _candidate_from_simple(match: re.Match[str]) -> _Candidate:
    return _Candidate(
        name=match.group("name"),
        name_start=match.start("name"),
        name_end=match.end("name"),
    )


def _candidate_from_definition(
    match: re.Match[str],
    *,
    role: SymbolRole = SymbolRole.UNKNOWN,
    arity: int | None = None,
) -> _Candidate:
    return _Candidate(
        name=match.group("name"),
        name_start=match.start("name"),
        name_end=match.end("name"),
        role=role,
        arity=arity,
        definition_operator=match.group("operator"),
        definition_rhs=match.group("rhs").strip(),
    )


def _split_args(raw: str) -> list[str]:
    stripped = raw.strip()
    if not stripped:
        return []
    return [part.strip() for part in stripped.split(",") if part.strip()]


def _parse_candidates(content: str, kind: IntroductionKind) -> list[_Candidate]:
    if kind == IntroductionKind.DEFINE:
        function_match = _FUNCTION_DEF_RE.match(content)
        if function_match is not None:
            return [
                _candidate_from_definition(
                    function_match,
                    role=SymbolRole.FUNCTION,
                    arity=len(_split_args(function_match.group("args"))),
                )
            ]
        simple_definition = _SIMPLE_DEF_RE.match(content)
        if simple_definition is not None:
            return [_candidate_from_definition(simple_definition)]

    if kind == IntroductionKind.SET:
        simple_definition = _SIMPLE_DEF_RE.match(content)
        if simple_definition is not None:
            return [_candidate_from_definition(simple_definition)]

    map_match = _MAP_RE.match(content)
    if map_match is not None:
        return [
            _Candidate(
                name=map_match.group("name"),
                name_start=map_match.start("name"),
                name_end=map_match.end("name"),
                role=SymbolRole.MAP,
                arity=1,
                domain_latex=map_match.group("domain").strip(),
                codomain_latex=map_match.group("codomain").strip(),
            )
        ]

    relation_match = _RELATION_RE.match(content)
    if relation_match is not None:
        relation = relation_match.group("relation")
        role = SymbolRole.SCALAR if relation != r"\in" else SymbolRole.UNKNOWN
        return [
            _Candidate(
                name=relation_match.group("name"),
                name_start=relation_match.start("name"),
                name_end=relation_match.end("name"),
                role=role,
                constraint_relation=relation,
                constraint_rhs=relation_match.group("rhs").strip(),
            )
        ]

    simple_match = _SIMPLE_SYMBOL_RE.match(content)
    if simple_match is not None:
        return [_candidate_from_simple(simple_match)]

    if _MULTI_SYMBOL_RE.match(content) is not None:
        return [
            _Candidate(
                name=match.group(0),
                name_start=match.start(),
                name_end=match.end(),
            )
            for match in re.finditer(_SIMPLE_SYMBOL, content)
        ]

    return []


def _cue_for_math(
    file: FrontendFile,
    parent: SourceSpan,
    math: FrontendMath,
) -> tuple[IntroductionKind, int] | None:
    left_start = max(parent.start_offset, math.span.start_offset - 80)
    left = file.raw[left_start : math.span.start_offset]
    right = file.raw[math.span.end_offset : min(parent.end_offset, math.span.end_offset + 24)]
    for kind, pattern in _CUE_PATTERNS:
        match = pattern.search(left)
        if match is None:
            continue
        if (
            kind == IntroductionKind.LET
            and re.match(r"\s+be\b", right, flags=re.IGNORECASE) is None
        ):
            continue
        return kind, left_start + match.start()
    return None


def _append_candidate(
    *,
    table: SymbolTable,
    file: FrontendFile,
    content_start: int,
    candidate: _Candidate,
    kind: IntroductionKind,
    scope_identifier: str,
    result_identifier: str | None,
    introduction_start: int,
    introduction_end: int,
) -> Symbol:
    symbol_source = _span(
        file.path,
        file.raw,
        content_start + candidate.name_start,
        content_start + candidate.name_end,
    )
    introduction_source = _span(file.path, file.raw, introduction_start, introduction_end)
    identifier = _symbol_id(scope_identifier, candidate.name, symbol_source)
    symbol = Symbol(
        identifier=identifier,
        name=candidate.name,
        role=candidate.role,
        arity=candidate.arity,
        domain_latex=candidate.domain_latex,
        codomain_latex=candidate.codomain_latex,
        introduction_kind=kind,
        scope_identifier=scope_identifier,
        result_identifier=result_identifier,
        source=symbol_source,
        introduction_source=introduction_source,
        raw_introduction=introduction_source.text(file.raw),
    )
    table.symbols.append(symbol)

    if candidate.definition_operator is not None and candidate.definition_rhs is not None:
        table.definitions.append(
            Definition(
                identifier=f"definition:{identifier}",
                symbol_identifier=identifier,
                operator=candidate.definition_operator,
                expression_latex=candidate.definition_rhs,
                source=introduction_source,
                raw=introduction_source.text(file.raw),
            )
        )

    if candidate.constraint_relation is not None and candidate.constraint_rhs is not None:
        table.constraints.append(
            Constraint(
                identifier=f"constraint:{identifier}",
                symbol_identifier=identifier,
                relation=candidate.constraint_relation,
                expression_latex=candidate.constraint_rhs,
                source=introduction_source,
                raw=introduction_source.text(file.raw),
            )
        )

    return symbol


def _add_quantifiers(
    *,
    table: SymbolTable,
    file: FrontendFile,
    math: FrontendMath,
    parent_scope_identifier: str,
    result_identifier: str,
    local_scope_by_math: dict[tuple[str, int, int], str],
) -> None:
    content, content_start = _math_inner(math)
    matches = list(_QUANTIFIER_RE.finditer(content))
    if not matches:
        return

    local_scope_identifier = (
        f"local:{result_identifier}@{Path(file.path).name}:{math.span.start_offset}"
    )
    local_scope_by_math[(file.path, math.span.start_offset, math.span.end_offset)] = (
        local_scope_identifier
    )
    table.scopes.append(
        Scope(
            identifier=local_scope_identifier,
            kind=ScopeKind.LOCAL,
            parent_identifier=parent_scope_identifier,
            result_identifier=result_identifier,
            source=math.span,
        )
    )

    for match in matches:
        relation = match.group("relation")
        rhs = (match.group("rhs") or "").strip() or None
        candidate = _Candidate(
            name=match.group("name"),
            name_start=match.start("name"),
            name_end=match.end("name"),
            constraint_relation=relation,
            constraint_rhs=rhs,
        )
        _append_candidate(
            table=table,
            file=file,
            content_start=content_start,
            candidate=candidate,
            kind=IntroductionKind.QUANTIFIER,
            scope_identifier=local_scope_identifier,
            result_identifier=result_identifier,
            introduction_start=math.span.start_offset,
            introduction_end=math.span.end_offset,
        )


def _add_explicit_introductions(
    *,
    table: SymbolTable,
    file: FrontendFile,
    span: SourceSpan,
    scope_identifier: str,
    result_identifier: str,
) -> None:
    for math in _math_in_span(file, span):
        cue = _cue_for_math(file, span, math)
        if cue is None:
            continue
        kind, introduction_start = cue
        content, content_start = _math_inner(math)
        for candidate in _parse_candidates(content, kind):
            _append_candidate(
                table=table,
                file=file,
                content_start=content_start,
                candidate=candidate,
                kind=kind,
                scope_identifier=scope_identifier,
                result_identifier=result_identifier,
                introduction_start=introduction_start,
                introduction_end=math.span.end_offset,
            )


def _take_braced_group(text: str, start: int) -> tuple[str, int] | None:
    """Return one balanced braced group and the offset immediately after it."""

    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        return None

    depth = 0
    content_start = index + 1
    for cursor in range(index, len(text)):
        char = text[cursor]
        if char == "{" and (cursor == 0 or text[cursor - 1] != "\\"):
            depth += 1
        elif char == "}" and (cursor == 0 or text[cursor - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return text[content_start:cursor], cursor + 1
    return None


def _project_definition_candidate(content: str) -> _Candidate | None:
    colon_match = _PROJECT_COLON_DEF_RE.match(content)
    if colon_match is not None:
        return _Candidate(
            name=colon_match.group("name"),
            name_start=colon_match.start("name"),
            name_end=colon_match.end("name"),
            definition_operator=":=",
            definition_rhs=colon_match.group("rhs").strip(),
        )

    stacked_match = _PROJECT_STACKED_DEF_PREFIX_RE.match(content)
    if stacked_match is None:
        return None
    annotation_group = _take_braced_group(content, stacked_match.end())
    if annotation_group is None:
        return None
    annotation, offset = annotation_group
    equals_group = _take_braced_group(content, offset)
    if equals_group is None:
        return None
    equals, offset = equals_group

    # Presentation wrappers such as ``\scriptstyle\text{\tiny def}`` are
    # irrelevant, but the semantic marker itself must be literal and the second
    # argument must still be exactly an equals sign modulo braces/whitespace.
    if _DEF_ANNOTATION_RE.search(annotation) is None:
        return None
    if re.sub(r"[{}\s]", "", equals) != "=":
        return None
    rhs = content[offset:].strip()
    if not rhs:
        return None
    return _Candidate(
        name=stacked_match.group("name"),
        name_start=stacked_match.start("name"),
        name_end=stacked_match.end("name"),
        definition_operator=":=",
        definition_rhs=rhs,
    )


def _inside_result_region(math: FrontendMath, regions: list[ResultRegion]) -> bool:
    for region in regions:
        for span in (region.statement_span, region.proof_span):
            if span is None or span.file != math.span.file:
                continue
            if (
                span.start_offset <= math.span.start_offset
                and math.span.end_offset <= span.end_offset
            ):
                return True
    return False


def _add_project_definitions(
    *,
    table: SymbolTable,
    file: FrontendFile,
    regions: list[ResultRegion],
) -> None:
    """Recover only mechanically explicit definitions outside result regions.

    Project scope is deliberately conservative: ordinary equalities are not
    definitions here.  We accept only explicit definitional operators so a
    later target can resolve a used symbol without importing unrelated section
    prose or promoting an arbitrary displayed equality into semantic context.
    """

    for math in file.math:
        if _inside_result_region(math, regions):
            continue
        content, content_start = _math_inner(math)
        candidate = _project_definition_candidate(content)
        if candidate is None:
            continue
        _append_candidate(
            table=table,
            file=file,
            content_start=content_start,
            candidate=candidate,
            kind=IntroductionKind.DEFINE,
            scope_identifier="project",
            result_identifier=None,
            introduction_start=math.span.start_offset,
            introduction_end=math.span.end_offset,
        )


def _masked_content(content: str) -> str:
    chars = list(content)
    for match in _STANDARD_WRAPPER_RE.finditer(content):
        for index in range(match.start(), match.end()):
            chars[index] = " "
    return "".join(chars)


def _symbol_occurrences(content: str, name: str) -> list[tuple[int, int]]:
    escaped = re.escape(name)
    if name.startswith("\\"):
        pattern = re.compile(rf"{escaped}(?![A-Za-z])")
    else:
        pattern = re.compile(rf"(?<![A-Za-z]){escaped}(?![A-Za-z])")
    return [(match.start(), match.end()) for match in pattern.finditer(content)]


def _is_declaration_occurrence(table: SymbolTable, name: str, source: SourceSpan) -> bool:
    return any(
        symbol.name == name
        and symbol.source.file == source.file
        and symbol.source.start_offset == source.start_offset
        and symbol.source.end_offset == source.end_offset
        for symbol in table.symbols
    )


def _add_uses(
    *,
    table: SymbolTable,
    file: FrontendFile,
    span: SourceSpan,
    scope_identifier: str,
    local_scope_by_math: dict[tuple[str, int, int], str],
) -> None:
    known_names = sorted({symbol.name for symbol in table.symbols}, key=len, reverse=True)
    for math in _math_in_span(file, span):
        content, content_start = _math_inner(math)
        masked = _masked_content(content)
        math_scope = local_scope_by_math.get(
            (file.path, math.span.start_offset, math.span.end_offset),
            scope_identifier,
        )
        for name in known_names:
            for start, end in _symbol_occurrences(masked, name):
                source = _span(file.path, file.raw, content_start + start, content_start + end)
                if _is_declaration_occurrence(table, name, source):
                    continue
                resolved = table.resolve(name, math_scope, source)
                table.uses.append(
                    SymbolUse(
                        name=name,
                        scope_identifier=math_scope,
                        source=source,
                        raw=source.text(file.raw),
                        resolved_symbol_identifier=(
                            resolved.identifier if resolved is not None else None
                        ),
                    )
                )


def extract_symbol_table(project: ParsedProject, regions: list[ResultRegion]) -> SymbolTable:
    """Build conservative symbol/definition/scope IR from normalized frontend facts."""

    table = SymbolTable(scopes=[Scope(identifier="project", kind=ScopeKind.PROJECT)])
    files = {file.path: file for file in project.files}
    local_scope_by_math: dict[tuple[str, int, int], str] = {}
    scope_rows: list[tuple[ResultRegion, FrontendFile, str, str, str | None]] = []

    for region in regions:
        file = files[region.file]
        result_scope = _scope_id(ScopeKind.RESULT, region, region.statement_span)
        statement_scope = _scope_id(ScopeKind.STATEMENT, region, region.statement_span)
        proof_scope = (
            _scope_id(ScopeKind.PROOF, region, region.proof_span)
            if region.proof_span is not None
            else None
        )
        result_end = (
            region.proof_span.end_offset
            if region.proof_span is not None
            else region.statement_span.end_offset
        )
        result_source = _span(
            file.path,
            file.raw,
            region.statement_span.start_offset,
            result_end,
        )
        table.scopes.extend(
            [
                Scope(
                    identifier=result_scope,
                    kind=ScopeKind.RESULT,
                    parent_identifier="project",
                    result_identifier=region.identifier,
                    source=result_source,
                ),
                Scope(
                    identifier=statement_scope,
                    kind=ScopeKind.STATEMENT,
                    parent_identifier=result_scope,
                    result_identifier=region.identifier,
                    source=region.statement_span,
                ),
            ]
        )
        if proof_scope is not None and region.proof_span is not None:
            table.scopes.append(
                Scope(
                    identifier=proof_scope,
                    kind=ScopeKind.PROOF,
                    parent_identifier=result_scope,
                    result_identifier=region.identifier,
                    source=region.proof_span,
                )
            )
        scope_rows.append((region, file, result_scope, statement_scope, proof_scope))

    # Ordinary manuscript prose can define notation before the theorem-like
    # environment that later uses it. Populate the existing project scope only
    # from explicit definitional operators; target selection downstream remains
    # use-driven, so this does not dump all project definitions into review.
    regions_by_file: dict[str, list[ResultRegion]] = {}
    for region in regions:
        regions_by_file.setdefault(region.file, []).append(region)
    for file in project.files:
        _add_project_definitions(
            table=table,
            file=file,
            regions=regions_by_file.get(file.path, []),
        )

    # Statement introductions are result-scoped so theorem hypotheses are visible
    # in the associated proof. Proof introductions remain proof-local.
    for region, file, result_scope, statement_scope, proof_scope in scope_rows:
        _add_explicit_introductions(
            table=table,
            file=file,
            span=region.statement_span,
            scope_identifier=result_scope,
            result_identifier=region.identifier,
        )
        for math in _math_in_span(file, region.statement_span):
            _add_quantifiers(
                table=table,
                file=file,
                math=math,
                parent_scope_identifier=statement_scope,
                result_identifier=region.identifier,
                local_scope_by_math=local_scope_by_math,
            )

        if proof_scope is not None and region.proof_span is not None:
            _add_explicit_introductions(
                table=table,
                file=file,
                span=region.proof_span,
                scope_identifier=proof_scope,
                result_identifier=region.identifier,
            )
            for math in _math_in_span(file, region.proof_span):
                _add_quantifiers(
                    table=table,
                    file=file,
                    math=math,
                    parent_scope_identifier=proof_scope,
                    result_identifier=region.identifier,
                    local_scope_by_math=local_scope_by_math,
                )

    # #17 records uses only for symbols already positively identified. Candidate
    # undeclared-symbol extraction belongs to #18, where false-positive policy is
    # part of the diagnostic design.
    for region, file, _result_scope, statement_scope, proof_scope in scope_rows:
        _add_uses(
            table=table,
            file=file,
            span=region.statement_span,
            scope_identifier=statement_scope,
            local_scope_by_math=local_scope_by_math,
        )
        if proof_scope is not None and region.proof_span is not None:
            _add_uses(
                table=table,
                file=file,
                span=region.proof_span,
                scope_identifier=proof_scope,
                local_scope_by_math=local_scope_by_math,
            )

    table.symbols.sort(key=lambda item: (item.source.file, item.source.start_offset))
    table.definitions.sort(key=lambda item: (item.source.file, item.source.start_offset))
    table.constraints.sort(key=lambda item: (item.source.file, item.source.start_offset))
    table.uses.sort(key=lambda item: (item.source.file, item.source.start_offset, item.name))
    return table
