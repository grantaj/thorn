from __future__ import annotations

from pathlib import Path

from thorn.latex import extract_project
from thorn.workspace import ProjectPositionLookup, WorkspaceResolution


def _resolved_names(project, result_identifier: str) -> list[str]:
    scope_ids = {
        scope.identifier
        for scope in project.symbol_table.scopes
        if scope.result_identifier == result_identifier
    }
    return [
        use.name
        for use in project.symbol_table.uses
        if use.scope_identifier in scope_ids and use.resolved_symbol_identifier is not None
    ]


def _write_repeated_child(
    tmp_path: Path,
    *,
    between: str = "",
) -> tuple[Path, Path]:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        "A map is called fibre-regular when every fibre contains two points.\n"
        "\\input{child}\n"
        f"{between}"
        "\\input{child}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    child.write_text(
        r"""\begin{theorem}\label{thm:child}
The map $f$ is fibre-regular.
\end{theorem}
\begin{proof}Inspect the fibres.\end{proof}
""",
        encoding="utf-8",
    )
    return main, child


def test_repeated_child_keeps_distinct_workspace_occurrences(tmp_path: Path) -> None:
    main, child = _write_repeated_child(tmp_path)
    project = extract_project(main)

    workspace = project.workspace
    assert workspace is not None
    assert workspace.resolution == WorkspaceResolution.RESOLVED

    child_occurrences = [
        occurrence
        for occurrence in workspace.occurrences
        if Path(occurrence.file).resolve() == child.resolve()
    ]
    assert len(child_occurrences) == 2
    assert len({item.occurrence_id for item in child_occurrences}) == 2

    labels = [label for label in workspace.labels if label.name == "thm:child"]
    assert {label.occurrence_id for label in labels} == {
        item.occurrence_id for item in child_occurrences
    }

    positions = ProjectPositionLookup(workspace).positions(child, 0)
    assert len(positions) == 2
    assert positions[0].occurrence_id != positions[1].occurrence_id
    assert positions[0].order_key != positions[1].order_key

    # Repeated physical source must not be collapsed into prose-derived mathematical
    # authority. The source remains available through the generic statement/context
    # path when a linguistic frontend is configured.
    assert "fibre-regular" not in _resolved_names(project, "thm:child")


def test_repeated_child_with_different_preceding_prose_still_fails_closed(
    tmp_path: Path,
) -> None:
    second = "A map is called fibre-regular when every fibre contains three points.\n"
    main, child = _write_repeated_child(tmp_path, between=second)
    project = extract_project(main)

    workspace = project.workspace
    assert workspace is not None
    child_occurrences = [
        occurrence
        for occurrence in workspace.occurrences
        if Path(occurrence.file).resolve() == child.resolve()
    ]
    assert len(child_occurrences) == 2

    # Path-level result IR cannot invent one semantic interpretation for two expanded
    # occurrences with different preceding source. Exact occurrence identity survives;
    # mathematical interpretation remains unresolved rather than guessed.
    assert "fibre-regular" not in _resolved_names(project, "thm:child")
    assert not any(
        item.raw.endswith("every fibre contains two points.")
        or item.raw.endswith("every fibre contains three points.")
        for item in project.symbol_table.definitions
    )
