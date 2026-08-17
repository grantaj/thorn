from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from thorn import cli
from thorn.analysis import AnalysisCategory, analyze_project
from thorn.latex import extract_project
from thorn.proof_language_review import ProofReviewModelResponse

_ROOT = Path(__file__).resolve().parents[1]
_QUICKSTART = _ROOT / "examples" / "quickstart"
_CLEAN = _QUICKSTART / "clean" / "paper.tex"
_STRUCTURAL = _QUICKSTART / "structural-problem" / "paper.tex"
_MATHEMATICAL = _QUICKSTART / "mathematical-problem" / "paper.tex"


def test_quickstart_manuscripts_parse_and_structural_expectations_hold() -> None:
    clean = extract_project(_CLEAN)
    structural = extract_project(_STRUCTURAL)
    mathematical = extract_project(_MATHEMATICAL)

    assert {unit.identifier for unit in clean.units} == {
        "lem:even-two",
        "lem:even-square",
        "thm:main",
    }
    assert analyze_project(clean) == []
    assert analyze_project(mathematical) == []

    findings = analyze_project(structural)
    assert len(findings) == 1
    assert findings[0].category == AnalysisCategory.MISSING_REFERENCE
    assert findings[0].rule == "TH103"
    assert findings[0].source.file == str(_STRUCTURAL)


@pytest.mark.parametrize("paper", [_CLEAN, _STRUCTURAL, _MATHEMATICAL])
def test_every_quickstart_example_generates_a_keyless_self_contained_report(
    paper: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    destination = tmp_path / f"{paper.parent.name}.html"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"thorn.providers.openai", "openai"}:
            raise AssertionError(f"quickstart report attempted provider import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert (
        cli.main(
            [
                "report",
                str(paper),
                "--structural-only",
                "--output",
                str(destination),
                "--fail-on",
                "never",
            ]
        )
        == 0
    )
    html = destination.read_text(encoding="utf-8")
    assert "Mathematical review report" in html
    assert "file://" in html
    assert "This self-contained report contains no external runtime assets" in html


def test_clean_quickstart_proof_graph_is_keyless(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "proof-graph.html"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert (
        cli.main(
            [
                "graph",
                str(_CLEAN),
                "--structural-only",
                "--output",
                str(destination),
            ]
        )
        == 0
    )
    html = destination.read_text(encoding="utf-8")
    assert "lem:even-two" in html
    assert "lem:even-square" in html
    assert "thm:main" in html
    assert str(_CLEAN) in html


def test_quickstart_lean_cli_exports_the_existing_supported_subset(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    destination = tmp_path / "quickstart.lean"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert (
        cli.main(
            [
                "lean",
                str(_CLEAN),
                "--structural-only",
                "--result",
                "thm:main",
                "--output",
                str(destination),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Status: complete" in output
    source = destination.read_text(encoding="utf-8")
    assert "Thorn Lean export status: complete" in source
    assert "sorry" not in source


def test_normal_review_cli_uses_thorn_proof_protocol_without_live_provider(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from thorn.providers import openai as openai_provider

    calls = []

    class FakeProvider:
        def __init__(self, model: str) -> None:
            self.model = model

        def review_proof_turn(self, request):
            calls.append(request)
            return ProofReviewModelResponse(action="review")

    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-a-live-key")
    monkeypatch.setattr(openai_provider, "OpenAIProvider", FakeProvider)
    report = tmp_path / "review.html"

    assert (
        cli.main(
            [
                "review",
                str(_MATHEMATICAL),
                "--structural-only",
                "--model",
                "test-model",
                "--report",
                str(report),
            ]
        )
        == 0
    )
    assert calls
    assert all(call.representation == "thorn-proof/1" for call in calls)
    assert all(call.protocol_version == "thorn-proof-review/2" for call in calls)
    assert "thorn-proof/1" in capsys.readouterr().err
    html = report.read_text(encoding="utf-8")
    assert "thorn-proof/1" in html
    assert "thorn-proof-review/2" in html
    assert "THORN-PROOF 1" in html


def test_version_is_a_real_install_sanity_check(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.startswith("thorn ")
