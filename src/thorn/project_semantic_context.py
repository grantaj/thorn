from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from thorn.frontend import FrontendFile, ParsedProject, SourceSpan
from thorn.linguistic_declarations import (
    ProseDeclarationCandidate,
    ProseDeclarationCapability,
    ProseDeclarationInventory,
    ProseDeclarationRole,
)
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
    ProjectPosition,
    ProjectPositionLookup,
    ProjectWorkspaceFacts,
    WorkspaceResolution,
)


@dataclass(frozen=True)
class _AuthoritySite:
    """One occurrence-specific Thorn authority decision for normalized evidence."""

    candidate: ProseDeclarationCandidate
    position: ProjectPosition

    @property
    def identifier(self) -> str:
        return (
            f"semantic:{self.position.occurrence_id}:"
            f"{self.candidate.term_source.file}:"
            f"{self.candidate.term_source.start_offset}"
        )


@dataclass(frozen=True)
class _UseCandidate:
    matched_term: str
    file: str
    start: int
    end: int
    position: ProjectPosition
    result_identifier: str | None
    scope_kind: ScopeKind
    owner_identifier: str | None = None
    ambient_scope: bool = False

    def logical_key(self) -> tuple[str, int, int, str, str | None, ScopeKind, str | None, bool]:
        """Path-level use identity whose occurrence resolutions must agree."""

        return (
            self.file,
            self.start,
            self.end,
            _normalized_term(self.matched_term),
            self.result_identifier,
            self.scope_kind,
            self.owner_identifier,
            self.ambient_scope,
        )


@dataclass(frozen=True)
class _Resolution:
    candidate: _UseCandidate
    target_identifier: str | None


@dataclass(frozen=True)
class _ResolvedUse:
    candidate: _UseCandidate
    target_identifier: str


def _normalized_term(term: str) -> str:
    """Normalize presentation whitespace only; do not infer lexical variants."""

    return " ".join(term.split()).casefold()


def _term_pattern(term: str) -> re.Pattern[str]:
    """Match the exact normalized declaration term without bespoke morphology."""

    pieces = [re.escape(piece) for piece in term.split()]
    if not pieces:
        return re.compile(r"(?!)")
    body = r"\s+".join(pieces)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _mask_range(characters: list[str], start: int, end: int) -> None:
    for index in range(max(0, start), min(len(characters), end)):
        if characters[index] != "\n":
            characters[index] = " "


def _has_substantive_payload(
    file: FrontendFile,
    projection: LinguisticProjection,
    candidate: ProseDeclarationCandidate,
) -> bool:
    """Apply the #167 fail-closed authority rule to exact candidate provenance."""

    payload = candidate.payload_source
    if payload is None or payload.file != file.path:
        return False
    if not (
        candidate.source.start_offset <= payload.start_offset <= payload.end_offset
        <= candidate.source.end_offset
    ):
        return False

    characters = list(projection.text[payload.start_offset : payload.end_offset])
    syntax_starts: list[int] = []
    for macro in file.macros:
        if macro.span.end_offset <= payload.start_offset or payload.end_offset <= macro.span.start_offset:
            continue
        if projection.token_containing(
            macro.span.start_offset,
            kind=ProjectionTokenKind.MATH,
        ) is not None:
            continue
        start = max(payload.start_offset, macro.span.start_offset) - payload.start_offset
        end = min(payload.end_offset, macro.span.end_offset) - payload.start_offset
        syntax_starts.append(start)
        _mask_range(characters, start, end)

    visible_starts = [
        index for index, character in enumerate(characters) if character.isalnum()
    ]
    visible_starts.extend(
        max(payload.start_offset, token.source.start_offset) - payload.start_offset
        for token in projection.tokens
        if token.kind == ProjectionTokenKind.MATH
        and token.source.end_offset > payload.start_offset
        and token.source.start_offset < payload.end_offset
    )
    if not visible_starts:
        return False
    first_payload = min(visible_starts)

    # Do not join a declaration cue to later prose across opaque TeX syntax.
    return not any(start < first_payload for start in syntax_starts)


def _eligible_sites(
    project: ParsedProject,
    inventory: ProseDeclarationInventory,
    workspace: ProjectWorkspaceFacts,
    projections: dict[str, LinguisticProjection],
) -> list[_AuthoritySite]:
    """Adjudicate candidate eligibility without rebuilding linguistic grammar."""

    if workspace.resolution != WorkspaceResolution.RESOLVED:
        return []
    if inventory.capability != ProseDeclarationCapability.COMPLETE:
        return []

    files = {file.path: file for file in project.files}
    lookup = ProjectPositionLookup(workspace)
    sites: list[_AuthoritySite] = []
    for candidate in inventory.candidates:
        file = files.get(candidate.source.file)
        projection = projections.get(candidate.source.file)
        if file is None or projection is None or not projection.complete:
            continue
        if not candidate.term.strip() or not _has_substantive_payload(file, projection, candidate):
            continue
        for position in lookup.positions(
            candidate.source.file,
            candidate.source.end_offset,
        ):
            sites.append(_AuthoritySite(candidate=candidate, position=position))

    return sorted(
        sites,
        key=lambda site: (
            site.position.order_key,
            _normalized_term(site.candidate.term),
            site.candidate.role.value,
        ),
    )


def _position_for_occurrence(
    lookup: ProjectPositionLookup,
    *,
    file: str,
    offset: int,
    occurrence_id: str,
) -> ProjectPosition | None:
    return next(
        (
            position
            for position in lookup.positions(file, offset)
            if position.occurrence_id == occurrence_id
        ),
        None,
    )


def _use_candidates(
    project: ParsedProject,
    regions: list[ResultRegion],
    sites: list[_AuthoritySite],
    projections: dict[str, LinguisticProjection],
    workspace: ProjectWorkspaceFacts,
) -> list[_UseCandidate]:
    lookup = ProjectPositionLookup(workspace)
    files = {file.path: file for file in project.files}
    terms: dict[str, str] = {}
    for site in sites:
        terms.setdefault(_normalized_term(site.candidate.term), site.candidate.term)
    patterns = [(term, _term_pattern(term)) for term in terms.values()]

    candidates: list[_UseCandidate] = []

    # Explicit result uses seed semantic reachability. Every physical source use
    # is evaluated in every workspace occurrence of that source; a later consensus
    # step refuses authority if those occurrence contexts disagree.
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
                    start = span.start_offset + match.start()
                    end = span.start_offset + match.end()
                    for position in lookup.positions(file.path, start):
                        candidates.append(
                            _UseCandidate(
                                matched_term=term,
                                file=file.path,
                                start=start,
                                end=end,
                                position=position,
                                result_identifier=region.identifier,
                                scope_kind=scope_kind,
                            )
                        )

    # Ambient candidates establish forward scope without requiring later results
    # to repeat the convention subject. They remain subject to occurrence-aware
    # ordering and same-term shadowing below.
    ambient_terms: dict[str, str] = {}
    for site in sites:
        if site.candidate.role == ProseDeclarationRole.AMBIENT:
            ambient_terms.setdefault(
                _normalized_term(site.candidate.term),
                site.candidate.term,
            )
    for region in regions:
        projection = projections.get(region.file)
        if region.file not in files or projection is None or not projection.complete:
            continue
        start = region.statement_span.start_offset
        for term in ambient_terms.values():
            for position in lookup.positions(region.file, start):
                candidates.append(
                    _UseCandidate(
                        matched_term=term,
                        file=region.file,
                        start=start,
                        end=start,
                        position=position,
                        result_identifier=region.identifier,
                        scope_kind=ScopeKind.STATEMENT,
                        ambient_scope=True,
                    )
                )

    # An authoritative declaration may depend on an earlier authoritative prose
    # declaration. Scan only exact normalized candidate terms in the already
    # eligible source projection; no declaration grammar or morphology lives here.
    for owner in sites:
        projection = projections[owner.candidate.source.file]
        source = owner.candidate.source
        text = projection.text[source.start_offset : source.end_offset]
        for term, pattern in patterns:
            for match in pattern.finditer(text):
                start = source.start_offset + match.start()
                end = source.start_offset + match.end()
                own_term = owner.candidate.term_source
                if start < own_term.end_offset and own_term.start_offset < end:
                    continue
                position = _position_for_occurrence(
                    lookup,
                    file=source.file,
                    offset=start,
                    occurrence_id=owner.position.occurrence_id,
                )
                if position is None:
                    continue
                candidates.append(
                    _UseCandidate(
                        matched_term=term,
                        file=source.file,
                        start=start,
                        end=end,
                        position=position,
                        result_identifier=None,
                        scope_kind=ScopeKind.PROJECT,
                        owner_identifier=owner.identifier,
                    )
                )

    return candidates


def _resolve_candidates(
    sites: list[_AuthoritySite],
    candidates: list[_UseCandidate],
) -> list[_Resolution]:
    resolved: list[_Resolution] = []
    for candidate in candidates:
        eligible = [
            site
            for site in sites
            if _normalized_term(site.candidate.term)
            == _normalized_term(candidate.matched_term)
            and (not candidate.ambient_scope or site.candidate.role == ProseDeclarationRole.AMBIENT)
            and site.position < candidate.position
        ]
        target = max(eligible, key=lambda site: site.position) if eligible else None
        resolved.append(
            _Resolution(
                candidate=candidate,
                target_identifier=target.identifier if target is not None else None,
            )
        )
    return resolved


def _consensus_resolved_uses(resolutions: list[_Resolution]) -> list[_ResolvedUse]:
    """Collapse path-level uses only when all occurrence contexts agree exactly."""

    groups: dict[
        tuple[str, int, int, str, str | None, ScopeKind, str | None, bool],
        list[_Resolution],
    ] = {}
    for resolution in resolutions:
        groups.setdefault(resolution.candidate.logical_key(), []).append(resolution)

    out: list[_ResolvedUse] = []
    for group in groups.values():
        targets = {resolution.target_identifier for resolution in group}
        if len(targets) != 1:
            continue
        target = next(iter(targets))
        if target is None:
            continue
        out.append(_ResolvedUse(candidate=group[0].candidate, target_identifier=target))
    return out


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
    site: _AuthoritySite,
) -> Symbol:
    candidate = site.candidate
    identifier = site.identifier
    symbol = Symbol(
        identifier=identifier,
        name=candidate.term,
        role=SymbolRole.UNKNOWN,
        introduction_kind=(
            IntroductionKind.DEFINE
            if candidate.role == ProseDeclarationRole.DEFINITION
            else IntroductionKind.FOR
        ),
        scope_identifier="project",
        source=candidate.term_source,
        introduction_source=candidate.source,
        raw_introduction=candidate.source.text(file.raw),
    )
    table.symbols.append(symbol)
    if candidate.role == ProseDeclarationRole.DEFINITION:
        table.definitions.append(
            Definition(
                identifier=f"{identifier}:definition",
                symbol_identifier=identifier,
                operator=":=",
                expression_latex="",
                source=candidate.source,
                raw=candidate.source.text(file.raw),
            )
        )
    else:
        table.constraints.append(
            Constraint(
                identifier=f"{identifier}:convention",
                symbol_identifier=identifier,
                relation=":",
                expression_latex="",
                source=candidate.source,
                raw=candidate.source.text(file.raw),
            )
        )
    return symbol


def _project_source_key(
    lookup: ProjectPositionLookup,
    source: SourceSpan,
) -> tuple[int, ...]:
    try:
        return lookup.sort_key(source.file, source.start_offset)
    except KeyError:
        return (10**12, source.start_offset)


def add_project_semantic_context(
    project: ParsedProject,
    regions: list[ResultRegion],
    table: SymbolTable,
    *,
    workspace: ProjectWorkspaceFacts,
    prose_declarations: ProseDeclarationInventory,
) -> None:
    """Apply Thorn-owned prose authority, visibility, shadowing, and reachability.

    This layer consumes only normalized declaration candidates, reversible source
    projections, canonical result spans, and occurrence-aware workspace facts.
    It does not recognize declaration phrases, infer lexical morphology, or expose
    linguistic-backend objects downstream.
    """

    if workspace.resolution != WorkspaceResolution.RESOLVED:
        return
    if prose_declarations.capability != ProseDeclarationCapability.COMPLETE:
        return

    files = {file.path: file for file in project.files}
    projections = {
        file.path: build_linguistic_projection(file)
        for file in project.files
    }
    if any(not projection.complete for projection in projections.values()):
        return

    sites = _eligible_sites(project, prose_declarations, workspace, projections)
    if not sites:
        return

    candidates = _use_candidates(project, regions, sites, projections, workspace)
    resolutions = _resolve_candidates(sites, candidates)
    resolved_uses = _consensus_resolved_uses(resolutions)
    active = _reachable_declarations(resolved_uses)
    if not active:
        return

    site_by_id = {site.identifier: site for site in sites}
    active_sites = sorted(
        (site_by_id[identifier] for identifier in active),
        key=lambda site: site.position,
    )

    actual_symbol_ids: dict[str, str] = {}
    for site in active_sites:
        symbol = _append_declaration(
            files[site.candidate.source.file],
            table,
            site,
        )
        actual_symbol_ids[site.identifier] = symbol.identifier

    existing_uses = {
        (
            _normalized_term(use.name),
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
        if candidate.owner_identifier is not None and candidate.owner_identifier not in active:
            continue

        file = files[candidate.file]
        source = file.span(candidate.start, candidate.end)
        target_site = site_by_id[resolved.target_identifier]
        name = target_site.candidate.term
        use_key = (
            _normalized_term(name),
            source.file,
            source.start_offset,
            source.end_offset,
        )
        if use_key in existing_uses:
            continue

        if candidate.result_identifier is None:
            resolved_scope_identifier = "project"
        else:
            resolved_scope_identifier = _scope_for_use(
                table,
                result_identifier=candidate.result_identifier,
                kind=candidate.scope_kind,
                source=source,
            )
            if resolved_scope_identifier is None:
                continue

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

    lookup = ProjectPositionLookup(workspace)
    site_positions = {site.identifier: site.position.order_key for site in active_sites}
    table.symbols.sort(
        key=lambda item: site_positions.get(
            item.identifier,
            _project_source_key(lookup, item.source),
        )
    )
    table.definitions.sort(
        key=lambda item: site_positions.get(
            item.symbol_identifier,
            _project_source_key(lookup, item.source),
        )
    )
    table.constraints.sort(
        key=lambda item: site_positions.get(
            item.symbol_identifier,
            _project_source_key(lookup, item.source),
        )
    )
    table.uses.sort(
        key=lambda item: (
            _project_source_key(lookup, item.source),
            _normalized_term(item.name),
        )
    )
