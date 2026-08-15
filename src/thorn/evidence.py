from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.frontend import SourceSpan


class InferenceStatus(StrEnum):
    """How strongly Thorn's local structural evidence supports an IR relation."""

    CONFIDENT = "confident"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class StructuralEvidence(BaseModel):
    """Parser-neutral evidence retained for later targeted semantic review."""

    reason: str
    source: SourceSpan
    target: SourceSpan | None = None
    context: str
    dependency_path: list[str] = Field(default_factory=list)
    frontend: str | None = None
