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
from thorn.proof_language_review import ProofReviewModelResponse
from thorn.provider_readiness import (
    READINESS_CANARY_CARRIED_ITEMS,
    READINESS_CANARY_MAX_OUTPUT_TOKENS,
    READINESS_CANARY_SOURCE_ENUM_SIZE,
    build_readiness_rescue_turn,
    build_readiness_turn,
    preflight_readiness,
    run_live_readiness,
    verify_readiness_evidence,
)
from thorn.providers import openai as openai_provider
from thorn.providers.execution_contract import (
    ProviderTransportProfile,
    build_provider_execution_contract,
)
from thorn.providers.request_envelope import proof_review_request_envelope


class _ReadinessResponse:
    def __init__(self, output_text: str, *, response_id: str) -> None:
        self.output_text = output_text
        self.status = "completed"
        self.response_id = response_id
        self.usage = SimpleNamespace(input_tokens=31, output_tokens=17, total_tokens=48)

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "id": self.response_id,
            "status": self.status,
            "output_text": self.output_text,
            "usage": {
                "input_tokens": 31,
                "output_tokens": 17,
                "total_tokens": 48,
            },
        }


class _ReadinessResponses:
    def __init__(self, responses: list[_ReadinessResponse]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _ReadinessResponse:
        self.calls.append(kwargs)
        return next(self.responses)


class _ReadinessClient:
    def __init__(self, responses: list[_ReadinessResponse]) -> None:
        self.responses = _ReadinessResponses(responses)
        self.max_retries = 2


def _initial_review_json() -> str:
    return ProofReviewModelResponse(action="review").model_dump_json()


def _rescue_review_json() -> str:
    return json.dumps(
        {
            "action": "review",
            "findings": [],
            "source_addresses": [],
            "review_items": [],
            "source_review_item_ids": [],
            "dispositions": [
                {
                    "item_id": f"RV{index}",
                    "status": "discharged",
                    "explanation": f"Synthetic readiness item {index} discharged.",
                    "finding": None,
                }
                for index in range(1, READINESS_CANARY_CARRIED_ITEMS + 1)
            ],
        }
    )


def test_readiness_preflight_is_keyless_and_covers_initial_and_rescue_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def should_not_construct_client(*args: object, **kwargs: object) -> object:
        raise AssertionError("preflight must not instantiate OpenAIProvider")

    from thorn import provider_readiness

    monkeypatch.setattr(provider_readiness, "OpenAIProvider", should_not_construct_client)
    evidence = preflight_readiness(
        "test-model",
        boundary_source_tree_sha="synthetic-tree",
        run_id="preflight-123",
    )

    assert evidence.mode == "preflight"
    assert evidence.status == "preflight-ready"
    assert evidence.provider_instantiated is False
    assert evidence.scientific_authorization is False
    assert evidence.max_output_tokens == READINESS_CANARY_MAX_OUTPUT_TOKENS
    assert evidence.boundary_source_tree_sha == "synthetic-tree"
    assert evidence.run_id == "preflight-123"
    assert len(evidence.transport_profiles) == 2

    initial_profile, rescue_profile = evidence.transport_profiles
    assert initial_profile.message_roles == ("system", "user")
    assert rescue_profile.message_roles == ("system", "user", "assistant", "user")
    assert initial_profile.max_enum_items >= READINESS_CANARY_SOURCE_ENUM_SIZE
    assert rescue_profile.max_enum_items >= READINESS_CANARY_CARRIED_ITEMS
    assert rescue_profile.max_array_bound >= READINESS_CANARY_CARRIED_ITEMS

    wire = evidence.execution_contract.wire_request
    assert wire["max_output_tokens"] == READINESS_CANARY_MAX_OUTPUT_TOKENS
    text = wire["text"]
    assert isinstance(text, dict)
    response_format = text["format"]
    assert isinstance(response_format, dict)
    schema = response_format["schema"]
    assert isinstance(schema, dict)
    assert "anyOf" in schema

    rescue_wire = evidence.rescue_execution_contract.wire_request
    messages = rescue_wire["input"]
    assert isinstance(messages, list)
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]


def test_transport_profile_erases_literal_values_but_preserves_cardinality_bound() -> None:
    readiness = preflight_readiness("test-model")
    profile = readiness.transport_profiles[0]
    smaller = ProviderTransportProfile(
        provider=profile.provider,
        endpoint=profile.endpoint,
        kind=profile.kind,
        message_roles=profile.message_roles,
        schema_shape_sha256=profile.schema_shape_sha256,
        max_enum_items=max(1, profile.max_enum_items - 1),
        max_array_bound=profile.max_array_bound,
    )
    larger = smaller.model_copy(
        update={"max_enum_items": profile.max_enum_items + 1}
    )

    assert profile.covers(smaller)
    assert not profile.covers(larger)


def test_live_readiness_exercises_both_profiles_and_replays_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _ReadinessClient(
        [
            _ReadinessResponse(
                _initial_review_json(),
                response_id="resp_readiness_initial",
            ),
            _ReadinessResponse(
                _rescue_review_json(),
                response_id="resp_readiness_rescue",
            ),
        ]
    )
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)

    evidence = run_live_readiness(
        "test-model",
        boundary_source_tree_sha="synthetic-tree",
        run_id="run-456",
    )

    assert evidence.status == "live-success"
    assert evidence.readiness_only is True
    assert evidence.scientific_authorization is False
    assert evidence.provider_attempts == 2
    assert evidence.responses_received == 2
    assert evidence.model_generations == 2
    assert evidence.input_tokens == 62
    assert evidence.output_tokens == 34
    assert evidence.total_tokens == 96
    assert len(client.responses.calls) == 2
    assert client.max_retries == 0
    assert client.responses.calls[0]["input"] != client.responses.calls[1]["input"]
    assert evidence.provider_response is not None
    assert evidence.provider_response["id"] == "resp_readiness_initial"
    assert evidence.rescue_provider_response is not None
    assert evidence.rescue_provider_response["id"] == "resp_readiness_rescue"

    initial, rescue = verify_readiness_evidence(evidence)
    assert initial.action == "review"
    assert rescue.action == "review"
    assert len(rescue.dispositions) == READINESS_CANARY_CARRIED_ITEMS


def test_readiness_rescue_contract_is_deterministic_and_multi_message() -> None:
    initial = build_readiness_turn()
    rescue = build_readiness_rescue_turn()
    assert rescue.stage == "rescue"
    assert rescue.initial_packet_fingerprint == initial.initial_packet_fingerprint
    contract = build_provider_execution_contract(
        proof_review_request_envelope(
            rescue,
            "test-model",
            max_output_tokens=READINESS_CANARY_MAX_OUTPUT_TOKENS,
        )
    )
    assert contract.transport_profile().message_roles == (
        "system",
        "user",
        "assistant",
        "user",
    )


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
