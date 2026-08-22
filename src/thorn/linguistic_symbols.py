from __future__ import annotations

import re
from pathlib import Path

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import FrontendFile, FrontendMath, ParsedProject, SourceSpan
from thorn.linguistic import LinguisticFrontend
from thorn.source_projection import (
    LinguisticProjection,
    LinguisticSpanTokenKind,
    build_linguistic_projection,
)
from thorn.symbols import (
    ResultRegion,
    ScopeKind,
    SymbolCandidateKind,
    SymbolIntroductionCandidate,
    SymbolRole,
    SymbolTable,
)

_SIMPLE_SYMBOL = r"(?:\\[A-Za-z]+|[A-Za-z])(?:_(?:\{[^{}]+\}|[A-Za-z0-9]+))?"
_FUNCTION_DEFINITION_RE = re.compile(
    rf"^\s*(?P<name>{_SIMPLE_SYMBOL})\s*\([^()]*\)\s*"
    r"(?P<operator>:=|=|\\coloneqq)\s*(?P<rhs>.+?)\s*$"
)
_SYMBOL_RE = re.compile(rf"^\s*(?P<name>{_SIMPLE_SYMBOL})(?P<rest>.*?)\s*$", re.DOTALL)
_DEFINITION_REST_RE = re.compile(
    r"^\s*(?P<operator>:=|=|\\coloneqq)\s*(?P<rhs>.+?)\s*$",
    re.DOTALL,
)
_DECLARATION_REST_RE = re.compile(
    r"^\s*(?:"
    r"\\in\b|:|<|>|\\(?:leq?|geq?)\b"
    r").+$",
    re.DOTALL,
)


def _span(file: FrontendFile, start: int, end: int) -> SourceSpan:
    return file.span(start, end)


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


def _math_in_span(
    file: FrontendFile,
    span: SourceSpan,
    projection: LinguisticProjection,
) -> list[FrontendMath]:
    return [
        math
        for math in file.math
        if math.span.start_offset >= span.start_offset
        and math.span.end_offset <= span.end_offset
        and projection.source_span_eligible(math.span)
    ]


def _candidate_shape(
    math: FrontendMath,
) -> tuple[str, int, int, SymbolCandidateKind, str | None, str | None] | None:
    content, content_start = _math_inner(math)
    function_definition = _FUNCTION_DEFINITION_RE.match(content)
    if function_definition is not None:
        return (
            function_definition.group("name"),
            content_start + function_definition.start("name"),
            content_start + function_definition.end("name"),
            SymbolCandidateKind.DEFINITION,
            function_definition.group("operator"),
            function_definition.group("rhs").strip(),
        )

    match = _SYMBOL_RE.match(content)
    if match is None:
        return None
    rest = match.group("rest")
    definition = _DEFINITION_REST_RE.match(rest)
    if definition is not None:
        kind = SymbolCandidateKind.DEFINITION
        operator = definition.group("operator")
        rhs = definition.group("rhs").strip()
    elif not rest.strip() or _DECLARATION_REST_RE.match(rest) is not None:
        kind = SymbolCandidateKind.INTRODUCTION
        operator = None
        rhs = None
    else:
        return None
    return (
        match.group("name"),
        content_start + match.start("name"),
        content_start + match.end("name"),
        kind,
        operator,
        rhs,
    )


def _scope_identifier(
    table: SymbolTable,
    result_identifier: str,
    kind: ScopeKind,
) -> str | None:
    for scope in table.scopes:
        if scope.result_identifier == result_identifier and scope.kind == kind:
            return scope.identifier
    return None


def _eligible_context_span(
    projection: LinguisticProjection,
    containing: SourceSpan,
    math: FrontendMath,
) -> SourceSpan | None:
    """Return a bounded local context that cannot cross excluded source."""

    window = projection.source_span(
        max(containing.start_offset, math.span.start_offset - 96),
        min(containing.end_offset, math.span.end_offset + 96),
    )
    for segment in projection.eligible_segments(window):
        if (
            segment.start_offset <= math.span.start_offset
            and math.span.end_offset <= segment.end_offset
        ):
            return segment
    return None


def _append_candidates_in_span(
    *,
    table: SymbolTable,
    file: FrontendFile,
    projection: LinguisticProjection,
    span: SourceSpan,
    scope_identifier: str,
    result_identifier: str,
    frontend: LinguisticFrontend,
) -> None:
    for math in _math_in_span(file, span, projection):
        shape = _candidate_shape(math)
        if shape is None:
            continue
        name, name_start, name_end, kind, operator, rhs = shape
        source = _span(file, name_start, name_end)
        if table.resolve(name, scope_identifier, source) is not None:
            continue

        context_span = _eligible_context_span(projection, span, math)
        if context_span is None:
            continue
        projected_context = projection.project_span(context_span)
        placeholder = next(
            (
                item
                for item in projected_context.placeholders
                if item.kind == LinguisticSpanTokenKind.MATH
                and item.source.start_offset == math.span.start_offset
                and item.source.end_offset == math.span.end_offset
            ),
            None,
        )
        dependency_path: list[str] = []
        if placeholder is not None:
            document = frontend.parse(projected_context.text)
            token = document.token_by_text(placeholder.token)
            if token is not None:
                dependency_path = document.root_path_signature(token.index)

        status = (
            InferenceStatus.AMBIGUOUS if dependency_path else InferenceStatus.UNRESOLVED
        )
        raw_context = context_span.text(file.raw)
        table.candidates.append(
            SymbolIntroductionCandidate(
                identifier=(
                    f"candidate:{kind.value}:{name}@{Path(file.path).name}:"
                    f"{source.start_offset}"
                ),
                name=name,
                kind=kind,
                role=(
                    SymbolRole.FUNCTION
                    if _FUNCTION_DEFINITION_RE.match(_math_inner(math)[0]) is not None
                    else SymbolRole.UNKNOWN
                ),
                scope_identifier=scope_identifier,
                result_identifier=result_identifier,
                source=source,
                math_source=math.span,
                raw_context=raw_context,
                definition_operator=operator,
                expression_latex=rhs,
                status=status,
                evidence=[
                    StructuralEvidence(
                        reason=(
                            "declaration-shaped mathematical syntax is grammatically "
                            "attached in local prose; declaration intent remains unresolved"
                        ),
                        source=math.span,
                        target=source,
                        context=raw_context,
                        dependency_path=dependency_path,
                        frontend=frontend.name,
                    )
                ],
            )
        )


def add_linguistic_symbol_candidates(
    project: ParsedProject,
    regions: list[ResultRegion],
    table: SymbolTable,
    frontend: LinguisticFrontend,
) -> None:
    """Add reviewable declaration candidates without mutating deterministic scope."""

    files = {file.path: file for file in project.files}
    projections = {
        file.path: build_linguistic_projection(file)
        for file in project.files
    }
    for region in regions:
        file = files.get(region.file)
        projection = projections.get(region.file)
        if file is None or projection is None or not projection.complete:
            continue
        result_scope = _scope_identifier(table, region.identifier, ScopeKind.RESULT)
        if result_scope is not None:
            _append_candidates_in_span(
                table=table,
                file=file,
                projection=projection,
                span=region.statement_span,
                scope_identifier=result_scope,
                result_identifier=region.identifier,
                frontend=frontend,
            )
        if region.proof_span is None:
            continue
        proof_scope = _scope_identifier(table, region.identifier, ScopeKind.PROOF)
        if proof_scope is not None:
            _append_candidates_in_span(
                table=table,
                file=file,
                projection=projection,
                span=region.proof_span,
                scope_identifier=proof_scope,
                result_identifier=region.identifier,
                frontend=frontend,
            )

    table.candidates.sort(key=lambda item: (item.source.file, item.source.start_offset))
