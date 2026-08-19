from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import ProofReviewTransport
from thorn.semantic_review_render import SemanticReviewRequest


class ProviderTransportEvidence(BaseModel):
    """Structured evidence captured when provider dispatch fails.

    Only stable, JSON-serializable fields that are useful for diagnosing provider
    failures are retained. Secrets, authorization headers, and arbitrary response
    objects are deliberately excluded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    exception_type: str
    message: str
    status_code: int | None = None
    request_id: str | None = None
    error_type: str | None = None
    code: str | None = None
    param: str | None = None
    body: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    retry_after: str | None = None


class ProviderTransportError(RuntimeError):
    """A provider request attempt that failed before Thorn received a response."""

    def __init__(self, message: str, *, evidence: ProviderTransportEvidence) -> None:
        super().__init__(message)
        self.evidence = evidence


class ProviderResponseValidationError(RuntimeError):
    """A received provider response that failed Thorn-local structured validation."""

    def __init__(
        self,
        message: str,
        *,
        response_payload: dict[str, object],
        validation_exception_type: str,
    ) -> None:
        super().__init__(message)
        self.response_payload = response_payload
        self.validation_exception_type = validation_exception_type


class AuditProvider(Protocol):
    model: str

    def attack(self, unit: TheoremUnit) -> AttackReport: ...

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport: ...


class SemanticReviewProvider(Protocol):
    """Provider boundary for one Thorn-owned, IR-derived semantic review request."""

    model: str

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport: ...


class EvaluationProvider(AuditProvider, SemanticReviewProvider, ProofReviewTransport, Protocol):
    """Combined evaluator boundary with provider usage/replay accounting.

    ``provider_attempts`` counts dispatches before the provider call is made.
    ``responses_received`` counts calls that returned a provider response object.
    ``model_generations`` counts responses for which model generation is known to
    have occurred. ``requests`` and ``live_requests`` remain compatibility aliases
    for logical/live provider attempts. Replays increment ``replay_hits`` and do not
    consume live attempts or tokens.
    """

    @property
    def requests(self) -> int: ...

    @property
    def live_requests(self) -> int: ...

    @property
    def replay_hits(self) -> int: ...

    @property
    def provider_attempts(self) -> int: ...

    @property
    def responses_received(self) -> int: ...

    @property
    def model_generations(self) -> int: ...

    @property
    def input_tokens(self) -> int: ...

    @property
    def output_tokens(self) -> int: ...

    @property
    def total_tokens(self) -> int: ...
