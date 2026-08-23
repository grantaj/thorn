from __future__ import annotations

import json
from collections import defaultdict

from pydantic import BaseModel, Field

from thorn.dependencies import DependencyResolution, ExtractedProject
from thorn.frontend import SourceSpan
from thorn.models import SourceRange
from thorn.symbols import ScopeKind, Symbol, SymbolUse, canonical_symbol_name
from thorn.workspace import ProjectPositionLookup


class SourceEvidenceObservation(BaseModel):
    """Source evidence carried by the assurance projection ``P``."""

    file: str
    start_line: int
    end_line: int
    start_offset: int | None = None
    end_offset: int | None = None
    start_column: int | None = None
    end_column: int | None = None

    @classmethod
    def from_span(cls, source: SourceSpan) -> SourceEvidenceObservation:
        return cls(
            file=source.file,
            start_line=source.start_line,
            end_line=source.end_line,
            start_offset=source.start_offset,
            end_offset=source.end_offset,
            start_column=source.start_column,
            end_column=source.end_column,
        )

    @classmethod
    def from_range(cls, source: SourceRange) -> SourceEvidenceObservation:
        return cls(
            file=source.file,
            start_line=source.start_line,
            end_line=source.end_line,
        )


class SemanticNodeObservation(BaseModel):
    """One labelled dependency node in the bounded executable ``Q`` projection."""

    key: str
    namespace: str
    binding: str | None = None
    payload: list[str] = Field(default_factory=list)
    visibility_owner: str | None = None
    shadow_rank: int | None = None


class SemanticResolutionObservation(BaseModel):
    """A source occurrence's dependency-relevant resolution, without coordinates."""

    namespace: str
    binding: str
    context_key: str
    target_key: str | None = None
    status: str


class SemanticRequirementObservation(BaseModel):
    """One direct prerequisite relation in the bounded executable ``Q`` projection."""

    owner_key: str
    prerequisite_key: str | None = None
    unresolved_reference: str | None = None
    status: str


class DependencySemanticSnapshot(BaseModel):
    """Canonicalized bounded projection of proof-dependency semantic observables ``Q``.

    The projection excludes source coordinates, parser roles, review-selection policy,
    and transitive closure. Keys come from dependency-observable content, not source
    coordinates. Equality therefore ignores irrelevant relocation and independent
    ordering.
    """

    workspace_resolution: str | None = None
    nodes: list[SemanticNodeObservation] = Field(default_factory=list)
    resolutions: list[SemanticResolutionObservation] = Field(default_factory=list)
    requirements: list[SemanticRequirementObservation] = Field(default_factory=list)


class NodeProvenanceObservation(BaseModel):
    """Exact available evidence decorating one semantically matched node."""

    node_key: str
    sources: list[SourceEvidenceObservation] = Field(default_factory=list)


class ResolutionProvenanceObservation(BaseModel):
    """Exact evidence for one source-backed resolution observation."""

    namespace: str
    binding: str
    context_key: str
    target_key: str | None = None
    status: str
    source: SourceEvidenceObservation


class RequirementProvenanceObservation(BaseModel):
    """Source evidence for one direct prerequisite relation."""

    owner_key: str
    prerequisite_key: str | None = None
    unresolved_reference: str | None = None
    status: str
    source: SourceEvidenceObservation
    source_occurrence_ids: list[str] = Field(default_factory=list)
    target_occurrence_ids: list[str] = Field(default_factory=list)


class DependencyProvenanceSnapshot(BaseModel):
    """Assurance projection ``P`` kept separate from semantic equality."""

    nodes: list[NodeProvenanceObservation] = Field(default_factory=list)
    resolutions: list[ResolutionProvenanceObservation] = Field(default_factory=list)
    requirements: list[RequirementProvenanceObservation] = Field(default_factory=list)


class DependencyObservationSnapshot(BaseModel):
    """Migration oracle with separate semantic ``Q`` and assurance ``P`` projections."""

    semantic: DependencySemanticSnapshot
    provenance: DependencyProvenanceSnapshot


def _source_key(source: SourceSpan) -> tuple[str, int, int, int, int, int, int]:
    return (
        source.file,
        source.start_offset,
        source.end_offset,
        source.start_line,
        source.start_column,
        source.end_line,
        source.end_column,
    )


def _project_source_key(
    lookup: ProjectPositionLookup | None,
    source: SourceSpan,
) -> tuple[tuple[int, ...], str, int, int, int, int, int, int]:
    project_key: tuple[int, ...]
    if lookup is None:
        project_key = (10**12, source.start_offset)
    else:
        try:
            project_key = lookup.sort_key(source.file, source.start_offset)
        except KeyError:
            project_key = (10**12, source.start_offset)
    return project_key, *_source_key(source)


def _canonical_key(prefix: str, *parts: object) -> str:
    encoded = json.dumps(
        parts,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{prefix}:{encoded}"


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def _result_keys(project: ExtractedProject) -> dict[str, str]:
    keys: dict[str, str] = {}
    for unit in project.units:
        binding = unit.label
        payload = _normalized_text(unit.statement)
        keys[unit.identifier] = _canonical_key("result", binding, payload)
    return keys


def _definition_facts(project: ExtractedProject) -> dict[str, list[str]]:
    table = project.symbol_table
    facts: dict[str, list[str]] = {}
    for definition in table.definitions:
        facts.setdefault(definition.symbol_identifier, []).append(
            f":= {_normalized_text(definition.expression_latex)}"
        )
    for constraint in table.constraints:
        facts.setdefault(constraint.symbol_identifier, []).append(
            f"{constraint.relation} {_normalized_text(constraint.expression_latex)}"
        )
    for symbol in table.symbols:
        if symbol.domain_latex:
            facts.setdefault(symbol.identifier, []).append(
                f"domain {_normalized_text(symbol.domain_latex)}"
            )
        if symbol.codomain_latex:
            facts.setdefault(symbol.identifier, []).append(
                f"codomain {_normalized_text(symbol.codomain_latex)}"
            )
    return {identifier: sorted(values) for identifier, values in facts.items()}


def _visibility_owner(
    project: ExtractedProject,
    symbol: Symbol,
    result_keys: dict[str, str],
) -> str | None:
    scope = project.symbol_table.scope(symbol.scope_identifier)
    if scope.kind == ScopeKind.PROJECT:
        return None
    if scope.result_identifier is None:
        return None
    return result_keys.get(scope.result_identifier)


def _semantic_symbol_keys(
    project: ExtractedProject,
    symbols: list[Symbol],
    result_keys: dict[str, str],
    facts: dict[str, list[str]],
) -> tuple[dict[str, str], dict[str, int]]:
    """Build content-addressed keys with order only where shadowing can observe it."""

    current_rank: dict[tuple[str | None, str], int] = defaultdict(int)
    previous_payload: dict[tuple[str | None, str], tuple[str, ...]] = {}
    keys: dict[str, str] = {}
    ranks: dict[str, int] = {}

    for symbol in symbols:
        binding = canonical_symbol_name(symbol.name)
        owner = _visibility_owner(project, symbol, result_keys)
        group = (owner, binding)
        payload = tuple(facts.get(symbol.identifier, []))
        if group in previous_payload and previous_payload[group] != payload:
            current_rank[group] += 1
        previous_payload[group] = payload
        rank = current_rank[group]
        keys[symbol.identifier] = _canonical_key(
            "symbol",
            owner,
            binding,
            rank,
            payload,
        )
        ranks[symbol.identifier] = rank
    return keys, ranks


def _span_contains(outer: SourceSpan, inner: SourceSpan) -> bool:
    return (
        outer.file == inner.file
        and outer.start_offset <= inner.start_offset
        and inner.end_offset <= outer.end_offset
    )


def _project_owner_for_use(
    project: ExtractedProject,
    use: SymbolUse,
    symbols: list[Symbol],
    symbol_keys: dict[str, str],
) -> str:
    candidates = [
        symbol
        for symbol in symbols
        if project.symbol_table.scope(symbol.scope_identifier).kind == ScopeKind.PROJECT
        and _span_contains(symbol.introduction_source, use.source)
    ]
    if not candidates:
        return "project-context"
    owner = min(
        candidates,
        key=lambda item: (
            item.introduction_source.end_offset - item.introduction_source.start_offset
        ),
    )
    return symbol_keys[owner.identifier]


def _resolution_context(
    project: ExtractedProject,
    use: SymbolUse,
    symbols: list[Symbol],
    symbol_keys: dict[str, str],
    result_keys: dict[str, str],
) -> str:
    scope = project.symbol_table.scope(use.scope_identifier)
    if scope.result_identifier is not None:
        return result_keys.get(
            scope.result_identifier,
            f"result:{scope.result_identifier}",
        )
    return _project_owner_for_use(project, use, symbols, symbol_keys)


def _requirement_key(item: SemanticRequirementObservation) -> tuple[str, str, str, str]:
    return (
        item.owner_key,
        item.prerequisite_key or "",
        item.unresolved_reference or "",
        item.status,
    )


def snapshot_dependency_observations(
    project: ExtractedProject,
) -> DependencyObservationSnapshot:
    """Project canonical behaviour onto bounded semantic ``Q`` and evidence ``P``.

    This is a migration witness, not a serialization of the current IR. It keeps direct
    dependency structure, binding/resolution state, mathematical payload, and capability
    status. Review policy, parser taxonomies, source coordinates, and derived transitive
    closure are excluded from semantic equality.
    """

    table = project.symbol_table
    lookup = (
        ProjectPositionLookup(project.workspace)
        if project.workspace is not None
        else None
    )
    symbols = sorted(
        table.symbols,
        key=lambda item: _project_source_key(lookup, item.source),
    )
    uses = sorted(
        table.uses,
        key=lambda item: (*_project_source_key(lookup, item.source), item.name),
    )
    result_keys = _result_keys(project)
    facts = _definition_facts(project)
    symbol_keys, shadow_ranks = _semantic_symbol_keys(
        project, symbols, result_keys, facts
    )

    nodes: list[SemanticNodeObservation] = []
    node_provenance: list[NodeProvenanceObservation] = []

    for unit in project.units:
        key = result_keys[unit.identifier]
        nodes.append(
            SemanticNodeObservation(
                key=key,
                namespace="result",
                binding=unit.label,
                payload=[_normalized_text(unit.statement)],
            )
        )
        node_provenance.append(
            NodeProvenanceObservation(
                node_key=key,
                sources=[SourceEvidenceObservation.from_range(unit.statement_range)],
            )
        )

    for symbol in symbols:
        key = symbol_keys[symbol.identifier]
        nodes.append(
            SemanticNodeObservation(
                key=key,
                namespace="symbol",
                binding=canonical_symbol_name(symbol.name),
                payload=facts.get(symbol.identifier, []),
                visibility_owner=_visibility_owner(project, symbol, result_keys),
                shadow_rank=shadow_ranks[symbol.identifier],
            )
        )
        sources = [SourceEvidenceObservation.from_span(symbol.source)]
        introduction = SourceEvidenceObservation.from_span(symbol.introduction_source)
        if introduction != sources[0]:
            sources.append(introduction)
        node_provenance.append(
            NodeProvenanceObservation(node_key=key, sources=sources)
        )

    resolution_by_key: dict[
        tuple[str, str, str, str | None, str],
        SemanticResolutionObservation,
    ] = {}
    resolution_provenance: list[ResolutionProvenanceObservation] = []

    for use in uses:
        binding = canonical_symbol_name(use.name)
        context_key = _resolution_context(
            project,
            use,
            symbols,
            symbol_keys,
            result_keys,
        )
        target_key = (
            symbol_keys.get(use.resolved_symbol_identifier)
            if use.resolved_symbol_identifier is not None
            else None
        )
        status = "resolved" if target_key is not None else "unresolved"
        semantic = SemanticResolutionObservation(
            namespace="symbol",
            binding=binding,
            context_key=context_key,
            target_key=target_key,
            status=status,
        )
        resolution_by_key[
            (semantic.namespace, binding, context_key, target_key, status)
        ] = semantic
        resolution_provenance.append(
            ResolutionProvenanceObservation(
                namespace="symbol",
                binding=binding,
                context_key=context_key,
                target_key=target_key,
                status=status,
                source=SourceEvidenceObservation.from_span(use.source),
            )
        )

    requirement_by_key: dict[
        tuple[str, str, str, str],
        SemanticRequirementObservation,
    ] = {}
    requirement_provenance: list[RequirementProvenanceObservation] = []

    for edge in project.dependency_graph.edges:
        owner_key = result_keys.get(edge.source_identifier)
        if owner_key is None:
            continue
        target_key = (
            result_keys.get(edge.target_identifier)
            if edge.target_identifier is not None
            else None
        )
        status = edge.resolution.value
        requirement = SemanticRequirementObservation(
            owner_key=owner_key,
            prerequisite_key=target_key,
            unresolved_reference=(
                edge.target_label
                if edge.resolution != DependencyResolution.RESOLVED
                else None
            ),
            status=status,
        )
        requirement_by_key[_requirement_key(requirement)] = requirement
        requirement_provenance.append(
            RequirementProvenanceObservation(
                owner_key=owner_key,
                prerequisite_key=target_key,
                unresolved_reference=requirement.unresolved_reference,
                status=status,
                source=SourceEvidenceObservation.from_range(edge.source),
                source_occurrence_ids=edge.source_occurrence_ids,
                target_occurrence_ids=edge.target_occurrence_ids,
            )
        )

    project_symbols = {
        symbol.identifier
        for symbol in symbols
        if table.scope(symbol.scope_identifier).kind == ScopeKind.PROJECT
    }

    for use in uses:
        target_identifier = use.resolved_symbol_identifier
        if target_identifier is None or target_identifier not in project_symbols:
            continue
        prerequisite_key = symbol_keys[target_identifier]
        scope = table.scope(use.scope_identifier)
        if scope.result_identifier is not None:
            owner_key = result_keys.get(scope.result_identifier)
        else:
            owner_key = _project_owner_for_use(
                project,
                use,
                symbols,
                symbol_keys,
            )
            if owner_key == "project-context":
                owner_key = None
        if owner_key is None:
            continue
        requirement = SemanticRequirementObservation(
            owner_key=owner_key,
            prerequisite_key=prerequisite_key,
            status="resolved",
        )
        requirement_by_key[_requirement_key(requirement)] = requirement
        requirement_provenance.append(
            RequirementProvenanceObservation(
                owner_key=owner_key,
                prerequisite_key=prerequisite_key,
                status="resolved",
                source=SourceEvidenceObservation.from_span(use.source),
            )
        )

    workspace_resolution = (
        project.workspace.resolution.value if project.workspace is not None else None
    )
    return DependencyObservationSnapshot(
        semantic=DependencySemanticSnapshot(
            workspace_resolution=workspace_resolution,
            nodes=sorted(nodes, key=lambda item: item.key),
            resolutions=sorted(
                resolution_by_key.values(),
                key=lambda item: (
                    item.namespace,
                    item.binding,
                    item.context_key,
                    item.target_key or "",
                    item.status,
                ),
            ),
            requirements=sorted(
                requirement_by_key.values(),
                key=_requirement_key,
            ),
        ),
        provenance=DependencyProvenanceSnapshot(
            nodes=sorted(node_provenance, key=lambda item: item.node_key),
            resolutions=sorted(
                resolution_provenance,
                key=lambda item: (
                    item.namespace,
                    item.binding,
                    item.context_key,
                    item.target_key or "",
                    item.status,
                    item.source.file,
                    item.source.start_line,
                    item.source.start_offset or -1,
                ),
            ),
            requirements=sorted(
                requirement_provenance,
                key=lambda item: (
                    item.owner_key,
                    item.prerequisite_key or "",
                    item.unresolved_reference or "",
                    item.status,
                    item.source.file,
                    item.source.start_line,
                    item.source.start_offset or -1,
                ),
            ),
        ),
    )
