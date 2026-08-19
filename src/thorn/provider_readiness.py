from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTurnRequest,
    build_proof_review_turn,
    validate_proof_review_response,
)
from thorn.providers.base import (
    ProviderResponseValidationError,
    ProviderTransportError,
    ProviderTransportEvidence,
)
from thorn.providers.execution_contract import (
    ProviderExecutionContract,
    build_provider_execution_contract,
)
from thorn.providers.openai import OpenAIProvider
from thorn.providers.request_envelope import proof_review_request_envelope

READINESS_CANARY_FORMAT: Literal["thorn-provider-readiness/1"] = (
    "thorn-provider-readiness/1"
)
READINESS_CANARY_MAX_OUTPUT_TOKENS = 256


class ProviderReadinessError(RuntimeError):
    """A readiness artifact cannot be trusted for the current provider boundary."""


class ProviderReadinessEvidence(BaseModel):
    """Non-scientific evidence from Thorn's synthetic provider readiness canary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: Literal["thorn-provider-readiness/1"] = READINESS_CANARY_FORMAT
    mode: Literal["preflight", "live"]
    status: Literal[
        "preflight-ready",
        "live-success",
        "live-transport-failure",
        "live-response-failure",
    ]
    readiness_only: bool = True
    scientific_authorization: bool = False
    synthetic_input: bool = True
    provider_instantiated: bool
    model: str
    request_retries: int = 0
    max_output_tokens: int = READINESS_CANARY_MAX_OUTPUT_TOKENS
    execution_fingerprint: str
    execution_contract: ProviderExecutionContract
    provider_attempts: int = 0
    responses_received: int = 0
    model_generations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    normalized_response: dict[str, object] | None = None
    structured_response: dict[str, object] | None = None
    provider_response: dict[str, object] | None = None
    transport_failure: ProviderTransportEvidence | None = None
    response_failure_type: str | None = None
    response_failure_message: str | None = None


def build_readiness_turn() -> ProofReviewTurnRequest:
    """Return the tiny synthetic initial turn used to exercise provider machinery.

    The normal one-time source-rescue state is advertised so the canary exercises the
    production initial-turn action schema. The readiness runner deliberately executes
    only this initial turn: a valid ``need_source`` response is readiness success and
    never causes a second paid canary request.
    """

    document = LLMProofLanguage(
        result_identifier="thm:provider-readiness-synthetic",
        lines=(
            "THORN-PROOF 1",
            "T0 SyntheticGoal <- P1 @T0",
            "P1 SyntheticGoal @P1",
            "GOAL G0 T0: SyntheticGoal | ctx P1 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="P1",
                ir_identifier="proof:P1",
                text="Synthetic proof step.",
            ),
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="result:T0",
                text="Synthetic theorem statement.",
            ),
        ),
    )
    return build_proof_review_turn(ProofLanguageReviewRequest(document=document))


def readiness_execution_contract(model: str) -> ProviderExecutionContract:
    turn = build_readiness_turn()
    envelope = proof_review_request_envelope(
        turn,
        model,
        max_output_tokens=READINESS_CANARY_MAX_OUTPUT_TOKENS,
    )
    return build_provider_execution_contract(envelope)


def preflight_readiness(model: str) -> ProviderReadinessEvidence:
    """Construct exact readiness evidence without instantiating a provider client."""

    contract = readiness_execution_contract(model)
    return ProviderReadinessEvidence(
        mode="preflight",
        status="preflight-ready",
        provider_instantiated=False,
        model=model,
        execution_fingerprint=contract.fingerprint(),
        execution_contract=contract,
    )


def _live_failure_evidence(
    provider: OpenAIProvider,
    expected_contract: ProviderExecutionContract,
    *,
    status: Literal["live-transport-failure", "live-response-failure"],
    transport_failure: ProviderTransportEvidence | None = None,
    structured_response: ProofReviewModelResponse | None = None,
    response_failure_type: str | None = None,
    response_failure_message: str | None = None,
) -> ProviderReadinessEvidence:
    return ProviderReadinessEvidence(
        mode="live",
        status=status,
        provider_instantiated=True,
        model=provider.model,
        execution_fingerprint=expected_contract.fingerprint(),
        execution_contract=expected_contract,
        provider_attempts=provider.provider_attempts,
        responses_received=provider.responses_received,
        model_generations=provider.model_generations,
        input_tokens=provider.input_tokens,
        output_tokens=provider.output_tokens,
        total_tokens=provider.total_tokens,
        structured_response=(
            structured_response.model_dump(mode="json")
            if structured_response is not None
            else None
        ),
        provider_response=provider.last_response_payload,
        transport_failure=transport_failure,
        response_failure_type=response_failure_type,
        response_failure_message=response_failure_message,
    )


def run_live_readiness(model: str) -> ProviderReadinessEvidence:
    """Run exactly one bounded, synthetic provider request with no retry."""

    turn = build_readiness_turn()
    envelope = proof_review_request_envelope(
        turn,
        model,
        max_output_tokens=READINESS_CANARY_MAX_OUTPUT_TOKENS,
    )
    expected_contract = build_provider_execution_contract(envelope)
    provider = OpenAIProvider(
        model=model,
        proof_review_max_output_tokens=READINESS_CANARY_MAX_OUTPUT_TOKENS,
    )
    provider_contract = provider.execution_contract(envelope)
    if provider_contract.canonical_json() != expected_contract.canonical_json():
        raise ProviderReadinessError(
            "live provider construction does not match readiness preflight contract"
        )

    try:
        response = provider.review_proof_turn(turn)
    except ProviderTransportError as exc:
        return _live_failure_evidence(
            provider,
            expected_contract,
            status="live-transport-failure",
            transport_failure=exc.evidence,
        )
    except ProviderResponseValidationError as exc:
        return _live_failure_evidence(
            provider,
            expected_contract,
            status="live-response-failure",
            response_failure_type=exc.validation_exception_type,
            response_failure_message=str(exc),
        )

    try:
        normalized = validate_proof_review_response(turn, response)
    except ProofReviewProtocolError as exc:
        return _live_failure_evidence(
            provider,
            expected_contract,
            status="live-response-failure",
            structured_response=response,
            response_failure_type=type(exc).__name__,
            response_failure_message=str(exc),
        )

    dispatched_contract = provider.last_execution_contract
    if dispatched_contract is None:
        raise ProviderReadinessError("live provider did not retain its dispatched contract")
    if dispatched_contract.canonical_json() != expected_contract.canonical_json():
        raise ProviderReadinessError(
            "provider mutated the readiness request after execution identity was established"
        )

    return ProviderReadinessEvidence(
        mode="live",
        status="live-success",
        provider_instantiated=True,
        model=model,
        execution_fingerprint=expected_contract.fingerprint(),
        execution_contract=expected_contract,
        provider_attempts=provider.provider_attempts,
        responses_received=provider.responses_received,
        model_generations=provider.model_generations,
        input_tokens=provider.input_tokens,
        output_tokens=provider.output_tokens,
        total_tokens=provider.total_tokens,
        normalized_response=normalized.model_dump(mode="json"),
        structured_response=response.model_dump(mode="json"),
        provider_response=provider.last_response_payload,
    )


def verify_readiness_evidence(evidence: ProviderReadinessEvidence) -> ProofReviewModelResponse:
    """Keylessly replay the validation boundary for successful readiness evidence."""

    if evidence.mode != "live" or evidence.status != "live-success":
        raise ProviderReadinessError("only successful live readiness evidence can be replayed")
    if evidence.scientific_authorization:
        raise ProviderReadinessError("readiness evidence must never carry scientific authorization")

    current_contract = readiness_execution_contract(evidence.model)
    if current_contract.fingerprint() != evidence.execution_fingerprint:
        raise ProviderReadinessError(
            "readiness evidence does not match the current final wire/validator/runtime contract"
        )
    if current_contract.canonical_json() != evidence.execution_contract.canonical_json():
        raise ProviderReadinessError("readiness execution contract is stale")
    if evidence.normalized_response is None:
        raise ProviderReadinessError("successful readiness evidence is missing normalized response")

    turn = build_readiness_turn()
    response = turn.response_model().model_validate(evidence.normalized_response)
    return validate_proof_review_response(turn, response)
