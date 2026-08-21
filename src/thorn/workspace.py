from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from thorn.frontend import (
    FrontendDiagnosticKind,
    FrontendFile,
    FrontendMacro,
    ParsedProject,
    SourceSpan,
)
from thorn.project_partiality import IncludeTarget, classify_includes


class WorkspaceResolution(StrEnum):
    RESOLVED = "resolved"
    PARTIAL = "partial"
    SOURCE_ERROR = "source_error"


class IncludeResolution(StrEnum):
    RESOLVED = "resolved"
    MISSING = "missing"
    CYCLE = "cycle"
    UNRESOLVED = "unresolved"


class WorkspaceDiagnosticKind(StrEnum):
    MISSING_FILE = "missing_file"
    INCLUDE_CYCLE = "include_cycle"
    UNSUPPORTED_DYNAMIC_STRUCTURE = "unsupported_dynamic_structure"
    SOURCE_ERROR = "source_error"
    BACKEND_LIMITATION = "backend_limitation"


class SourceOccurrence(BaseModel):
    """One occurrence of a source file in expanded project order."""

    occurrence_id: str
    file: str
    ordinal: int = Field(ge=0)
    via_include_id: str | None = None


class IncludeSite(BaseModel):
    include_id: str
    parent_occurrence_id: str
    command: str | None = None
    target_written: str | None = None
    resolved_file: str | None = None
    source: SourceSpan
    resolution: IncludeResolution
    child_occurrence_id: str | None = None


class LabelFact(BaseModel):
    name: str
    occurrence_id: str
    source: SourceSpan


class ReferenceFact(BaseModel):
    name: str
    occurrence_id: str
    source: SourceSpan
    definition: SourceSpan | None = None


class WorkspaceDiagnostic(BaseModel):
    kind: WorkspaceDiagnosticKind
    message: str
    source: SourceSpan | None = None


class ProjectWorkspaceFacts(BaseModel):
    """Thorn-owned normalized source/workspace fact boundary."""

    root_file: str
    resolution: WorkspaceResolution
    occurrences: list[SourceOccurrence] = Field(default_factory=list)
    includes: list[IncludeSite] = Field(default_factory=list)
    labels: list[LabelFact] = Field(default_factory=list)
    references: list[ReferenceFact] = Field(default_factory=list)
    diagnostics: list[WorkspaceDiagnostic] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_occurrence_identity(self) -> ProjectWorkspaceFacts:
        occurrence_ids = [item.occurrence_id for item in self.occurrences]
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("source occurrence ids must be unique")
        ordinals = [item.ordinal for item in self.occurrences]
        if ordinals != list(range(len(ordinals))):
            raise ValueError("source occurrence ordinals must be contiguous expanded order")
        known = set(occurrence_ids)
        include_ids: set[str] = set()
        for site in self.includes:
            if site.include_id in include_ids:
                raise ValueError("include ids must be unique")
            include_ids.add(site.include_id)
            if site.parent_occurrence_id not in known:
                raise ValueError("include parent must name a source occurrence")
            if site.child_occurrence_id is not None and site.child_occurrence_id not in known:
                raise ValueError("include child must name a source occurrence")
        for occurrence in self.occurrences:
            if (
                occurrence.via_include_id is not None
                and occurrence.via_include_id not in include_ids
            ):
                raise ValueError("occurrence via_include_id must name an include site")
        for label in self.labels:
            if label.occurrence_id not in known:
                raise ValueError("label facts must name a source occurrence")
        for reference in self.references:
            if reference.occurrence_id not in known:
                raise ValueError("reference facts must name a source occurrence")
        return self


@dataclass(frozen=True, order=True)
class ProjectPosition:
    """One occurrence-aware source position in expanded project order."""

    order_key: tuple[int, ...]
    occurrence_id: str = field(compare=False)
    file: str = field(compare=False)
    offset: int = field(compare=False)


class ProjectPositionLookup:
    """Resolve source points to comparable occurrence-aware project positions."""

    def __init__(self, facts: ProjectWorkspaceFacts) -> None:
        self.facts = facts
        self._occurrences = {item.occurrence_id: item for item in facts.occurrences}
        self._includes = {item.include_id: item for item in facts.includes}
        self._prefixes: dict[str, tuple[int, ...]] = {}
        for occurrence in facts.occurrences:
            self._prefixes[occurrence.occurrence_id] = self._prefix(occurrence)

    def _prefix(self, occurrence: SourceOccurrence) -> tuple[int, ...]:
        existing = self._prefixes.get(occurrence.occurrence_id)
        if existing is not None:
            return existing
        if occurrence.via_include_id is None:
            return ()
        include = self._includes[occurrence.via_include_id]
        parent = self._occurrences[include.parent_occurrence_id]
        return self._prefix(parent) + (include.source.start_offset, 1)

    def occurrences_for_file(self, file: str | Path) -> list[SourceOccurrence]:
        requested = str(file)
        exact = [item for item in self.facts.occurrences if item.file == requested]
        if exact:
            return exact
        resolved = str(Path(file).resolve())
        return [
            item
            for item in self.facts.occurrences
            if str(Path(item.file).resolve()) == resolved
        ]

    def positions(self, file: str | Path, offset: int) -> list[ProjectPosition]:
        if offset < 0:
            raise ValueError("source offset must be non-negative")
        return [
            ProjectPosition(
                order_key=self._prefixes[item.occurrence_id] + (offset, 0),
                occurrence_id=item.occurrence_id,
                file=item.file,
                offset=offset,
            )
            for item in self.occurrences_for_file(file)
        ]

    def earliest_position(self, file: str | Path, offset: int) -> ProjectPosition:
        positions = self.positions(file, offset)
        if not positions:
            raise KeyError(f"source file has no project occurrence: {file!s}")
        return min(positions)

    def sort_key(self, file: str | Path, offset: int) -> tuple[int, ...]:
        return self.earliest_position(file, offset).order_key


@dataclass(frozen=True)
class _IncludeDirective:
    command: str
    target_written: str | None
    source: SourceSpan
    target: IncludeTarget | None
    diagnostic_message: str | None = None
    malformed: bool = False


def _required_argument(macro: FrontendMacro) -> str | None:
    for argument in macro.arguments:
        if not argument.optional:
            return argument.value.strip()
    return None


def _include_directives(file: FrontendFile) -> list[_IncludeDirective]:
    targets, partiality = classify_includes(file)
    targets_by_start = {item.source.start_offset: item for item in targets}
    partiality_by_start = {
        item.source.start_offset: item
        for item in partiality
        if item.source is not None
    }
    directives: list[_IncludeDirective] = []
    for macro in sorted(file.macros, key=lambda item: item.span.start_offset):
        target = targets_by_start.get(macro.span.start_offset)
        diagnostic = partiality_by_start.get(macro.span.start_offset)
        if target is None and diagnostic is None:
            continue
        if target is not None:
            directives.append(
                _IncludeDirective(
                    command=macro.name,
                    target_written=target.value,
                    source=target.source,
                    target=target,
                )
            )
            continue
        assert diagnostic is not None
        reason = diagnostic.message.rsplit(": ", 1)[-1]
        directives.append(
            _IncludeDirective(
                command=macro.name,
                target_written=_required_argument(macro),
                source=diagnostic.source or macro.span,
                target=None,
                diagnostic_message=diagnostic.message,
                malformed=reason in {
                    "complete direct target is unavailable",
                    "direct target is empty",
                },
            )
        )
    return directives


def _target_path(file: FrontendFile, target: str) -> str:
    child = Path(target)
    if child.suffix == "":
        child = child.with_suffix(".tex")
    return str((Path(file.path).parent / child).resolve())


def _workspace_resolution(diagnostics: list[WorkspaceDiagnostic]) -> WorkspaceResolution:
    if any(item.kind == WorkspaceDiagnosticKind.SOURCE_ERROR for item in diagnostics):
        return WorkspaceResolution.SOURCE_ERROR
    if diagnostics:
        return WorkspaceResolution.PARTIAL
    return WorkspaceResolution.RESOLVED


def build_project_workspace_facts(project: ParsedProject) -> ProjectWorkspaceFacts:
    """Build occurrence-aware workspace facts from normalized frontend facts.

    The resolver performs only deterministic orchestration of already-normalized
    macro/diagnostic facts. It does not rescan source text or expand TeX macros.
    """

    root = str(Path(project.main_file).resolve())
    files = {str(Path(file.path).resolve()): file for file in project.files}
    occurrences: list[SourceOccurrence] = []
    includes: list[IncludeSite] = []
    labels: list[LabelFact] = []
    references: list[ReferenceFact] = []
    diagnostics: list[WorkspaceDiagnostic] = []
    include_count = 0
    represented_partiality: set[tuple[str, int]] = set()

    for diagnostic in project.diagnostics:
        if diagnostic.kind == FrontendDiagnosticKind.PARSE_ERROR:
            diagnostics.append(
                WorkspaceDiagnostic(
                    kind=WorkspaceDiagnosticKind.SOURCE_ERROR,
                    message=diagnostic.message,
                    source=diagnostic.source,
                )
            )
        elif diagnostic.kind == FrontendDiagnosticKind.UNSUPPORTED_CONSTRUCT:
            diagnostics.append(
                WorkspaceDiagnostic(
                    kind=WorkspaceDiagnosticKind.BACKEND_LIMITATION,
                    message=diagnostic.message,
                    source=diagnostic.source,
                )
            )

    def visit(file_path: str, via_include_id: str | None, active: tuple[str, ...]) -> None:
        nonlocal include_count
        file = files.get(file_path)
        if file is None:
            return
        occurrence_id = f"o{len(occurrences)}"
        occurrences.append(
            SourceOccurrence(
                occurrence_id=occurrence_id,
                file=file_path,
                ordinal=len(occurrences),
                via_include_id=via_include_id,
            )
        )

        for macro in file.macros:
            argument = _required_argument(macro)
            if not argument:
                continue
            if macro.name == "label":
                labels.append(
                    LabelFact(
                        name=argument,
                        occurrence_id=occurrence_id,
                        source=macro.span,
                    )
                )
            elif macro.name in {"ref", "eqref", "cref", "Cref", "autoref"}:
                for name in (item.strip() for item in argument.split(",")):
                    if name:
                        references.append(
                            ReferenceFact(name=name, occurrence_id=occurrence_id, source=macro.span)
                        )

        for directive in _include_directives(file):
            include_id = f"i{include_count}"
            include_count += 1
            if directive.target is None:
                represented_partiality.add((file.path, directive.source.start_offset))
                diagnostics.append(
                    WorkspaceDiagnostic(
                        kind=(
                            WorkspaceDiagnosticKind.SOURCE_ERROR
                            if directive.malformed
                            else WorkspaceDiagnosticKind.UNSUPPORTED_DYNAMIC_STRUCTURE
                        ),
                        message=directive.diagnostic_message or "unresolved project structure",
                        source=directive.source,
                    )
                )
                includes.append(
                    IncludeSite(
                        include_id=include_id,
                        parent_occurrence_id=occurrence_id,
                        command=directive.command,
                        target_written=directive.target_written,
                        source=directive.source,
                        resolution=IncludeResolution.UNRESOLVED,
                    )
                )
                continue

            child_path = _target_path(file, directive.target.value)
            if child_path not in files:
                diagnostics.append(
                    WorkspaceDiagnostic(
                        kind=WorkspaceDiagnosticKind.MISSING_FILE,
                        message=f"included LaTeX file not found: {child_path}",
                        source=directive.source,
                    )
                )
                includes.append(
                    IncludeSite(
                        include_id=include_id,
                        parent_occurrence_id=occurrence_id,
                        command=directive.command,
                        target_written=directive.target.value,
                        source=directive.source,
                        resolution=IncludeResolution.MISSING,
                    )
                )
                continue

            if child_path in active:
                diagnostics.append(
                    WorkspaceDiagnostic(
                        kind=WorkspaceDiagnosticKind.INCLUDE_CYCLE,
                        message=f"include cycle reaches active source file: {child_path}",
                        source=directive.source,
                    )
                )
                includes.append(
                    IncludeSite(
                        include_id=include_id,
                        parent_occurrence_id=occurrence_id,
                        command=directive.command,
                        target_written=directive.target.value,
                        resolved_file=child_path,
                        source=directive.source,
                        resolution=IncludeResolution.CYCLE,
                    )
                )
                continue

            child_occurrence_id = f"o{len(occurrences)}"
            includes.append(
                IncludeSite(
                    include_id=include_id,
                    parent_occurrence_id=occurrence_id,
                    command=directive.command,
                    target_written=directive.target.value,
                    resolved_file=child_path,
                    source=directive.source,
                    resolution=IncludeResolution.RESOLVED,
                    child_occurrence_id=child_occurrence_id,
                )
            )
            visit(child_path, include_id, (*active, child_path))

    if root in files:
        visit(root, None, (root,))
    else:
        diagnostics.append(
            WorkspaceDiagnostic(
                kind=WorkspaceDiagnosticKind.MISSING_FILE,
                message=f"project root is unavailable in normalized frontend facts: {root}",
            )
        )

    for diagnostic in project.diagnostics:
        if diagnostic.kind != FrontendDiagnosticKind.PROJECT_PARTIALITY:
            continue
        if diagnostic.source is not None and (
            diagnostic.source.file,
            diagnostic.source.start_offset,
        ) in represented_partiality:
            continue
        diagnostics.append(
            WorkspaceDiagnostic(
                kind=WorkspaceDiagnosticKind.BACKEND_LIMITATION,
                message=diagnostic.message,
                source=diagnostic.source,
            )
        )

    definitions: dict[str, list[SourceSpan]] = {}
    for label in labels:
        definitions.setdefault(label.name, []).append(label.source)
    references = [
        reference.model_copy(
            update={"definition": definitions[reference.name][0]}
        )
        if len(definitions.get(reference.name, [])) == 1
        else reference
        for reference in references
    ]

    return ProjectWorkspaceFacts(
        root_file=root,
        resolution=_workspace_resolution(diagnostics),
        occurrences=occurrences,
        includes=includes,
        labels=labels,
        references=references,
        diagnostics=diagnostics,
    )
