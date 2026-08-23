from __future__ import annotations

import re

from thorn.frontend import FrontendFile, FrontendMath, ParsedProject, SourceSpan
from thorn.source_projection import LinguisticProjection, build_linguistic_projection
from thorn.symbol_extract import (
    _CUE_PATTERNS,
    _SIMPLE_SYMBOL,
    _append_candidate,
    _Candidate,
    _inside_result_region,
    _is_declaration_occurrence,
    _masked_content,
    _math_inner,
    _parse_candidates,
    _span,
    _symbol_occurrences,
)
from thorn.symbols import (
    IntroductionKind,
    ResultRegion,
    ScopeKind,
    Symbol,
    SymbolRole,
    SymbolTable,
    SymbolUse,
    canonical_symbol_name,
)
from thorn.workspace import (
    ProjectPositionLookup,
    ProjectWorkspaceFacts,
    WorkspaceResolution,
)

# Project-scope declarations deliberately reuse the ordinary symbol-extraction
# syntax and candidate construction above. Do not grow a second definition/map/
# relation parser here: project context differs in *authority policy*, not in the
# mathematical declaration grammar. False positives at project scope are more
# dangerous because they can alter resolution in every later result.

_INFIX_ALIAS_RE = re.compile(
    rf"^\s*(?P<left>{_SIMPLE_SYMBOL})\s*"
    r"(?P<name>\\[A-Za-z]+)\s*"
    rf"(?P<right>{_SIMPLE_SYMBOL})\s*$"
)
_ALIAS_BRIDGE_RE = re.compile(
    r"^\s*(?:to\s+mean|means?|is\s+defined\s+(?:as|to\s+be))\s*$",
    re.IGNORECASE,
)
_PROJECT_CONVENTION_TAIL_RE = re.compile(
    r"^\s*(?:in\s+what\s+follows|throughout|henceforth|from\s+now\s+on)\b",
    re.IGNORECASE,
)
_MAP_TAIL_RE = re.compile(r"^\s+be\b", re.IGNORECASE)


def _cue_for_math(
    file: FrontendFile,
    math: FrontendMath,
    projection: LinguisticProjection,
) -> tuple[IntroductionKind, int] | None:
    """Return a cue only from normalized source-role-eligible text."""

    if not projection.source_span_eligible(math.span):
        return None
    left_start = max(0, math.span.start_offset - 96)
    left = projection.text[left_start : math.span.start_offset]
    for kind, pattern in _CUE_PATTERNS:
        match = pattern.search(left)
        if match is not None:
            return kind, left_start + match.start()
    return None


def _candidate_is_authoritative_project_context(
    *,
    kind: IntroductionKind,
    candidate: _Candidate,
    tail: str,
) -> bool:
    """Require stronger evidence for project scope than for bounded local scope.

    A false positive in project scope can affect symbol resolution in later
    results. Therefore declaration-looking prose is not enough: the mathematical
    form itself must be explicitly definitional, a typed map declaration, or an
    explicitly scoped convention.
    """

    if kind in {IntroductionKind.DEFINE, IntroductionKind.SET}:
        return candidate.definition_operator is not None
    if kind == IntroductionKind.LET:
        return candidate.definition_operator is not None or (
            candidate.role == SymbolRole.MAP and _MAP_TAIL_RE.match(tail) is not None
        )
    if kind == IntroductionKind.FOR:
        return (
            candidate.constraint_relation is not None
            and _PROJECT_CONVENTION_TAIL_RE.match(tail) is not None
        )
    return False


def _standard_candidate(
    file: FrontendFile,
    math: FrontendMath,
    kind: IntroductionKind,
    projection: LinguisticProjection,
) -> tuple[int, _Candidate] | None:
    content, content_start = _math_inner(file, math)
    candidates = _parse_candidates(content, kind)

    # ``Let A=[-1,1]`` is a definitional introduction. Reuse the shared SET
    # equality grammar instead of maintaining a second project-only parser;
    # preserve LET as the actual introduction kind when the symbol is appended.
    if kind == IntroductionKind.LET and not candidates:
        candidates = _parse_candidates(content, IntroductionKind.SET)

    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    tail = projection.text[
        math.span.end_offset : min(len(file.raw), math.span.end_offset + 96)
    ]
    if not _candidate_is_authoritative_project_context(
        kind=kind,
        candidate=candidate,
        tail=tail,
    ):
        return None
    return content_start, candidate


def _alias_candidate(
    file: FrontendFile,
    left_math: FrontendMath,
    right_math: FrontendMath,
) -> tuple[int, _Candidate] | None:
    left, left_start = _math_inner(file, left_math)
    right, _ = _math_inner(file, right_math)
    infix = _INFIX_ALIAS_RE.fullmatch(left)
    if infix is None:
        return None
    return (
        left_start,
        _Candidate(
            name=infix.group("name"),
            name_start=infix.start("name"),
            name_end=infix.end("name"),
            arity=2,
            definition_operator=":=",
            definition_rhs=right.strip(),
        ),
    )


def _already_declared(
    table: SymbolTable,
    *,
    candidate: _Candidate,
    content_start: int,
    file: FrontendFile,
) -> bool:
    source = _span(
        file.path,
        file.raw,
        content_start + candidate.name_start,
        content_start + candidate.name_end,
    )
    canonical = canonical_symbol_name(candidate.name)
    return any(
        symbol.scope_identifier == "project"
        and canonical_symbol_name(symbol.name) == canonical
        and symbol.source.file == source.file
        and symbol.source.start_offset == source.start_offset
        and symbol.source.end_offset == source.end_offset
        for symbol in table.symbols
    )


def _append_project_candidate(
    table: SymbolTable,
    file: FrontendFile,
    *,
    candidate: _Candidate,
    content_start: int,
    kind: IntroductionKind,
    introduction_start: int,
    introduction_end: int,
) -> Symbol | None:
    if _already_declared(
        table,
        candidate=candidate,
        content_start=content_start,
        file=file,
    ):
        return None
    return _append_candidate(
        table=table,
        file=file,
        content_start=content_start,
        candidate=candidate,
        kind=kind,
        scope_identifier="project",
        result_identifier=None,
        introduction_start=introduction_start,
        introduction_end=introduction_end,
    )


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


def _record_project_declaration_uses(
    project: ParsedProject,
    table: SymbolTable,
    symbols: list[Symbol],
    *,
    workspace: ProjectWorkspaceFacts,
    projections: dict[str, LinguisticProjection],
    existing: set[tuple[str, str, int, int]],
) -> None:
    """Record exact math-symbol references between explicit project declarations."""

    files = {file.path: file for file in project.files}
    for owner in symbols:
        file = files.get(owner.introduction_source.file)
        projection = projections.get(owner.introduction_source.file)
        if file is None or projection is None:
            continue
        for math in file.math:
            if not (
                owner.introduction_source.start_offset <= math.span.start_offset
                and math.span.end_offset <= owner.introduction_source.end_offset
                and projection.source_span_eligible(math.span)
            ):
                continue
            content, content_start = _math_inner(file, math)
            masked = _masked_content(content)
            for symbol in symbols:
                for start, end in _symbol_occurrences(masked, symbol.name):
                    source = _span(
                        file.path,
                        file.raw,
                        content_start + start,
                        content_start + end,
                    )
                    if _is_declaration_occurrence(table, symbol.name, source):
                        continue
                    key = (symbol.name, source.file, source.start_offset, source.end_offset)
                    if key in existing:
                        continue
                    resolved = table.resolve(
                        symbol.name,
                        "project",
                        source,
                        workspace=workspace,
                    )
                    table.uses.append(
                        SymbolUse(
                            name=symbol.name,
                            scope_identifier="project",
                            source=source,
                            raw=source.text(file.raw),
                            resolved_symbol_identifier=(
                                resolved.identifier if resolved is not None else None
                            ),
                        )
                    )
                    existing.add(key)


def _record_uses(
    project: ParsedProject,
    regions: list[ResultRegion],
    table: SymbolTable,
    added: list[Symbol],
    *,
    workspace: ProjectWorkspaceFacts,
    projections: dict[str, LinguisticProjection],
) -> None:
    """Record project-symbol uses with occurrence-aware resolution."""

    files = {file.path: file for file in project.files}
    existing = {
        (use.name, use.source.file, use.source.start_offset, use.source.end_offset)
        for use in table.uses
    }
    project_symbols = [
        symbol
        for symbol in table.symbols
        if table.scope(symbol.scope_identifier).kind == ScopeKind.PROJECT
    ]
    _record_project_declaration_uses(
        project,
        table,
        project_symbols,
        workspace=workspace,
        projections=projections,
        existing=existing,
    )

    if not added:
        return

    for region in regions:
        file = files.get(region.file)
        projection = projections.get(region.file)
        if file is None or projection is None:
            continue
        spans = [(region.statement_span, ScopeKind.STATEMENT)]
        if region.proof_span is not None:
            spans.append((region.proof_span, ScopeKind.PROOF))
        for span, kind in spans:
            for math in file.math:
                if not (
                    span.start_offset <= math.span.start_offset
                    and math.span.end_offset <= span.end_offset
                    and projection.source_span_eligible(math.span)
                ):
                    continue
                content, content_start = _math_inner(file, math)
                masked = _masked_content(content)
                for symbol in added:
                    for start, end in _symbol_occurrences(masked, symbol.name):
                        source = _span(
                            file.path,
                            file.raw,
                            content_start + start,
                            content_start + end,
                        )
                        if _is_declaration_occurrence(table, symbol.name, source):
                            continue
                        key = (symbol.name, source.file, source.start_offset, source.end_offset)
                        if key in existing:
                            continue
                        scope = _scope_for_use(
                            table,
                            result_identifier=region.identifier,
                            kind=kind,
                            source=source,
                        )
                        if scope is None:
                            continue
                        resolved = table.resolve(
                            symbol.name,
                            scope,
                            source,
                            workspace=workspace,
                        )
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
                        existing.add(key)


def _sort_key(
    lookup: ProjectPositionLookup,
    source: SourceSpan,
) -> tuple[tuple[int, ...], str, int, int]:
    try:
        project_key = lookup.sort_key(source.file, source.start_offset)
    except KeyError:
        project_key = (10**12, source.start_offset)
    return project_key, source.file, source.start_offset, source.end_offset


def add_project_authoritative_context(
    project: ParsedProject,
    regions: list[ResultRegion],
    table: SymbolTable,
    *,
    workspace: ProjectWorkspaceFacts | None,
) -> None:
    """Recover conservative authoritative declarations outside result regions.

    Declaration parsing is shared with ``symbol_extract``. This layer adds only
    project-scope policy, the explicit infix ``to mean`` bridge, and use recording
    for symbols discovered after base extraction. Source-role eligibility comes from
    the reversible normalized projection and project visibility from workspace facts.
    """

    if workspace is None or workspace.resolution != WorkspaceResolution.RESOLVED:
        return

    projections = {file.path: build_linguistic_projection(file) for file in project.files}
    if any(not projection.complete for projection in projections.values()):
        return

    regions_by_file: dict[str, list[ResultRegion]] = {}
    for region in regions:
        regions_by_file.setdefault(region.file, []).append(region)

    added: list[Symbol] = []
    for file in project.files:
        projection = projections[file.path]
        file_regions = regions_by_file.get(file.path, [])
        outside = [
            math
            for math in file.math
            if not _inside_result_region(math.span, file_regions)
            and projection.source_span_eligible(math.span)
        ]
        for index, math in enumerate(outside):
            cue = _cue_for_math(file, math, projection)
            if cue is None:
                continue
            kind, introduction_start = cue

            if kind == IntroductionKind.DEFINE and index + 1 < len(outside):
                next_math = outside[index + 1]
                bridge = projection.text[math.span.end_offset : next_math.span.start_offset]
                if _ALIAS_BRIDGE_RE.fullmatch(bridge) is not None:
                    parsed_alias = _alias_candidate(file, math, next_math)
                    if parsed_alias is not None:
                        content_start, candidate = parsed_alias
                        symbol = _append_project_candidate(
                            table,
                            file,
                            candidate=candidate,
                            content_start=content_start,
                            kind=kind,
                            introduction_start=introduction_start,
                            introduction_end=next_math.span.end_offset,
                        )
                        if symbol is not None:
                            added.append(symbol)
                            continue

            parsed = _standard_candidate(file, math, kind, projection)
            if parsed is None:
                continue
            content_start, candidate = parsed
            symbol = _append_project_candidate(
                table,
                file,
                candidate=candidate,
                content_start=content_start,
                kind=kind,
                introduction_start=introduction_start,
                introduction_end=math.span.end_offset,
            )
            if symbol is not None:
                added.append(symbol)

    _record_uses(
        project,
        regions,
        table,
        added,
        workspace=workspace,
        projections=projections,
    )
    lookup = ProjectPositionLookup(workspace)
    table.symbols.sort(key=lambda item: _sort_key(lookup, item.source))
    table.definitions.sort(key=lambda item: _sort_key(lookup, item.source))
    table.constraints.sort(key=lambda item: _sort_key(lookup, item.source))
    table.uses.sort(key=lambda item: (*_sort_key(lookup, item.source), item.name))
