from __future__ import annotations

import re
from pathlib import Path

from thorn.check import check_project
from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.support import SupportKind

_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


class StaticDependencyFrontend:
    name = "static-dependencies"

    def parse(self, text: str) -> LinguisticDocument:
        tokens = [
            LinguisticToken(
                index=0,
                text="predicate",
                lemma="predicate",
                pos="VERB",
                dependency="ROOT",
                head_index=0,
                sentence_index=0,
                start=0,
                end=0,
            )
        ]
        for match in _PLACEHOLDER_RE.finditer(text):
            tokens.append(
                LinguisticToken(
                    index=len(tokens),
                    text=match.group(0),
                    lemma=match.group(0),
                    pos="PROPN",
                    dependency="obl",
                    head_index=0,
                    sentence_index=0,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return LinguisticDocument(text=text, tokens=tokens)


class NoRootFrontend:
    name = "no-root"

    def parse(self, text: str) -> LinguisticDocument:
        return LinguisticDocument(text=text, tokens=[])


def test_conclusion_word_does_not_force_confident_prior_claim(tmp_path: Path) -> None:
    tex = tmp_path / "conclusion-trap.tex"
    tex.write_text(
        r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
We first establish notation. Therefore, in the next section, we discuss an example.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    core = extract_project(tex)
    core_claims = core.proof_support_graph.claims_for_result("thm:main")
    assert core.proof_support_graph.confident_incoming_edges(core_claims[1].identifier)

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    claims = project.proof_support_graph.claims_for_result("thm:main")
    edges = project.proof_support_graph.incoming_edges(claims[1].identifier)

    assert len(edges) == 1
    assert edges[0].kind == SupportKind.PRIOR_CLAIM
    assert edges[0].status == InferenceStatus.AMBIGUOUS
    assert edges[0].confidence is None
    assert edges[0].evidence[0].frontend == "static-dependencies"
    assert "lexical overlap alone" in edges[0].evidence[0].reason
    assert project.proof_support_graph.confident_incoming_edges(claims[1].identifier) == []
    assert check_project(project) == []


def test_elliptical_adjacent_claim_is_retained_as_unresolved_candidate(tmp_path: Path) -> None:
    tex = tmp_path / "elliptical-conclusion.tex"
    tex.write_text(
        r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
A base fact. Accordingly the conclusion.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    core = extract_project(tex)
    core_claims = core.proof_support_graph.claims_for_result("thm:main")
    assert core.proof_support_graph.incoming_edges(core_claims[1].identifier) == []

    project = extract_project(tex, linguistic_frontend=NoRootFrontend())
    claims = project.proof_support_graph.claims_for_result("thm:main")
    edges = project.proof_support_graph.incoming_edges(claims[1].identifier)

    assert len(edges) == 1
    assert edges[0].kind == SupportKind.PRIOR_CLAIM
    assert edges[0].status == InferenceStatus.UNRESOLVED
    assert edges[0].confidence is None
    assert edges[0].evidence[0].frontend == "no-root"
    assert edges[0].evidence[0].dependency_path == []
    assert "adjacent claims" in edges[0].evidence[0].reason
    assert project.proof_support_graph.confident_incoming_edges(claims[1].identifier) == []
    assert check_project(project) == []


def test_reference_cue_does_not_force_support_over_exposition(tmp_path: Path) -> None:
    tex = tmp_path / "reference-trap.tex"
    tex.write_text(
        r"""\documentclass{article}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:base}
A base fact.
\end{lemma}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
Using coordinates is convenient here; later see Lemma~\ref{lem:base} for background.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    core = extract_project(tex)
    core_claim = core.proof_support_graph.claims_for_result("thm:main")[0]
    assert core.proof_support_graph.confident_incoming_edges(core_claim.identifier)

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    claim = project.proof_support_graph.claims_for_result("thm:main")[0]
    edges = project.proof_support_graph.incoming_edges(claim.identifier)

    assert len(edges) == 1
    assert edges[0].kind == SupportKind.RESULT_REFERENCE
    assert edges[0].status == InferenceStatus.AMBIGUOUS
    assert edges[0].confidence is None
    assert edges[0].source.text(tex.read_text(encoding="utf-8")) == r"\ref{lem:base}"
    assert "support versus exposition" in edges[0].evidence[0].reason
    assert project.proof_support_graph.confident_incoming_edges(claim.identifier) == []
    assert check_project(project) == []
