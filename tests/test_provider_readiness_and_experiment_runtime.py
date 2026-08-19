from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from thorn.experiment_runtime import (
    ProviderBudget,
    ProviderBudgetSpec,
    ProviderUsageSnapshot,
    conservative_wire_input_token_bound,
)
from thorn.provider_readiness import (
    READINESS_CANARY_MAX_OUTPUT_TOKENS,
    build_readiness_turn,
    preflight_readiness,
    run_live_readiness,
    verify_readiness_evidence,
)
from thorn.providers import openai as openai_provider
from thorn.providers.execution_contract import build_provider_execution_contract
from thorn.providers.request_envelope import proof_review_request_envelope


class _ReadinessResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.status = "completed"
        self.usage = SimpleNamespace(input_tokens=31, output_tokens=17, total_tokens=48)

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "id": "resp_readiness_synthetic",
            "status": self.status,
            "output_text": self.output_text,
            "usage": {
                "input_tokens": 31,
                "output_tokens": 17,
                "total_tokens": 48,
            },
        }


class _ReadinessResponses:
    def __init__(self, response: _ReadinessResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _ReadinessResponse:
        self.calls.append(kwargs)
        return self.response


class _ReadinessClient:
    def __init__(self, response: _ReadinessResponse) -> None:
        self.responses = _ReadinessResponses(response)
        self.max_retries = 2


def _need_source_json() -> str:
    return json.dumps(
        {
            "action": "need_source",
            "findings": [],
            "source_addresses": ["P1"],
            "review_items": [
                {
                    "id": "RV1",
                    "kind": "question",
                    "summary": "Check the synthetic source step.",
                }
            ],
            "source_review_item_ids": ["RV1"],
            "dispositions": [],
        }
    )


def test_readiness_preflight_is_keyless_and_exercises_normal_initial_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def should_not_construct_client(*args: object, **kwargs: object) -> object:
        raise AssertionError("preflight must not instantiate OpenAIProvider")

    from thorn import provider_readiness

    monkeypatch.setattr(provider_readiness, "OpenAIProvider", should_not_construct_client)
    evidence = preflight_readiness("test-model")

    assert evidence.mode == "preflight"
    assert evidence.status == "preflight-ready"
    assert evidence.provider_instantiated is False
    assert evidence.scientific_authorization is False
    assert evidence.max_output_tokens == READINESS_CANARY_MAX_OUTPUT_TOKENS
    wire = evidence.execution_contract.wire_request
    assert wire["max_output_tokens"] == READINESS_CANARY_MAX_OUTPUT_TOKENS
    text = wire["text"]
    assert isinstance(text, dict)
    response_format = text["format"]
    assert isinstance(response_format, dict)
    schema = response_format["schema"]
    assert isinstance(schema, dict)
    assert "anyOf" in schema


def test_live_readiness_makes_exactly_one_call_even_when_model_requests_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ReadinessClient(_ReadinessResponse(_need_source_json()))
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)

    evidence = run_live_readiness("test-model")

    assert evidence.status == "live-success"
    assert evidence.readiness_only is True
    assert evidence.scientific_authorization is False
    assert evidence.provider_attempts == 1
    assert evidence.responses_received == 1
    assert evidence.model_generations == 1
    assert evidence.input_tokens == 31
    assert evidence.output_tokens == 17
    assert evidence.total_tokens == 48
    assert len(client.responses.calls) == 1
    assert client.max_retries == 0
    assert evidence.provider_response is not None
    assert evidence.provider_response["id"] == "resp_readiness_synthetic"

    replayed = verify_readiness_evidence(evidence)
    assert replayed.action == "need_source"
    assert replayed.source_addresses == ("P1",)


def test_shared_budget_counts_failed_attempts_without_inventing_usage() -> None:
    turn = build_readiness_turn()
    contract = build_provider_execution_contract(
        proof_review_request_envelope(turn, "test-model")
    )
    bound = conservative_wire_input_token_bound(contract)
    spec = ProviderBudgetSpec(
        max_cases=1,
        max_provider_attempts=2,
        max_input_tokens=bound + 100,
        max_output_tokens_per_request=4096,
        max_output_tokens=8192,
    )
    budget = ProviderBudget(spec)
    before = ProviderUsageSnapshot()
    after = ProviderUsageSnapshot(
        requests=1,
        live_requests=1,
        provider_attempts=1,
    )

    budget.reserve(contract)
    budget.commit(before, after)

    assert budget.reserved_turns == 1
    assert budget.provider_attempts == 1
    assert budget.input_tokens == 0
    assert budget.output_tokens == 0
