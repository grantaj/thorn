from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from thorn.frontend import FrontendFile, FrontendMath, ParsedProject, SourceSpan


class ScopeKind(StrEnum):
    PROJECT = "project"
    RESULT = "result"
    STATEMENT = "statement"
    PROOF = "proof"
    LOCAL = "local"


class SymbolRole(StrEnum):
    UNKNOWN = "unknown"
    SCALAR = "scalar"
    MAP = "map"
    FUNCTION = "function"
    SET = "set"
    SEQUENCE = "sequence"
    INDEX = "index"


class IntroductionKind(StrEnum):
    LET = "let"
    FOR = "for"
    DEFINE = "define"
    SET = "set"
    QUANTIFIER = "quantifier"


class Scope(BaseModel):
    identifier: str
    kind: ScopeKind
    parent_identifier: str | None = None
    result_identifier: str | None = None
    source: SourceSpan | None = None


class Symbol(BaseModel):
    identifier: str
    name: str
    role: SymbolRole = SymbolRole.UNKNOWN
    arity: int | None = None
    domain_latex: str | None = None
    codomain_latex: str | None = None
    introduction_kind: IntroductionKind
    scope_identifier: str
    result_identifier: str | None = None
    source: SourceSpan
    introduction_source: SourceSpan
    raw_introduction: str


class Definition(BaseModel):
    identifier: str
    symbol_identifier: str
    operator: str
    expression_latex: str
    source: SourceSpan
    raw: str


class Constraint(BaseModel):
    identifier: str
    symbol_identifier: str
    relation: str
    expression_latex: str
    source: SourceSpan
    raw: str


class SymbolUse(BaseModel):
    name: str
    scope_identifier: str
    source: SourceSpan
    raw: str
    resolved_symbol_identifier: str | None = None


class ResultRegion(BaseModel):
    """Source regions needed by symbol extraction, independent of parser backend."""

    identifier: str
    file: str
    statement_span: SourceSpan
    proof_span: SourceSpan | None = None


class SymbolTable(BaseModel):
    scopes: list[Scope] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    uses: list[SymbolUse] = Field(default_factory=list)

    def scope(self, identifier: str) -> Scope:
        for scope in self.scopes:
            if scope.identifier == identifier:
                return scope
        raise KeyError(f"unknown scope {identifier!r}")

    def symbol(self, identifier: str) -> Symbol:
        for symbol in self.symbols:
            if symbol.identifier == identifier:
                return symbol
        raise KeyError(f"unknown symbol {identifier!r}")

    def scope_chain(self, identifier: str) -> list[str]:
        chain: list[str] = []
        current: str | None = identifier
        while current is not None:
            if current in chain:
                raise ValueError(f"scope cycle at {current!r}")
            chain.append(current)
            current = self.scope(current).parent_identifier
        return chain

    def visible_symbols(self, scope_identifier: str, source: SourceSpan | None = None) -> list[Symbol]:
        chain = self.scope_chain(scope_identifier)
        rank = {scope_id: index for index, scope_id in enumerate(chain)}
        visible: list[Symbol] = []
        for symbol in self.symbols:
            if symbol.scope_identifier not in rank:
                continue
            if source is not None and symbol.source.file == source.file:
                if symbol.source.start_offset > source.start_offset:
                    continue
            visible.append(symbol)
        return sorted(
            visible,
            key=lambda symbol: (rank[symbol.scope_identifier], -symbol.source.start_offset),
        )

    def resolve(
        self,
        name: str,
        scope_identifier: str,
        source: SourceSpan,
    ) -> Symbol | None:
        for symbol in self.visible_symbols(scope_identifier, source):
            if symbol.name == name:
                return symbol
        return None


_SIMPLE_SYMBOL = r"(?:\\[A-Za-z]+|[A-Za-z])(?:_(?:\{[^{}]+\}|[A-Za-z0-9]+))?"
_SIMPLE_SYMBOL_RE = re.compile(rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*$")
_MULTI_SYMBOL_RE = re.compile(rf"^\s*(?P<names>{_SIMPLE_SYMBOL}(?:\s*,\s*{_SIMPLE_SYMBOL})+)\s*$")
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


def _split_args(raw: str) -> list[str]:
    stripped = raw.strip()
    if not stripped:
        return []
    return [part.strip() for part in stripped.split(",") if part.strip()]


def _candidate_from_match(match: re.Match[str], *, role: SymbolRole = SymbolRole.UNKNOWN) -> _Candidate:
    return _Candidate(
        name=match.group("name"),
        name_start=match.start("name"),
        name_end=match.end("name"),
        role=role,
    )


def _parse_candidates(content: str, kind: IntroductionKind) -> list[_Candidate]:
    if kind == IntroductionKind.DEFINE:
        function_match = _FUNCTION_DEF_RE.match(content)
        if function_match is not None:
            args = _split_args(function_match.group("args"))
            return [
                _Candidate(
                    name=function_match.group("name"),
                    name_start=function_match.start("name"),
                    name_end=function_match.end("name"),
                    role=SymbolRole.FUNCTION,
                    arity=len(args),
                    definition_operator=function_match.group("operator"),
                    definition_rhs=function_match.group("rhs").strip(),
                )
            ]
        simple_definition = _SIMPLE_DEF_RE.match(content)
        if simple_definition is not None:
            candidate = _candidate_from_match(simple_definition)
            return [
                _Candidate(
                    **candidate.__dict__,
                    definition_operator=simple_definition.group("operator"),
                    definition_rhs=simple_definition.group("rhs").strip(),
                )
            ]

    if kind == IntroductionKind.SET:
        simple_definition = _SIMPLE_DEF_RE.match(content)
        if simple_definition is not None:
            candidate = _candidate_from_match(simple_definition)
            return [
                _Candidate(
                    **candidate.__dict__,
                    definition_operator=simple_definition.group("operator"),
                    definition_rhs=simple_definition.group("rhs").strip(),
                )
            ]

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
        return [_candidate_from_match(simple_match)]

    multi_match = _MULTI_SYMBOL_RE.match(content)
    if multi_match is not None:
        candidates: list[_Candidate] = []
        for token_match in re.finditer(_SIMPLE_SYMBOL, content):
            candidates.append(
                _Candidate(
                    name=token_match.group(0),
                    name_start=token_match.start(),
                    name_end=token_match.end(),
                )
            )
        return candidates

    return []


def _cue_for_math(file: FrontendFile, parent: SourceSpan, math: FrontendMath) -> tuple[IntroductionKind, int] | None:
    left_start = max(parent.start_offset, math.span.start_offset - 80)
    left = file.raw[left_start : math.span.start_offset]
    right = file.raw[math.span.end_offset : min(parent.end_offset, math.span.end_offset + 24)]
    for kind, pattern in _CUE_PATTERNS:
        match = pattern.search(left)
        if match is None:
            continue
        if kind == IntroductionKind.LET and re.match(r"\s+be\b", right, flags=re.IGNORECASE) is None:
            continue
        return kind, left_start + match.start()
    return None


def _append_candidate(
    *,
    table: SymbolTable,
    file: FrontendFile,
    content: str,
    content_start: int,
    candidate: _Candidate,
    kind: IntroductionKind,
    scope_identifier: str,
    result_identifier: str,
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
    local_scope_by_math[(file.path, math.span.start_offset, math.span.end_offset)] = local_scope_identifier
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
        candidate = _Candidate(
            name=match.group("name"),
            name_start=match.start("name"),
            name_end=match.end("name"),
            constraint_relation=match.group("relation"),
            constraint_rhs=(match.group("rhs") or "").strip() or None,
        )
        _append_candidate(
            table=table,
            file=file,
            content=content,
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
                content=content,
                content_start=content_start,
                candidate=candidate,
                kind=kind,
                scope_identifier=scope_identifier,
                result_identifier=result_identifier,
                introduction_start=introduction_start,
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
                if any(
                    symbol.name == name
                    and symbol.source.file == source.file
                    and symbol.source.start_offset == source.start_offset
                    and symbol.source.end_offset == source.end_offset
                    for symbol in table.symbols
                ):
                    continue
                resolved = table.resolve(name, math_scope, source)
                table.uses.append(
                    SymbolUse(
                        name=name,
                        scope_identifier=math_scope,
                        source=source,
                        raw=source.text(file.raw),
                        resolved_symbol_identifier=resolved.identifier if resolved is not None else None,
                    )
                )


def extract_symbol_table(project: ParsedProject, regions: list[ResultRegion]) -> SymbolTable:
    """Build conservative symbol/definition/scope IR from normalized frontend facts."""

    table = SymbolTable(
        scopes=[Scope(identifier="project", kind=ScopeKind.PROJECT)]
    )
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
        result_end = region.proof_span.end_offset if region.proof_span is not None else region.statement_span.end_offset
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

    # Pass 1: declarations and local binders. Statement declarations are put in
    # result scope deliberately so the associated proof can see hypotheses.
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

    # Pass 2: uses of symbols Thorn has positively identified. This intentionally
    # does not invent undeclared symbols yet; #18 can layer candidate-undefined
    # analysis on top without making conventional notation noisy in #17.
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
