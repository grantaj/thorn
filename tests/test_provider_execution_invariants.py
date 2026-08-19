from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.models import AttackReport, SourceRange, TheoremUnit
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    build_proof_review_turn,
)
from thorn.providers import execution_contract
from thorn.providers import openai as openai_provider
from thorn.providers.base import ProviderResponseValidationError, ProviderTransportError
from thorn.providers.execution_contract import ProviderRuntimeIdentity
from thorn.providers.replay import (
    RecordedExchange,
    RecordedRejectedExchange,
    RecordedUsage,
    RecordingConflictError,
    RecordingProvider,
    ReplayMissError,
    ReplayProvider,
)
from thorn.providers.request_envelope import attack_request_envelope, proof_review_request_envelope


def _runtime(*, lock: str = "lock-a") -> ProviderRuntimeIdentity:
    return ProviderRuntimeIdentity(
        python="3.11.16",
        provider_lock_sha256=lock,
        locked_packages={"openai": "3.3.0", "pydantic": "2.13.4"},
    )


def _unit() -> TheoremUnit:
    return TheoremUnit(
        identifier="thm:invariant",
        environment="theorem",
        statement="Every synthetic widget is bounded.",
        proof="This is synthetic provider-boundary test material.",
        statement_range=SourceRange(file="synthetic.tex", start_line=1, end_line=2),
    )


def _proof_turn():
    document = LLMProofLanguage(
        result_identifier="thm:synthetic",
        lines=(
            "THORN-PROOF 1",
            "T0 SyntheticGoal <- P1 @T0",
            "P1 SyntheticStep @E1",
            "GOAL G0 T0: SyntheticGoal | ctx P1 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="E1",
                ir_identifier="edge:E1",
                text="Synthetic source evidence.",
            ),
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="result:T0",
                text="Synthetic theorem source.",
            ),
        ),
    )
    return build_proof_review_turn(ProofLanguageReviewRequest(document=document))


def _walk_objects(value: object) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    if isinstance(value, dict):
        if value.get("type") == "object":
            objects.append(value)
        for child in value.values():
            objects.extend(_walk_objects(child))
    elif isinstance(value, list):
        for child in value:
            objects.extend(_walk_objects(child))
    return objects


def test_execution_fingerprint_covers_final_wire_validator_and_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = proof_review_request_envelope(_proof_turn(), "test-model")
    contract = execution_contract.build_provider_execution_contract(
        envelope,
        runtime=_runtime(),
    )

    assert contract.endpoint == "responses.create"
    assert contract.wire_request["model"] == "test-model"
    assert contract.wire_request["max_output_tokens"] == 4096
    assert contract.wire_request["store"] is False
    text = contract.wire_request["text"]
    assert isinstance(text, dict)
    response_format = text["format"]
    assert isinstance(response_format, dict)
    assert response_format["strict"] is True
    schema = response_format["schema"]
    assert isinstance(schema, dict)
    for object_schema in _walk_objects(schema):
        assert object_schema["additionalProperties"] is False
        properties = object_schema.get("properties")
        if isinstance(properties, dict):
            assert object_schema["required"] == list(properties)

    changed_wire = dict(contract.wire_request)
    changed_wire["store"] = True
    changed_contract = contract.model_copy(update={"wire_request": changed_wire})
    assert changed_contract.fingerprint() != contract.fingerprint()

    changed_runtime = execution_contract.build_provider_execution_contract(
        envelope,
        runtime=_runtime(lock="lock-b"),
    )
    assert changed_runtime.fingerprint() != contract.fingerprint()

    monkeypatch.setattr(
        execution_contract,
        "PROOF_REVIEW_VALIDATOR_CONTRACT",
        "thorn-proof-review-validator/test-change",
    )
    changed_validator = execution_contract.build_provider_execution_contract(
        envelope,
        runtime=_runtime(),
    )
    assert changed_validator.fingerprint() != contract.fingerprint()


class _FakeResponses:
    def __init__(self, outcomes: list[str | Exception]) -> None:
        self.outcomes = iter(outcomes)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            output_text=outcome,
            status="completed" if outcome else "incomplete",
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=3 if outcome else 0,
                total_tokens=14 if outcome else 11,
            ),
        )


class _FakeClient:
    def __init__(self, outcomes: list[str | Exception]) -> None:
        self.responses = _FakeResponses(outcomes)
        self.max_retries = 2


class _FakeHTTPError(RuntimeError):
    def __init__(self, message: str = "rate limited") -> None:
        super().__init__(message)
        self.status_code = 429
        self.request_id = "req_synthetic_146"
        self.body = {
            "error": {
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded",
                "param": "model",
                "message": message,
            }
        }
        self.response = SimpleNamespace(
            status_code=429,
            headers={"retry-after": "2", "x-request-id": self.request_id},
        )


def test_provider_dispatches_the_already_fingerprinted_wire_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = _unit()
    envelope = attack_request_envelope(unit, "test-model")
    contract = execution_contract.build_provider_execution_contract(
        envelope,
        runtime=_runtime(),
    )
    client = _FakeClient([AttackReport(findings=[]).model_dump_json()])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")
    monkeypatch.setattr(provider, "execution_contract", lambda _envelope: contract)

    assert provider.attack(unit) == AttackReport(findings=[])

    assert client.max_retries == 0
    assert client.responses.calls == [contract.provider_kwargs()]
    assert provider.last_execution_contract is contract
    assert provider.provider_attempts == 1
    assert provider.responses_received == 1
    assert provider.model_generations == 1


def test_transport_failure_is_counted_before_dispatch_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _FakeClient([_FakeHTTPError()])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")
    recorder = RecordingProvider(provider, tmp_path)

    with pytest.raises(ProviderTransportError) as caught:
        recorder.attack(_unit())

    evidence = caught.value.evidence
    assert evidence.status_code == 429
    assert evidence.request_id == "req_synthetic_146"
    assert evidence.error_type == "rate_limit_error"
    assert evidence.code == "rate_limit_exceeded"
    assert evidence.param == "model"
    assert evidence.retry_after == "2"
    assert provider.requests == provider.live_requests == provider.provider_attempts == 1
    assert provider.responses_received == provider.model_generations == 0
    assert provider.total_tokens == 0

    rejected = list((tmp_path / "rejected").glob("*/*.json"))
    assert len(rejected) == 1
    exchange = RecordedRejectedExchange.model_validate_json(
        rejected[0].read_text(encoding="utf-8")
    )
    assert exchange.execution_contract is not None
    assert exchange.usage.provider_attempts == 1
    assert exchange.usage.responses_received == 0
    assert exchange.usage.model_generations == 0
    assert exchange.rejection.kind == "transport_failure"
    assert exchange.rejection.transport == evidence


def test_transport_evidence_never_persists_arbitrary_exception_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secret = "sk-test-super-secret Authorization: Bearer top-secret"
    client = _FakeClient([_FakeHTTPError(secret)])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    recorder = RecordingProvider(openai_provider.OpenAIProvider(model="test-model"), tmp_path)

    with pytest.raises(ProviderTransportError) as caught:
        recorder.attack(_unit())

    serialized = caught.value.evidence.model_dump_json()
    assert "sk-test-super-secret" not in serialized
    assert "Bearer top-secret" not in serialized
    rejected = next((tmp_path / "rejected").glob("*/*.json"))
    assert "sk-test-super-secret" not in rejected.read_text(encoding="utf-8")
    assert "Bearer top-secret" not in rejected.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("output", "exception_type"),
    [
        ("", "MissingStructuredOutput"),
        ("{", "ValidationError"),
        ('{"findings":"not-a-list"}', "ValidationError"),
    ],
)
def test_received_invalid_structured_output_is_separate_from_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
    output: str,
    exception_type: str,
) -> None:
    client = _FakeClient([output])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")

    with pytest.raises(ProviderResponseValidationError) as caught:
        provider.attack(_unit())

    assert caught.value.validation_exception_type == exception_type
    assert provider.provider_attempts == 1
    assert provider.responses_received == 1
    assert provider.model_generations == (1 if output else 0)


def test_recording_provider_passes_and_records_exact_nondefault_proof_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    turn = _proof_turn()
    output = ProofReviewModelResponse(action="review").model_dump_json()
    client = _FakeClient([output])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(
        model="test-model",
        proof_review_max_output_tokens=256,
    )
    recorder = RecordingProvider(provider, tmp_path)

    response = recorder.review_proof_turn(turn)
    assert response.action == "review"
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0]["max_output_tokens"] == 256
    assert recorder.exact_replay_verifications == 1

    accepted = list(tmp_path.glob("*.json"))
    assert len(accepted) == 1
    exchange = RecordedExchange.model_validate_json(accepted[0].read_text(encoding="utf-8"))
    assert exchange.request.max_output_tokens == 256
    assert exchange.execution_contract is not None
    assert exchange.execution_contract.wire_request["max_output_tokens"] == 256
    assert provider.last_execution_contract is not None
    assert exchange.execution_contract == provider.last_execution_contract

    replay = ReplayProvider(
        model="test-model",
        directory=tmp_path,
        proof_review_max_output_tokens=256,
    )
    assert replay.review_proof_turn(turn) == response


def test_accepted_recording_is_immutable_and_conflicting_duplicate_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = AttackReport(findings=[]).model_dump_json()
    second = (
        '{"findings":[{"id":"F1","category":"other","severity":"warning",'
        '"title":"Synthetic","explanation":"Synthetic conflict.","evidence":[],'
        '"counterexample":null,"confidence":0.5}]}'
    )
    client = _FakeClient([first, second])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")
    recorder = RecordingProvider(provider, tmp_path)

    recorder.attack(_unit())
    accepted = list(tmp_path.glob("*.json"))
    assert len(accepted) == 1
    original_bytes = accepted[0].read_bytes()
    assert recorder.exact_replay_verifications == 1

    with pytest.raises(RecordingConflictError, match="conflicting evidence"):
        recorder.attack(_unit())

    assert accepted[0].read_bytes() == original_bytes
    conflicts = list((tmp_path / "conflicts").glob("*/*.json"))
    assert len(conflicts) == 1


def test_v2_replay_is_exact_and_runtime_change_invalidates_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _FakeClient([AttackReport(findings=[]).model_dump_json()])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")
    recorder = RecordingProvider(provider, tmp_path)
    recorder.attack(_unit())

    replay = ReplayProvider(model="test-model", directory=tmp_path)
    assert replay.attack(_unit()) == AttackReport(findings=[])
    assert replay.replay_hits == 1
    assert replay.legacy_replay_hits == 0
    assert replay.provider_attempts == 0

    from thorn.providers import replay as replay_module

    original_builder = replay_module.build_provider_execution_contract

    def changed_runtime(envelope: Any):
        return original_builder(envelope, runtime=_runtime(lock="changed-lock"))

    monkeypatch.setattr(replay_module, "build_provider_execution_contract", changed_runtime)
    stale_runtime_replay = ReplayProvider(model="test-model", directory=tmp_path)
    with pytest.raises(ReplayMissError, match="provider runtime lock"):
        stale_runtime_replay.attack(_unit())


def test_legacy_envelope_recording_remains_replayable_but_non_exact(tmp_path: Path) -> None:
    envelope = attack_request_envelope(_unit(), "test-model")
    legacy = RecordedExchange(
        format_version=1,
        fingerprint=envelope.fingerprint(),
        request=envelope,
        execution_contract=None,
        response=AttackReport(findings=[]).model_dump(mode="json"),
        usage=RecordedUsage(requests=1, input_tokens=7, output_tokens=2, total_tokens=9),
    )
    path = tmp_path / f"{envelope.fingerprint()}.json"
    path.write_text(legacy.model_dump_json(indent=2) + "\n", encoding="utf-8")

    replay = ReplayProvider(model="test-model", directory=tmp_path)
    assert replay.attack(_unit()) == AttackReport(findings=[])
    assert replay.replay_hits == 1
    assert replay.legacy_replay_hits == 1
    assert replay.recorded_total_tokens == 9
