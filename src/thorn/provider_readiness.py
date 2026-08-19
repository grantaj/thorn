from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict

from thorn.llm_proof_language import (
    DEFAULT_MAX_SOURCE_REQUESTS,
    LLMProofLanguage,
    ProofLanguageSourceHandle,
)
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTurnRequest,
    build_proof_review_turn,
    build_rescue_turn,
    validate_proof_review_response,
)
from thorn.providers.base import (
    ProviderResponseValidationError,
    ProviderTransportError,
    ProviderTransportEvidence,
)
from thorn.providers.execution_contract import (
    ProviderExecutionContract,
    ProviderTransportProfile,
    build_provider_execution_contract,
    provider_adapter_sha256,
    provider_lock_sha256,
)
from thorn.providers.openai import OpenAIProvider
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    proof_review_request_envelope,
)

READINESS_CANARY_FORMAT: Literal["thorn-provider-readiness/2"] = (
    "thorn-provider-readiness/2"
)
READINESS_CANARY_MAX_OUTPUT_TOKENS = PROOF_REVIEW_MAX_OUTPUT_TOKENS
READINESS_CANARY_SOURCE_ENUM_SIZE = 64
READINESS_CANARY_CARRIED_ITEMS = DEFAULT_MAX_SOURCE_REQUESTS


class ProviderReadinessError(RuntimeError):
    """A readiness artifact cannot be trusted for the current provider boundary."""


class ProviderReadinessEvidence(BaseModel):
    """Non-scientific evidence from Thorn's max-shape provider readiness canary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: Literal["thorn-provider-readiness/2"] = READINESS_CANARY_FORMAT
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
    generated_at: datetime
    run_id: str
    boundary_source_tree_sha: str
    adapter_sha256: str
    provider_lock_sha256: str
    request_retries: int = 0
    max_output_tokens: int = READINESS_CANARY_MAX_OUTPUT_TOKENS
    execution_fingerprint: str
    execution_contract: ProviderExecutionContract
    rescue_execution_fingerprint: str
    rescue_execution_contract: ProviderExecutionContract
    transport_profiles: tuple[ProviderTransportProfile, ...]
    provider_attempts: int = 0
    responses_received: int = 0
    model_generations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    normalized_response: dict[str, object] | None = None
    rescue_normalized_response: dict[str, object] | None = None
    structured_response: dict[str, object] | None = None
    rescue_structured_response: dict[str, object] | None = None
    provider_response: dict[str, object] | None = None
    rescue_provider_response: dict[str, object] | None = None
    failed_profile: Literal["initial", "rescue"] | None = None
    transport_failure: ProviderTransportEvidence | None = None
    response_failure_type: str | None = None
    response_failure_message: str | None = None

    def covers_contract(self, contract: ProviderExecutionContract) -> bool:
        profile = contract.transport_profile()
        return any(readiness.covers(profile) for readiness in self.transport_profiles)


class _ReadinessIdentityFields(TypedDict):
    generated_at: datetime
    run_id: str
    boundary_source_tree_sha: str
    adapter_sha256: str
    provider_lock_sha256: str


def _identity_fields(
    *,
    boundary_source_tree_sha: str,
    run_id: str,
) -> _ReadinessIdentityFields:
    return {
        "generated_at": datetime.now(UTC),
        "run_id": run_id,
        "boundary_source_tree_sha": boundary_source_tree_sha,
        "adapter_sha256": provider_adapter_sha256(),
        "provider_lock_sha256": provider_lock_sha256(),
    }


def _readiness_document(initial: ProofReviewTurnRequest | None = None) -> LLMProofLanguage:
    addresses = tuple(
        f"S{index:02d}" for index in range(1, READINESS_CANARY_SOURCE_ENUM_SIZE + 1)
    )
    lines = [
        "THORN-PROOF 1",
        "T0 SyntheticGoal <- P1 @S01",
    ]
    lines.extend(
        f"P{index} SyntheticStep{index} @S{index:02d}"
        for index in range(1, READINESS_CANARY_SOURCE_ENUM_SIZE + 1)
    )
    lines.append("GOAL G0 T0: SyntheticGoal | ctx P1 | open @S01")
    document = LLMProofLanguage(
        result_identifier="thm:provider-readiness-synthetic",
        lines=tuple(lines),
        sources=tuple(
            ProofLanguageSourceHandle(
                address=address,
                ir_identifier=f"synthetic:{address}",
                text=f"Synthetic source {address}.",
            )
            for address in addresses
        ),
    )
    if initial is not None and document.fingerprint() != initial.initial_packet_fingerprint:
        raise ProviderReadinessError(
            "synthetic readiness document construction is not deterministic"
        )
    return document


def build_readiness_turn() -> ProofReviewTurnRequest:
    """Build a max-cardinality initial schema probe with synthetic content only."""

    return build_proof_review_turn(
        ProofLanguageReviewRequest(document=_readiness_document())
    )


def _synthetic_source_request() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=("S01",),
        review_items=tuple(
            ProofReviewItem(
                id=f"RV{index}",
                kind="question",
                summary=f"Synthetic carried review item {index}.",
            )
            for index in range(1, READINESS_CANARY_CARRIED_ITEMS + 1)
        ),
        source_review_item_ids=tuple(
            f"RV{index}" for index in range(1, READINESS_CANARY_CARRIED_ITEMS + 1)
        ),
    )


def build_readiness_rescue_turn() -> ProofReviewTurnRequest:
    initial = build_readiness_turn()
    request = ProofLanguageReviewRequest(document=_readiness_document(initial))
    return build_rescue_turn(request, initial, _synthetic_source_request())


def readiness_execution_contracts(
    model: str,
) -> tuple[ProviderExecutionContract, ProviderExecutionContract]:
    initial = build_readiness_turn()
    rescue = build_readiness_rescue_turn()
    return (
        build_provider_execution_contract(
            proof_review_request_envelope(
                initial,
                model,
                max_output_tokens=READINESS_CANARY_MAX_OUTPUT_TOKENS,
            )
        ),
        build_provider_execution_contract(
            proof_review_request_envelope(
                rescue,
                model,
                max_output_tokens=READINESS_CANARY_MAX_OUTPUT_TOKENS,
            )
        ),
    )


def readiness_execution_contract(model: str) -> ProviderExecutionContract:
    """Compatibility accessor for the initial readiness contract."""

    return readiness_execution_contracts(model)[0]


def preflight_readiness(
    model: str,
    *,
    boundary_source_tree_sha: str = "unversioned",
    run_id: str = "preflight",
) -> ProviderReadinessEvidence:
    """Construct both provider transport profiles without instantiating a client."""

    initial, rescue = readiness_execution_contracts(model)
    return ProviderReadinessEvidence(
        mode="preflight",
        status="preflight-ready",
        provider_instantiated=False,
        model=model,
        execution_fingerprint=initial.fingerprint(),
        execution_contract=initial,
        rescue_execution_fingerprint=rescue.fingerprint(),
        rescue_execution_contract=rescue,
        transport_profiles=(initial.transport_profile(), rescue.transport_profile()),
        **_identity_fields(
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        ),
    )


def _live_failure_evidence(
    provider: OpenAIProvider,
    initial_contract: ProviderExecutionContract,
    rescue_contract: ProviderExecutionContract,
    *,
    failed_profile: Literal["initial", "rescue"],
    status: Literal["live-transport-failure", "live-response-failure"],
    initial_response: ProofReviewModelResponse | None = None,
    initial_normalized: ProofReviewModelResponse | None = None,
    transport_failure: ProviderTransportEvidence | None = None,
    structured_response: ProofReviewModelResponse | None = None,
    response_failure_type: str | None = None,
    response_failure_message: str | None = None,
    boundary_source_tree_sha: str,
    run_id: str,
) -> ProviderReadinessEvidence:
    return ProviderReadinessEvidence(
        mode="live",
        status=status,
        provider_instantiated=True,
        model=provider.model,
        execution_fingerprint=initial_contract.fingerprint(),
        execution_contract=initial_contract,
        rescue_execution_fingerprint=rescue_contract.fingerprint(),
        rescue_execution_contract=rescue_contract,
        transport_profiles=(
            initial_contract.transport_profile(),
            rescue_contract.transport_profile(),
        ),
        provider_attempts=provider.provider_attempts,
        responses_received=provider.responses_received,
        model_generations=provider.model_generations,
        input_tokens=provider.input_tokens,
        output_tokens=provider.output_tokens,
        total_tokens=provider.total_tokens,
        normalized_response=(
            initial_normalized.model_dump(mode="json")
            if initial_normalized is not None
            else None
        ),
        structured_response=(
            initial_response.model_dump(mode="json")
            if initial_response is not None
            else None
        ),
        rescue_structured_response=(
            structured_response.model_dump(mode="json")
            if structured_response is not None and failed_profile == "rescue"
            else None
        ),
        provider_response=(
            provider.last_response_payload if failed_profile == "initial" else None
        ),
        rescue_provider_response=(
            provider.last_response_payload if failed_profile == "rescue" else None
        ),
        failed_profile=failed_profile,
        transport_failure=transport_failure,
        response_failure_type=response_failure_type,
        response_failure_message=response_failure_message,
        **_identity_fields(
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        ),
    )


def run_live_readiness(
    model: str,
    *,
    boundary_source_tree_sha: str = "unversioned",
    run_id: str = "local",
) -> ProviderReadinessEvidence:
    """Run two bounded synthetic calls at the production proof-review output cap."""

    initial_turn = build_readiness_turn()
    rescue_turn = build_readiness_rescue_turn()
    initial_contract, rescue_contract = readiness_execution_contracts(model)
    provider = OpenAIProvider(
        model=model,
        proof_review_max_output_tokens=READINESS_CANARY_MAX_OUTPUT_TOKENS,
    )

    try:
        initial_response = provider.review_proof_turn(
            initial_turn,
            execution_contract=initial_contract,
        )
    except ProviderTransportError as exc:
        return _live_failure_evidence(
            provider,
            initial_contract,
            rescue_contract,
            failed_profile="initial",
            status="live-transport-failure",
            transport_failure=exc.evidence,
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        )
    except ProviderResponseValidationError as exc:
        return _live_failure_evidence(
            provider,
            initial_contract,
            rescue_contract,
            failed_profile="initial",
            status="live-response-failure",
            response_failure_type=exc.validation_exception_type,
            response_failure_message=str(exc),
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        )

    try:
        initial_normalized = validate_proof_review_response(initial_turn, initial_response)
    except ProofReviewProtocolError as exc:
        return _live_failure_evidence(
            provider,
            initial_contract,
            rescue_contract,
            failed_profile="initial",
            status="live-response-failure",
            initial_response=initial_response,
            response_failure_type=type(exc).__name__,
            response_failure_message=str(exc),
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        )

    initial_provider_payload = provider.last_response_payload
    try:
        rescue_response = provider.review_proof_turn(
            rescue_turn,
            execution_contract=rescue_contract,
        )
    except ProviderTransportError as exc:
        return _live_failure_evidence(
            provider,
            initial_contract,
            rescue_contract,
            failed_profile="rescue",
            status="live-transport-failure",
            initial_response=initial_response,
            initial_normalized=initial_normalized,
            transport_failure=exc.evidence,
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        )
    except ProviderResponseValidationError as exc:
        return _live_failure_evidence(
            provider,
            initial_contract,
            rescue_contract,
            failed_profile="rescue",
            status="live-response-failure",
            initial_response=initial_response,
            initial_normalized=initial_normalized,
            response_failure_type=exc.validation_exception_type,
            response_failure_message=str(exc),
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        )

    try:
        rescue_normalized = validate_proof_review_response(rescue_turn, rescue_response)
    except ProofReviewProtocolError as exc:
        return _live_failure_evidence(
            provider,
            initial_contract,
            rescue_contract,
            failed_profile="rescue",
            status="live-response-failure",
            initial_response=initial_response,
            initial_normalized=initial_normalized,
            structured_response=rescue_response,
            response_failure_type=type(exc).__name__,
            response_failure_message=str(exc),
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        )

    if provider.provider_attempts != 2:
        raise ProviderReadinessError(
            "readiness canary must execute exactly two provider attempts"
        )

    return ProviderReadinessEvidence(
        mode="live",
        status="live-success",
        provider_instantiated=True,
        model=model,
        execution_fingerprint=initial_contract.fingerprint(),
        execution_contract=initial_contract,
        rescue_execution_fingerprint=rescue_contract.fingerprint(),
        rescue_execution_contract=rescue_contract,
        transport_profiles=(
            initial_contract.transport_profile(),
            rescue_contract.transport_profile(),
        ),
        provider_attempts=provider.provider_attempts,
        responses_received=provider.responses_received,
        model_generations=provider.model_generations,
        input_tokens=provider.input_tokens,
        output_tokens=provider.output_tokens,
        total_tokens=provider.total_tokens,
        normalized_response=initial_normalized.model_dump(mode="json"),
        rescue_normalized_response=rescue_normalized.model_dump(mode="json"),
        structured_response=initial_response.model_dump(mode="json"),
        rescue_structured_response=rescue_response.model_dump(mode="json"),
        provider_response=initial_provider_payload,
        rescue_provider_response=provider.last_response_payload,
        **_identity_fields(
            boundary_source_tree_sha=boundary_source_tree_sha,
            run_id=run_id,
        ),
    )


def verify_readiness_evidence(
    evidence: ProviderReadinessEvidence,
) -> tuple[ProofReviewModelResponse, ProofReviewModelResponse]:
    """Keylessly replay both validation boundaries for successful readiness evidence."""

    if evidence.mode != "live" or evidence.status != "live-success":
        raise ProviderReadinessError(
            "only successful live readiness evidence can be replayed"
        )
    if evidence.scientific_authorization:
        raise ProviderReadinessError(
            "readiness evidence must never carry scientific authorization"
        )
    if evidence.adapter_sha256 != provider_adapter_sha256():
        raise ProviderReadinessError(
            "readiness evidence was produced by a different provider adapter"
        )
    if evidence.provider_lock_sha256 != provider_lock_sha256():
        raise ProviderReadinessError(
            "readiness evidence was produced under a different provider lock"
        )

    current_initial, current_rescue = readiness_execution_contracts(evidence.model)
    expected_pairs = (
        (current_initial, evidence.execution_contract, evidence.execution_fingerprint),
        (
            current_rescue,
            evidence.rescue_execution_contract,
            evidence.rescue_execution_fingerprint,
        ),
    )
    for current, recorded, fingerprint in expected_pairs:
        if current.fingerprint() != fingerprint:
            raise ProviderReadinessError(
                "readiness evidence does not match the current wire/validator/runtime contract"
            )
        if current.canonical_json() != recorded.canonical_json():
            raise ProviderReadinessError("readiness execution contract is stale")

    current_profiles = (
        current_initial.transport_profile(),
        current_rescue.transport_profile(),
    )
    if evidence.transport_profiles != current_profiles:
        raise ProviderReadinessError("readiness transport profiles are stale")
    if (
        evidence.normalized_response is None
        or evidence.rescue_normalized_response is None
    ):
        raise ProviderReadinessError(
            "successful readiness evidence is missing normalized responses"
        )

    initial_turn = build_readiness_turn()
    initial_response = initial_turn.response_model().model_validate(
        evidence.normalized_response
    )
    initial_response = validate_proof_review_response(initial_turn, initial_response)

    rescue_turn = build_readiness_rescue_turn()
    rescue_response = rescue_turn.response_model().model_validate(
        evidence.rescue_normalized_response
    )
    rescue_response = validate_proof_review_response(rescue_turn, rescue_response)
    return initial_response, rescue_response
