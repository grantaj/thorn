from pathlib import Path

from thorn.dependencies import DependencyResolution, ReferenceContext
from thorn.latex import extract_project


def test_multi_file_project_exposes_dependency_queries(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    section = tmp_path / "section.tex"
    main.write_text(
        r"""
\newtheorem{lemma}{Lemma}
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
B.
\end{theorem}
\begin{proof}
Use \ref{lem:a}.
\end{proof}
\begin{corollary}\label{cor:c}
C.
\end{corollary}
\begin{proof}By \ref{thm:b}.\end{proof}
\begin{theorem}\label{thm:unrelated}
D.
\end{theorem}
\begin{proof}Directly.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main)
    graph = project.dependency_graph

    assert [node.identifier for node in graph.nodes] == [
        "lem:a",
        "thm:b",
        "cor:c",
        "thm:unrelated",
    ]
    assert graph.direct_dependency_ids("thm:b") == ["lem:a"]
    assert graph.reverse_dependency_ids("lem:a") == ["thm:b"]
    assert graph.direct_dependency_ids("cor:c") == ["thm:b"]
    assert graph.transitive_dependency_ids("cor:c") == ["lem:a", "thm:b"]
    assert graph.direct_dependency_ids("thm:unrelated") == []
    assert graph.cycles() == []

    edge = next(
        edge
        for edge in graph.edges
        if edge.source_identifier == "thm:b" and edge.target_identifier == "lem:a"
    )
    expected_line = section.read_text(encoding="utf-8").splitlines().index(
        r"Use \ref{lem:a}."
    ) + 1
    assert edge.target_label == "lem:a"
    assert edge.context == ReferenceContext.PROOF
    assert edge.source.file == str(section.resolve())
    assert edge.source.start_line == expected_line
    assert edge.source.end_line == expected_line

    rendered = graph.render_dependency_context("thm:b")
    assert project.unit("thm:b").referenced_results == rendered
    assert len(rendered) == 1
    assert "[lemma lem:a]" in rendered[0]
    assert "A." in rendered[0]
    assert str(section.resolve()) in rendered[0]


def test_transitive_cycle_detection_handles_three_hop_cycle(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""
\newtheorem{lemma}{Lemma}
\begin{document}
\begin{lemma}\label{lem:a}
A follows from \ref{lem:b}.
\end{lemma}
\begin{lemma}\label{lem:b}
B follows from \ref{lem:c}.
\end{lemma}
\begin{lemma}\label{lem:c}
C follows from \ref{lem:a}.
\end{lemma}
\end{document}
""",
        encoding="utf-8",
    )

    graph = extract_project(tex).dependency_graph

    assert graph.direct_dependency_ids("lem:a") == ["lem:b"]
    assert graph.transitive_dependency_ids("lem:a") == ["lem:b", "lem:c"]
    assert graph.cycles() == [["lem:a", "lem:b", "lem:c"]]


def test_duplicate_theorem_labels_produce_ambiguous_edge(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:dup}First.\end{lemma}
\begin{lemma}\label{lem:dup}Second.\end{lemma}
\begin{theorem}\label{thm:use}
Use \ref{lem:dup}.
\end{theorem}
\end{document}
""",
        encoding="utf-8",
    )

    graph = extract_project(tex).dependency_graph
    ambiguous = [
        edge
        for edge in graph.edges
        if edge.resolution == DependencyResolution.AMBIGUOUS
    ]

    assert len(ambiguous) == 1
    assert ambiguous[0].source_identifier == "thm:use"
    assert ambiguous[0].target_label == "lem:dup"
    assert ambiguous[0].target_identifier is None
    assert graph.direct_dependency_ids("thm:use") == []
    assert graph.unresolved_edges() == ambiguous
