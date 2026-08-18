from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected patch context missing in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/thorn/providers/base.py",
    "class AuditProvider(Protocol):\n",
    '''class ProviderResponseValidationError(RuntimeError):
    """A completed provider response that failed Thorn-local structured validation."""

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
''',
)

replace(
    "src/thorn/providers/request_envelope.py",
    "def proof_review_request_envelope(\n",
    '''def _proof_review_response_schema(
    request: ProofReviewTurnRequest,
) -> dict[str, object]:
    """Expose the request-specific proof-review action states to the provider.

    Pydantic's model-level validators still enforce relational invariants that JSON
    Schema cannot express cleanly, but the provider must not be offered combinations
    that are invalid merely because of the selected protocol action.
    """

    schema = json.loads(json.dumps(request.response_schema()))
    if request.stage != "initial" or not request.source_rescue_allowed:
        return schema

    schema["anyOf"] = [
        {
            "properties": {
                "action": {"const": "review"},
                "source_addresses": {"maxItems": 0},
                "review_items": {"maxItems": 0},
                "source_review_item_ids": {"maxItems": 0},
            }
        },
        {
            "properties": {
                "action": {"const": "need_source"},
                "findings": {"maxItems": 0},
                "source_addresses": {"minItems": 1},
                "review_items": {"minItems": 1},
                "source_review_item_ids": {"minItems": 1},
            }
        },
    ]
    return schema


def proof_review_request_envelope(
''',
)
replace(
    "src/thorn/providers/request_envelope.py",
    '''    return ProviderRequestEnvelope(
        kind="proof_review",
        model=model,
''',
    '''    return ProviderRequestEnvelope(
        provider="openai-responses-create-json-schema",
        kind="proof_review",
        model=model,
''',
)
replace(
    "src/thorn/providers/request_envelope.py",
    "        response_schema=request.response_schema(),\n",
    "        response_schema=_proof_review_response_schema(request),\n",
)

Path("src/thorn/providers/openai.py").write_text(r'''from __future__ import annotations

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
        return parsed

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
''', encoding="utf-8")

replace(
    "src/thorn/providers/replay.py",
    "from thorn.providers.base import EvaluationProvider\n",
    "from thorn.providers.base import EvaluationProvider, ProviderResponseValidationError\n",
)
replace(
    "src/thorn/providers/replay.py",
    "        response: BaseModel | None,\n",
    "        response: BaseModel | dict[str, object] | None,\n",
)
replace(
    "src/thorn/providers/replay.py",
    '''        response_payload = response.model_dump(mode="json") if response is not None else None
''',
    '''        response_payload = (
            response.model_dump(mode="json")
            if isinstance(response, BaseModel)
            else response
        )
''',
)
replace(
    "src/thorn/providers/replay.py",
    '''        try:
            response = self._delegate.review_proof_turn(request)
        except Exception as exc:
''',
    '''        try:
            response = self._delegate.review_proof_turn(request)
        except ProviderResponseValidationError as exc:
            usage = RecordedUsage.snapshot(self._delegate).minus(before)
            self._write_rejected(
                envelope,
                exc.response_payload,
                usage,
                RecordedRejection(
                    kind="provider_failure",
                    message="provider returned structured content that failed local validation",
                    exception_type=exc.validation_exception_type,
                    validator_replayable=False,
                ),
            )
            raise
        except Exception as exc:
''',
)

replace(
    "tests/test_proof_language_review.py",
    '''    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self.response,
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )
''',
    '''    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self.response,
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self.response.model_dump_json(),
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )
''',
)
replace(
    "tests/test_proof_language_review.py",
    '''    text_format = call["text_format"]
    assert isinstance(text_format, type)
    assert issubclass(text_format, ProofReviewModelResponse)
    assert text_format is not ProofReviewModelResponse
    messages = call["input"]
''',
    '''    text = call["text"]
    assert isinstance(text, dict)
    text_format = text["format"]
    assert isinstance(text_format, dict)
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    schema = text_format["schema"]
    assert isinstance(schema, dict)
    assert "anyOf" in schema
    assert schema["additionalProperties"] is False
    messages = call["input"]
''',
)

Path("tests/test_issue_137_schema_transport.py").write_text(r'''from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import ProofLanguageReviewRequest, build_proof_review_turn
from thorn.providers import openai as openai_provider
from thorn.providers.base import ProviderResponseValidationError
from thorn.providers.openai import OpenAIProvider
from thorn.providers.replay import RecordedRejectedExchange, RecordingProvider
from thorn.providers.request_envelope import proof_review_request_envelope


def _turn():
    document = LLMProofLanguage(
        result_identifier="thm:a3",
        lines=(
            "THORN-PROOF 1",
            "T0 Goal",
            "P1 Step <- ? @E1",
            "GOAL G0 T0: Goal | ctx P1 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(address="E1", ir_identifier="edge:E1", text="Source E1."),
            ProofLanguageSourceHandle(address="T0", ir_identifier="result:T0", text="Source T0."),
        ),
    )
    return build_proof_review_turn(ProofLanguageReviewRequest(document=document))


def _branch(schema: dict[str, object], action: str) -> dict[str, object]:
    branches = schema.get("anyOf")
    assert isinstance(branches, list)
    for candidate in branches:
        assert isinstance(candidate, dict)
        properties = candidate.get("properties")
        assert isinstance(properties, dict)
        action_schema = properties.get("action")
        if isinstance(action_schema, dict) and action_schema.get("const") == action:
            return candidate
    raise AssertionError(f"missing {action} branch")


def test_initial_provider_schema_exposes_action_safe_states() -> None:
    turn = _turn()
    envelope = proof_review_request_envelope(turn, "test-model")
    schema = envelope.response_schema

    assert envelope.provider == "openai-responses-create-json-schema"
    review = _branch(schema, "review")
    review_properties = review["properties"]
    assert isinstance(review_properties, dict)
    assert review_properties["source_addresses"] == {"maxItems": 0}
    assert review_properties["review_items"] == {"maxItems": 0}
    assert review_properties["source_review_item_ids"] == {"maxItems": 0}

    need_source = _branch(schema, "need_source")
    source_properties = need_source["properties"]
    assert isinstance(source_properties, dict)
    assert source_properties["findings"] == {"maxItems": 0}
    assert source_properties["source_addresses"] == {"minItems": 1}
    assert source_properties["review_items"] == {"minItems": 1}
    assert source_properties["source_review_item_ids"] == {"minItems": 1}


class _CompletedInvalidResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.usage = SimpleNamespace(input_tokens=321, output_tokens=45, total_tokens=366)

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "id": "resp_issue_137_a3",
            "output": [{"type": "message", "content": self.output_text}],
            "usage": {
                "input_tokens": 321,
                "output_tokens": 45,
                "total_tokens": 366,
            },
        }


class _FakeResponses:
    def __init__(self, response: _CompletedInvalidResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _CompletedInvalidResponse:
        self.calls.append(kwargs)
        return self.response


class _FakeClient:
    def __init__(self, response: _CompletedInvalidResponse) -> None:
        self.responses = _FakeResponses(response)
        self.max_retries = 2


def test_a3_local_validation_failure_preserves_usage_and_provider_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    turn = _turn()
    invalid = json.dumps(
        {
            "action": "review",
            "findings": [],
            "source_addresses": ["E1"],
            "review_items": [],
            "source_review_item_ids": [],
            "dispositions": [],
        }
    )
    completed = _CompletedInvalidResponse(invalid)
    client = _FakeClient(completed)
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = OpenAIProvider(model="test-model")
    recorder = RecordingProvider(provider, tmp_path)

    with pytest.raises(ProviderResponseValidationError, match="failed Thorn-local validation"):
        recorder.review_proof_turn(turn)

    assert provider.requests == provider.live_requests == 1
    assert provider.input_tokens == 321
    assert provider.output_tokens == 45
    assert provider.total_tokens == 366
    assert client.max_retries == 0
    assert len(client.responses.calls) == 1

    call = client.responses.calls[0]
    text = call["text"]
    assert isinstance(text, dict)
    response_format = text["format"]
    assert isinstance(response_format, dict)
    advertised = response_format["schema"]
    assert isinstance(advertised, dict)
    assert advertised["additionalProperties"] is False
    assert "anyOf" in advertised

    rejected = list((tmp_path / "rejected").glob("*/*.json"))
    assert len(rejected) == 1
    exchange = RecordedRejectedExchange.model_validate_json(
        rejected[0].read_text(encoding="utf-8")
    )
    assert exchange.usage.requests == 1
    assert exchange.usage.input_tokens == 321
    assert exchange.usage.output_tokens == 45
    assert exchange.response == completed.model_dump(mode="json")
    assert exchange.rejection.kind == "provider_failure"
    assert exchange.rejection.exception_type == "ValidationError"
    assert exchange.rejection.validator_replayable is False
''', encoding="utf-8")
