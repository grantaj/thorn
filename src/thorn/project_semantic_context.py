from __future__ import annotations

import re
from dataclasses import dataclass

from thorn.frontend import FrontendFile, ParsedProject, SourceSpan
from thorn.source_projection import (
    LinguisticProjection,
    ProjectionTokenKind,
    build_linguistic_projection,
)
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
from thorn.workspace import (
    ProjectPositionLookup,
    ProjectWorkspaceFacts,
    build_project_workspace_facts,
)

# This module recognizes declaration *grammar*, never mathematical vocabulary.
# Ordinary prose declarations become review context only when a theorem/proof
# depends on them directly or through another authoritative declaration.
# Explicit ambient cues additionally establish a scope dependency on later
# results. Proximity alone is never a semantic edge.
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


@dataclass(frozen=True)
class _Declaration:
    kind: str
    term: str
    term_start: int
    term_end: int
    source_start: int
    source_end: int


@dataclass(frozen=True)
class _DeclarationSite:
    file: str
    declaration: _Declaration

    @property
    def identifier(self) -> str:
        return f"semantic:{self.file}:{self.declaration.term_start}"


@dataclass(frozen=True)
class _UseCandidate:
    matched_term: str
    file: str
    start: int
    end: int
    result_identifier: str | None
    scope_kind: ScopeKind
    owner_identifier: str | None = None
    ambient_scope: bool = False


@dataclass(frozen=True)
class _ResolvedUse:
    candidate: _UseCandidate
    target_identifier: str


def _mask_range(characters: list[str], start: int, end: int) -> None:
    for index in range(max(0, start), min(len(characters), end)):
        if characters[index] != "\n":
            characters[index] = " "


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


def _has_substantive_payload(
    file: FrontendFile,
    projection: LinguisticProjection,
    *,
    cue_end: int,
    source_end: int,
) -> bool:
    """Return whether a declaration cue has conservative defining content."""

    characters = list(projection.text[cue_end:source_end])
    syntax_starts: list[int] = []
    for macro in file.macros:
        if macro.span.end_offset <= cue_end or source_end <= macro.span.start_offset:
            continue
        if projection.token_containing(
            macro.span.start_offset,
            kind=ProjectionTokenKind.MATH,
        ) is not None:
            continue
        start = max(cue_end, macro.span.start_offset) - cue_end
        end = min(source_end, macro.span.end_offset) - cue_end
        syntax_starts.append(start)
        _mask_range(characters, start, end)

    payload_starts = [
        index for index, character in enumerate(characters) if character.isalnum()
    ]
    payload_starts.extend(
        max(cue_end, token.source.start_offset) - cue_end
        for token in projection.tokens
        if token.kind == ProjectionTokenKind.MATH
        and token.source.end_offset > cue_end
        and token.source.start_offset < source_end
    )
    if not payload_starts:
        return False
    payload_start = min(payload_starts)

    # If opaque/non-math TeX syntax appears before the first visible payload,
    # the source does not establish that the later text is its defining
    # complement. Fail closed rather than joining across the syntax boundary.
    return not any(start < payload_start for start in syntax_starts)


def _declarations(
    file: FrontendFile,
    regions: list[ResultRegion],
    projection: LinguisticProjection,
) -> list[_Declaration]:
    if not projection.complete:
        return []

    candidates: list[_Declaration] = []
    patterns = (
        ("definition", _CALLED_RE),
        ("definition", _SAID_TO_BE_RE),
        ("definition", _WE_SAY_RE),
        ("definition", _BY_MEAN_RE),
        ("ambient", _AMBIENT_RE),
    )
    for kind, pattern in patterns:
        for match in pattern.finditer(projection.text):
            sentence = projection.sentence_span(match.start())
            source_start = sentence.start_offset
            source_end = sentence.end_offset
            if _overlaps_result(source_start, source_end, regions):
                continue
            # A declaration-shaped cue is grammatical evidence, not mathematical
            # authority. Promotion requires an actual defining complement.
            if not _has_substantive_payload(
                file,
                projection,
                cue_end=match.end(),
                source_end=source_end,
            ):
                continue
            raw_term = file.raw[match.start("term") : match.end("term")]
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
    return sorted(
        unique.values(),
        key=lambda item: (item.source_start, item.term.casefold()),
    )


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
    elif (
        final.lower().endswith("s")
        and not final.lower().endswith("ss")
        and len(final) > 1
    ):
        singular = final[:-1]
    if singular is not None:
        variants.append(" ".join([*words[:-1], singular]))
    return tuple(dict.fromkeys(variants))


def _terms_match(left: str, right: str) -> bool:
    left_variants = {item.casefold() for item in _term_variants(left)}
    right_variants = {item.casefold() for item in _term_variants(right)}
    return bool(left_variants & right_variants)


def _term_pattern(term: str) -> re.Pattern[str]:
    alternatives: list[str] = []
    for variant in _term_variants(term):
        pieces = [re.escape(piece) for piece in variant.split()]
        alternatives.append(r"\s+".join(pieces))
    body = "(?:" + "|".join(alternatives) + ")"
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _document_order(
    project: ParsedProject,
    points: set[tuple[str, int]],
    workspace: ProjectWorkspaceFacts | None = None,
) -> dict[tuple[str, int], int]:
    """Assign compatibility point ranks from normalized workspace positions."""

    lookup = ProjectPositionLookup(workspace or build_project_workspace_facts(project))
    # Declaration/use identities remain path-based until the occurrence-aware
    # authority migration in #161 Slice D. Preserve that behavior here by using
    # each path point's earliest occurrence while sourcing all order from the
    # normalized workspace boundary rather than traversing includes again.
    ordered = sorted(points, key=lambda point: lookup.sort_key(*point))
    return {point: index for index, point in enumerate(ordered)}


def _use_candidates(
    project: ParsedProject,
    regions: list[ResultRegion],
    sites: list[_DeclarationSite],
    projections: dict[str, LinguisticProjection],
) -> list[_UseCandidate]:
    files = {file.path: file for file in project.files}
    terms: dict[str, str] = {}
    for site in sites:
        terms.setdefault(site.declaration.term.casefold(), site.declaration.term)
    patterns = [(term, _term_pattern(term)) for term in terms.values()]

    candidates: list[_UseCandidate] = []

    # Direct result uses seed the semantic dependency closure.
    for region in regions:
        file = files.get(region.file)
        projection = projections.get(region.file)
        if file is None or projection is None or not projection.complete:
            continue
        spans = [(region.statement_span, ScopeKind.STATEMENT)]
        if region.proof_span is not None:
            spans.append((region.proof_span, ScopeKind.PROOF))
        for span, scope_kind in spans:
            text = projection.text[span.start_offset : span.end_offset]
            for term, pattern in patterns:
                for match in pattern.finditer(text):
                    candidates.append(
                        _UseCandidate(
                            matched_term=term,
                            file=file.path,
                            start=span.start_offset + match.start(),
                            end=span.start_offset + match.end(),
                            result_identifier=region.identifier,
                            scope_kind=scope_kind,
                        )
                    )

    # Explicit ambient cues are scope declarations: their mathematical purpose
    # is precisely to avoid repeating the subject in every later theorem. Model
    # that as an implicit use at each later statement boundary. Resolution below
    # still enforces forward document order and same-term ambient shadowing.
    ambient_terms: dict[str, str] = {}
    for site in sites:
        if site.declaration.kind == "ambient":
            ambient_terms.setdefault(
                site.declaration.term.casefold(),
                site.declaration.term,
            )
    for region in regions:
        projection = projections.get(region.file)
        if region.file not in files or projection is None or not projection.complete:
            continue
        for term in ambient_terms.values():
            candidates.append(
                _UseCandidate(
                    matched_term=term,
                    file=region.file,
                    start=region.statement_span.start_offset,
                    end=region.statement_span.start_offset,
                    result_identifier=region.identifier,
                    scope_kind=ScopeKind.STATEMENT,
                    ambient_scope=True,
                )
            )

    # Authoritative declarations may themselves depend on earlier prose
    # definitions/conventions. Those edges are required before one-shot rescue.
    for owner in sites:
        file = files[owner.file]
        projection = projections[owner.file]
        declaration = owner.declaration
        text = projection.text[declaration.source_start : declaration.source_end]
        for term, pattern in patterns:
            for match in pattern.finditer(text):
                start = declaration.source_start + match.start()
                end = declaration.source_start + match.end()
                if start < declaration.term_end and declaration.term_start < end:
                    continue
                candidates.append(
                    _UseCandidate(
                        matched_term=term,
                        file=file.path,
                        start=start,
                        end=end,
                        result_identifier=None,
                        scope_kind=ScopeKind.PROJECT,
                        owner_identifier=owner.identifier,
                    )
                )

    return candidates


def _resolve_uses(
    sites: list[_DeclarationSite],
    candidates: list[_UseCandidate],
    order: dict[tuple[str, int], int],
) -> list[_ResolvedUse]:
    site_order = {
        site.identifier: order[(site.file, site.declaration.source_end)]
        for site in sites
    }
    resolved_by_location: dict[
        tuple[str, int, int, str, str | None, ScopeKind, str | None],
        tuple[int, _ResolvedUse],
    ] = {}

    for candidate in candidates:
        use_order = order[(candidate.file, candidate.start)]
        eligible = [
            site
            for site in sites
            if _terms_match(site.declaration.term, candidate.matched_term)
            and (not candidate.ambient_scope or site.declaration.kind == "ambient")
            and site_order[site.identifier] < use_order
        ]
        if not eligible:
            continue
        target = max(eligible, key=lambda site: site_order[site.identifier])
        target_order = site_order[target.identifier]
        key = (
            candidate.file,
            candidate.start,
            candidate.end,
            candidate.matched_term.casefold(),
            candidate.result_identifier,
            candidate.scope_kind,
            candidate.owner_identifier,
        )
        resolved = _ResolvedUse(
            candidate=candidate,
            target_identifier=target.identifier,
        )
        previous = resolved_by_location.get(key)
        if previous is None or target_order > previous[0]:
            resolved_by_location[key] = (target_order, resolved)

    return [item[1] for item in resolved_by_location.values()]


def _reachable_declarations(resolved_uses: list[_ResolvedUse]) -> set[str]:
    active = {
        use.target_identifier
        for use in resolved_uses
        if use.candidate.result_identifier is not None
    }
    dependencies: dict[str, set[str]] = {}
    for use in resolved_uses:
        owner = use.candidate.owner_identifier
        if owner is None:
            continue
        dependencies.setdefault(owner, set()).add(use.target_identifier)

    pending = list(active)
    while pending:
        owner = pending.pop()
        for dependency in dependencies.get(owner, set()):
            if dependency in active:
                continue
            active.add(dependency)
            pending.append(dependency)
    return active


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
    source = file.span(declaration.term_start, declaration.term_end)
    introduction = file.span(declaration.source_start, declaration.source_end)
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


def add_project_semantic_context(
    project: ParsedProject,
    regions: list[ResultRegion],
    table: SymbolTable,
    *,
    workspace: ProjectWorkspaceFacts | None = None,
) -> None:
    """Recover explicit prose semantics as ordinary project-scope symbol edges.

    Ordinary declaration-shaped prose is only eligible source material. It is
    activated when a theorem/proof uses it directly or transitively through
    another activated declaration. Explicit ambient cues are different: the cue
    itself establishes a forward scope dependency on later results, even when
    their wording omits the convention's subject. All lexical matching uses a
    reversible frontend-derived linguistic projection, and all resolution follows
    expanded project/include order.
    """

    regions_by_file: dict[str, list[ResultRegion]] = {}
    for region in regions:
        regions_by_file.setdefault(region.file, []).append(region)

    files = {file.path: file for file in project.files}
    projections = {
        file.path: build_linguistic_projection(file)
        for file in project.files
    }
    sites: list[_DeclarationSite] = []
    for file in project.files:
        file_regions = regions_by_file.get(file.path, [])
        for declaration in _declarations(
            file,
            file_regions,
            projections[file.path],
        ):
            sites.append(_DeclarationSite(file=file.path, declaration=declaration))

    if not sites:
        return

    candidates = _use_candidates(project, regions, sites, projections)
    points = {
        (site.file, site.declaration.source_end)
        for site in sites
    } | {
        (candidate.file, candidate.start)
        for candidate in candidates
    }
    order = _document_order(project, points, workspace)
    resolved_uses = _resolve_uses(sites, candidates, order)
    active = _reachable_declarations(resolved_uses)
    if not active:
        return

    site_by_id = {site.identifier: site for site in sites}
    active_sites = sorted(
        (site_by_id[identifier] for identifier in active),
        key=lambda site: order[(site.file, site.declaration.source_end)],
    )

    actual_symbol_ids: dict[str, str] = {}
    for site in active_sites:
        declaration = site.declaration
        existing = next(
            (
                symbol
                for symbol in table.symbols
                if symbol.name.casefold() == declaration.term.casefold()
                and symbol.source.file == site.file
                and symbol.source.start_offset == declaration.term_start
            ),
            None,
        )
        if existing is not None:
            actual_symbol_ids[site.identifier] = existing.identifier
            continue
        symbol = _append_declaration(files[site.file], table, declaration)
        actual_symbol_ids[site.identifier] = symbol.identifier

    existing_uses = {
        (
            use.name.casefold(),
            use.source.file,
            use.source.start_offset,
            use.source.end_offset,
        )
        for use in table.uses
    }
    for resolved in resolved_uses:
        candidate = resolved.candidate
        if resolved.target_identifier not in active:
            continue
        if (
            candidate.owner_identifier is not None
            and candidate.owner_identifier not in active
        ):
            continue

        file = files[candidate.file]
        source = file.span(candidate.start, candidate.end)
        target_site = site_by_id[resolved.target_identifier]
        name = target_site.declaration.term
        use_key = (name.casefold(), source.file, source.start_offset, source.end_offset)
        if use_key in existing_uses:
            continue

        if candidate.result_identifier is None:
            resolved_scope_identifier = "project"
        else:
            maybe_scope_identifier = _scope_for_use(
                table,
                result_identifier=candidate.result_identifier,
                kind=candidate.scope_kind,
                source=source,
            )
            if maybe_scope_identifier is None:
                continue
            resolved_scope_identifier = maybe_scope_identifier

        table.uses.append(
            SymbolUse(
                name=name,
                scope_identifier=resolved_scope_identifier,
                source=source,
                raw=source.text(file.raw),
                resolved_symbol_identifier=actual_symbol_ids[resolved.target_identifier],
            )
        )
        existing_uses.add(use_key)

    table.symbols.sort(key=lambda item: (item.source.file, item.source.start_offset))
    table.definitions.sort(
        key=lambda item: (item.source.file, item.source.start_offset)
    )
    table.constraints.sort(
        key=lambda item: (item.source.file, item.source.start_offset)
    )
    table.uses.sort(
        key=lambda item: (item.source.file, item.source.start_offset, item.name)
    )
