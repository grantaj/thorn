from __future__ import annotations

from pathlib import Path

from thorn.latex import extract_project
from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewItem,
    ProofReviewModelResponse,
    build_proof_review_turn,
    build_rescue_turn,
)
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.review_workflow import prepare_proof_review


def _need(*addresses: str) -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=addresses,
        review_items=(
            ProofReviewItem(
                id="RV1",
                kind="question",
                summary="Does the bounded exact source settle this review question?",
            ),
        ),
        source_review_item_ids=("RV1",),
    )


def _deep_chain_document() -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:deep-chain",
        lines=(
            "THORN-PROOF 1",
            "P1 A <- ? @P1",
            "P2 B <- P1 ? @P2",
            "T0 C <- P2 ? @T0",
            "HOLE O1 P1: A | ctx - | open @P1",
            "HOLE O2 P2: B | ctx P1 | open @P2",
            "GOAL G0 T0: C | ctx P2 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="P1",
                ir_identifier="claim:P1",
                text="Distant prerequisite A.",
            ),
            ProofLanguageSourceHandle(
                address="P2",
                ir_identifier="claim:P2",
                text="Nearest prerequisite B.",
            ),
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="result:T0",
                text="Requested conclusion C.",
            ),
        ),
    )


def test_bounded_enrichment_prefers_nearest_prerequisite() -> None:
    request = ProofLanguageReviewRequest(
        document=_deep_chain_document(),
        max_source_addresses=2,
    )
    initial = build_proof_review_turn(request)

    rescue = build_rescue_turn(request, initial, _need("T0"))

    assert rescue.requested_source_addresses == ("P2", "T0")
    assert "SOURCE @P2" in rescue.user_content
    assert "SOURCE @T0" in rescue.user_content
    assert "SOURCE @P1" not in rescue.user_content


def test_requested_handles_remain_mandatory_when_they_fill_the_cap() -> None:
    request = ProofLanguageReviewRequest(
        document=_deep_chain_document(),
        max_source_addresses=2,
    )
    initial = build_proof_review_turn(request)

    rescue = build_rescue_turn(request, initial, _need("P2", "T0"))

    assert rescue.requested_source_addresses == ("P2", "T0")
    assert "SOURCE @P1" not in rescue.user_content


def test_issue_101_c0_live_source_selection_stays_within_bound() -> None:
    path = Path("eval/robustness/issue_101/clean_control.tex")
    project = extract_project(path)
    unit = project.unit("thm:uniform-decay")
    prepared = prepare_proof_review(project, unit)
    request = ProofLanguageReviewRequest(document=prepared.document)
    initial = build_proof_review_turn(request)

    # The preserved pre-repair live response requested exactly these two handles.
    response = _need("T0", "P3")
    rescue = build_rescue_turn(request, initial, response)

    assert initial.max_source_addresses == 8
    assert len(response.source_addresses) == 2
    assert set(response.source_addresses) <= set(rescue.requested_source_addresses)
    assert len(rescue.requested_source_addresses) <= initial.max_source_addresses
    assert set(rescue.requested_source_addresses) <= set(initial.allowed_source_addresses)


def test_bounded_rescue_selection_and_fingerprint_are_deterministic() -> None:
    request = ProofLanguageReviewRequest(
        document=_deep_chain_document(),
        max_source_addresses=2,
    )
    initial = build_proof_review_turn(request)
    response = _need("T0")

    first = build_rescue_turn(request, initial, response)
    second = build_rescue_turn(request, initial, response)

    assert first.requested_source_addresses == second.requested_source_addresses
    assert proof_review_request_envelope(first, "test-model").fingerprint() == (
        proof_review_request_envelope(second, "test-model").fingerprint()
    )
