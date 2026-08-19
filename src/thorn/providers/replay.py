from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal, TypeVar, cast

from pydantic import BaseModel, ValidationError

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import (
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTurnRequest,
    validate_proof_review_response,
)
from thorn.providers.base import (
    EvaluationProvider,
    ProviderResponseValidationError,
    ProviderTransportError,
    ProviderTransportEvidence,
)
from thorn.providers.execution_contract import (
    ProviderExecutionContract,
    build_provider_execution_contract,
)
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    ProviderRequestEnvelope,
    attack_request_envelope,
    defense_request_envelope,
    proof_review_request_envelope,
    semantic_request_envelope,
)
from thorn.semantic_review_render import SemanticReviewRequest

TResponse = TypeVar("TResponse", bound=BaseModel)


class ReplayError(RuntimeError):
    """Base class for recorded-evaluation failures."""


class ReplayMissError(ReplayError):
    """Raised when no exact recording exists for the current execution identity."""


class ReplayStaleError(ReplayError):
    """Raised when a recording file does not match its declared identity."""


class ReplayAmbiguousError(ReplayError):
    """Raised when forensic replay has multiple rejected responses and no selection."""


class RecordingConflictError(ReplayError):
    """Raised when the same execution identity has conflicting accepted evidence."""


class RecordedUsage(BaseModel):
    """Per-exchange accounting, including failed provider attempts."""

    requests: int = 0
    provider_attempts: int = 0
    responses_received: int = 0
    model_generations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def snapshot(cls, provider: EvaluationProvider) -> RecordedUsage:
        requests = int(getattr(provider, "requests", 0))
        attempts = int(getattr(provider, "provider_attempts", requests))
        responses = int(getattr(provider, "responses_received", requests))
        generations = int(getattr(provider, "model_generations", responses))
        return cls(
            requests=requests,
            provider_attempts=attempts,
            responses_received=responses,
            model_generations=generations,
            input_tokens=int(getattr(provider, "input_tokens", 0)),
            output_tokens=int(getattr(provider, "output_tokens", 0)),
            total_tokens=int(getattr(provider, "total_tokens", 0)),
        )

    def minus(self, earlier: RecordedUsage) -> RecordedUsage:
        return RecordedUsage(
            requests=self.requests - earlier.requests,
            provider_attempts=self.provider_attempts - earlier.provider_attempts,
            responses_received=self.responses_received - earlier.responses_received,
            model_generations=self.model_generations - earlier.model_generations,
            input_tokens=self.input_tokens - earlier.input_tokens,
            output_tokens=self.output_tokens - earlier.output_tokens,
            total_tokens=self.total_tokens - earlier.total_tokens,
        )


class RecordedExchange(BaseModel):
    """Accepted provider evidence."""

    format_version: int = 2
    fingerprint: str
    request: ProviderRequestEnvelope
    execution_contract: ProviderExecutionContract | None = None
    response: dict[str, object]
    usage: RecordedUsage


RejectedRecordingKind = Literal[
    "proof_review_protocol",
    "transport_failure",
    "response_validation",
    "provider_failure",
]


class RecordedRejection(BaseModel):
    kind: RejectedRecordingKind
    message: str
    exception_type: str
    validator_replayable: bool
    transport: ProviderTransportEvidence | None = None


class RecordedRejectedExchange(BaseModel):
    """Quarantined evidence that ordinary replay can never consume."""

    format_version: int = 2
    fingerprint: str
    request: ProviderRequestEnvelope
    execution_contract: ProviderExecutionContract | None = None
    response: dict[str, object] | None = None
    usage: RecordedUsage
    rejection: RecordedRejection
    response_fingerprint: str


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _exchange_fingerprint(exchange: RecordedExchange) -> str:
    payload = exchange.model_dump(mode="json")
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _rejected_response_fingerprint(
    response: dict[str, object] | None,
    rejection: RecordedRejection,
) -> str:
    payload = {
        "response": response,
        "rejection": rejection.model_dump(mode="json"),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _generic_provider_rejection(exc: Exception) -> RecordedRejection:
    """Classify an unstructured delegate failure without serializing its message."""

    return RecordedRejection(
        kind="provider_failure",
        message="provider did not return a structured response",
        exception_type=type(exc).__name__,
        validator_replayable=False,
    )


def _proof_output_cap(provider: object) -> int:
    direct = getattr(provider, "proof_review_max_output_tokens", None)
    if isinstance(direct, int):
        return direct
    delegate = getattr(provider, "_delegate", None)
    nested = getattr(delegate, "proof_review_max_output_tokens", None)
    if isinstance(nested, int):
        return nested
    return PROOF_REVIEW_MAX_OUTPUT_TOKENS


class RecordingProvider:
    """Record immutable evidence from the exact contract passed to dispatch.

    Production delegates that advertise ``accepts_execution_contract`` receive the
    exact object built by this wrapper. The recorder then checks that the delegate
    retained that same contract as its dispatched identity. Every accepted exchange
    is exact-replayed immediately after commit, so later failures cannot leave prior
    accepted scientific evidence unverified.
    """

    def __init__(
        self,
        delegate: EvaluationProvider,
        directory: Path,
        *,
        verify_after_write: bool = True,
    ) -> None:
        self._delegate = delegate
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.model = delegate.model
        self.verify_after_write = verify_after_write
        self.exact_replay_verifications = 0
        self.proof_review_max_output_tokens = _proof_output_cap(delegate)

    @property
    def requests(self) -> int:
        return int(getattr(self._delegate, "requests", 0))

    @property
    def live_requests(self) -> int:
        return int(getattr(self._delegate, "live_requests", self.requests))

    @property
    def replay_hits(self) -> int:
        return int(getattr(self._delegate, "replay_hits", 0))

    @property
    def provider_attempts(self) -> int:
        return int(getattr(self._delegate, "provider_attempts", self.requests))

    @property
    def responses_received(self) -> int:
        return int(getattr(self._delegate, "responses_received", self.requests))

    @property
    def model_generations(self) -> int:
        return int(getattr(self._delegate, "model_generations", self.responses_received))

    @property
    def input_tokens(self) -> int:
        return int(getattr(self._delegate, "input_tokens", 0))

    @property
    def output_tokens(self) -> int:
        return int(getattr(self._delegate, "output_tokens", 0))

    @property
    def total_tokens(self) -> int:
        return int(getattr(self._delegate, "total_tokens", 0))

    def execution_contract(
        self,
        envelope: ProviderRequestEnvelope,
    ) -> ProviderExecutionContract:
        builder = getattr(self._delegate, "execution_contract", None)
        if callable(builder):
            contract = builder(envelope)
            if isinstance(contract, ProviderExecutionContract):
                return contract
        return build_provider_execution_contract(envelope)

    def _call_with_contract(
        self,
        method_name: str,
        contract: ProviderExecutionContract,
        *args: object,
    ) -> TResponse:
        method = getattr(self._delegate, method_name)
        if bool(getattr(self._delegate, "accepts_execution_contract", False)):
            return cast(TResponse, method(*args, execution_contract=contract))
        return cast(TResponse, method(*args))

    def _assert_dispatched_contract(self, contract: ProviderExecutionContract) -> None:
        dispatched = getattr(self._delegate, "last_execution_contract", None)
        if dispatched is None:
            return
        if not isinstance(dispatched, ProviderExecutionContract):
            raise RecordingConflictError(
                "delegate retained an invalid execution contract"
            )
        if (
            dispatched is not contract
            and dispatched.canonical_json() != contract.canonical_json()
        ):
            raise RecordingConflictError(
                "delegate dispatched a different execution contract from the recorder"
            )

    def _write(
        self,
        envelope: ProviderRequestEnvelope,
        contract: ProviderExecutionContract,
        response: BaseModel,
        usage: RecordedUsage,
    ) -> None:
        fingerprint = contract.fingerprint()
        exchange = RecordedExchange(
            fingerprint=fingerprint,
            request=envelope,
            execution_contract=contract,
            response=response.model_dump(mode="json"),
            usage=usage,
        )
        destination = self.directory / f"{fingerprint}.json"
        if destination.exists():
            try:
                existing = RecordedExchange.model_validate_json(
                    destination.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as exc:
                raise RecordingConflictError(
                    f"existing recording {destination} is unreadable; refusing to overwrite it"
                ) from exc
            if existing == exchange:
                return

            conflicts = self.directory / "conflicts" / fingerprint
            conflicts.mkdir(parents=True, exist_ok=True)
            conflict_path = conflicts / f"{_exchange_fingerprint(exchange)}.json"
            if not conflict_path.exists():
                temporary = conflict_path.with_suffix(".json.tmp")
                temporary.write_text(
                    exchange.model_dump_json(indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(conflict_path)
            raise RecordingConflictError(
                "accepted recording already exists for execution fingerprint "
                f"{fingerprint}; conflicting evidence was preserved separately"
            )

        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            exchange.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    def _write_rejected(
        self,
        envelope: ProviderRequestEnvelope,
        contract: ProviderExecutionContract,
        response: BaseModel | dict[str, object] | None,
        usage: RecordedUsage,
        rejection: RecordedRejection,
    ) -> None:
        fingerprint = contract.fingerprint()
        response_payload = (
            response.model_dump(mode="json") if isinstance(response, BaseModel) else response
        )
        response_fingerprint = _rejected_response_fingerprint(
            response_payload,
            rejection,
        )
        exchange = RecordedRejectedExchange(
            fingerprint=fingerprint,
            request=envelope,
            execution_contract=contract,
            response=response_payload,
            usage=usage,
            rejection=rejection,
            response_fingerprint=response_fingerprint,
        )
        directory = self.directory / "rejected" / fingerprint
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{response_fingerprint}.json"
        if destination.exists():
            return
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(
            exchange.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    def _invoke(
        self,
        envelope: ProviderRequestEnvelope,
        callback: Callable[[ProviderExecutionContract], TResponse],
    ) -> tuple[TResponse, RecordedUsage, ProviderExecutionContract]:
        contract = self.execution_contract(envelope)
        before = RecordedUsage.snapshot(self._delegate)
        try:
            response = callback(contract)
            self._assert_dispatched_contract(contract)
        except ProviderTransportError as exc:
            self._assert_dispatched_contract(contract)
            usage = RecordedUsage.snapshot(self._delegate).minus(before)
            self._write_rejected(
                envelope,
                contract,
                None,
                usage,
                RecordedRejection(
                    kind="transport_failure",
                    message=str(exc),
                    exception_type=exc.evidence.exception_type,
                    validator_replayable=False,
                    transport=exc.evidence,
                ),
            )
            raise
        except ProviderResponseValidationError as exc:
            self._assert_dispatched_contract(contract)
            usage = RecordedUsage.snapshot(self._delegate).minus(before)
            self._write_rejected(
                envelope,
                contract,
                exc.response_payload,
                usage,
                RecordedRejection(
                    kind="response_validation",
                    message=str(exc),
                    exception_type=exc.validation_exception_type,
                    validator_replayable=False,
                ),
            )
            raise
        except RecordingConflictError:
            raise
        except Exception as exc:
            usage = RecordedUsage.snapshot(self._delegate).minus(before)
            self._write_rejected(
                envelope,
                contract,
                None,
                usage,
                _generic_provider_rejection(exc),
            )
            raise

        usage = RecordedUsage.snapshot(self._delegate).minus(before)
        return response, usage, contract

    def _replay(self) -> ReplayProvider:
        return ReplayProvider(
            model=self.model,
            directory=self.directory,
            proof_review_max_output_tokens=self.proof_review_max_output_tokens,
        )

    def attack(self, unit: TheoremUnit) -> AttackReport:
        envelope = attack_request_envelope(unit, self.model)
        response, usage, contract = self._invoke(
            envelope,
            lambda exact: self._call_with_contract("attack", exact, unit),
        )
        self._write(envelope, contract, response, usage)
        if self.verify_after_write:
            if self._replay().attack(unit) != response:
                raise RecordingConflictError(
                    "immediate exact replay changed accepted attack evidence"
                )
            self.exact_replay_verifications += 1
        return response

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        envelope = semantic_request_envelope(request, self.model)
        response, usage, contract = self._invoke(
            envelope,
            lambda exact: self._call_with_contract("review_semantic", exact, request),
        )
        self._write(envelope, contract, response, usage)
        if self.verify_after_write:
            if self._replay().review_semantic(request) != response:
                raise RecordingConflictError(
                    "immediate exact replay changed accepted semantic evidence"
                )
            self.exact_replay_verifications += 1
        return response

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(
            request,
            self.model,
            max_output_tokens=self.proof_review_max_output_tokens,
        )
        response, usage, contract = self._invoke(
            envelope,
            lambda exact: self._call_with_contract(
                "review_proof_turn",
                exact,
                request,
            ),
        )
        try:
            normalized = validate_proof_review_response(request, response)
        except ProofReviewProtocolError as exc:
            self._write_rejected(
                envelope,
                contract,
                response,
                usage,
                RecordedRejection(
                    kind="proof_review_protocol",
                    message=str(exc),
                    exception_type="ProofReviewProtocolError",
                    validator_replayable=True,
                ),
            )
            raise

        self._write(envelope, contract, normalized, usage)
        if self.verify_after_write:
            if self._replay().review_proof_turn(request) != normalized:
                raise RecordingConflictError(
                    "immediate exact replay changed accepted proof-review evidence"
                )
            self.exact_replay_verifications += 1
        return normalized

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
    ) -> DefenseReport:
        envelope = defense_request_envelope(unit, findings, self.model)
        response, usage, contract = self._invoke(
            envelope,
            lambda exact: self._call_with_contract(
                "defend",
                exact,
                unit,
                findings,
            ),
        )
        self._write(envelope, contract, response, usage)
        if self.verify_after_write:
            if self._replay().defend(unit, findings) != response:
                raise RecordingConflictError(
                    "immediate exact replay changed accepted defense evidence"
                )
            self.exact_replay_verifications += 1
        return response


class ReplayProvider:
    """Replay accepted evidence without constructing a live provider client."""

    def __init__(
        self,
        model: str,
        directory: Path,
        *,
        proof_review_max_output_tokens: int = PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    ) -> None:
        self.model = model
        self.directory = directory
        self.proof_review_max_output_tokens = proof_review_max_output_tokens
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.legacy_replay_hits = 0
        self.provider_attempts = 0
        self.responses_received = 0
        self.model_generations = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.recorded_input_tokens = 0
        self.recorded_output_tokens = 0
        self.recorded_total_tokens = 0

    def execution_contract(
        self,
        envelope: ProviderRequestEnvelope,
    ) -> ProviderExecutionContract:
        return build_provider_execution_contract(envelope)

    def _load(
        self,
        envelope: ProviderRequestEnvelope,
    ) -> tuple[RecordedExchange, bool]:
        contract = self.execution_contract(envelope)
        exact_fingerprint = contract.fingerprint()
        exact_path = self.directory / f"{exact_fingerprint}.json"
        legacy_fingerprint = envelope.fingerprint()
        legacy_path = self.directory / f"{legacy_fingerprint}.json"

        if exact_path.exists():
            path = exact_path
            expected_fingerprint = exact_fingerprint
            legacy = False
        elif legacy_path.exists():
            path = legacy_path
            expected_fingerprint = legacy_fingerprint
            legacy = True
        else:
            raise ReplayMissError(
                "no recording for "
                f"{envelope.kind} execution fingerprint {exact_fingerprint}; the final wire "
                "request, validator contract, provider runtime lock, model, prompt, "
                "or recording set has changed"
            )

        try:
            exchange = RecordedExchange.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as exc:
            raise ReplayError(f"invalid recording {path}: {exc}") from exc
        if exchange.fingerprint != expected_fingerprint:
            raise ReplayStaleError(
                f"recording {path} declares fingerprint {exchange.fingerprint}, "
                f"expected {expected_fingerprint}"
            )
        if exchange.request.canonical_json() != envelope.canonical_json():
            raise ReplayStaleError(
                f"recording {path} semantic request does not match its current request"
            )
        if legacy:
            if exchange.execution_contract is not None:
                raise ReplayStaleError(
                    f"recording {path} is stored under a legacy identity but declares v2 execution"
                )
        else:
            recorded_contract = exchange.execution_contract
            if recorded_contract is None:
                raise ReplayStaleError(
                    f"recording {path} lacks its final provider execution contract"
                )
            if recorded_contract.canonical_json() != contract.canonical_json():
                raise ReplayStaleError(
                    f"recording {path} provider execution contract does not match current execution"
                )
        return exchange, legacy

    def _record_hit(self, exchange: RecordedExchange, *, legacy: bool) -> None:
        self.requests += 1
        self.replay_hits += 1
        if legacy:
            self.legacy_replay_hits += 1
        self.recorded_input_tokens += exchange.usage.input_tokens
        self.recorded_output_tokens += exchange.usage.output_tokens
        self.recorded_total_tokens += exchange.usage.total_tokens

    def attack(self, unit: TheoremUnit) -> AttackReport:
        exchange, legacy = self._load(attack_request_envelope(unit, self.model))
        response = AttackReport.model_validate(exchange.response)
        self._record_hit(exchange, legacy=legacy)
        return response

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        exchange, legacy = self._load(semantic_request_envelope(request, self.model))
        response = AttackReport.model_validate(exchange.response)
        self._record_hit(exchange, legacy=legacy)
        return response

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(
            request,
            self.model,
            max_output_tokens=self.proof_review_max_output_tokens,
        )
        exchange, legacy = self._load(envelope)
        response = request.response_model().model_validate(exchange.response)
        response = validate_proof_review_response(request, response)
        self._record_hit(exchange, legacy=legacy)
        return response

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
    ) -> DefenseReport:
        exchange, legacy = self._load(
            defense_request_envelope(unit, findings, self.model)
        )
        response = DefenseReport.model_validate(exchange.response)
        self._record_hit(exchange, legacy=legacy)
        return response


class ForensicReplayProvider(ReplayProvider):
    """Replay accepted turns normally or explicitly selected quarantined failures."""

    def __init__(
        self,
        model: str,
        directory: Path,
        *,
        rejected_response_fingerprints: dict[str, str] | None = None,
        proof_review_max_output_tokens: int = PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    ) -> None:
        super().__init__(
            model=model,
            directory=directory,
            proof_review_max_output_tokens=proof_review_max_output_tokens,
        )
        self.rejected_response_fingerprints = dict(rejected_response_fingerprints or {})
        self.forensic_hits = 0

    def _load_rejected(
        self,
        envelope: ProviderRequestEnvelope,
    ) -> RecordedRejectedExchange:
        contract = self.execution_contract(envelope)
        exact_fingerprint = contract.fingerprint()
        legacy_fingerprint = envelope.fingerprint()

        directory = self.directory / "rejected" / exact_fingerprint
        fingerprint = exact_fingerprint
        expected_contract: ProviderExecutionContract | None = contract
        if not directory.exists():
            directory = self.directory / "rejected" / legacy_fingerprint
            fingerprint = legacy_fingerprint
            expected_contract = None

        candidates = sorted(directory.glob("*.json")) if directory.exists() else []
        if not candidates:
            raise ReplayMissError(
                "no quarantined recording for "
                f"{envelope.kind} execution fingerprint {exact_fingerprint}; the exact request "
                "has no captured rejected response"
            )

        by_fingerprint = {path.stem: path for path in candidates}
        selected = self.rejected_response_fingerprints.get(fingerprint)
        if selected is None:
            selected = self.rejected_response_fingerprints.get(exact_fingerprint)
        if selected is None:
            selected = self.rejected_response_fingerprints.get(legacy_fingerprint)
        if selected is None:
            if len(candidates) != 1:
                raise ReplayAmbiguousError(
                    "multiple quarantined responses exist for "
                    f"{envelope.kind} fingerprint {fingerprint}; select one response fingerprint"
                )
            path = candidates[0]
        else:
            selected_path = by_fingerprint.get(selected)
            if selected_path is None:
                raise ReplayMissError(
                    "no quarantined response "
                    f"{selected} for {envelope.kind} fingerprint {fingerprint}"
                )
            path = selected_path

        try:
            exchange = RecordedRejectedExchange.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as exc:
            raise ReplayError(f"invalid quarantined recording {path}: {exc}") from exc

        if exchange.fingerprint != fingerprint:
            raise ReplayStaleError(
                f"quarantined recording {path} declares fingerprint {exchange.fingerprint}, "
                f"expected {fingerprint}"
            )
        if exchange.request.canonical_json() != envelope.canonical_json():
            raise ReplayStaleError(
                f"quarantined recording {path} semantic request does not match current request"
            )
        if expected_contract is None:
            if exchange.execution_contract is not None:
                raise ReplayStaleError(
                    f"quarantined recording {path} mixes legacy and v2 execution identity"
                )
        else:
            if exchange.execution_contract is None:
                raise ReplayStaleError(
                    f"quarantined recording {path} lacks its execution contract"
                )
            if exchange.execution_contract.canonical_json() != expected_contract.canonical_json():
                raise ReplayStaleError(
                    f"quarantined recording {path} execution contract is stale"
                )

        expected_response_fingerprint = _rejected_response_fingerprint(
            exchange.response,
            exchange.rejection,
        )
        if exchange.response_fingerprint != expected_response_fingerprint:
            raise ReplayStaleError(
                f"quarantined recording {path} content fingerprint does not match its payload"
            )
        if path.stem != exchange.response_fingerprint:
            raise ReplayStaleError(
                f"quarantined recording {path} filename does not match its content fingerprint"
            )
        return exchange

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(
            request,
            self.model,
            max_output_tokens=self.proof_review_max_output_tokens,
        )
        contract_fingerprint = self.execution_contract(envelope).fingerprint()
        legacy_fingerprint = envelope.fingerprint()
        explicitly_selected = (
            contract_fingerprint in self.rejected_response_fingerprints
            or legacy_fingerprint in self.rejected_response_fingerprints
        )
        if not explicitly_selected:
            try:
                return super().review_proof_turn(request)
            except ReplayMissError:
                pass

        exchange = self._load_rejected(envelope)
        if (
            exchange.rejection.kind != "proof_review_protocol"
            or not exchange.rejection.validator_replayable
            or exchange.response is None
        ):
            raise ReplayError(
                "quarantined provider failure has no validator-replayable structured response"
            )

        try:
            response = request.response_model().model_validate(exchange.response)
        except ValidationError as exc:
            raise ReplayStaleError(
                "quarantined structured response no longer satisfies the request-specific schema"
            ) from exc

        try:
            validate_proof_review_response(request, response)
        except ProofReviewProtocolError as exc:
            if str(exc) != exchange.rejection.message:
                raise ReplayStaleError(
                    "quarantined response now fails with a different proof-review protocol error"
                ) from exc
            self.forensic_hits += 1
            raise

        raise ReplayStaleError(
            "quarantined response no longer reproduces its proof-review protocol rejection"
        )
