from __future__ import annotations

import json
from pathlib import Path

import pytest

from thorn.frontends import RegexLatexFrontend
from thorn.project_partiality import normalize_project_structure
from thorn.workspace import (
    IncludeResolution,
    ProjectPositionLookup,
    WorkspaceResolution,
    build_project_workspace_facts,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "eval/workspace_resolution/cases.json").read_text(encoding="utf-8"))


def _materialize(tmp_path: Path, name: str) -> Path:
    fixture = tmp_path / name
    fixture.mkdir()
    for relative, source in CASES[name]["files"].items():
        path = fixture / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return fixture


def _facts(tmp_path: Path, name: str):
    fixture = _materialize(tmp_path, name)
    parsed = normalize_project_structure(
        RegexLatexFrontend().parse_project(fixture / "main.tex")
    )
    return fixture, build_project_workspace_facts(parsed)


@pytest.mark.parametrize("name", sorted(CASES))
def test_workspace_facts_match_issue_159_resolution_matrix(
    tmp_path: Path,
    name: str,
) -> None:
    fixture, facts = _facts(tmp_path, name)
    expectation = CASES[name]["expectation"]

    assert facts.resolution == WorkspaceResolution(expectation["status"])
    if expectation["expanded"] is not None:
        assert [
            str(Path(item.file).relative_to(fixture))
            for item in facts.occurrences
        ] == expectation["expanded"]


def test_repeated_inclusion_preserves_distinct_occurrence_identity(tmp_path: Path) -> None:
    fixture, facts = _facts(tmp_path, "repeated")
    part = fixture / "part.tex"

    occurrences = ProjectPositionLookup(facts).occurrences_for_file(part)
    assert len(occurrences) == 2
    assert occurrences[0].occurrence_id != occurrences[1].occurrence_id
    assert [item.ordinal for item in occurrences] == [1, 2]
    assert [item.resolution for item in facts.includes] == [
        IncludeResolution.RESOLVED,
        IncludeResolution.RESOLVED,
    ]
    assert facts.includes[0].child_occurrence_id == occurrences[0].occurrence_id
    assert facts.includes[1].child_occurrence_id == occurrences[1].occurrence_id


def test_project_positions_follow_nested_include_and_return_order(tmp_path: Path) -> None:
    fixture, facts = _facts(tmp_path, "nested")
    lookup = ProjectPositionLookup(facts)
    main = fixture / "main.tex"
    a = fixture / "a.tex"
    b = fixture / "b.tex"
    main_source = main.read_text(encoding="utf-8")
    a_source = a.read_text(encoding="utf-8")
    b_source = b.read_text(encoding="utf-8")

    keys = [
        lookup.sort_key(main, main_source.index("ROOT-BEFORE")),
        lookup.sort_key(a, a_source.index("A-BEFORE")),
        lookup.sort_key(b, b_source.index("B-MARK")),
        lookup.sort_key(a, a_source.index("A-AFTER")),
        lookup.sort_key(main, main_source.index("ROOT-AFTER")),
    ]
    assert keys == sorted(keys)


def test_cycle_is_an_explicit_unexpanded_relationship(tmp_path: Path) -> None:
    _, facts = _facts(tmp_path, "cycle")

    assert facts.resolution == WorkspaceResolution.PARTIAL
    assert any(item.resolution == IncludeResolution.CYCLE for item in facts.includes)
    assert all(
        item.child_occurrence_id is None
        for item in facts.includes
        if item.resolution == IncludeResolution.CYCLE
    )
