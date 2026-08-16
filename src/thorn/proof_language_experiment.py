from __future__ import annotations

from typing import Literal

from thorn.llm_proof_language import LLMProofLanguage
from thorn.models import TheoremUnit
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewTurnRequest,
    build_proof_review_turn,
    build_raw_review_turn,
)
from thorn.providers.request_envelope import (
    ProviderRequestEnvelope,
    proof_review_request_envelope,
    render_theorem_unit,
)

ProofReviewExperimentArm = Literal["raw", "proof_ir", "proof_ir_rescue"]
PROOF_REVIEW_EXPERIMENT_ARMS: tuple[ProofReviewExperimentArm, ...] = (
    "raw",
    "proof_ir",
    "proof_ir_rescue",
)


def proof_review_experiment_turn(
    unit: TheoremUnit,
    document: LLMProofLanguage,
    arm: ProofReviewExperimentArm,
) -> ProofReviewTurnRequest:
    """Build one initial A/B/C turn while holding the review contract fixed."""

    if arm == "raw":
        return build_raw_review_turn(render_theorem_unit(unit))
    if arm == "proof_ir":
        return build_proof_review_turn(
            ProofLanguageReviewRequest(
                document=document,
                allow_source_rescue=False,
            )
        )
    if arm == "proof_ir_rescue":
        return build_proof_review_turn(
            ProofLanguageReviewRequest(
                document=document,
                allow_source_rescue=True,
            )
        )
    raise ValueError(f"unknown proof-review experiment arm: {arm!r}")


def proof_review_experiment_envelope(
    unit: TheoremUnit,
    document: LLMProofLanguage,
    model: str,
    arm: ProofReviewExperimentArm,
) -> ProviderRequestEnvelope:
    return proof_review_request_envelope(
        proof_review_experiment_turn(unit, document, arm),
        model,
    )
