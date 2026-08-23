from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from thorn.dependencies import ExtractedProject
from thorn.eval_review import build_result_review_context
from thorn.frontend import SourceSpan
from thorn.semantic_dependencies import result_project_symbol_dependency_ids
from thorn.symbols import Symbol, SymbolUse, canonical_symbol_name
from thorn.workspace import ProjectPositionLookup


class ExactSourceObservation(BaseModel):
    """Exact source occurrence used by provenance/evidence A/B comparisons."""

    file: str
    start_offset: int
    end_offset: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    @classmethod
    def from_span(cls, source: SourceSpan) -> ExactSourceObservation:
        return cls(
            file=source.file,
            start_offset=source.start_offset,
            end_offset=source.end_offset,
            start_line=source.start_line,
            start_column=source.start_column,
            end_line=source.end_line,
            end_column=source.end_column,
        )


class SemanticDeclarationObservation(BaseModel):
    """Dependency-observable declaration state without source coordinates."""

    key: str
    name: str
    role: str
    arity: int | None = None
    scope_kind: str
    result_identifier: str | None = None
    definition_expressions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class SemanticUseResolutionObservation(BaseModel):
    """One dependency-relevant occurrence and its canonical resolution."""

    key: str
    name: str
    scope_kind: str
    result_identifier: str | None = None
    target_key: str | None = None


class SemanticResultDependencyObservation(BaseModel):
    """Observable dependency/review closure for one theorem-like result."""

    result_identifier: str
    direct_result_dependencies: list[str] = Field(default_factory=list)
    transitive_result_dependencies: list[str] = Field(default_factory=list)
    project_declaration_dependencies: list[str] = Field(default_factory=list)
    review_declarations: list[str] = Field(default_factory=list)
    review_result_dependencies: list[str] = Field(default_factory=list)
    uncertain_support_relations: list[str] = Field(default_factory=list)


class DependencySemanticSnapshot(BaseModel):
    """Current-source projection of proof-dependency semantic observables ``Q``.

    Exact source positions are intentionally absent. Two source histories should not become
    different mathematics merely because equivalent material occurs at different offsets.
    Stable local keys preserve graph identity for differential tests without embedding raw
    provenance into semantic equality.
    """

    workspace_resolution: str | None = None
    declarations: list[SemanticDeclarationObservation] = Field(default_factory=list)
    uses: list[SemanticUseResolutionObservation] = Field(default_factory=list)
    results: list[SemanticResultDependencyObservation] = Field(default_factory=list)


class DeclarationProvenanceObservation(BaseModel):
    """Exact evidence decorating one semantically matched declaration."""

    key: str
    source: ExactSourceObservation
    introduction_source: ExactSourceObservation


class UseProvenanceObservation(BaseModel):
    """Exact evidence decorating one semantically matched source use."""

    key: str
    source: ExactSourceObservation


class DependencyProvenanceSnapshot(BaseModel):
    """Exact provenance/evidence projection ``P`` kept separate from semantic equality."""

    declarations: list[DeclarationProvenanceObservation] = Field(default_factory=list)
    uses: list[UseProvenanceObservation] = Field(default_factory=list)


class DependencyObservationSnapshot(BaseModel):
    """A/B oracle split into semantic ``Q`` and exact-provenance ``P`` projections."""

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


def _semantic_symbol_keys(symbols: list[Symbol]) -> dict[str, str]:
    """Assign source-coordinate-free local graph keys by canonical name and occurrence."""

    ordinals: dict[str, int] = defaultdict(int)
    keys: dict[str, str] = {}
    for symbol in symbols:
        name = canonical_symbol_name(symbol.name)
        ordinal = ordinals[name]
        ordinals[name] += 1
        keys[symbol.identifier] = f"{name}#{ordinal}"
    return keys


def _semantic_use_keys(uses: list[SymbolUse]) -> dict[str, str]:
    """Assign coordinate-free local keys to uses for provenance correspondence."""

    ordinals: dict[str, int] = defaultdict(int)
    keys: dict[str, str] = {}
    for use in uses:
        name = canonical_symbol_name(use.name)
        ordinal = ordinals[name]
        ordinals[name] += 1
        keys[use.identifier] = f"{name}-use#{ordinal}"
    return keys


def snapshot_dependency_observations(
    project: ExtractedProject,
) -> DependencyObservationSnapshot:
    """Project canonical behaviour onto semantic ``Q`` and exact-evidence ``P``.

    ``semantic`` intentionally omits raw source coordinates and introduction wording.
    ``provenance`` carries exact source authority for semantically matched graph elements.
    Continuation-sensitive equivalence is tested by applying the same future source
    continuation to both extraction paths and comparing another semantic snapshot.
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
    symbol_keys = _semantic_symbol_keys(symbols)
    use_keys = _semantic_use_keys(uses)

    definitions_by_symbol: dict[str, list[str]] = {}
    for definition in table.definitions:
        definitions_by_symbol.setdefault(definition.symbol_identifier, []).append(
            definition.expression_latex
        )

    constraints_by_symbol: dict[str, list[str]] = {}
    for constraint in table.constraints:
        constraints_by_symbol.setdefault(constraint.symbol_identifier, []).append(
            f"{constraint.relation} {constraint.expression_latex}"
        )

    declarations = [
        SemanticDeclarationObservation(
            key=symbol_keys[symbol.identifier],
            name=canonical_symbol_name(symbol.name),
            role=symbol.role.value,
            arity=symbol.arity,
            scope_kind=table.scope(symbol.scope_identifier).kind.value,
            result_identifier=symbol.result_identifier,
            definition_expressions=sorted(definitions_by_symbol.get(symbol.identifier, [])),
            constraints=sorted(constraints_by_symbol.get(symbol.identifier, [])),
        )
        for symbol in symbols
    ]
    declaration_provenance = [
        DeclarationProvenanceObservation(
            key=symbol_keys[symbol.identifier],
            source=ExactSourceObservation.from_span(symbol.source),
            introduction_source=ExactSourceObservation.from_span(symbol.introduction_source),
        )
        for symbol in symbols
    ]

    semantic_uses: list[SemanticUseResolutionObservation] = []
    use_provenance: list[UseProvenanceObservation] = []
    for use in uses:
        scope = table.scope(use.scope_identifier)
        key = use_keys[use.identifier]
        semantic_uses.append(
            SemanticUseResolutionObservation(
                key=key,
                name=canonical_symbol_name(use.name),
                scope_kind=scope.kind.value,
                result_identifier=scope.result_identifier,
                target_key=(
                    symbol_keys.get(use.resolved_symbol_identifier)
                    if use.resolved_symbol_identifier is not None
                    else None
                ),
            )
        )
        use_provenance.append(
            UseProvenanceObservation(
                key=key,
                source=ExactSourceObservation.from_span(use.source),
            )
        )

    results: list[SemanticResultDependencyObservation] = []
    for unit in project.units:
        review = build_result_review_context(project, unit.identifier).items[0]
        project_targets = [
            symbol_keys[identifier]
            for identifier in result_project_symbol_dependency_ids(project, unit.identifier)
        ]
        review_declarations = sorted(
            symbol_keys[symbol.identifier]
            for symbol in review.symbols
            if symbol.identifier in symbol_keys
        )
        results.append(
            SemanticResultDependencyObservation(
                result_identifier=unit.identifier,
                direct_result_dependencies=project.dependency_graph.direct_dependency_ids(
                    unit.identifier
                ),
                transitive_result_dependencies=project.dependency_graph.transitive_dependency_ids(
                    unit.identifier
                ),
                project_declaration_dependencies=project_targets,
                review_declarations=review_declarations,
                review_result_dependencies=sorted(
                    dependency.identifier for dependency in review.dependencies
                ),
                uncertain_support_relations=sorted(review.trigger_relation_identifiers),
            )
        )

    workspace_resolution = (
        project.workspace.resolution.value if project.workspace is not None else None
    )
    return DependencyObservationSnapshot(
        semantic=DependencySemanticSnapshot(
            workspace_resolution=workspace_resolution,
            declarations=declarations,
            uses=semantic_uses,
            results=results,
        ),
        provenance=DependencyProvenanceSnapshot(
            declarations=declaration_provenance,
            uses=use_provenance,
        ),
    )
