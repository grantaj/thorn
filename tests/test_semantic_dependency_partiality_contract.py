"""Fail-closed partiality cases for the semantic-dependency conformance contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from thorn.dependencies import DependencyResolution
from thorn.frontend import FrontendDiagnosticKind, LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project
from thorn.review_workflow import prepare_proof_review

FrontendFactory = Callable[[], LatexFrontend]
_FRONTENDS: tuple[FrontendFactory, ...] = (RegexLatexFrontend, PylatexencLatexFrontend)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_malformed_theorem_is_diagnostic_not_invented_result(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:broken}
This theorem environment is truncated.
\end{document}
""",
        encoding="utf-8",
    )

    parsed = frontend_factory().parse_project(tex)
    parse_errors = [
        diagnostic
        for diagnostic in parsed.diagnostics
        if diagnostic.kind == FrontendDiagnosticKind.PARSE_ERROR
    ]

    assert parse_errors
    assert any("theorem" in diagnostic.message for diagnostic in parse_errors)

    # The stable semantic consequence is that malformed source is not promoted into
    # a mathematical result or result scope, regardless of parser recovery details.
    project = extract_project(tex, frontend=frontend_factory())
    assert project.units == []
    assert not any(scope.result_identifier == "thm:broken" for scope in project.symbol_table.scopes)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_missing_include_is_explicit_exact_source_unavailability(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    source = "before\n\\input{missing}\nafter\n"
    tex.write_text(source, encoding="utf-8")

    parsed = frontend_factory().parse_project(tex)
    missing = [
        diagnostic
        for diagnostic in parsed.diagnostics
        if diagnostic.kind == FrontendDiagnosticKind.MISSING_FILE
    ]

    assert len(missing) == 1
    diagnostic = missing[0]
    assert diagnostic.source is not None
    assert diagnostic.source.text(source) == r"\input{missing}"
    assert diagnostic.source.start_line == 2


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_missing_dependency_remains_unresolved_without_invented_review_source(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:main}
The conclusion follows from Lemma~\ref{lem:missing}.
\end{theorem}
\begin{proof}
Use Lemma~\ref{lem:missing}.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    project = extract_project(tex, frontend=frontend_factory())
    unresolved = project.dependency_graph.unresolved_edges()

    assert len(unresolved) == 2
    assert all(edge.resolution == DependencyResolution.MISSING for edge in unresolved)
    assert all(edge.target_label == "lem:missing" for edge in unresolved)
    assert all(edge.target_identifier is None for edge in unresolved)

    document = prepare_proof_review(project, project.unit("thm:main")).document
    assert not any(
        source.referenced_result_identifier == "lem:missing"
        for source in document.sources
    )


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_ambiguous_dependency_remains_unresolved_without_arbitrary_target(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:dup}First candidate.\end{lemma}
\begin{lemma}\label{lem:dup}Second candidate.\end{lemma}
\begin{theorem}\label{thm:main}
Use Lemma~\ref{lem:dup}.
\end{theorem}
\begin{proof}Apply the cited lemma.\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    project = extract_project(tex, frontend=frontend_factory())
    unresolved = project.dependency_graph.unresolved_edges()

    assert len(unresolved) == 1
    edge = unresolved[0]
    assert edge.resolution == DependencyResolution.AMBIGUOUS
    assert edge.target_label == "lem:dup"
    assert edge.target_identifier is None

    document = prepare_proof_review(project, project.unit("thm:main")).document
    assert not any(
        source.referenced_result_identifier == "lem:dup"
        for source in document.sources
    )
