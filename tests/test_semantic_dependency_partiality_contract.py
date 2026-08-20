"""Fail-closed partiality cases for the semantic-dependency conformance contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from thorn.dependencies import DependencyResolution, ExtractedProject
from thorn.frontend import FrontendDiagnosticKind, LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project
from thorn.review_workflow import prepare_proof_review

FrontendFactory = Callable[[], LatexFrontend]
_FRONTENDS: tuple[FrontendFactory, ...] = (RegexLatexFrontend, PylatexencLatexFrontend)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


def _result_scope_ids(project: ExtractedProject, result_identifier: str) -> set[str]:
    return {
        scope.identifier
        for scope in project.symbol_table.scopes
        if scope.result_identifier == result_identifier
    }


def _assert_no_authority(
    project: ExtractedProject,
    *,
    result_identifier: str,
    term: str,
) -> None:
    table = project.symbol_table
    symbol_ids = {
        symbol.identifier
        for symbol in table.symbols
        if symbol.name.casefold() == term.casefold()
    }
    assert not any(
        item.symbol_identifier in symbol_ids
        for item in [*table.definitions, *table.constraints]
    )

    result_scope_ids = _result_scope_ids(project, result_identifier)
    assert not any(
        use.resolved_symbol_identifier is not None
        and use.scope_identifier in result_scope_ids
        and use.name.casefold() == term.casefold()
        for use in table.uses
    )


def _assert_exact_definition(
    project: ExtractedProject,
    *,
    term: str,
    source_text: str,
) -> None:
    definitions = [
        definition
        for definition in project.symbol_table.definitions
        if definition.raw == source_text
    ]
    assert len(definitions) == 1
    definition = definitions[0]
    symbol = project.symbol_table.symbol(definition.symbol_identifier)
    assert symbol.name.casefold() == term.casefold()
    raw_file = Path(definition.source.file).read_text(encoding="utf-8")
    assert definition.source.text(raw_file) == source_text


def _assert_exact_constraint(
    project: ExtractedProject,
    *,
    term: str,
    source_text: str,
) -> None:
    constraints = [
        constraint
        for constraint in project.symbol_table.constraints
        if constraint.raw == source_text
    ]
    assert len(constraints) == 1
    constraint = constraints[0]
    symbol = project.symbol_table.symbol(constraint.symbol_identifier)
    assert symbol.name.casefold() == term.casefold()
    raw_file = Path(constraint.source.file).read_text(encoding="utf-8")
    assert constraint.source.text(raw_file) == source_text


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

    # #162 deliberately does not constrain whether a frontend retains a partial
    # or error syntax node. The stable semantic consequence is that Thorn does
    # not promote malformed source into a mathematical result or result scope.
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

    # The normalized unavailable-source fact and its provenance are normative.
    # Downstream project resolution may fail closed or return an explicitly
    # partial project; #162 intentionally does not freeze that mechanism.


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


_NAMED_TRUNCATIONS = (
    ("A graph is called edge-rigid when", "edge-rigid"),
    (r"A graph is called edge-rigid when \label{decl}", "edge-rigid"),
    (
        r"A graph is called edge-rigid when \label{decl} Additional prose follows.",
        "edge-rigid",
    ),
    ("A map is said to be fibre-pure if", "fibre-pure"),
    (r"A map is said to be fibre-pure if \emph{}", "fibre-pure"),
    ("We say that a lattice is shell-balanced whenever", "shell-balanced"),
    ("By a chain-finite order we mean", "chain-finite order"),
)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
@pytest.mark.parametrize(("truncated", "term"), _NAMED_TRUNCATIONS)
def test_truncated_named_declaration_is_source_not_authority(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
    truncated: str,
    term: str,
) -> None:
    tex = tmp_path / "main.tex"
    complete = (
        "A simplicial complex is called facet-sparse when every facet has at most "
        "three vertices."
    )
    tex.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{truncated}\n\n"
        f"{complete}\n\n"
        "\\begin{theorem}\\label{thm:main}\n"
        f"The object satisfies {term} and facet-sparse.\n"
        "\\end{theorem}\n"
        "\\begin{proof}Inspect the defining conditions.\\end{proof}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    parsed = frontend_factory().parse_project(tex)
    assert len(parsed.files) == 1
    raw = parsed.files[0].raw
    start = raw.index(truncated)
    assert raw[start : start + len(truncated)] == truncated

    project = extract_project(tex, frontend=frontend_factory())
    _assert_no_authority(project, result_identifier="thm:main", term=term)
    _assert_exact_definition(project, term="facet-sparse", source_text=complete)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_truncated_ambient_convention_is_source_not_scope_authority(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    truncated = (
        r"Throughout, all spectral spaces are \label{ambient}",
        r"Unless otherwise stated, modules are \emph{}",
    )
    complete = "In what follows, every covering map is finite-sheeted."
    tex.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{truncated[0]}\n\n"
        f"{truncated[1]}\n\n"
        f"{complete}\n\n"
        "\\begin{theorem}\\label{thm:main}\n"
        "Every object has the advertised property.\n"
        "\\end{theorem}\n"
        "\\begin{proof}Use the standing convention.\\end{proof}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    parsed = frontend_factory().parse_project(tex)
    assert len(parsed.files) == 1
    raw = parsed.files[0].raw
    for source_text in truncated:
        start = raw.index(source_text)
        assert raw[start : start + len(source_text)] == source_text

    project = extract_project(tex, frontend=frontend_factory())
    _assert_no_authority(project, result_identifier="thm:main", term="spectral spaces")
    _assert_no_authority(project, result_identifier="thm:main", term="modules")
    _assert_exact_constraint(project, term="covering map", source_text=complete)

    # Whether a future selector exposes partial source as non-authoritative
    # evidence is deliberately outside this backend-independent contract.
