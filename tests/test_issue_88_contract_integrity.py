from __future__ import annotations

import pytest

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    advertised_source_addresses,
    build_proof_review_turn,
    build_rescue_turn,
)


def _document(
    *advertised: str,
    held_only: tuple[str, ...] = (),
) -> LLMProofLanguage:
    lines = ["THORN-PROOF 1", "T0 Goal"]
    for index, address in enumerate(advertised, start=1):
        lines.append(f"P{index} Fact{index} <- ? @{address}")
    lines.append("GOAL G0 T0: Goal | ctx - | open")
    all_handles = (*advertised, *held_only)
    return LLMProofLanguage(
        result_identifier="thm:closed-world-integrity",
        lines=tuple(lines),
        sources=tuple(
            ProofLanguageSourceHandle(
                address=address,
                ir_identifier=f"source:{index}",
                text=f"Exact source for {address}.",
            )
            for index, address in enumerate(all_handles, start=1)
        ),
    )


def test_zero_advertised_handles_disable_effective_rescue_consistently() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    turn = build_proof_review_turn(request)
    schema = turn.response_schema()

    assert turn.allowed_source_addresses == ()
    assert turn.source_rescue_allowed is False
    assert turn.max_source_addresses == 0
    assert "SOURCE_RESCUE disabled\n" in turn.user_content
    assert "SOURCE_RESCUE allowed-once\n" not in turn.user_content
    assert schema["properties"]["action"]["const"] == "review"
    assert schema["properties"]["source_addresses"]["maxItems"] == 0


def test_source_disclosure_rebinds_stored_contract_to_exact_advertised_packet() -> None:
    document = _document("E1", held_only=("H1",))
    request = ProofLanguageReviewRequest(document=document)
    turn = build_proof_review_turn(request)

    assert advertised_source_addresses(document) == ("E1",)
    assert document.source("H1").text == "Exact source for H1."
    assert "H1" not in turn.allowed_source_addresses

    # model_copy(update=...) deliberately bypasses normal Pydantic validation and
    # simulates an incorrectly constructed internal turn. H1 is a real held source
    # handle, but it was never advertised in this exact packet and must therefore
    # remain undisclosable at the final rescue boundary.
    forged = turn.model_copy(update={"allowed_source_addresses": ("E1", "H1")})
    source_request = ProofReviewModelResponse(
        action="need_source",
        source_addresses=("H1",),
        review_items=(
            ProofReviewItem(
                id="RV1",
                kind="question",
                summary="Does the held source settle this review question?",
            ),
        ),
        source_review_item_ids=("RV1",),
    )

    with pytest.raises(
        ProofReviewProtocolError,
        match="source-selection contract does not match proof-language packet",
    ):
        build_rescue_turn(request, forged, source_request)