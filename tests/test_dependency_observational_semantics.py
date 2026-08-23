from __future__ import annotations

import re
from pathlib import Path

import thorn.project_context as project_context
from thorn.dependency_observations import snapshot_dependency_observations
from thorn.frontends.regex import RegexLatexFrontend
from thorn.latex import extract_project


def _paper(body: str) -> str:
    return (
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body}"
        "\\end{document}\n"
    )


def _definition(snapshot, name: str) -> str | None:
    matches = [item for item in snapshot.declarations if item.name == name]
    assert len(matches) <= 1
    if not matches or not matches[0].definition_expressions:
        return None
    assert len(matches[0].definition_expressions) == 1
    return matches[0].definition_expressions[0]


def test_q_snapshot_detects_alias_semantic_loss_without_losing_formula_control(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The #203 alias ablation is observable at Q, not just in private IR shape."""

    main = tmp_path / "main.tex"
    main.write_text(
        _paper(
            "Define $x \\star y$ to mean $x+y$.\n"
            "\\[\n"
            "q := 1\n"
            "\\]\n"
            "\\begin{theorem}\\label{thm:use}\n"
            "$x\\star y=x+y$ and $q=q$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )

    baseline = snapshot_dependency_observations(
        extract_project(main, frontend=RegexLatexFrontend())
    )
    assert _definition(baseline, r"\star") == "x+y"
    assert _definition(baseline, "q") == "1"

    monkeypatch.setattr(project_context, "_ALIAS_BRIDGE_RE", re.compile(r"(?!)"))
    candidate = snapshot_dependency_observations(
        extract_project(main, frontend=RegexLatexFrontend())
    )

    assert _definition(candidate, r"\star") is None
    assert _definition(candidate, "q") == "1"
    assert baseline != candidate

    baseline_result = next(
        item for item in baseline.results if item.result_identifier == "thm:use"
    )
    candidate_result = next(
        item for item in candidate.results if item.result_identifier == "thm:use"
    )
    assert any(
        key.startswith(r"\star@")
        for key in baseline_result.project_declaration_dependencies
    )
    assert not any(
        key.startswith(r"\star@")
        for key in candidate_result.project_declaration_dependencies
    )


def test_q_snapshot_observes_project_shadowing_by_expanded_source_order(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    first = tmp_path / "zz_first.tex"
    second = tmp_path / "aa_second.tex"
    main.write_text(
        _paper(
            "\\input{zz_first}\n"
            "\\input{aa_second}\n"
            "\\begin{theorem}\\label{thm:after}\n"
            "$q=q$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )
    first.write_text("Set $q = 1$.\n", encoding="utf-8")
    second.write_text("Set $q = 2$.\n", encoding="utf-8")

    snapshot = snapshot_dependency_observations(
        extract_project(main, frontend=RegexLatexFrontend())
    )
    q_declarations = [item for item in snapshot.declarations if item.name == "q"]
    assert [item.definition_expressions for item in q_declarations] == [["1"], ["2"]]

    theorem_uses = [
        use
        for use in snapshot.uses
        if use.result_identifier == "thm:after" and use.name == "q"
    ]
    assert theorem_uses
    targets = {use.target_key for use in theorem_uses}
    assert len(targets) == 1
    target = next(iter(targets))
    assert target is not None
    second_key = next(
        item.key for item in q_declarations if item.definition_expressions == ["2"]
    )
    assert target == second_key


def test_q_snapshot_preserves_repeated_occurrence_fail_closed_resolution(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        _paper(
            "Set $q = 0$.\n"
            "\\input{child}\n"
            "Set $q = 1$.\n"
            "\\input{child}\n"
        ),
        encoding="utf-8",
    )
    child.write_text(
        "\\begin{theorem}\\label{thm:child}\n"
        "$q=q$.\n"
        "\\end{theorem}\n",
        encoding="utf-8",
    )

    snapshot = snapshot_dependency_observations(
        extract_project(main, frontend=RegexLatexFrontend())
    )
    child_uses = [
        use
        for use in snapshot.uses
        if use.result_identifier == "thm:child" and use.name == "q"
    ]
    assert child_uses
    assert {use.target_key for use in child_uses} == {None}
