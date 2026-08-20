import pytest
from pydantic import ValidationError

from thorn.frontend import SourceSpan
from thorn.workspace import (
    IncludeResolution,
    IncludeSite,
    ProjectWorkspaceFacts,
    SourceOccurrence,
    WorkspaceResolution,
)


def _span(file: str) -> SourceSpan:
    return SourceSpan(
        file=file,
        start_offset=0,
        end_offset=8,
        start_line=1,
        start_column=1,
        end_line=1,
        end_column=9,
    )


def test_repeated_file_occurrences_have_distinct_identity() -> None:
    facts = ProjectWorkspaceFacts(
        root_file="main.tex",
        resolution=WorkspaceResolution.RESOLVED,
        occurrences=[
            SourceOccurrence(occurrence_id="o0", file="main.tex", ordinal=0),
            SourceOccurrence(
                occurrence_id="o1", file="part.tex", ordinal=1, via_include_id="i0"
            ),
            SourceOccurrence(
                occurrence_id="o2", file="part.tex", ordinal=2, via_include_id="i1"
            ),
        ],
        includes=[
            IncludeSite(
                include_id="i0",
                parent_occurrence_id="o0",
                target_written="part",
                resolved_file="part.tex",
                source=_span("main.tex"),
                resolution=IncludeResolution.RESOLVED,
                child_occurrence_id="o1",
            ),
            IncludeSite(
                include_id="i1",
                parent_occurrence_id="o0",
                target_written="part",
                resolved_file="part.tex",
                source=_span("main.tex"),
                resolution=IncludeResolution.RESOLVED,
                child_occurrence_id="o2",
            ),
        ],
    )
    assert [x.file for x in facts.occurrences] == ["main.tex", "part.tex", "part.tex"]


def test_expanded_order_is_explicit_and_contiguous() -> None:
    with pytest.raises(ValidationError, match="contiguous expanded order"):
        ProjectWorkspaceFacts(
            root_file="main.tex",
            resolution=WorkspaceResolution.RESOLVED,
            occurrences=[SourceOccurrence(occurrence_id="o0", file="main.tex", ordinal=1)],
        )


def test_include_parent_must_be_occurrence_not_path() -> None:
    with pytest.raises(ValidationError, match="include parent"):
        ProjectWorkspaceFacts(
            root_file="main.tex",
            resolution=WorkspaceResolution.PARTIAL,
            occurrences=[SourceOccurrence(occurrence_id="o0", file="main.tex", ordinal=0)],
            includes=[
                IncludeSite(
                    include_id="i0",
                    parent_occurrence_id="main.tex",
                    source=_span("main.tex"),
                    resolution=IncludeResolution.UNRESOLVED,
                )
            ],
        )
