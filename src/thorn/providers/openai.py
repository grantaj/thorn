from __future__ import annotations

import copy
from typing import Any, cast

from openai import OpenAI
from pydantic import ValidationError

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import ProofReviewModelResponse, ProofReviewTurnRequest
from thorn.providers.base import ProviderResponseValidationError
from thorn.providers.request_envelope import (
    attack_request_envelope,
    defense_request_envelope,
    proof_review_request_envelope,
    semantic_request_envelope,
)
from thorn.semantic_review_render import SemanticReviewRequest


def _strict_json_schema(schema: dict[str, object]) -> dict[str, object]:
    """Return the strict Structured Outputs form of a canonical response schema."""

    strict = copy.deepcopy(schema)

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                value.setdefault("additionalProperties", False)
                properties = value.get("properties")
                if isinstance(properties, dict):
                    value["required"] = list(properties)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(strict)
    return strict


def _response_payload(response: object) -> dict[str, object]:
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        if isinstance(payload, dict):
            return cast(dict[str, object], payload)

    usage = getattr(response, "usage", None)
    return {
        "output_text": str(getattr(response, "output_text", "")),
        "usage": {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        },
    }


class OpenAIProvider:
    def __init__(self, model: str = "gpt-5.6") -> None:
        self.model = model
        self.client = OpenAI()
        self.client.max_retries = 0
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def _record_usage(self, response: object) -> None:
        self.requests += 1
        self.live_requests += 1
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)

    def attack(self, unit: TheoremUnit) -> AttackReport:
        envelope = attack_request_envelope(unit, self.model)
        response = self.client.responses.parse(
            model=self.model,
            input=cast(Any, envelope.input_messages()),
            text_format=AttackReport,
        )
        self._record_usage(response)
        if response.output_parsed is None:
            raise RuntimeError("attacker returned no structured result")
        return response.output_parsed

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        envelope = semantic_request_envelope(request, self.model)
        response = self.client.responses.parse(
            model=self.model,
            input=cast(Any, envelope.input_messages()),
            text_format=AttackReport,
        )
        self._record_usage(response)
        if response.output_parsed is None:
            raise RuntimeError("semantic reviewer returned no structured result")
        return response.output_parsed

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(request, self.model)
        response = self.client.responses.create(
            model=self.model,
            input=cast(Any, envelope.input_messages()),
            text=cast(
                Any,
                {
                    "format": {
                        "type": "json_schema",
                        "name": "ProofReviewModelResponse",
                        "schema": _strict_json_schema(envelope.response_schema),
                        "strict": True,
                    }
                },
            ),
            max_output_tokens=envelope.max_output_tokens,
            store=False,
        )
        self._record_usage(response)
        output_text = getattr(response, "output_text", "")
        if not isinstance(output_text, str) or not output_text:
            raise RuntimeError("proof-language reviewer returned no structured result")
        try:
            parsed = request.response_model().model_validate_json(output_text)
        except ValidationError as exc:
            raise ProviderResponseValidationError(
                "provider returned proof-review JSON that failed Thorn-local validation",
                response_payload=_response_payload(response),
                validation_exception_type=type(exc).__name__,
            ) from exc
        if not isinstance(parsed, ProofReviewModelResponse):
            raise RuntimeError("proof-language reviewer returned the wrong structured result")
        return ProofReviewModelResponse.model_validate(parsed.model_dump(mode="python"))

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport:
        envelope = defense_request_envelope(unit, findings, self.model)
        response = self.client.responses.parse(
            model=self.model,
            input=cast(Any, envelope.input_messages()),
            text_format=DefenseReport,
        )
        self._record_usage(response)
        if response.output_parsed is None:
            raise RuntimeError("defender returned no structured result")
        return response.output_parsed
