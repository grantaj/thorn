from pathlib import Path

from thorn.frontends import get_frontend
from thorn.latex import extract_project
from thorn.support import ClaimForm, QualifierKind, SupportKind


def _write_support_fixture(path: Path) -> Path:
    path.write_text(
        r"""
\documentclass{article}
\usepackage{amsmath,amsthm}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:base}
A base fact.
\end{lemma}
\begin{proof}
By continuity, the base fact follows.
\end{proof}

\begin{equation}\label{eq:bound}
1 \le 2.
\end{equation}

\begin{theorem}\label{thm:main}
A supported conclusion.
\end{theorem}
\begin{proof}
By Lemma~\ref{lem:base}, choose a limiting object.
\[
  x^2 \ge 0
\]
for every $x\in\mathbb R$.
The limit clearly has full rank.
Therefore the limit is admissible.
By definition, the final conclusion follows from \eqref{eq:bound}.
\end{proof}
\end{document}
""".lstrip(),
        encoding="utf-8",
    )
    return path


def test_extracts_claims_and_explicit_support_kinds(tmp_path: Path) -> None:
    tex = _write_support_fixture(tmp_path / "support.tex")
    project = extract_project(tex)
    graph = project.proof_support_graph

    main_claims = graph.claims_for_result("thm:main")
    assert [claim.form for claim in main_claims] == [
        ClaimForm.PROSE,
        ClaimForm.DISPLAY,
        ClaimForm.PROSE,
        ClaimForm.PROSE,
        ClaimForm.PROSE,
    ]
    assert main_claims[0].raw.startswith("By Lemma~\\ref{lem:base}")
    assert main_claims[1].raw.startswith("\\[")
    assert main_claims[2].raw == "The limit clearly has full rank."
    assert main_claims[3].raw == "Therefore the limit is admissible."

    first_support = graph.incoming_edges(main_claims[0].identifier)
    assert len(first_support) == 1
    assert first_support[0].kind == SupportKind.RESULT_REFERENCE
    assert first_support[0].target_label == "lem:base"

    display = main_claims[1]
    assert len(display.qualifiers) == 1
    qualifier = display.qualifiers[0]
    assert qualifier.kind == QualifierKind.TRAILING_BINDER
    assert qualifier.raw == r"for every $x\in\mathbb R$."
    assert [bound.name for bound in qualifier.bound_names] == ["x"]
    assert qualifier.source.start_line == 25

    sneaky = main_claims[2]
    conclusion = main_claims[3]
    assert graph.incoming_edges(sneaky.identifier) == []
    conclusion_support = graph.incoming_edges(conclusion.identifier)
    assert len(conclusion_support) == 1
    assert conclusion_support[0].kind == SupportKind.PRIOR_CLAIM
    assert conclusion_support[0].source_claim_identifier == sneaky.identifier
    assert graph.downstream_claim_ids(sneaky.identifier) == [conclusion.identifier]
    assert sneaky.identifier in graph.load_bearing_claim_ids()
    assert sneaky.identifier in graph.unsupported_load_bearing_claim_ids()

    final_support = graph.incoming_edges(main_claims[4].identifier)
    assert {edge.kind for edge in final_support} == {
        SupportKind.DEFINITION,
        SupportKind.EQUATION_REFERENCE,
    }
    assert next(
        edge for edge in final_support if edge.kind == SupportKind.EQUATION_REFERENCE
    ).target_label == "eq:bound"

    base_claim = graph.claims_for_result("lem:base")[0]
    base_support = graph.incoming_edges(base_claim.identifier)
    assert len(base_support) == 1
    assert base_support[0].kind == SupportKind.NAMED_PROPERTY
    assert base_support[0].named_property == "continuity"


def test_trailing_rebindings_keep_distinct_binding_identity(tmp_path: Path) -> None:
    tex = tmp_path / "binders.tex"
    tex.write_text(
        r"""
\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:binders}
A statement.
\end{theorem}
\begin{proof}
\[
  x > 0
\]
for every $x\in A$.
\[
  x < 1
\]
for every $x\in B$.
\end{proof}
\end{document}
""".lstrip(),
        encoding="utf-8",
    )

    claims = extract_project(tex).proof_support_graph.claims_for_result("thm:binders")
    displays = [claim for claim in claims if claim.form == ClaimForm.DISPLAY]
    assert len(displays) == 2
    first_bound = displays[0].qualifiers[0].bound_names[0]
    second_bound = displays[1].qualifiers[0].bound_names[0]
    assert first_bound.name == second_bound.name == "x"
    assert first_bound.identifier != second_bound.identifier
    assert first_bound.source.start_offset != second_bound.source.start_offset


def test_explicit_since_reason_is_support_without_validity_claim(tmp_path: Path) -> None:
    tex = tmp_path / "since.tex"
    tex.write_text(
        r"""
\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:since}
A statement.
\end{theorem}
\begin{proof}
Since $x>0$, $x^2>0$.
\end{proof}
\end{document}
""".lstrip(),
        encoding="utf-8",
    )

    graph = extract_project(tex).proof_support_graph
    claim = graph.claims_for_result("thm:since")[0]
    support = graph.incoming_edges(claim.identifier)
    assert len(support) == 1
    assert support[0].kind == SupportKind.EXPLICIT_REASON
    assert support[0].raw_justification == "$x>0$"


def test_support_ir_is_frontend_neutral_on_representative_fixture(
    tmp_path: Path,
) -> None:
    tex = _write_support_fixture(tmp_path / "frontends.tex")
    regex = extract_project(tex, frontend=get_frontend("regex")).proof_support_graph
    pylatexenc = extract_project(
        tex,
        frontend=get_frontend("pylatexenc"),
    ).proof_support_graph

    assert pylatexenc.model_dump() == regex.model_dump()
