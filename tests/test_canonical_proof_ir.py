from __future__ import annotations

import re
from pathlib import Path

from thorn.canonical_proof_ir import (
    CanonicalNodeKind,
    build_canonical_proof_ir,
    canonicalize_mathematical_text,
    normalize_latex_math,
)
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.semantic_review_render import build_semantic_review_request

CASES = Path("eval/cases/ladder")


class _RootedTestFrontend:
    name = "rooted-test"

    def parse(self, text: str) -> LinguisticDocument:
        matches = list(re.finditer(r"\S+", text))
        tokens: list[LinguisticToken] = []
        for index, match in enumerate(matches):
            tokens.append(
                LinguisticToken(
                    index=index,
                    text=match.group(0),
                    lemma=match.group(0).lower(),
                    pos="VERB" if index == 0 else "NOUN",
                    dependency="ROOT" if index == 0 else "dep",
                    head_index=0,
                    sentence_index=0,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return LinguisticDocument(text=text, tokens=tokens)


def _build(path: Path, target_identifier: str):
    project = extract_project(path, linguistic_frontend=_RootedTestFrontend())
    unit = project.unit(target_identifier)
    context = build_result_review_context(project, target_identifier)
    assert len(context.items) == 1
    request = build_semantic_review_request(context.items[0])
    return request, build_canonical_proof_ir(unit, request)


def _write_document(path: Path, *, proof: str) -> None:
    path.write_text(
        """\\documentclass{article}
\\usepackage{amsthm}
\\newtheorem{theorem}{Theorem}
\\begin{document}
\\begin{theorem}\\label{thm:test}
$Q$.
\\end{theorem}
\\begin{proof}
"""
        + proof
        + """
\\end{proof}
\\end{document}
""",
        encoding="utf-8",
    )


def test_safe_mathematical_vocabulary_normalizes_to_symbols() -> None:
    first = canonicalize_mathematical_text(
        "For all $x\\in X$, if $P(x)$, then $Q(x)$."
    )
    second = canonicalize_mathematical_text(
        "For every $x\\in X$, if $P(x)$, then $Q(x)$."
    )

    assert first == second == "∀x∈ X.(P(x)⇒Q(x))"
    assert normalize_latex_math(
        r"\forall x\in X, P(x)\Rightarrow Q(x)"
    ) == "∀ x∈ X, P(x)⇒ Q(x)"


def test_non_load_bearing_exposition_does_not_change_canonical_ir(tmp_path: Path) -> None:
    base = tmp_path / "base.tex"
    with_exposition = tmp_path / "with-exposition.tex"
    display = """\\[
Q
\\]
"""
    _write_document(base, proof=display)
    _write_document(
        with_exposition,
        proof="This sentence only orients the reader.\n" + display,
    )

    _, base_ir = _build(base, "thm:test")
    _, exposition_ir = _build(with_exposition, "thm:test")

    assert base_ir.render_initial() == exposition_ir.render_initial()
    assert exposition_ir.pruned_claims == 1
    assert "orients the reader" not in exposition_ir.render_initial()


def test_non_slice_math_retains_math_but_not_narration(tmp_path: Path) -> None:
    path = tmp_path / "math-exposition.tex"
    _write_document(
        path,
        proof=(
            "For orientation only, record the auxiliary quantity $Z$.\n"
            "\\[\nQ\n\\]\n"
        ),
    )

    _, canonical = _build(path, "thm:test")
    rendered = canonical.render_initial()

    assert "For orientation" not in rendered
    assert "U1:Z" in rendered
    assert canonical.unresolved_math_claims == 1
    unresolved = next(
        node for node in canonical.nodes if node.kind == CanonicalNodeKind.UNRESOLVED_MATH
    )
    assert "For orientation" in canonical.source(unresolved.address).text


def test_therefore_and_hence_have_identical_structural_ir(tmp_path: Path) -> None:
    therefore = tmp_path / "therefore.tex"
    hence = tmp_path / "hence.tex"
    premise = """\\[
P
\\]
"""
    _write_document(therefore, proof=premise + "Therefore $Q$.\n")
    _write_document(hence, proof=premise + "Hence $Q$.\n")

    _, therefore_ir = _build(therefore, "thm:test")
    _, hence_ir = _build(hence, "thm:test")

    assert therefore_ir.render_initial() == hence_ir.render_initial()
    assert "therefore" not in therefore_ir.render_initial().lower()
    assert "hence" not in hence_ir.render_initial().lower()
    assert ":c" in therefore_ir.render_initial()


def test_result_reference_becomes_dependency_edge_not_prose(tmp_path: Path) -> None:
    path = tmp_path / "dependency.tex"
    path.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:prior}
$P$.
\end{lemma}
\begin{proof}
\[
P
\]
\end{proof}
\begin{theorem}\label{thm:test}
$Q$.
\end{theorem}
\begin{proof}
By Lemma~\ref{lem:prior}, $Q$.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    _, canonical = _build(path, "thm:test")
    rendered = canonical.render_initial()

    assert "By Lemma" not in rendered
    assert "R1:" in rendered
    assert "R1>C1:r" in rendered


def test_disconnected_expository_prose_is_pruned() -> None:
    _, canonical = _build(
        CASES / "06_support_structure/expository_prose_clean.tex",
        "thm:expository",
    )

    rendered = canonical.render_initial()
    assert canonical.pruned_claims == 1
    assert "This sentence only records notation for the reader" not in rendered
    assert "continuity" in rendered


def test_ambiguous_load_bearing_prose_survives_backward_slice() -> None:
    request, canonical = _build(
        CASES / "06_support_structure/sneaky_prose_downstream.tex",
        "lem:sneaky-limit",
    )

    before = request.item.model_dump(mode="json")
    rendered = canonical.render_initial()

    assert canonical.pruned_claims == 0
    assert "The limit clearly has full rank." in rendered
    assert ":c?" in rendered
    full_rank = next(
        node
        for node in canonical.nodes
        if node.kind == CanonicalNodeKind.OPAQUE_PROSE and "full rank" in node.atom
    )
    assert canonical.source(full_rank.address).text == "The limit clearly has full rank."
    assert request.item.model_dump(mode="json") == before
