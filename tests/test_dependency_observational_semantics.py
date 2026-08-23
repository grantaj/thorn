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


def _nodes(snapshot, *, namespace: str, binding: str | None = None):
    return [
        item
        for item in snapshot.semantic.nodes
        if item.namespace == namespace
        and (binding is None or item.binding == binding)
    ]


def _result_key(snapshot, label: str) -> str:
    matches = _nodes(snapshot, namespace="result", binding=label)
    assert len(matches) == 1
    return matches[0].key


def _symbol_with_payload(snapshot, name: str, fact: str):
    matches = [
        item
        for item in _nodes(snapshot, namespace="symbol", binding=name)
        if fact in item.payload
    ]
    assert len(matches) == 1
    return matches[0]


def _node_provenance(snapshot, key: str):
    return [
        item
        for item in snapshot.provenance.nodes
        if item.node_key == key
    ]


def test_q_detects_alias_loss_without_losing_formula_control(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The #211 alias ablation changes dependency semantics, not merely private IR."""

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

    baseline = snapshot_dependency_observations(extract_project(main))
    star = _symbol_with_payload(baseline, r"\star", ":= x+y")
    q = _symbol_with_payload(baseline, "q", ":= 1")
    result_key = _result_key(baseline, "thm:use")
    assert any(
        edge.owner_key == result_key and edge.prerequisite_key == star.key
        for edge in baseline.semantic.requirements
    )
    q_provenance = _node_provenance(baseline, q.key)

    monkeypatch.setattr(project_context, "_ALIAS_BRIDGE_RE", re.compile(r"(?!)"))
    candidate = snapshot_dependency_observations(extract_project(main))

    assert not [
        item
        for item in _nodes(candidate, namespace="symbol", binding=r"\star")
        if ":= x+y" in item.payload
    ]
    candidate_q = _symbol_with_payload(candidate, "q", ":= 1")
    assert candidate_q == q
    assert _node_provenance(candidate, candidate_q.key) == q_provenance
    assert baseline.semantic != candidate.semantic


def test_p_records_source_evidence_for_require_edges(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text(
        _paper(
            "\\begin{theorem}\\label{thm:a}\n"
            "$A=A$.\n"
            "\\end{theorem}\n"
            "\\begin{theorem}\\label{thm:b}\n"
            "By \\ref{thm:a}, $B=B$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )

    snapshot = snapshot_dependency_observations(extract_project(main))
    a_key = _result_key(snapshot, "thm:a")
    b_key = _result_key(snapshot, "thm:b")
    assert any(
        edge.owner_key == b_key
        and edge.prerequisite_key == a_key
        and edge.status == "resolved"
        for edge in snapshot.semantic.requirements
    )
    evidence = [
        item
        for item in snapshot.provenance.requirements
        if item.owner_key == b_key and item.prerequisite_key == a_key
    ]
    assert evidence
    assert all(item.source.file.endswith("main.tex") for item in evidence)


def test_semantic_q_ignores_source_offsets_while_p_tracks_them(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    body = (
        "Set $q = 1$.\n"
        "\\begin{theorem}\\label{thm:use}\n"
        "$q=q$.\n"
        "\\end{theorem}\n"
    )
    main.write_text(_paper(body), encoding="utf-8")
    original = snapshot_dependency_observations(extract_project(main))

    main.write_text(_paper("\n\n" + body), encoding="utf-8")
    shifted = snapshot_dependency_observations(extract_project(main))

    assert original.semantic == shifted.semantic
    assert original.provenance != shifted.provenance


def test_semantic_q_ignores_order_of_independent_scopes(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    first = (
        "\\begin{theorem}\\label{thm:a}\n"
        "Set $x = 1$. Then $x=x$.\n"
        "\\end{theorem}\n"
    )
    second = (
        "\\begin{theorem}\\label{thm:b}\n"
        "Set $x = 2$. Then $x=x$.\n"
        "\\end{theorem}\n"
    )

    main.write_text(_paper(first + second), encoding="utf-8")
    original = snapshot_dependency_observations(extract_project(main))
    main.write_text(_paper(second + first), encoding="utf-8")
    swapped = snapshot_dependency_observations(extract_project(main))

    assert original.semantic == swapped.semantic
    assert original.provenance != swapped.provenance


def test_q_observes_project_shadowing_by_expanded_source_order(
    tmp_path: Path,
) -> None:
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

    snapshot = snapshot_dependency_observations(extract_project(main))
    q1 = _symbol_with_payload(snapshot, "q", ":= 1")
    q2 = _symbol_with_payload(snapshot, "q", ":= 2")
    assert q1.shadow_rank == 0
    assert q2.shadow_rank == 1

    result_key = _result_key(snapshot, "thm:after")
    resolutions = [
        item
        for item in snapshot.semantic.resolutions
        if item.context_key == result_key and item.binding == "q"
    ]
    assert resolutions
    assert {item.target_key for item in resolutions} == {q2.key}


def test_q_preserves_repeated_occurrence_fail_closed_resolution(
    tmp_path: Path,
) -> None:
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

    snapshot = snapshot_dependency_observations(extract_project(main))
    result_key = _result_key(snapshot, "thm:child")
    resolutions = [
        item
        for item in snapshot.semantic.resolutions
        if item.context_key == result_key and item.binding == "q"
    ]
    assert resolutions
    assert {item.target_key for item in resolutions} == {None}
    assert {item.status for item in resolutions} == {"unresolved"}


def test_q_projection_conforms_between_default_and_regex_frontends(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    main.write_text(
        _paper(
            "Set $q = 1$.\n"
            "\\begin{theorem}\\label{thm:use}\n"
            "$q=q$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )

    production = snapshot_dependency_observations(extract_project(main))
    compatibility = snapshot_dependency_observations(
        extract_project(main, frontend=RegexLatexFrontend())
    )
    assert production.semantic == compatibility.semantic
