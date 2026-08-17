from __future__ import annotations

import pytest

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    build_proof_review_turn,
    build_rescue_turn,
)


def _need(*addresses: str) -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=addresses,
        review_items=(
            ProofReviewItem(
                id="R1",
                kind="question",
                summary="Does exact prerequisite source settle this review question?",
            ),
        ),
        source_review_item_ids=("R1",),
    )


def _chain_document() -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:chain",
        lines=(
            "THORN-PROOF 1",
            "T0 Q <- P2 ? @P2,T0 @T0",
            "P1 A <- ? @P1",
            "P2 Q <- P1 ~ @E1 @P2",
            "HOLE O1 P1: A | ctx - | open @P1",
            "HOLE O2 P2: Q | ctx P1 | open @P2",
            "GOAL G0 T0: Q | ctx P1,P2 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="P1",
                ir_identifier="claim:P1",
                text="First prerequisite.",
            ),
            ProofLanguageSourceHandle(
                address="P2",
                ir_identifier="claim:P2",
                text="Second prerequisite.",
            ),
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="result:T0",
                text="Claim Q.",
            ),
            ProofLanguageSourceHandle(
                address="E1",
                ir_identifier="edge:E1",
                text="Recovered edge evidence.",
            ),
        ),
    )


def _cancellation_document() -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:cancellation",
        lines=(
            "THORN-PROOF 1",
            "T0 x=y <- P1 ? @P1,T0 @T0",
            "U1 a(x-y)=0 <- ? @U1",
            "P1 x=y <- ? @P1",
            "HOLE O1 U1: a(x-y)=0 | ctx - | open @U1",
            "HOLE O2 P1: x=y | ctx U1 | open @P1",
            "GOAL G0 T0: x=y | ctx U1,P1 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="U1",
                ir_identifier="claim:U1",
                text="From ax=ay, subtract and factor to get a(x-y)=0.",
            ),
            ProofLanguageSourceHandle(
                address="P1",
                ir_identifier="claim:P1",
                text="Since a is nonzero, x-y=0 and hence x=y.",
            ),
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="result:T0",
                text="If a is nonzero and ax=ay, then x=y.",
            ),
        ),
    )


def test_rescue_expands_requested_proposition_to_unresolved_context() -> None:
    request = ProofLanguageReviewRequest(document=_chain_document())
    initial = build_proof_review_turn(request)

    rescue = build_rescue_turn(request, initial, _need("P2"))

    assert rescue.requested_source_addresses == ("P1", "P2")
    assert rescue.prior_response == _need("P2")
    assert "SOURCE @P1\nFirst prerequisite.\nEND_SOURCE @P1" in rescue.user_content
    assert "SOURCE @P2\nSecond prerequisite.\nEND_SOURCE @P2" in rescue.user_content
    assert "SOURCE @E1" not in rescue.user_content


def test_rescue_expands_goal_context_dependency_first_without_duplicates() -> None:
    request = ProofLanguageReviewRequest(document=_chain_document())
    initial = build_proof_review_turn(request)

    rescue = build_rescue_turn(request, initial, _need("P2", "T0"))

    assert rescue.requested_source_addresses == ("P1", "P2", "T0")


def test_rescue_expansion_covers_cancellation_regression_shape() -> None:
    request = ProofLanguageReviewRequest(document=_cancellation_document())
    initial = build_proof_review_turn(request)

    rescue = build_rescue_turn(request, initial, _need("P1"))

    assert rescue.requested_source_addresses == ("U1", "P1")
    assert "SOURCE @U1" in rescue.user_content
    assert "SOURCE @P1" in rescue.user_content


def test_expanded_rescue_still_obeys_existing_source_cap() -> None:
    request = ProofLanguageReviewRequest(
        document=_chain_document(),
        max_source_addresses=1,
    )
    initial = build_proof_review_turn(request)

    with pytest.raises(ProofReviewProtocolError, match="at most 1"):
        build_rescue_turn(request, initial, _need("P2"))


def test_review_contract_forbids_converting_recovery_uncertainty_to_defect() -> None:
    request = ProofLanguageReviewRequest(document=_chain_document())
    initial = build_proof_review_turn(request)
    rescue = build_rescue_turn(request, initial, _need("P2"))

    assert "Never report a defect solely because" in initial.user_content
    assert "FINAL_RESCUE_POLICY" in rescue.user_content
    assert "do not convert that uncertainty into a mathematical finding" in rescue.user_content
