from __future__ import annotations

from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path

import pytest

from thorn.canonical_proof_ir import CanonicalEdgeKind, build_canonical_proof_ir
from thorn.dependencies import ExtractedProject
from thorn.eval_review import build_result_review_context
from thorn.frontend import FrontendRegionKind, LatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.frontends.regex import RegexLatexFrontend
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument
from thorn.semantic_review_render import build_semantic_review_request
from thorn.support import ClaimForm, SupportEdge, SupportKind

FrontendFactory = Callable[[], LatexFrontend]

if find_spec("tree_sitter") is not None and find_spec("tree_sitter_latex") is not None:
    from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

    _OPTIONAL_FRONTENDS: tuple[FrontendFactory, ...] = (TreeSitterLatexFrontend,)
else:
    _OPTIONAL_FRONTENDS = ()

_FRONTENDS: tuple[FrontendFactory, ...] = (
    RegexLatexFrontend,
    PylatexencLatexFrontend,
    *_OPTIONAL_FRONTENDS,
)


class NoRootFrontend:
    name = "no-root"

    def parse(self, text: str) -> LinguisticDocument:
        return LinguisticDocument(text=text, tokens=[])


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


def _source(body: str) -> str:
    return (
        "\\documentclass{article}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        "\\begin{theorem}\\label{thm:main}\n"
        "The conclusion holds.\n"
        "\\end{theorem}\n"
        "\\begin{proof}\n"
        f"{body.strip()}\n"
        "\\end{proof}\n"
        "\\end{document}\n"
    )


def _prior_claim_edges(
    project: ExtractedProject,
    claim_identifier: str,
) -> list[SupportEdge]:
    return [
        edge
        for edge in project.proof_support_graph.incoming_edges(claim_identifier)
        if edge.kind == SupportKind.PRIOR_CLAIM
    ]


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_comment_boundary_breaks_explicit_and_canonical_adjacency(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    source = _source(
        r"""
First $A$.
% HIDDEN_BOUNDARY
Therefore $B$.
"""
    )
    main.write_text(source, encoding="utf-8")

    project = extract_project(main, frontend=frontend_factory())
    claims = project.proof_support_graph.claims_for_result("thm:main")

    assert [claim.raw for claim in claims] == ["First $A$.", "Therefore $B$."]
    assert _prior_claim_edges(project, claims[1].identifier) == []

    review_item = build_result_review_context(project, "thm:main").items[0]
    request = build_semantic_review_request(review_item)
    proof_ir = build_canonical_proof_ir(project.unit("thm:main"), request)
    assert all(edge.kind != CanonicalEdgeKind.PRIOR_CLAIM for edge in proof_ir.edges)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
@pytest.mark.parametrize(
    ("boundary", "kind"),
    (
        (r"\begin{verbatim}" "\nHIDDEN\n" r"\end{verbatim}", FrontendRegionKind.VERBATIM),
        (r"\begin{lstlisting}" "\nHIDDEN\n" r"\end{lstlisting}", FrontendRegionKind.LISTING),
        (
            r"\begin{minted}{python}" "\nHIDDEN\n" r"\end{minted}",
            FrontendRegionKind.MINTED,
        ),
    ),
)
def test_advertised_environment_boundary_cannot_be_bridged(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
    boundary: str,
    kind: FrontendRegionKind,
) -> None:
    main = tmp_path / "main.tex"
    source = _source(f"First $A$.\n{boundary}\nTherefore $B$.")
    main.write_text(source, encoding="utf-8")

    frontend = frontend_factory()
    parsed = frontend.parse_project(main)
    parsed_file = parsed.file(main)
    if not parsed_file.regions_complete or not any(
        region.kind == kind for region in parsed_file.regions
    ):
        pytest.skip(f"{frontend.name} does not advertise complete {kind.value} regions")

    project = extract_project(main, frontend=frontend)
    claims = project.proof_support_graph.claims_for_result("thm:main")

    assert [claim.raw for claim in claims] == ["First $A$.", "Therefore $B$."]
    assert _prior_claim_edges(project, claims[1].identifier) == []


def test_local_nlp_adjacency_respects_boundary_and_eligible_control(tmp_path: Path) -> None:
    separated = tmp_path / "separated.tex"
    separated.write_text(
        _source(
            r"""
First $A$.
% HIDDEN_BOUNDARY
Next $B$.
"""
        ),
        encoding="utf-8",
    )
    separated_project = extract_project(
        separated,
        frontend=RegexLatexFrontend(),
        linguistic_frontend=NoRootFrontend(),
    )
    separated_claims = separated_project.proof_support_graph.claims_for_result("thm:main")
    assert _prior_claim_edges(separated_project, separated_claims[1].identifier) == []

    adjacent = tmp_path / "adjacent.tex"
    adjacent.write_text(
        _source(
            r"""
First $A$.
Next $B$.
"""
        ),
        encoding="utf-8",
    )
    adjacent_project = extract_project(
        adjacent,
        frontend=RegexLatexFrontend(),
        linguistic_frontend=NoRootFrontend(),
    )
    adjacent_claims = adjacent_project.proof_support_graph.claims_for_result("thm:main")
    assert len(_prior_claim_edges(adjacent_project, adjacent_claims[1].identifier)) == 1


def test_trailing_binder_does_not_cross_boundary_but_eligible_control_survives(
    tmp_path: Path,
) -> None:
    separated = tmp_path / "separated.tex"
    separated.write_text(
        _source(
            r"""
\[
  m \le f(x) \le M
\]
% HIDDEN_BOUNDARY
for every $x\in X$.
"""
        ),
        encoding="utf-8",
    )
    separated_project = extract_project(separated, frontend=RegexLatexFrontend())
    separated_claims = separated_project.proof_support_graph.claims_for_result("thm:main")
    separated_display = next(
        claim for claim in separated_claims if claim.form == ClaimForm.DISPLAY
    )
    assert separated_display.qualifiers == []
    assert any(claim.raw == r"for every $x\in X$." for claim in separated_claims)

    adjacent = tmp_path / "adjacent.tex"
    adjacent.write_text(
        _source(
            r"""
\[
  m \le f(x) \le M
\]
for every $x\in X$.
"""
        ),
        encoding="utf-8",
    )
    adjacent_project = extract_project(adjacent, frontend=RegexLatexFrontend())
    adjacent_claims = adjacent_project.proof_support_graph.claims_for_result("thm:main")
    adjacent_display = next(
        claim for claim in adjacent_claims if claim.form == ClaimForm.DISPLAY
    )
    assert len(adjacent_display.qualifiers) == 1
    assert adjacent_display.qualifiers[0].raw == r"for every $x\in X$."


def test_explicit_conclusion_still_uses_eligible_previous_claim(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    main.write_text(
        _source(
            r"""
First $A$.
Therefore $B$.
"""
        ),
        encoding="utf-8",
    )

    project = extract_project(main, frontend=RegexLatexFrontend())
    claims = project.proof_support_graph.claims_for_result("thm:main")
    edges = _prior_claim_edges(project, claims[1].identifier)

    assert len(edges) == 1
    assert edges[0].source_claim_identifier == claims[0].identifier
