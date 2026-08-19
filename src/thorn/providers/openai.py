from __future__ import annotations

from typing import Any, TypeVar, cast

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import ProofReviewModelResponse, ProofReviewTurnRequest
from thorn.providers.base import (
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

TModel = TypeVar("TModel", bound=BaseModel)
_SAFE_TRANSPORT_MESSAGE = "provider request failed before a response was returned"
_SAFE_RESPONSE_STATUS_MESSAGE = "provider response did not complete successfully"


def _json_safe(value: object) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _json_safe(model_dump(mode="json"))
        except (TypeError, ValueError):
            pass
    return None


def _transport_evidence(exc: Exception) -> ProviderTransportEvidence:
    raw_body = getattr(exc, "body", None)
    safe_body = _json_safe(raw_body)
    body_dict = safe_body if isinstance(safe_body, dict) else {}
    error = body_dict.get("error")
    error_dict = error if isinstance(error, dict) else body_dict

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)

    def header(name: str) -> str | None:
        if headers is None:
            return None
        getter = getattr(headers, "get", None)
        if not callable(getter):
            return None
        value = getter(name)
        return str(value) if value is not None else None

    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        response_status = getattr(response, "status_code", None)
        status_code = response_status if isinstance(response_status, int) else None

    request_id = getattr(exc, "request_id", None)
    if request_id is None:
        request_id = header("x-request-id")

    def text_field(name: str) -> str | None:
        value = error_dict.get(name)
        return str(value) if value is not None else None

    error_type = text_field("type")
    code = text_field("code")
    param = text_field("param")
    sanitized_body: dict[str, object] | None = None
    structured_error = {
        key: value
        for key, value in {
            "type": error_type,
            "code": code,
            "param": param,
        }.items()
        if value is not None
    }
    if structured_error:
        sanitized_body = {"error": structured_error}

    return ProviderTransportEvidence(
        exception_type=type(exc).__name__,
        message=_SAFE_TRANSPORT_MESSAGE,
        status_code=status_code,
        request_id=str(request_id) if request_id is not None else None,
        error_type=error_type,
        code=code,
        param=param,
        body=sanitized_body,
        retry_after=header("retry-after"),
    )


def _safe_named_fields(value: object, allowed: tuple[str, ...]) -> dict[str, object] | None:
    raw = _json_safe(value)
    if not isinstance(raw, dict):
        return None
    result: dict[str, object] = {}
    for name in allowed:
        field = raw.get(name)
        if isinstance(field, (str, int, float, bool)) or field is None:
            if field is not None:
                result[name] = field
    return result or None


def _response_payload(response: object) -> dict[str, object]:
    usage = getattr(response, "usage", None)
    response_id = getattr(response, "id", None)
    if response_id is None:
        response_id = getattr(response, "response_id", None)
    status = getattr(response, "status", None)
    output_text = getattr(response, "output_text", "")

    payload: dict[str, object] = {
        "status": str(status) if status is not None else "<missing>",
        "output_text": output_text if isinstance(output_text, str) else "",
        "usage": {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        },
    }
    if response_id is not None:
        payload["id"] = str(response_id)

    error = _safe_named_fields(
        getattr(response, "error", None),
        ("type", "code", "param"),
    )
    if error is not None:
        payload["error"] = error
    incomplete_details = _safe_named_fields(
        getattr(response, "incomplete_details", None),
        ("reason",),
    )
    if incomplete_details is not None:
        payload["incomplete_details"] = incomplete_details
    return payload


def _generation_known(response: object) -> bool:
    if getattr(response, "status", None) == "completed":
        return True
    usage = getattr(response, "usage", None)
    if int(getattr(usage, "output_tokens", 0) or 0) > 0:
        return True
    output_text = getattr(response, "output_text", "")
    return isinstance(output_text, str) and bool(output_text)


class OpenAIProvider:
    """OpenAI transport with one explicit, fingerprintable execution boundary."""

    accepts_execution_contract = True

    def __init__(
        self,
        model: str = "gpt-5.6",
        *,
        proof_review_max_output_tokens: int = PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    ) -> None:
        if proof_review_max_output_tokens <= 0:
            raise ValueError("proof_review_max_output_tokens must be positive")
        self.model = model
        self.proof_review_max_output_tokens = proof_review_max_output_tokens
        self.client = OpenAI()
        self.client.max_retries = 0
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.provider_attempts = 0
        self.responses_received = 0
        self.model_generations = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.last_execution_contract: ProviderExecutionContract | None = None
        self.last_response_payload: dict[str, object] | None = None

    def execution_contract(
        self,
        envelope: ProviderRequestEnvelope,
    ) -> ProviderExecutionContract:
        """Return the exact contract that would be dispatched for ``envelope``."""

        return build_provider_execution_contract(envelope)

    def _record_usage(self, response: object) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)

    def _execute_contract(self, contract: ProviderExecutionContract) -> object:
        self.last_execution_contract = contract
        self.last_response_payload = None

        self.requests += 1
        self.live_requests += 1
        self.provider_attempts += 1
        try:
            response = self.client.responses.create(
                **cast(Any, contract.provider_kwargs())
            )
        except Exception as exc:
            evidence = _transport_evidence(exc)
            raise ProviderTransportError(
                _SAFE_TRANSPORT_MESSAGE,
                evidence=evidence,
            ) from exc

        self.responses_received += 1
        self.last_response_payload = _response_payload(response)
        if _generation_known(response):
            self.model_generations += 1
        self._record_usage(response)
        return response

    def _execute(
        self,
        envelope: ProviderRequestEnvelope,
        *,
        execution_contract: ProviderExecutionContract | None = None,
    ) -> tuple[object, ProviderExecutionContract]:
        expected = self.execution_contract(envelope)
        contract = execution_contract or expected
        if contract.canonical_json() != expected.canonical_json():
            raise ValueError("supplied provider execution contract does not match request envelope")
        response = self._execute_contract(contract)
        return response, contract

    def _validate_structured_response(
        self,
        response: object,
        response_model: type[TModel],
        *,
        label: str,
    ) -> TModel:
        if getattr(response, "status", None) != "completed":
            raise ProviderResponseValidationError(
                _SAFE_RESPONSE_STATUS_MESSAGE,
                response_payload=_response_payload(response),
                validation_exception_type="ProviderResponseNotCompleted",
            )

        output_text = getattr(response, "output_text", "")
        if not isinstance(output_text, str) or not output_text:
            raise ProviderResponseValidationError(
                f"{label} returned no structured result",
                response_payload=_response_payload(response),
                validation_exception_type="MissingStructuredOutput",
            )
        try:
            return response_model.model_validate_json(output_text)
        except ValidationError as exc:
            raise ProviderResponseValidationError(
                f"{label} returned JSON that failed Thorn-local validation",
                response_payload=_response_payload(response),
                validation_exception_type=type(exc).__name__,
            ) from exc

    def attack(
        self,
        unit: TheoremUnit,
        *,
        execution_contract: ProviderExecutionContract | None = None,
    ) -> AttackReport:
        envelope = attack_request_envelope(unit, self.model)
        response, _ = self._execute(envelope, execution_contract=execution_contract)
        return self._validate_structured_response(response, AttackReport, label="attacker")

    def review_semantic(
        self,
        request: SemanticReviewRequest,
        *,
        execution_contract: ProviderExecutionContract | None = None,
    ) -> AttackReport:
        envelope = semantic_request_envelope(request, self.model)
        response, _ = self._execute(envelope, execution_contract=execution_contract)
        return self._validate_structured_response(
            response,
            AttackReport,
            label="semantic reviewer",
        )

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
        *,
        execution_contract: ProviderExecutionContract | None = None,
    ) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(
            request,
            self.model,
            max_output_tokens=self.proof_review_max_output_tokens,
        )
        response, _ = self._execute(envelope, execution_contract=execution_contract)
        parsed = self._validate_structured_response(
            response,
            request.response_model(),
            label="proof-language reviewer",
        )
        return ProofReviewModelResponse.model_validate(parsed.model_dump(mode="python"))

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
        *,
        execution_contract: ProviderExecutionContract | None = None,
    ) -> DefenseReport:
        envelope = defense_request_envelope(unit, findings, self.model)
        response, _ = self._execute(envelope, execution_contract=execution_contract)
        return self._validate_structured_response(response, DefenseReport, label="defender")
