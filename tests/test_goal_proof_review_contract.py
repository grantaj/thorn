from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    PROMPT_VERSION,
    PROTOCOL_VERSION,
    ProofLanguageReviewRequest,
    build_proof_review_turn,
)
from thorn.providers.request_envelope import proof_review_request_envelope


def test_review_v2_explicitly_requires_goal_support_comparison() -> None:
    document = LLMProofLanguage(
        result_identifier="thm:test",
        lines=(
            "THORN-PROOF 1",
            "T0 Q <- C1 ? @C1,T0",
            "C1 P",
            "GOAL G0 T0: Q | ctx C1 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="ir:T0",
                text="Q",
            ),
            ProofLanguageSourceHandle(
                address="C1",
                ir_identifier="ir:C1",
                text="P",
            ),
        ),
    )
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=document))
    envelope = proof_review_request_envelope(turn, "test-model")

    assert PROMPT_VERSION == "proof_language_reviewer_v2"
    assert PROTOCOL_VERSION == "thorn-proof-review/2"
    assert envelope.protocol_version == PROTOCOL_VERSION
    assert envelope.initial_packet_fingerprint == document.fingerprint()
    assert (
        "For each theorem goal, compare what must be shown with the strongest "
        "conclusion actually supported by the recovered proof structure"
        in envelope.system_prompt
    )
    assert (
        "do not treat an unresolved candidate discharge as evidence that the goal follows"
        in envelope.system_prompt
    )
