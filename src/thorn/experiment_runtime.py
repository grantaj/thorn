from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from thorn.proof_language_review import (
    ProofReviewModelResponse,
    ProofReviewTransport,
    ProofReviewTurnRequest,
)
from thorn.provider_readiness import ProviderReadinessEvidence, verify_readiness_evidence
from thorn.providers.execution_contract import (
    ProviderExecutionContract,
    ProviderRuntimeIdentity,
    ProviderTransportProfile,
    build_provider_execution_contract,
    current_provider_runtime,
    provider_adapter_sha256,
    provider_lock_sha256,
    provider_runtime_matches_lock,
)
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    proof_review_request_envelope,
)

EXPERIMENT_MANIFEST_FORMAT: Literal["thorn-provider-experiment/2"] = (
    "thorn-provider-experiment/2"
)
SERIALIZATION_FRAMING_RESERVE_BYTES = 2_048


class ExperimentFreezeError(RuntimeError):
    """A provider experiment no longer matches its declared freeze surface."""


class ProviderUsageSnapshot(BaseModel):
    """Unambiguous provider/replay counters at one experiment boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requests: int = 0
    live_requests: int = 0
    replay_hits: int = 0
    provider_attempts: int = 0
    responses_received: int = 0
    model_generations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def capture(cls, provider: object) -> ProviderUsageSnapshot:
        requests = int(getattr(provider, "requests", 0))
        attempts = int(getattr(provider, "provider_attempts", 0))
        responses = int(getattr(provider, "responses_received", 0))
        generations = int(getattr(provider, "model_generations", 0))
        return cls(
            requests=requests,
            live_requests=int(getattr(provider, "live_requests", 0)),
            replay_hits=int(getattr(provider, "replay_hits", 0)),
            provider_attempts=attempts,
            responses_received=responses,
            model_generations=generations,
            input_tokens=int(getattr(provider, "input_tokens", 0)),
            output_tokens=int(getattr(provider, "output_tokens", 0)),
            total_tokens=int(getattr(provider, "total_tokens", 0)),
        )

    def minus(self, earlier: ProviderUsageSnapshot) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot(
            requests=self.requests - earlier.requests,
            live_requests=self.live_requests - earlier.live_requests,
            replay_hits=self.replay_hits - earlier.replay_hits,
            provider_attempts=self.provider_attempts - earlier.provider_attempts,
            responses_received=self.responses_received - earlier.responses_received,
            model_generations=self.model_generations - earlier.model_generations,
            input_tokens=self.input_tokens - earlier.input_tokens,
            output_tokens=self.output_tokens - earlier.output_tokens,
            total_tokens=self.total_tokens - earlier.total_tokens,
        )


class ProviderBudgetSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_cases: int = Field(ge=1)
    max_provider_attempts: int = Field(ge=1)
    max_input_tokens: int = Field(ge=1)
    max_output_tokens_per_request: int = Field(ge=1)
    max_output_tokens: int = Field(ge=1)


class ProviderExperimentCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    path: str
    target: str
    source_sha256: str
    initial_execution_fingerprint: str


class ProviderReadinessFreeze(BaseModel):
    """Successful live readiness evidence frozen into a scientific manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_sha256: str
    run_id: str
    generated_at: datetime
    boundary_source_tree_sha: str
    adapter_sha256: str
    provider_lock_sha256: str
    transport_profile_fingerprints: tuple[str, ...]
    max_age_hours: int = Field(default=24, ge=1, le=168)


class ProviderExperimentManifest(BaseModel):
    """Data-only freeze surface for new provider-backed experiments."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: Literal["thorn-provider-experiment/2"] = EXPERIMENT_MANIFEST_FORMAT
    experiment_id: str
    repository_revision: str
    src_tree_sha: str
    runner_sha256: str
    constraints_sha256: str
    model: str
    representation: str
    protocol: str
    prompt_version: str
    provider_retries: Literal[0] = 0
    paid_execution_authorized: Literal[False] = False
    runtime: ProviderRuntimeIdentity
    readiness: ProviderReadinessFreeze
    budget: ProviderBudgetSpec
    cases: tuple[ProviderExperimentCase, ...]

    @classmethod
    def load(cls, path: Path) -> ProviderExperimentManifest:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


@dataclass
class ProviderBudget:
    """One reusable live/replay budget guard over final execution contracts."""

    spec: ProviderBudgetSpec
    reserved_turns: int = 0
    provider_attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def reserve(self, contract: ProviderExecutionContract) -> None:
        if self.reserved_turns + 1 > self.spec.max_provider_attempts:
            raise ExperimentFreezeError("provider-attempt ceiling would be exceeded")
        max_output_tokens = contract.wire_request.get("max_output_tokens")
        if max_output_tokens != self.spec.max_output_tokens_per_request:
            raise ExperimentFreezeError("per-request output-token cap drifted")
        wire_bound = conservative_wire_input_token_bound(contract)
        if self.input_tokens + wire_bound > self.spec.max_input_tokens:
            raise ExperimentFreezeError("input-token ceiling would be exceeded")
        projected_output = self.output_tokens + self.spec.max_output_tokens_per_request
        if projected_output > self.spec.max_output_tokens:
            raise ExperimentFreezeError("aggregate output-token ceiling would be exceeded")
        self.reserved_turns += 1

    def commit(
        self,
        before: ProviderUsageSnapshot,
        after: ProviderUsageSnapshot,
    ) -> None:
        delta = after.minus(before)
        if delta.provider_attempts < 0 or delta.provider_attempts > 1:
            raise ExperimentFreezeError(
                "one logical turn changed provider-attempt count by more than one"
            )
        if delta.responses_received < 0 or delta.responses_received > 1:
            raise ExperimentFreezeError(
                "one logical turn changed response count by more than one"
            )
        if delta.model_generations < 0 or delta.model_generations > 1:
            raise ExperimentFreezeError(
                "one logical turn changed model-generation count by more than one"
            )
        self.provider_attempts += delta.provider_attempts
        self.input_tokens += delta.input_tokens
        self.output_tokens += delta.output_tokens
        if self.provider_attempts > self.spec.max_provider_attempts:
            raise ExperimentFreezeError("provider-attempt ceiling was exceeded")
        if self.input_tokens > self.spec.max_input_tokens:
            raise ExperimentFreezeError("provider-reported input usage exceeded ceiling")
        if self.output_tokens > self.spec.max_output_tokens:
            raise ExperimentFreezeError("provider-reported output usage exceeded ceiling")


def conservative_wire_input_token_bound(contract: ProviderExecutionContract) -> int:
    """Conservative no-tokenizer bound over the actual provider wire payload."""

    encoded = json.dumps(
        contract.wire_request,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return len(encoded) + SERIALIZATION_FRAMING_RESERVE_BYTES


def _proof_output_cap(provider: object) -> int:
    direct = getattr(provider, "proof_review_max_output_tokens", None)
    if isinstance(direct, int):
        return direct
    delegate = getattr(provider, "_delegate", None)
    nested = getattr(delegate, "proof_review_max_output_tokens", None)
    if isinstance(nested, int):
        return nested
    return PROOF_REVIEW_MAX_OUTPUT_TOKENS


def _execution_contract(
    provider: object,
    request: ProofReviewTurnRequest,
    model: str,
) -> ProviderExecutionContract:
    envelope = proof_review_request_envelope(
        request,
        model,
        max_output_tokens=_proof_output_cap(provider),
    )
    builder = getattr(provider, "execution_contract", None)
    if callable(builder):
        candidate = builder(envelope)
        if isinstance(candidate, ProviderExecutionContract):
            return candidate
    return build_provider_execution_contract(envelope)


def assert_contract_profile_covered(
    contract: ProviderExecutionContract,
    readiness_profiles: tuple[ProviderTransportProfile, ...],
) -> None:
    scientific_profile = contract.transport_profile()
    if not any(profile.covers(scientific_profile) for profile in readiness_profiles):
        raise ExperimentFreezeError(
            "provider transport profile was not exercised by frozen readiness evidence: "
            f"{scientific_profile.fingerprint()}"
        )


@dataclass
class GuardedProofReviewTransport:
    """Budget/freeze wrapper shared by manifest-driven live and replay runs."""

    delegate: ProofReviewTransport
    budget: ProviderBudget
    expected_initial_fingerprint: str
    readiness_profiles: tuple[ProviderTransportProfile, ...] = ()
    model: str = field(init=False)
    contracts: list[ProviderExecutionContract] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.model = self.delegate.model

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        contract = _execution_contract(self.delegate, request, self.model)
        if (
            request.stage == "initial"
            and contract.fingerprint() != self.expected_initial_fingerprint
        ):
            raise ExperimentFreezeError("frozen initial provider execution fingerprint drifted")
        if self.readiness_profiles:
            assert_contract_profile_covered(contract, self.readiness_profiles)
        self.budget.reserve(contract)
        before = ProviderUsageSnapshot.capture(self.delegate)
        try:
            response = self.delegate.review_proof_turn(request)
        finally:
            self.budget.commit(before, ProviderUsageSnapshot.capture(self.delegate))
        self.contracts.append(contract)
        return response


def assert_manifest_runtime(manifest: ProviderExperimentManifest) -> None:
    current = current_provider_runtime()
    if not provider_runtime_matches_lock(current):
        raise ExperimentFreezeError(
            "installed provider dependency closure does not match committed runtime lock"
        )
    if current != manifest.runtime:
        raise ExperimentFreezeError(
            "provider runtime differs from experiment manifest: "
            f"current={current.model_dump(mode='json')!r} "
            f"frozen={manifest.runtime.model_dump(mode='json')!r}"
        )


def assert_readiness_compatible(
    evidence: ProviderReadinessEvidence,
    *,
    evidence_sha256: str,
    manifest: ProviderExperimentManifest,
    scientific_contracts: tuple[ProviderExecutionContract, ...],
) -> None:
    """Require fresh, frozen readiness coverage for every scientific profile."""

    verify_readiness_evidence(evidence)
    frozen = manifest.readiness
    if evidence_sha256 != frozen.evidence_sha256:
        raise ExperimentFreezeError("readiness evidence bytes differ from the frozen manifest")
    if evidence.model != manifest.model:
        raise ExperimentFreezeError("readiness model does not match scientific manifest")
    if evidence.run_id != frozen.run_id:
        raise ExperimentFreezeError("readiness run identity differs from the frozen manifest")
    if evidence.generated_at != frozen.generated_at:
        raise ExperimentFreezeError("readiness generation time differs from the frozen manifest")
    if evidence.boundary_source_tree_sha != frozen.boundary_source_tree_sha:
        raise ExperimentFreezeError("readiness provider source-tree identity drifted")
    if frozen.boundary_source_tree_sha != manifest.src_tree_sha:
        raise ExperimentFreezeError("readiness did not exercise the frozen provider source tree")
    if evidence.adapter_sha256 != frozen.adapter_sha256:
        raise ExperimentFreezeError("readiness adapter identity differs from the manifest")
    if evidence.adapter_sha256 != provider_adapter_sha256():
        raise ExperimentFreezeError("current provider adapter differs from readiness evidence")
    if evidence.provider_lock_sha256 != frozen.provider_lock_sha256:
        raise ExperimentFreezeError("readiness provider lock differs from the manifest")
    if evidence.provider_lock_sha256 != provider_lock_sha256():
        raise ExperimentFreezeError("current provider lock differs from readiness evidence")

    evidence_profiles = tuple(profile.fingerprint() for profile in evidence.transport_profiles)
    if evidence_profiles != frozen.transport_profile_fingerprints:
        raise ExperimentFreezeError("readiness transport profiles differ from the manifest")

    generated = evidence.generated_at
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    age_hours = (datetime.now(UTC) - generated).total_seconds() / 3600
    if age_hours < 0 or age_hours > frozen.max_age_hours:
        raise ExperimentFreezeError("readiness evidence is outside the frozen freshness window")

    for contract in scientific_contracts:
        if contract.runtime != manifest.runtime:
            raise ExperimentFreezeError("scientific contract runtime differs from manifest")
        if contract.provider != evidence.execution_contract.provider:
            raise ExperimentFreezeError("readiness and scientific provider identities differ")
        if contract.endpoint != evidence.execution_contract.endpoint:
            raise ExperimentFreezeError("readiness and scientific provider endpoints differ")
        if contract.acceptance_contract != evidence.execution_contract.acceptance_contract:
            raise ExperimentFreezeError("readiness and scientific validator contracts differ")
        assert_contract_profile_covered(contract, evidence.transport_profiles)
