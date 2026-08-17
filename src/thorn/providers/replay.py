from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import (
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTurnRequest,
    validate_proof_review_response,
)
from thorn.providers.base import EvaluationProvider
from thorn.providers.request_envelope import (
    ProviderRequestEnvelope,
    attack_request_envelope,
    defense_request_envelope,
    proof_review_request_envelope,
    semantic_request_envelope,
)
from thorn.semantic_review_render import SemanticReviewRequest


class ReplayError(RuntimeError):
    """Base class for recorded-evaluation failures."""


class ReplayMissError(ReplayError):
    """Raised when no exact recording exists for the current request fingerprint."""


class ReplayStaleError(ReplayError):
    """Raised when a recording file does not match its current request fingerprint."""


class ReplayAmbiguousError(ReplayError):
    """Raised when forensic replay has multiple rejected responses and no selection."""


class RecordedUsage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def snapshot(cls, provider: EvaluationProvider) -> RecordedUsage:
        return cls(
            requests=provider.requests,
            input_tokens=provider.input_tokens,
            output_tokens=provider.output_tokens,
            total_tokens=provider.total_tokens,
        )

    def minus(self, earlier: RecordedUsage) -> RecordedUsage:
        return RecordedUsage(
            requests=self.requests - earlier.requests,
            input_tokens=self.input_tokens - earlier.input_tokens,
            output_tokens=self.output_tokens - earlier.output_tokens,
            total_tokens=self.total_tokens - earlier.total_tokens,
        )


class RecordedExchange(BaseModel):
    format_version: int = 1
    fingerprint: str
    request: ProviderRequestEnvelope
    response: dict[str, object]
    usage: RecordedUsage


RejectedRecordingKind = Literal["proof_review_protocol", "provider_failure"]


class RecordedRejection(BaseModel):
    kind: RejectedRecordingKind
    message: str
    exception_type: str
    validator_replayable: bool


class RecordedRejectedExchange(BaseModel):
    """Quarantined evidence that can never satisfy ordinary replay lookup."""

    format_version: int = 1
    fingerprint: str
    request: ProviderRequestEnvelope
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


def _rejected_response_fingerprint(
    response: dict[str, object] | None,
    rejection: RecordedRejection,
) -> str:
    payload = {
        "response": response,
        "rejection": rejection.model_dump(mode="json"),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class RecordingProvider:
    """Record successful responses and quarantine rejected proof-review evidence."""

    def __init__(self, delegate: EvaluationProvider, directory: Path) -> None:
        self._delegate = delegate
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.model = delegate.model

    @property
    def requests(self) -> int:
        return self._delegate.requests

    @property
    def live_requests(self) -> int:
        return getattr(self._delegate, "live_requests", self._delegate.requests)

    @property
    def replay_hits(self) -> int:
        return getattr(self._delegate, "replay_hits", 0)

    @property
    def input_tokens(self) -> int:
        return self._delegate.input_tokens

    @property
    def output_tokens(self) -> int:
        return self._delegate.output_tokens

    @property
    def total_tokens(self) -> int:
        return self._delegate.total_tokens

    def _write(
        self,
        envelope: ProviderRequestEnvelope,
        response: BaseModel,
        usage: RecordedUsage,
    ) -> None:
        fingerprint = envelope.fingerprint()
        exchange = RecordedExchange(
            fingerprint=fingerprint,
            request=envelope,
            response=response.model_dump(mode="json"),
            usage=usage,
        )
        destination = self.directory / f"{fingerprint}.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(exchange.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)

    def _write_rejected(
        self,
        envelope: ProviderRequestEnvelope,
        response: BaseModel | None,
        usage: RecordedUsage,
        rejection: RecordedRejection,
    ) -> None:
        fingerprint = envelope.fingerprint()
        response_payload = response.model_dump(mode="json") if response is not None else None
        response_fingerprint = _rejected_response_fingerprint(response_payload, rejection)
        exchange = RecordedRejectedExchange(
            fingerprint=fingerprint,
            request=envelope,
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
        temporary.write_text(exchange.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)

    def attack(self, unit: TheoremUnit) -> AttackReport:
        envelope = attack_request_envelope(unit, self.model)
        before = RecordedUsage.snapshot(self._delegate)
        response = self._delegate.attack(unit)
        usage = RecordedUsage.snapshot(self._delegate).minus(before)
        self._write(envelope, response, usage)
        return response

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        envelope = semantic_request_envelope(request, self.model)
        before = RecordedUsage.snapshot(self._delegate)
        response = self._delegate.review_semantic(request)
        usage = RecordedUsage.snapshot(self._delegate).minus(before)
        self._write(envelope, response, usage)
        return response

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(request, self.model)
        before = RecordedUsage.snapshot(self._delegate)
        try:
            response = self._delegate.review_proof_turn(request)
        except Exception as exc:
            usage = RecordedUsage.snapshot(self._delegate).minus(before)
            self._write_rejected(
                envelope,
                None,
                usage,
                RecordedRejection(
                    kind="provider_failure",
                    message="provider did not return a structured proof-review response",
                    exception_type=type(exc).__name__,
                    validator_replayable=False,
                ),
            )
            raise

        usage = RecordedUsage.snapshot(self._delegate).minus(before)
        try:
            normalized = validate_proof_review_response(request, response)
        except ProofReviewProtocolError as exc:
            self._write_rejected(
                envelope,
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

        self._write(envelope, normalized, usage)
        return normalized

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
    ) -> DefenseReport:
        envelope = defense_request_envelope(unit, findings, self.model)
        before = RecordedUsage.snapshot(self._delegate)
        response = self._delegate.defend(unit, findings)
        usage = RecordedUsage.snapshot(self._delegate).minus(before)
        self._write(envelope, response, usage)
        return response


class ReplayProvider:
    """Replay exact accepted provider exchanges without constructing a live client."""

    def __init__(self, model: str, directory: Path) -> None:
        self.model = model
        self.directory = directory
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.recorded_input_tokens = 0
        self.recorded_output_tokens = 0
        self.recorded_total_tokens = 0

    def _load(self, envelope: ProviderRequestEnvelope) -> RecordedExchange:
        fingerprint = envelope.fingerprint()
        path = self.directory / f"{fingerprint}.json"
        if not path.exists():
            raise ReplayMissError(
                "no recording for "
                f"{envelope.kind} fingerprint {fingerprint}; the model, prompt, "
                "rendered input, output schema, protocol metadata, or recording set has changed"
            )
        try:
            exchange = RecordedExchange.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError, json.JSONDecodeError) as exc:
            raise ReplayError(f"invalid recording {path}: {exc}") from exc
        if exchange.fingerprint != fingerprint:
            raise ReplayStaleError(
                f"recording {path} declares fingerprint {exchange.fingerprint}, "
                f"expected {fingerprint}"
            )
        if exchange.request.canonical_json() != envelope.canonical_json():
            raise ReplayStaleError(
                f"recording {path} request payload does not match fingerprint {fingerprint}"
            )
        return exchange

    def _record_hit(self, exchange: RecordedExchange) -> None:
        self.requests += 1
        self.replay_hits += 1
        self.recorded_input_tokens += exchange.usage.input_tokens
        self.recorded_output_tokens += exchange.usage.output_tokens
        self.recorded_total_tokens += exchange.usage.total_tokens

    def attack(self, unit: TheoremUnit) -> AttackReport:
        exchange = self._load(attack_request_envelope(unit, self.model))
        response = AttackReport.model_validate(exchange.response)
        self._record_hit(exchange)
        return response

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        exchange = self._load(semantic_request_envelope(request, self.model))
        response = AttackReport.model_validate(exchange.response)
        self._record_hit(exchange)
        return response

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        exchange = self._load(proof_review_request_envelope(request, self.model))
        response = request.response_model().model_validate(exchange.response)
        response = validate_proof_review_response(request, response)
        self._record_hit(exchange)
        return response

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
    ) -> DefenseReport:
        exchange = self._load(defense_request_envelope(unit, findings, self.model))
        response = DefenseReport.model_validate(exchange.response)
        self._record_hit(exchange)
        return response


class ForensicReplayProvider(ReplayProvider):
    """Replay accepted turns normally and explicit quarantined failures for diagnosis."""

    def __init__(
        self,
        model: str,
        directory: Path,
        *,
        rejected_response_fingerprints: dict[str, str] | None = None,
    ) -> None:
        super().__init__(model=model, directory=directory)
        self.rejected_response_fingerprints = dict(rejected_response_fingerprints or {})
        self.forensic_hits = 0

    def _load_rejected(
        self,
        envelope: ProviderRequestEnvelope,
    ) -> RecordedRejectedExchange:
        fingerprint = envelope.fingerprint()
        directory = self.directory / "rejected" / fingerprint
        candidates = sorted(directory.glob("*.json")) if directory.exists() else []
        if not candidates:
            raise ReplayMissError(
                "no quarantined recording for "
                f"{envelope.kind} fingerprint {fingerprint}; the exact request has no "
                "captured rejected response"
            )

        by_fingerprint = {path.stem: path for path in candidates}
        selected = self.rejected_response_fingerprints.get(fingerprint)
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
                "quarantined recording "
                f"{path} request payload does not match fingerprint {fingerprint}"
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
        try:
            return super().review_proof_turn(request)
        except ReplayMissError:
            pass

        envelope = proof_review_request_envelope(request, self.model)
        exchange = self._load_rejected(envelope)
        if (
            exchange.rejection.kind != "proof_review_protocol"
            or not exchange.rejection.validator_replayable
            or exchange.response is None
        ):
            raise ReplayError(
                "quarantined provider failure has no structured response and is not "
                "validator-replayable"
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
