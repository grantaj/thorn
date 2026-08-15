from pathlib import Path

from thorn.latex import extract_project
from thorn.support import SupportKind


def test_bare_expository_result_reference_is_not_support(tmp_path: Path) -> None:
    tex = tmp_path / "reference-cues.tex"
    tex.write_text(
        r"""
\documentclass{article}
\usepackage{amsthm}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:background}
A background result.
\end{lemma}
\begin{proof}
The claim is immediate.
\end{proof}
\begin{theorem}\label{thm:target}
A target result.
\end{theorem}
\begin{proof}
For comparison, Lemma~\ref{lem:background} uses different notation.
The target statement follows directly from the hypothesis.
\end{proof}
\end{document}
""".lstrip(),
        encoding="utf-8",
    )

    graph = extract_project(tex).proof_support_graph
    claims = graph.claims_for_result("thm:target")
    target_ids = {claim.identifier for claim in claims}
    assert not any(
        edge.kind == SupportKind.RESULT_REFERENCE
        and edge.target_claim_identifier in target_ids
        for edge in graph.edges
    )


def test_explicit_by_reference_is_support(tmp_path: Path) -> None:
    tex = tmp_path / "reference-support.tex"
    tex.write_text(
        r"""
\documentclass{article}
\usepackage{amsthm}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:background}
A background result.
\end{lemma}
\begin{proof}
The claim is immediate.
\end{proof}
\begin{theorem}\label{thm:target}
A target result.
\end{theorem}
\begin{proof}
By Lemma~\ref{lem:background}, the target statement follows.
\end{proof}
\end{document}
""".lstrip(),
        encoding="utf-8",
    )

    graph = extract_project(tex).proof_support_graph
    claim = graph.claims_for_result("thm:target")[0]
    incoming = graph.incoming_edges(claim.identifier)
    assert len(incoming) == 1
    assert incoming[0].kind == SupportKind.RESULT_REFERENCE
    assert incoming[0].target_label == "lem:background"
