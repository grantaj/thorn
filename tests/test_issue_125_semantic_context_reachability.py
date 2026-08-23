from __future__ import annotations

from pathlib import Path

import pytest

from candidate_context_contract import prepare_all_prior_context
from sentence_contract_frontend import SentenceContractFrontend
from thorn.context_retrieval import build_result_context_pools
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.llm_proof_language import parse_source_rescue_request, render_source_rescue
from thorn.proof_language_review import (
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewTurnRequest,
    advertised_source_addresses,
)
from thorn.report import ProofReviewReportInput, ReviewExecution, proof_review_metadata

ROOT = Path(__file__).resolve().parents[1]
A2_SOURCE = ROOT / "eval" / "robustness" / "issue_101" / "variant_prose_uniformity.tex"


def _extract(path: Path):
    return extract_project(
        path,
        linguistic_frontend=SentenceContractFrontend(),
    )


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
    project = _extract(paper)
    return paper, project, prepare_all_prior_context(project, "thm:main")


def _source_matching(prepared, needle: str):
    matches = [source for source in prepared.document.sources if needle in source.text]
    assert len(matches) == 1
    return matches[0]


def test_reduced_prose_predicate_is_reachable_without_packet_prose(tmp_path: Path) -> None:
    definition = (
        "A map will be called \\emph{balanced} when every fibre contains exactly two points."
    )
    paper, project, prepared = _prepare(
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
    assert not any(symbol.name == "balanced" for symbol in project.symbol_table.symbols)

    request = parse_source_rescue_request(prepared.document, f"NEED_SOURCE {source.address}")
    rescue = render_source_rescue(prepared.document, request)
    assert definition in rescue.text


def test_prose_context_is_not_promoted_into_result_selector_authority(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
A map will be called \emph{balanced} when every fibre contains exactly two points.

\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}
The assertion follows from the construction.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )
    project = _extract(paper)

    item = build_result_review_context(project, "thm:main").items[0]
    assert all(symbol.name != "balanced" for symbol in item.symbols)
    assert not any(
        "every fibre contains exactly two points" in definition.raw
        for definition in item.definitions
    )

    pools = build_result_context_pools(project, "thm:main")
    assert any(
        "every fibre contains exactly two points" in candidate.text
        for pool in pools
        for candidate in pool.candidates
    )


def test_ambient_convention_is_exact_reachable_context(tmp_path: Path) -> None:
    convention = r"Throughout, the coefficient ring is \(R=\mathbb Z/6\mathbb Z\)."
    _, project, prepared = _prepare(
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

    source = _source_matching(prepared, "Throughout, the coefficient ring is")
    advertised = set(advertised_source_addresses(prepared.document))
    assert source.address in advertised
    assert convention in render_source_rescue(
        prepared.document,
        parse_source_rescue_request(prepared.document, f"NEED_SOURCE {source.address}"),
    ).text
    assert not any(symbol.name == "coefficient ring" for symbol in project.symbol_table.symbols)


def test_nearby_motivational_prose_may_be_candidate_but_not_authority(tmp_path: Path) -> None:
    motivation = "Balanced maps are a useful illustration of finite covering phenomena."
    _, project, prepared = _prepare(
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
    assert any(motivation in text for text in source_texts)
    assert motivation not in prepared.document.render_initial()
    assert not any(symbol.name == "balanced" for symbol in project.symbol_table.symbols)


def test_held_out_geometric_predicate_uses_same_context_mechanism(tmp_path: Path) -> None:
    definition = (
        "A quadrilateral is called \\emph{diagonal-regular} when its two diagonals "
        "have equal length."
    )
    _, project, prepared = _prepare(
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
    assert not any(symbol.name == "regular" for symbol in project.symbol_table.symbols)


def test_recovered_prose_keeps_report_source_navigation(tmp_path: Path) -> None:
    definition = (
        "A map will be called \\emph{balanced} when every fibre contains exactly two points."
    )
    paper, project, prepared = _prepare(
        tmp_path,
        rf"""
{definition}

\begin{{theorem}}\label{{thm:main}}
The map \(f\) is balanced.
\end{{theorem}}
\begin{{proof}}
The assertion follows from the construction.
\end{{proof}}
""",
    )
    unit = project.unit("thm:main")
    source = _source_matching(prepared, "every fibre contains exactly two points")
    initial = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint=prepared.document.fingerprint(),
        user_content=prepared.document.render_initial(),
        source_rescue_allowed=True,
        allowed_source_addresses=(source.address,),
    )
    prior = ProofReviewModelResponse(
        action="need_source",
        source_addresses=(source.address,),
        review_items=(
            ProofReviewItem(
                id="RV1",
                kind="question",
                summary="What source context defines balanced?",
            ),
        ),
        source_review_item_ids=("RV1",),
    )
    rescue = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="rescue",
        initial_packet_fingerprint=prepared.document.fingerprint(),
        user_content=definition,
        source_rescue_allowed=False,
        requested_source_addresses=(source.address,),
        initial_user_content=initial.user_content,
        prior_response=prior,
    )
    metadata = proof_review_metadata(
        ProofReviewReportInput(
            result_identifier=unit.identifier,
            initial_turn=initial,
            model="keyless-test",
            execution=ReviewExecution.REPLAY,
            rescue_turn=rescue,
            document=prepared.document,
            source=unit.statement_range,
        )
    )

    assert len(metadata.source_rescue) == 1
    report_source = metadata.source_rescue[0].source
    assert report_source is not None
    assert report_source.file == str(paper.resolve())
    assert report_source.excerpt == definition
    assert report_source.source_addresses == (source.address,)
    assert report_source.uri is not None and report_source.uri.startswith("file:")


def test_source_rescue_remains_closed_world_for_advisory_context(tmp_path: Path) -> None:
    _, _, prepared = _prepare(
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
    project = _extract(A2_SOURCE)
    prepared = prepare_all_prior_context(project, "thm:uniform-decay")
    advertised = set(advertised_source_addresses(prepared.document))

    definition = _source_matching(prepared, "will be called \\emph{stable}")
    convention = _source_matching(prepared, "Throughout, the observation window is")

    assert definition.address in advertised
    assert convention.address in advertised
    assert "following uniform requirement holds" in definition.text
    assert "\\mathcal W" in convention.text
