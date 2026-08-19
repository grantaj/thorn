from __future__ import annotations

from pathlib import Path

import pytest

from thorn.latex import extract_project
from thorn.llm_proof_language import parse_source_rescue_request, render_source_rescue
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review

ROOT = Path(__file__).resolve().parents[1]
A2_SOURCE = ROOT / "eval" / "robustness" / "issue_101" / "variant_prose_uniformity.tex"


def _prepare(tmp_path: Path, body: str):
    paper = tmp_path / "paper.tex"
    paper.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body.strip()}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    project = extract_project(paper)
    unit = project.unit("thm:main")
    return paper, prepare_proof_review(project, unit)


def _source_matching(prepared, needle: str):
    matches = [source for source in prepared.document.sources if needle in source.text]
    assert len(matches) == 1
    return matches[0]


def test_reduced_prose_predicate_is_reachable_without_packet_prose(tmp_path: Path) -> None:
    definition = (
        "A map will be called \\emph{balanced} when every fibre contains exactly two points."
    )
    paper, prepared = _prepare(
        tmp_path,
        rf"""
{definition}
Balanced maps are a useful illustration of finite covering phenomena.

\begin{{theorem}}\label{{thm:main}}
The map \(f\) is balanced.
\end{{theorem}}
\begin{{proof}}
The assertion follows from the construction.
\end{{proof}}
""",
    )

    source = _source_matching(prepared, "every fibre contains exactly two points")
    packet = prepared.document.render_initial()
    advertised = set(advertised_source_addresses(prepared.document))

    assert definition not in packet
    assert source.address in advertised
    assert source.source_span is not None
    assert source.source_span.file == str(paper.resolve())
    assert source.source_span.text(paper.read_text(encoding="utf-8")) == definition

    request = parse_source_rescue_request(prepared.document, f"NEED_SOURCE {source.address}")
    rescue = render_source_rescue(prepared.document, request)
    assert definition in rescue.text


def test_ambient_convention_is_reachable_when_result_uses_its_subject(tmp_path: Path) -> None:
    convention = r"Throughout, the coefficient ring is \(R=\mathbb Z/6\mathbb Z\)."
    _, prepared = _prepare(
        tmp_path,
        rf"""
{convention}

\begin{{theorem}}\label{{thm:main}}
Cancellation by \(2\) is valid in the coefficient ring.
\end{{theorem}}
\begin{{proof}}
Apply the stated cancellation law.
\end{{proof}}
""",
    )

    source = _source_matching(prepared, "coefficient ring")
    advertised = set(advertised_source_addresses(prepared.document))
    assert source.address in advertised
    assert convention in render_source_rescue(
        prepared.document,
        parse_source_rescue_request(prepared.document, f"NEED_SOURCE {source.address}"),
    ).text


def test_nearby_motivational_prose_is_not_semantic_source(tmp_path: Path) -> None:
    motivation = "Balanced maps are a useful illustration of finite covering phenomena."
    _, prepared = _prepare(
        tmp_path,
        rf"""
A map will be called \emph{{balanced}} when every fibre contains exactly two points.
{motivation}

\begin{{theorem}}\label{{thm:main}}
The map \(f\) is balanced.
\end{{theorem}}
\begin{{proof}}
The assertion follows from the construction.
\end{{proof}}
""",
    )

    source_texts = [source.text for source in prepared.document.sources]
    assert any("every fibre contains exactly two points" in text for text in source_texts)
    assert not any(motivation in text for text in source_texts)
    assert motivation not in prepared.document.render_initial()


def test_held_out_geometric_predicate_uses_same_dependency_mechanism(tmp_path: Path) -> None:
    definition = (
        "A quadrilateral is called \\emph{diagonal-regular} when its two diagonals have equal length."
    )
    _, prepared = _prepare(
        tmp_path,
        rf"""
{definition}

\begin{{theorem}}\label{{thm:main}}
Every rectangle is diagonal-regular.
\end{{theorem}}
\begin{{proof}}
Use the usual diagonal symmetry of a rectangle.
\end{{proof}}
""",
    )

    source = _source_matching(prepared, "two diagonals have equal length")
    assert source.address in set(advertised_source_addresses(prepared.document))
    assert "converg" not in source.text.lower()
    assert "uniform" not in source.text.lower()


def test_source_rescue_remains_closed_world_for_semantic_context(tmp_path: Path) -> None:
    _, prepared = _prepare(
        tmp_path,
        r"""
A map will be called \emph{balanced} when every fibre contains exactly two points.

\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}
The assertion follows from the construction.
\end{proof}
""",
    )

    with pytest.raises(KeyError, match="unknown proof-language source addresses"):
        parse_source_rescue_request(prepared.document, "NEED_SOURCE NOT_A_SOURCE")


def test_historical_a2_definition_and_ambient_window_are_reachable() -> None:
    project = extract_project(A2_SOURCE)
    prepared = prepare_proof_review(project, project.unit("thm:uniform-decay"))
    advertised = set(advertised_source_addresses(prepared.document))

    definition = _source_matching(prepared, "will be called \\emph{stable}")
    convention = _source_matching(prepared, "Throughout, the observation window is")

    assert definition.address in advertised
    assert convention.address in advertised
    assert "following uniform requirement holds" in definition.text
    assert "\\mathcal W" in convention.text
