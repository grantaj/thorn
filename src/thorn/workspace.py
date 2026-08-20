from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from thorn.frontend import SourceSpan


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
    """One occurrence of a source file in expanded project order.

    The same file may appear more than once. `occurrence_id`, rather than the
    path, is therefore the identity consumed by downstream scope/provenance code.
    """

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
    """Thorn-owned normalized source/workspace fact boundary.

    This model deliberately contains no mathematical authority, scope,
    shadowing, materiality, or Proof-IR decisions.
    """

    root_file: str
    resolution: WorkspaceResolution
    occurrences: list[SourceOccurrence] = Field(default_factory=list)
    includes: list[IncludeSite] = Field(default_factory=list)
    labels: list[LabelFact] = Field(default_factory=list)
    references: list[ReferenceFact] = Field(default_factory=list)
    diagnostics: list[WorkspaceDiagnostic] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_occurrence_identity(self) -> "ProjectWorkspaceFacts":
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
        for fact in [*self.labels, *self.references]:
            if fact.occurrence_id not in known:
                raise ValueError("reference facts must name a source occurrence")
        return self
