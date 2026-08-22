from __future__ import annotations

from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path

import pytest

from thorn.canonical_proof_ir import build_canonical_proof_ir
from thorn.eval_review import build_result_review_context
from thorn.frontend import LatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.frontends.regex import RegexLatexFrontend
from thorn.latex import extract_project
from thorn.semantic_review_render import build_semantic_review_request
from thorn.support import ClaimForm, SupportKind

FrontendFactory = Callable[[], LatexFrontend]

if find_spec("tree_sitter") is not None and find_spec("tree_sitter_latex") is not None:
    from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

    _OPTIONAL_FRONTENDS: tuple[FrontendFactory, ...] = (TreeSitterLatexFrontend,)
else:
    _OPTIONAL_FRONTENDS = ()

_RETAINED_FRONTENDS: tuple[FrontendFactory, ...] = (
    RegexLatexFrontend,
    PylatexencLatexFrontend,
    *_OPTIONAL_FRONTENDS,
)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


def _source(body: str) -> str:
    return (
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body.strip()}\n"
        "\\end{document}\n"
    )


@pytest.mark.parametrize(
    "frontend_factory",
    _RETAINED_FRONTENDS,
    ids=_frontend_id,
)
def test_excluded_proof_source_never_becomes_claim_or_support(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    source = _source(
        r"""
\begin{theorem}\label{thm:eligible}
For every $x$, $x=x$.
\end{theorem}
\begin{proof}
First $x=x$.
% Therefore by compactness, COMMENT_ONLY.
\begin{verbatim}
Since VERBATIM_ONLY, therefore false.
By compactness, false.
\end{verbatim}
Therefore $x=x$.
% Since TRAILING_COMMENT_ONLY, false.
\end{proof}
"""
    )
    main.write_text(source, encoding="utf-8")

    project = extract_project(main, frontend=frontend_factory())
    claims = project.proof_support_graph.claims_for_result("thm:eligible")
    claim_text = "\n".join(claim.raw for claim in claims)
    edge_text = "\n".join(edge.raw_justification for edge in project.proof_support_graph.edges)

    assert "COMMENT_ONLY" not in claim_text
    assert "TRAILING_COMMENT_ONLY" not in claim_text
    assert "VERBATIM_ONLY" not in claim_text
    assert "COMMENT_ONLY" not in edge_text
    assert "TRAILING_COMMENT_ONLY" not in edge_text
    assert "VERBATIM_ONLY" not in edge_text
    assert [claim.raw for claim in claims] == ["First $x=x$.", "Therefore $x=x$."]

    review_item = build_result_review_context(project, "thm:eligible").items[0]
    request = build_semantic_review_request(review_item)
    proof_ir = build_canonical_proof_ir(project.unit("thm:eligible"), request)
    advertised_source = "\n".join(item.text for item in proof_ir.sources)
    assert "COMMENT_ONLY" not in advertised_source
    assert "TRAILING_COMMENT_ONLY" not in advertised_source
    assert "VERBATIM_ONLY" not in advertised_source


def test_excluded_source_is_a_hard_claim_boundary_with_exact_offsets(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    source = _source(
        r"""
\begin{theorem}\label{thm:offsets}
The claim holds.
\end{theorem}
\begin{proof}
Before the comment.
% HIDDEN_BOUNDARY
After the comment.
\end{proof}
"""
    )
    main.write_text(source, encoding="utf-8")

    project = extract_project(main, frontend=RegexLatexFrontend())
    claims = project.proof_support_graph.claims_for_result("thm:offsets")

    assert [claim.raw for claim in claims] == ["Before the comment.", "After the comment."]
    assert [claim.source.text(source) for claim in claims] == [
        "Before the comment.",
        "After the comment.",
    ]
    assert all("HIDDEN_BOUNDARY" not in claim.source.text(source) for claim in claims)


def test_display_math_and_trailing_binder_survive_eligible_projection(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    source = _source(
        r"""
\begin{theorem}\label{thm:binder}
The bound holds.
\end{theorem}
\begin{proof}
\[
  m \le f(x) \le M
\]
for every $x\in X$.
Therefore $m\le M$.
\end{proof}
"""
    )
    main.write_text(source, encoding="utf-8")

    project = extract_project(main, frontend=RegexLatexFrontend())
    claims = project.proof_support_graph.claims_for_result("thm:binder")
    display = next(claim for claim in claims if claim.form == ClaimForm.DISPLAY)

    assert len(display.qualifiers) == 1
    qualifier = display.qualifiers[0]
    assert qualifier.raw == "for every $x\\in X$."
    assert qualifier.source.text(source) == "for every $x\\in X$."
    assert qualifier.bound_names[0].name == "x"


def test_explicit_result_and_property_support_remain_available(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text(
        _source(
            r"""
\begin{lemma}\label{lem:base}
The base fact holds.
\end{lemma}
\begin{proof}Immediate.\end{proof}
\begin{theorem}\label{thm:support}
The conclusion holds.
\end{theorem}
\begin{proof}
By Lemma~\ref{lem:base}, the first step follows.
By compactness, pass to a convergent subsequence.
\end{proof}
"""
        ),
        encoding="utf-8",
    )

    project = extract_project(main, frontend=RegexLatexFrontend())
    claims = {
        claim.identifier
        for claim in project.proof_support_graph.claims_for_result("thm:support")
    }
    edges = [
        edge
        for edge in project.proof_support_graph.edges
        if edge.target_claim_identifier in claims
    ]

    assert any(
        edge.kind == SupportKind.RESULT_REFERENCE and edge.target_label == "lem:base"
        for edge in edges
    )
    assert any(
        edge.kind == SupportKind.NAMED_PROPERTY and edge.named_property == "compactness"
        for edge in edges
    )
