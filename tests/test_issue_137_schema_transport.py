from __future__ import annotations

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


def _property(branch: dict[str, object], name: str) -> dict[str, object]:
    properties = branch.get("properties")
    assert isinstance(properties, dict)
    value = properties.get(name)
    assert isinstance(value, dict)
    return value


def test_initial_provider_schema_exposes_action_safe_states() -> None:
    turn = _turn()
    envelope = proof_review_request_envelope(turn, "test-model")
    schema = envelope.response_schema
    root_properties = schema.get("properties")
    assert isinstance(root_properties, dict)

    assert envelope.provider == "openai-responses-create-json-schema"
    review = _branch(schema, "review")
    assert review["type"] == "object"
    assert review["additionalProperties"] is False
    review_properties = review["properties"]
    assert isinstance(review_properties, dict)
    assert set(review_properties) == set(root_properties)
    assert _property(review, "source_addresses")["maxItems"] == 0
    assert _property(review, "review_items")["maxItems"] == 0
    assert _property(review, "source_review_item_ids")["maxItems"] == 0

    need_source = _branch(schema, "need_source")
    assert need_source["type"] == "object"
    assert need_source["additionalProperties"] is False
    source_properties = need_source["properties"]
    assert isinstance(source_properties, dict)
    assert set(source_properties) == set(root_properties)
    assert _property(need_source, "findings")["maxItems"] == 0
    assert _property(need_source, "source_addresses")["minItems"] == 1
    assert _property(need_source, "review_items")["minItems"] == 1
    assert _property(need_source, "source_review_item_ids")["minItems"] == 1


class _CompletedInvalidResponse:
    def __init__(self, output_text: str) -> None:
        self.id = "resp_issue_137_a3"
        self.output_text = output_text
        self.status = "completed"
        self.usage = SimpleNamespace(input_tokens=321, output_tokens=45, total_tokens=366)

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "id": self.id,
            "status": self.status,
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

    assert provider.requests == provider.live_requests == provider.provider_attempts == 1
    assert provider.responses_received == provider.model_generations == 1
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
    branches = advertised.get("anyOf")
    assert isinstance(branches, list)
    for branch in branches:
        assert isinstance(branch, dict)
        assert branch["type"] == "object"
        assert branch["additionalProperties"] is False
        properties = branch["properties"]
        required = branch["required"]
        assert isinstance(properties, dict)
        assert isinstance(required, list)
        assert required == list(properties)

    rejected = list((tmp_path / "rejected").glob("*/*.json"))
    assert len(rejected) == 1
    exchange = RecordedRejectedExchange.model_validate_json(
        rejected[0].read_text(encoding="utf-8")
    )
    assert exchange.execution_contract is not None
    assert exchange.usage.requests == 1
    assert exchange.usage.provider_attempts == 1
    assert exchange.usage.responses_received == 1
    assert exchange.usage.model_generations == 1
    assert exchange.usage.input_tokens == 321
    assert exchange.usage.output_tokens == 45
    assert exchange.response == {
        "id": "resp_issue_137_a3",
        "status": "completed",
        "output_text": invalid,
        "usage": {
            "input_tokens": 321,
            "output_tokens": 45,
            "total_tokens": 366,
        },
    }
    assert exchange.rejection.kind == "response_validation"
    assert exchange.rejection.exception_type == "ValidationError"
    assert exchange.rejection.validator_replayable is False
