from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from thorn.frontend import SourceSpan
from thorn.project_order import (
    ExpandedSourceChunk,
    FileOccurrence,
    IncludeOccurrence,
    IncludeResolution,
    ProjectDiagnosticKind,
    ProjectOrder,
    ProjectOrderDiagnostic,
    ProjectOrderStatus,
    ProjectRoot,
    ProjectRootBasis,
)


def _span(path: Path, start: int, end: int) -> SourceSpan:
    return SourceSpan(
        file=str(path),
        start_offset=start,
        end_offset=end,
        start_line=1,
        start_column=start + 1,
        end_line=1,
        end_column=end + 1,
    )


def _root(main: Path) -> ProjectRoot:
    return ProjectRoot(
        main_file=str(main),
        workspace_root=str(main.parent),
        basis=ProjectRootBasis.REQUESTED,
    )


def test_chunks_preserve_return_to_parent_expansion_order(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    include_span = _span(main, 5, 18)
    order = ProjectOrder(
        root=_root(main),
        status=ProjectOrderStatus.RESOLVED,
        files=[
            FileOccurrence(identifier="f0", file=str(main), depth=0),
            FileOccurrence(
                identifier="f1",
                file=str(child),
                parent_include_identifier="i0",
                depth=1,
            ),
        ],
        includes=[
            IncludeOccurrence(
                identifier="i0",
                parent_file_occurrence_identifier="f0",
                source=include_span,
                command="input",
                raw_target="child",
                resolved_file=str(child),
                resolution=IncludeResolution.RESOLVED,
            )
        ],
        chunks=[
            ExpandedSourceChunk(
                identifier="c0",
                file_occurrence_identifier="f0",
                source=_span(main, 0, 5),
                order_index=0,
            ),
            ExpandedSourceChunk(
                identifier="c1",
                file_occurrence_identifier="f1",
                source=_span(child, 0, 20),
                order_index=1,
            ),
            ExpandedSourceChunk(
                identifier="c2",
                file_occurrence_identifier="f0",
                source=_span(main, 18, 30),
                order_index=2,
            ),
        ],
    )

    assert [Path(path).name for path in order.expanded_file_sequence()] == [
        "main.tex",
        "child.tex",
        "main.tex",
    ]


def test_repeated_include_keeps_distinct_occurrence_identity(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    order = ProjectOrder(
        root=_root(main),
        status=ProjectOrderStatus.RESOLVED,
        files=[
            FileOccurrence(identifier="f0", file=str(main), depth=0),
            FileOccurrence(
                identifier="f1a", file=str(child), parent_include_identifier="i1", depth=1
            ),
            FileOccurrence(
                identifier="f1b", file=str(child), parent_include_identifier="i2", depth=1
            ),
        ],
        includes=[
            IncludeOccurrence(
                identifier="i1",
                parent_file_occurrence_identifier="f0",
                source=_span(main, 0, 13),
                command="input",
                raw_target="child",
                resolved_file=str(child),
                resolution=IncludeResolution.RESOLVED,
            ),
            IncludeOccurrence(
                identifier="i2",
                parent_file_occurrence_identifier="f0",
                source=_span(main, 20, 33),
                command="input",
                raw_target="child",
                resolved_file=str(child),
                resolution=IncludeResolution.RESOLVED,
            ),
        ],
        chunks=[
            ExpandedSourceChunk(
                identifier="c1",
                file_occurrence_identifier="f1a",
                source=_span(child, 0, 10),
                order_index=0,
            ),
            ExpandedSourceChunk(
                identifier="c2",
                file_occurrence_identifier="f1b",
                source=_span(child, 0, 10),
                order_index=1,
            ),
        ],
    )

    assert order.files[1].file == order.files[2].file
    assert order.files[1].identifier != order.files[2].identifier
    assert order.chunks[0].source == order.chunks[1].source
    assert order.chunks[0].file_occurrence_identifier != order.chunks[1].file_occurrence_identifier


def test_unresolved_dynamic_structure_cannot_claim_resolved_order(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    dynamic = IncludeOccurrence(
        identifier="i0",
        parent_file_occurrence_identifier="f0",
        source=_span(main, 10, 32),
        command="input",
        raw_target=r"\chapterfile",
        resolution=IncludeResolution.UNRESOLVED,
    )

    with pytest.raises(ValidationError, match="resolved ProjectOrder"):
        ProjectOrder(
            root=_root(main),
            status=ProjectOrderStatus.RESOLVED,
            files=[FileOccurrence(identifier="f0", file=str(main), depth=0)],
            includes=[dynamic],
        )

    partial = ProjectOrder(
        root=_root(main),
        status=ProjectOrderStatus.PARTIAL,
        files=[FileOccurrence(identifier="f0", file=str(main), depth=0)],
        includes=[dynamic],
        diagnostics=[
            ProjectOrderDiagnostic(
                kind=ProjectDiagnosticKind.UNSUPPORTED_DYNAMIC_STRUCTURE,
                message="include target depends on TeX expansion",
                source=dynamic.source,
                include_occurrence_identifier=dynamic.identifier,
            )
        ],
    )
    assert partial.status == ProjectOrderStatus.PARTIAL


def test_source_error_is_distinct_from_valid_but_unresolved(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    diagnostic = ProjectOrderDiagnostic(
        kind=ProjectDiagnosticKind.SOURCE_ERROR,
        message="malformed include command",
        source=_span(main, 5, 12),
    )
    order = ProjectOrder(
        root=_root(main),
        status=ProjectOrderStatus.SOURCE_ERROR,
        files=[FileOccurrence(identifier="f0", file=str(main), depth=0)],
        diagnostics=[diagnostic],
    )
    assert order.status == ProjectOrderStatus.SOURCE_ERROR


def test_include_provenance_must_belong_to_parent_occurrence(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    other = tmp_path / "other.tex"
    child = tmp_path / "child.tex"

    with pytest.raises(ValidationError, match="include provenance"):
        ProjectOrder(
            root=_root(main),
            status=ProjectOrderStatus.RESOLVED,
            files=[
                FileOccurrence(identifier="f0", file=str(main), depth=0),
                FileOccurrence(
                    identifier="f1",
                    file=str(child),
                    parent_include_identifier="i0",
                    depth=1,
                ),
            ],
            includes=[
                IncludeOccurrence(
                    identifier="i0",
                    parent_file_occurrence_identifier="f0",
                    source=_span(other, 0, 10),
                    command="input",
                    raw_target="child",
                    resolved_file=str(child),
                    resolution=IncludeResolution.RESOLVED,
                )
            ],
        )
