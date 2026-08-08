from pathlib import Path

from thorn.latex import extract_units


def test_extracts_custom_theorem_and_proof(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""
\newtheorem{fact}{Fact}
\begin{document}
\begin{fact}[Small]\label{fact:one}
One is positive.
\end{fact}
\begin{proof}
Indeed, $1>0$.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )
    units = extract_units(tex)
    assert len(units) == 1
    unit = units[0]
    assert unit.environment == "fact"
    assert unit.title == "Small"
    assert unit.label == "fact:one"
    assert "One is positive" in unit.statement
    assert unit.proof is not None and "1>0" in unit.proof
    assert unit.proof_range is not None


def test_follows_inputs_and_resolves_result_refs(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    section = tmp_path / "section.tex"
    main.write_text(
        r"""
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\input{section}
""",
        encoding="utf-8",
    )
    section.write_text(
        r"""
\begin{lemma}\label{lem:a}
A.
\end{lemma}
\begin{proof}Proof A.\end{proof}
\begin{theorem}\label{thm:b}
B.
\end{theorem}
\begin{proof}Use \ref{lem:a}.\end{proof}
""",
        encoding="utf-8",
    )
    units = extract_units(main)
    assert [unit.label for unit in units] == ["lem:a", "thm:b"]
    theorem = units[1]
    assert len(theorem.referenced_results) == 1
    assert "lem:a" in theorem.referenced_results[0]


def test_comment_does_not_create_input_dependency(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text("% \\input{missing}\n", encoding="utf-8")
    assert extract_units(main) == []
