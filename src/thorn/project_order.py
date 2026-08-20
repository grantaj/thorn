from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from thorn.frontend import SourceSpan


class ProjectOrderStatus(StrEnum):
    """Confidence in the normalized project order supplied by a workspace backend."""

    RESOLVED = "resolved"
    PARTIAL = "partial"
    SOURCE_ERROR = "source_error"


class ProjectRootBasis(StrEnum):
    """How the backend established the main document/root fact."""

    REQUESTED = "requested"
    DISCOVERED = "discovered"
    CONFIGURED = "configured"


class IncludeResolution(StrEnum):
    RESOLVED = "resolved"
    MISSING = "missing"
    UNRESOLVED = "unresolved"
    CYCLE = "cycle"


class ProjectDiagnosticKind(StrEnum):
    MISSING_FILE = "missing_file"
    INCLUDE_CYCLE = "include_cycle"
    UNSUPPORTED_DYNAMIC_STRUCTURE = "unsupported_dynamic_structure"
    SOURCE_ERROR = "source_error"
    BACKEND_LIMITATION = "backend_limitation"


class ReferenceKind(StrEnum):
    LABEL_DEFINITION = "label_definition"
    REFERENCE_USE = "reference_use"


class ProjectRoot(BaseModel):
    """Normalized project-root fact; it carries no mathematical semantics."""

    main_file: str
    workspace_root: str
    basis: ProjectRootBasis


class FileOccurrence(BaseModel):
    """One execution occurrence of a physical source file in expanded order."""

    identifier: str
    file: str
    parent_include_identifier: str | None = None
    depth: int = Field(ge=0)


class IncludeOccurrence(BaseModel):
    """One executed include site, distinguished even when source text repeats."""

    identifier: str
    parent_file_occurrence_identifier: str
    source: SourceSpan
    command: str
    raw_target: str
    resolved_file: str | None = None
    resolution: IncludeResolution


class ExpandedSourceChunk(BaseModel):
    """A source interval whose global position is known without crossing an include.

    Chunks, rather than a flat file list, preserve return-to-parent order. The same
    physical span may occur more than once when its file is included repeatedly;
    `file_occurrence_identifier` is therefore part of source identity.
    """

    identifier: str
    file_occurrence_identifier: str
    source: SourceSpan
    order_index: int = Field(ge=0)


class ReferenceOccurrence(BaseModel):
    """Occurrence-aware label/reference source fact."""

    identifier: str
    file_occurrence_identifier: str
    kind: ReferenceKind
    name: str
    source: SourceSpan


class ProjectOrderDiagnostic(BaseModel):
    kind: ProjectDiagnosticKind
    message: str
    source: SourceSpan | None = None
    include_occurrence_identifier: str | None = None


class ProjectOrder(BaseModel):
    """Thorn-owned, backend-neutral project/workspace fact boundary.

    This model intentionally contains no theorem authority, declaration status,
    mathematical scope, or shadowing decisions. A workspace backend establishes
    source occurrence/order facts; Thorn's semantic layers consume those facts.
    """

    root: ProjectRoot
    status: ProjectOrderStatus
    files: list[FileOccurrence] = Field(default_factory=list)
    includes: list[IncludeOccurrence] = Field(default_factory=list)
    chunks: list[ExpandedSourceChunk] = Field(default_factory=list)
    references: list[ReferenceOccurrence] = Field(default_factory=list)
    diagnostics: list[ProjectOrderDiagnostic] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_occurrence_graph(self) -> ProjectOrder:
        file_by_id = self._unique(self.files, "file occurrence")
        include_by_id = self._unique(self.includes, "include occurrence")
        self._unique(self.chunks, "expanded source chunk")
        self._unique(self.references, "reference occurrence")

        if self.files:
            roots = [item for item in self.files if item.parent_include_identifier is None]
            if len(roots) != 1:
                raise ValueError("ProjectOrder must contain exactly one root file occurrence")
            root = roots[0]
            if root.file != self.root.main_file or root.depth != 0:
                raise ValueError("root file occurrence must match ProjectRoot.main_file at depth zero")

        child_by_include: dict[str, FileOccurrence] = {}
        for file_occurrence in self.files:
            parent_id = file_occurrence.parent_include_identifier
            if parent_id is None:
                continue
            include = include_by_id.get(parent_id)
            if include is None:
                raise ValueError(f"unknown parent include occurrence {parent_id!r}")
            if include.resolution != IncludeResolution.RESOLVED:
                raise ValueError("only resolved includes may own a child file occurrence")
            if include.resolved_file != file_occurrence.file:
                raise ValueError("child file occurrence must match include resolved_file")
            if parent_id in child_by_include:
                raise ValueError("a resolved include occurrence may produce only one child occurrence")
            child_by_include[parent_id] = file_occurrence

        for include in self.includes:
            parent = file_by_id.get(include.parent_file_occurrence_identifier)
            if parent is None:
                raise ValueError(
                    f"unknown include parent file occurrence "
                    f"{include.parent_file_occurrence_identifier!r}"
                )
            if include.source.file != parent.file:
                raise ValueError("include provenance must lie in its parent physical file")
            if include.resolution == IncludeResolution.RESOLVED:
                if include.resolved_file is None:
                    raise ValueError("resolved include requires resolved_file")
                if include.identifier not in child_by_include:
                    raise ValueError("resolved include requires a distinct child file occurrence")
            elif include.identifier in child_by_include:
                raise ValueError("unresolved include cannot have a child file occurrence")

        chunk_indices = sorted(item.order_index for item in self.chunks)
        if chunk_indices != list(range(len(chunk_indices))):
            raise ValueError("expanded source chunk order_index values must be contiguous from zero")
        for chunk in self.chunks:
            owner = file_by_id.get(chunk.file_occurrence_identifier)
            if owner is None:
                raise ValueError(
                    f"unknown chunk file occurrence {chunk.file_occurrence_identifier!r}"
                )
            if chunk.source.file != owner.file:
                raise ValueError("chunk provenance must lie in its physical file occurrence")

        for reference in self.references:
            owner = file_by_id.get(reference.file_occurrence_identifier)
            if owner is None:
                raise ValueError(
                    f"unknown reference file occurrence {reference.file_occurrence_identifier!r}"
                )
            if reference.source.file != owner.file:
                raise ValueError("reference provenance must lie in its physical file occurrence")

        unresolved = any(
            include.resolution != IncludeResolution.RESOLVED for include in self.includes
        )
        source_error = any(
            diagnostic.kind == ProjectDiagnosticKind.SOURCE_ERROR
            for diagnostic in self.diagnostics
        )
        if self.status == ProjectOrderStatus.RESOLVED and (unresolved or source_error):
            raise ValueError("resolved ProjectOrder cannot contain unresolved structure/source error")
        if self.status == ProjectOrderStatus.SOURCE_ERROR and not source_error:
            raise ValueError("source_error ProjectOrder requires a source-error diagnostic")

        return self

    @staticmethod
    def _unique(items: list[BaseModel], description: str) -> dict[str, BaseModel]:
        result: dict[str, BaseModel] = {}
        for item in items:
            identifier = getattr(item, "identifier")
            if identifier in result:
                raise ValueError(f"duplicate {description} identifier {identifier!r}")
            result[identifier] = item
        return result

    def expanded_file_sequence(self) -> list[str]:
        """Return physical files in source-chunk order, retaining repeated occurrences."""

        files_by_id = {item.identifier: item.file for item in self.files}
        sequence: list[str] = []
        last_occurrence: str | None = None
        for chunk in sorted(self.chunks, key=lambda item: item.order_index):
            if chunk.file_occurrence_identifier == last_occurrence:
                continue
            sequence.append(files_by_id[chunk.file_occurrence_identifier])
            last_occurrence = chunk.file_occurrence_identifier
        return sequence

    def physical_files(self) -> set[str]:
        """Physical source paths, deliberately distinct from occurrence identity."""

        return {str(Path(item.file)) for item in self.files}
