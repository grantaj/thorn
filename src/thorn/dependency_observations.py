from __future__ import annotations

from pydantic import BaseModel, Field

from thorn.dependencies import ExtractedProject
from thorn.eval_review import build_result_review_context
from thorn.frontend import SourceSpan
from thorn.semantic_dependencies import result_project_symbol_dependency_ids
from thorn.symbols import Symbol, canonical_symbol_name
from thorn.workspace import ProjectPositionLookup


class ExactSourceObservation(BaseModel):
    """Exact source occurrence used by dependency-observational A/B comparisons."""

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


class DeclarationObservation(BaseModel):
    """Dependency-observable declaration state, independent of introduction wording."""

    key: str
    name: str
    role: str
    arity: int | None = None
    scope_kind: str
    result_identifier: str | None = None
    source: ExactSourceObservation
    introduction_source: ExactSourceObservation
    definition_expressions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class UseResolutionObservation(BaseModel):
    """One extant source occurrence and the canonical declaration it resolves to."""

    name: str
    scope_kind: str
    result_identifier: str | None = None
    source: ExactSourceObservation
    target_key: str | None = None


class ResultDependencyObservation(BaseModel):
    """Observable dependency/review closure for one theorem-like result."""

    result_identifier: str
    direct_result_dependencies: list[str] = Field(default_factory=list)
    transitive_result_dependencies: list[str] = Field(default_factory=list)
    project_declaration_dependencies: list[str] = Field(default_factory=list)
    review_declarations: list[str] = Field(default_factory=list)
    review_result_dependencies: list[str] = Field(default_factory=list)
    uncertain_support_relations: list[str] = Field(default_factory=list)


class DependencyObservationSnapshot(BaseModel):
    """Current-source projection of the proof-dependency observable family ``Q``.

    This is deliberately not a serialization of Thorn's internal IR. It records the
    semantic observations on which competing extraction/elaboration paths are to be
    compared. Continuation-sensitive equivalence is tested by applying the same future
    source continuation to both paths and taking another snapshot.
    """

    workspace_resolution: str | None = None
    declarations: list[DeclarationObservation] = Field(default_factory=list)
    uses: list[UseResolutionObservation] = Field(default_factory=list)
    results: list[ResultDependencyObservation] = Field(default_factory=list)


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


def _symbol_key(symbol: Symbol) -> str:
    source = symbol.source
    return (
        f"{canonical_symbol_name(symbol.name)}@{source.file}:"
        f"{source.start_offset}:{source.end_offset}"
    )


def snapshot_dependency_observations(
    project: ExtractedProject,
) -> DependencyObservationSnapshot:
    """Project current canonical state onto dependency-observable A/B behaviour.

    The snapshot intentionally omits surface introduction kinds and support-relation
    taxonomies. Those distinctions should be preserved by a replacement only if a
    dependency query demonstrates that they are observable. Exact provenance, resolution,
    project order, scope, closure, uncertainty and bounded review reachability are retained.
    """

    table = project.symbol_table
    lookup = (
        ProjectPositionLookup(project.workspace)
        if project.workspace is not None
        else None
    )
    symbol_keys = {symbol.identifier: _symbol_key(symbol) for symbol in table.symbols}

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
        DeclarationObservation(
            key=symbol_keys[symbol.identifier],
            name=canonical_symbol_name(symbol.name),
            role=symbol.role.value,
            arity=symbol.arity,
            scope_kind=table.scope(symbol.scope_identifier).kind.value,
            result_identifier=symbol.result_identifier,
            source=ExactSourceObservation.from_span(symbol.source),
            introduction_source=ExactSourceObservation.from_span(symbol.introduction_source),
            definition_expressions=sorted(definitions_by_symbol.get(symbol.identifier, [])),
            constraints=sorted(constraints_by_symbol.get(symbol.identifier, [])),
        )
        for symbol in sorted(
            table.symbols,
            key=lambda item: _project_source_key(lookup, item.source),
        )
    ]

    uses = []
    for use in sorted(
        table.uses,
        key=lambda item: (*_project_source_key(lookup, item.source), item.name),
    ):
        scope = table.scope(use.scope_identifier)
        uses.append(
            UseResolutionObservation(
                name=canonical_symbol_name(use.name),
                scope_kind=scope.kind.value,
                result_identifier=scope.result_identifier,
                source=ExactSourceObservation.from_span(use.source),
                target_key=(
                    symbol_keys.get(use.resolved_symbol_identifier)
                    if use.resolved_symbol_identifier is not None
                    else None
                ),
            )
        )

    results: list[ResultDependencyObservation] = []
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
            ResultDependencyObservation(
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
        workspace_resolution=workspace_resolution,
        declarations=declarations,
        uses=uses,
        results=results,
    )
