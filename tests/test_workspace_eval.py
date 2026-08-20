from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "workspace_eval", ROOT / "eval/workspace_resolution/run.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CASES = json.loads((ROOT / "eval/workspace_resolution/cases.json").read_text())


def _run(name: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        fixture = MODULE.materialize_case(name, CASES[name], Path(tmp))
        return MODULE.run_thorn(fixture)


def test_fixture_matrix_is_complete() -> None:
    assert {
        "one_level", "nested", "parent_child_scope", "child_parent_return", "shadowing",
        "repeated", "cycle", "missing", "cross_file_reference", "fake_syntax",
        "macro_static", "macro_dynamic", "malformed",
    } == set(CASES)


def test_current_thorn_evidence_exposes_repeated_include_loss() -> None:
    result = _run("repeated")
    assert result["files"] == ["main.tex", "part.tex"]
    assert len(result["includes"]) == 2


def test_current_thorn_reports_missing_file() -> None:
    result = _run("missing")
    assert any(x["kind"] == "missing_file" for x in result["diagnostics"])


def test_nested_dependency_discovery_is_path_centric_not_occurrence_stream() -> None:
    result = _run("nested")
    assert result["files"] == ["main.tex", "a.tex", "b.tex"]
