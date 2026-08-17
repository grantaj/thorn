from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import (
    ProofReviewModelResponse,
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


class RecordingProvider:
    """Record successful responses from another evaluation provider."""

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
        response = validate_proof_review_response(
            request,
            self._delegate.review_proof_turn(request),
        )
        usage = RecordedUsage.snapshot(self._delegate).minus(before)
        self._write(envelope, response, usage)
        return response

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
    """Replay exact recorded provider exchanges without constructing a live client."""

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
