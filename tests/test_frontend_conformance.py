from collections.abc import Callable
from pathlib import Path

import pytest

from thorn.dependencies import DependencyResolution, ReferenceContext
from thorn.frontend import FrontendDiagnosticKind, LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project, extract_units

FrontendFactory = Callable[[], LatexFrontend]

# Every serious backend must satisfy this source/provenance and structural
# contract. Backend-specific disagreements belong in test_frontend_ab.py rather
# than being silently normalized here.
_FRONTENDS: tuple[FrontendFactory, ...] = (RegexLatexFrontend, PylatexencLatexFrontend)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_frontend_preserves_syntax_and_exact_provenance(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    source = r"""\newtheorem{fact}{Fact}
% \input{missing}
\begin{document}
Escaped percent: \%.
\begin{fact}[Small]\label{fact:one}
Let $x\in\mathbb R$ and use \foo[alpha]{a{b}c}.
\begin{enumerate}
\item Nested.
\end{enumerate}
\[
x^2 \ge 0.
\]
\end{fact}
\begin{proof}
Indeed.
\end{proof}
\end{document}
"""
    tex.write_text(source, encoding="utf-8")

    parsed = frontend_factory().parse_project(tex)
    assert parsed.diagnostics == []
    assert len(parsed.files) == 1
    file = parsed.files[0]
    assert file.path == str(tex.resolve())
    assert file.raw == source

    # A commented-out include is not syntax. Escaped percent remains visible as
    # a control-symbol macro rather than starting a comment.
    assert not any(macro.name == "input" for macro in file.macros)
    assert any(macro.name == "%" for macro in file.macros)

    newtheorem = next(macro for macro in file.macros if macro.name == "newtheorem")
    assert [argument.value for argument in newtheorem.arguments] == ["fact", "Fact"]
    assert newtheorem.span.text(source) == newtheorem.raw
    assert newtheorem.span.start_offset == 0
    assert newtheorem.span.start_line == 1
    assert newtheorem.span.start_column == 1

    foo = next(macro for macro in file.macros if macro.name == "foo")
    assert [argument.value for argument in foo.arguments] == ["alpha", "a{b}c"]
    assert [argument.optional for argument in foo.arguments] == [True, False]
    assert foo.span.text(source) == foo.raw

    fact = next(environment for environment in file.environments if environment.name == "fact")
    assert fact.arguments[0].optional is True
    assert fact.arguments[0].value == "Small"
    assert fact.span.text(source) == fact.raw
    assert "\\label{fact:one}" in fact.body(source)
    assert any(
        environment.name == "enumerate"
        and environment.span.start_offset > fact.body_span.start_offset
        and environment.span.end_offset < fact.body_span.end_offset
        for environment in file.environments
    )

    label = next(macro for macro in file.macros if macro.name == "label")
    expected_label_offset = source.index(r"\label{fact:one}")
    assert label.span.start_offset == expected_label_offset
    assert label.span.text(source) == r"\label{fact:one}"
    assert label.span.start_line == 5

    assert any(item.delimiter == "$" and "x\\in" in item.raw for item in file.math)
    assert any(item.delimiter == r"\[\]" and "x^2" in item.raw for item in file.math)
    assert all(item.span.text(source) == item.raw for item in file.math)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_frontend_follows_input_and_include_projects(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    first = tmp_path / "first.tex"
    second = tmp_path / "second.tex"
    main.write_text("\\input{first}\n\\include{second.tex}\n", encoding="utf-8")
    first.write_text("First.\n", encoding="utf-8")
    second.write_text("Second.\n", encoding="utf-8")

    parsed = frontend_factory().parse_project(main)

    assert {Path(file.path).name for file in parsed.files} == {
        "main.tex",
        "first.tex",
        "second.tex",
    }
    assert parsed.diagnostics == []


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_frontend_reports_missing_include_with_source(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    main.write_text("before\n\\input{missing}\nafter\n", encoding="utf-8")

    parsed = frontend_factory().parse_project(main)
    missing = [
        item for item in parsed.diagnostics if item.kind == FrontendDiagnosticKind.MISSING_FILE
    ]

    assert len(missing) == 1
    assert missing[0].source is not None
    assert missing[0].source.start_line == 2
    assert "missing.tex" in missing[0].message

    # The compatibility theorem-extraction API retains the old failure behavior.
    with pytest.raises(FileNotFoundError):
        extract_units(main, frontend=frontend_factory())


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_frontend_reports_malformed_environment_without_inventing_a_pair(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        "\\begin{document}\n\\begin{proof}\nunfinished\n\\end{document}\n",
        encoding="utf-8",
    )

    parsed = frontend_factory().parse_project(tex)
    errors = [
        item for item in parsed.diagnostics if item.kind == FrontendDiagnosticKind.PARSE_ERROR
    ]

    assert errors
    assert any("proof" in item.message for item in errors)
    assert not any(environment.name == "proof" for environment in parsed.files[0].environments)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_dependency_graph_is_a_frontend_conformance_oracle(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    section = tmp_path / "section.tex"
    main.write_text(
        r"""\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\newtheorem{corollary}{Corollary}
\input{section}
""",
        encoding="utf-8",
    )
    section.write_text(
        r"""\begin{lemma}\label{lem:a}
A.
\end{lemma}
\begin{proof}Proof A.\end{proof}
\begin{theorem}\label{thm:b}
B follows from \ref{lem:a}.
\end{theorem}
\begin{proof}
Again use \ref{lem:a}.
\end{proof}
\begin{corollary}\label{cor:c}
C.
\end{corollary}
\begin{proof}By \ref{thm:b}.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main, frontend=frontend_factory())
    graph = project.dependency_graph

    assert [node.identifier for node in graph.nodes] == ["lem:a", "thm:b", "cor:c"]
    assert graph.direct_dependency_ids("thm:b") == ["lem:a"]
    assert graph.reverse_dependency_ids("lem:a") == ["thm:b"]
    assert graph.transitive_dependency_ids("cor:c") == ["lem:a", "thm:b"]
    assert graph.cycles() == []

    theorem_edges = [edge for edge in graph.edges if edge.source_identifier == "thm:b"]
    assert len(theorem_edges) == 2
    assert {edge.context for edge in theorem_edges} == {
        ReferenceContext.STATEMENT,
        ReferenceContext.PROOF,
    }
    assert all(edge.resolution == DependencyResolution.RESOLVED for edge in theorem_edges)
    expected_lines = {
        index + 1
        for index, line in enumerate(section.read_text(encoding="utf-8").splitlines())
        if r"\ref{lem:a}" in line
    }
    assert {edge.source.start_line for edge in theorem_edges} == expected_lines


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_duplicate_labels_remain_ambiguous_through_frontend(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:dup}First.\end{lemma}
\begin{lemma}\label{lem:dup}Second.\end{lemma}
\begin{theorem}\label{thm:use}Use \ref{lem:dup}.\end{theorem}
\end{document}
""",
        encoding="utf-8",
    )

    graph = extract_project(tex, frontend=frontend_factory()).dependency_graph
    ambiguous = [
        edge for edge in graph.edges if edge.resolution == DependencyResolution.AMBIGUOUS
    ]

    assert len(ambiguous) == 1
    assert ambiguous[0].source_identifier == "thm:use"
    assert ambiguous[0].target_label == "lem:dup"
    assert ambiguous[0].target_identifier is None
