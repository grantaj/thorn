from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.models import CandidateFinding, FindingCategory, Severity
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewDisposition,
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTurnRequest,
    build_proof_review_turn,
    build_rescue_turn,
    review_proof_language,
    validate_proof_review_response,
)
from thorn.providers import openai as openai_provider
from thorn.providers.openai import OpenAIProvider
from thorn.providers.replay import (
    ForensicReplayProvider,
    RecordedRejectedExchange,
    RecordingProvider,
    ReplayAmbiguousError,
    ReplayError,
    ReplayMissError,
    ReplayProvider,
    ReplayStaleError,
)
from thorn.providers.request_envelope import proof_review_request_envelope


def _document(*, marker: str = "") -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:test",
        lines=(
            "THORN-PROOF 1",
            "T0 Q(a)",
            "C1 Q(a) <- ? @E1",
            f"GOAL G0 T0: Q(a) | open @C1{marker}",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="E1",
                ir_identifier="edge:E1",
                text="By Lemma 4, Q(a).",
            ),
            ProofLanguageSourceHandle(
                address="C1",
                ir_identifier="claim:C1",
                text="Therefore Q(a).",
            ),
        ),
    )


def _finding(finding_id: str) -> CandidateFinding:
    return CandidateFinding(
        id=finding_id,
        category=FindingCategory.UNSUPPORTED_CLAIM,
        severity=Severity.ERROR,
        title=f"Finding {finding_id}",
        explanation=f"Explanation for {finding_id}.",
        confidence=0.9,
    )


def _need() -> ProofReviewModelResponse:
    item = ProofReviewItem(
        id="RV1",
        kind="concern",
        summary="Carried concern.",
    )
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=("E1",),
        review_items=(item,),
        source_review_item_ids=(item.id,),
    )


def _turns(*, marker: str = "") -> tuple[
    ProofLanguageReviewRequest,
    ProofReviewTurnRequest,
    ProofReviewTurnRequest,
]:
    request = ProofLanguageReviewRequest(document=_document(marker=marker))
    initial = build_proof_review_turn(request)
    rescue = build_rescue_turn(request, initial, _need())
    return request, initial, rescue


def _conflicting_response(
    *,
    explanation: str = "Conflicting explanation.",
) -> ProofReviewModelResponse:
    carried = _finding("F1")
    conflicting = carried.model_copy(update={"explanation": explanation})
    return ProofReviewModelResponse(
        action="review",
        findings=(conflicting,),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="The carried concern is confirmed.",
                finding=carried,
            ),
        ),
    )


class _Transport:
    model = "test-model"

    def __init__(self, responses: list[ProofReviewModelResponse | Exception]) -> None:
        self.responses = list(responses)
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.client_secret = "sk-delegate-secret"

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse:
        del request
        self.requests += 1
        self.live_requests += 1
        self.input_tokens += 10
        self.output_tokens += 2
        self.total_tokens += 12
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeResponses:
    def __init__(self, output: ProofReviewModelResponse) -> None:
        self.output = output

    def parse(self, **kwargs: object) -> SimpleNamespace:
        del kwargs
        return SimpleNamespace(
            output_parsed=self.output,
            usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
        )


class _FakeClient:
    def __init__(self, output: ProofReviewModelResponse) -> None:
        self.responses = _FakeResponses(output)
        self.max_retries = 0


def _rejected_paths(directory: Path, request: ProofReviewTurnRequest) -> list[Path]:
    fingerprint = proof_review_request_envelope(request, "test-model").fingerprint()
    return sorted((directory / "rejected" / fingerprint).glob("*.json"))


def test_openai_proof_review_provider_returns_schema_valid_protocol_rejection_to_thorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, rescue = _turns()
    invalid = _conflicting_response()
    schema_valid = rescue.response_model().model_validate(invalid.model_dump(mode="python"))
    client = _FakeClient(schema_valid)
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)

    provider = OpenAIProvider(model="test-model")
    returned = provider.review_proof_turn(rescue)

    assert returned.model_dump(mode="json") == schema_valid.model_dump(mode="json")
    assert provider.requests == provider.live_requests == 1
    with pytest.raises(
        ProofReviewProtocolError,
        match="reuses finding identity across rescue accounting: F1",
    ):
        validate_proof_review_response(rescue, returned)


def test_protocol_rejection_is_quarantined_and_forensic_replay_reproduces_it(
    tmp_path: Path,
) -> None:
    request, _, rescue = _turns()
    invalid = _conflicting_response()
    recorder = RecordingProvider(_Transport([_need(), invalid]), tmp_path)

    with pytest.raises(
        ProofReviewProtocolError,
        match="reuses finding identity across rescue accounting: F1",
    ):
        review_proof_language(request, recorder)

    accepted = list(tmp_path.glob("*.json"))
    rejected = _rejected_paths(tmp_path, rescue)
    assert len(accepted) == 1
    assert len(rejected) == 1

    exchange = RecordedRejectedExchange.model_validate_json(
        rejected[0].read_text(encoding="utf-8")
    )
    assert exchange.fingerprint == exchange.request.fingerprint()
    assert exchange.response == invalid.model_dump(mode="json")
    assert exchange.usage.requests == 1
    assert exchange.usage.total_tokens == 12
    assert exchange.rejection.kind == "proof_review_protocol"
    assert exchange.rejection.validator_replayable is True
    assert exchange.rejection.message == (
        "final response reuses finding identity across rescue accounting: F1"
    )

    normal = ReplayProvider("test-model", tmp_path)
    with pytest.raises(ReplayMissError):
        review_proof_language(request, normal)
    assert normal.live_requests == 0
    assert normal.replay_hits == 1

    forensic = ForensicReplayProvider("test-model", tmp_path)
    with pytest.raises(
        ProofReviewProtocolError,
        match="reuses finding identity across rescue accounting: F1",
    ):
        review_proof_language(request, forensic)
    assert forensic.live_requests == 0
    assert forensic.replay_hits == 1
    assert forensic.forensic_hits == 1


def test_multiple_rejected_responses_coexist_and_require_explicit_selection(
    tmp_path: Path,
) -> None:
    _, _, rescue = _turns()
    first = _conflicting_response(explanation="First conflicting explanation.")
    second = _conflicting_response(explanation="Second conflicting explanation.")
    recorder = RecordingProvider(_Transport([first, second, first]), tmp_path)

    for expected in ("F1", "F1", "F1"):
        with pytest.raises(ProofReviewProtocolError, match=expected):
            recorder.review_proof_turn(rescue)

    rejected = _rejected_paths(tmp_path, rescue)
    assert len(rejected) == 2

    ambiguous = ForensicReplayProvider("test-model", tmp_path)
    with pytest.raises(ReplayAmbiguousError, match="multiple quarantined responses"):
        ambiguous.review_proof_turn(rescue)

    request_fingerprint = proof_review_request_envelope(rescue, "test-model").fingerprint()
    for path in rejected:
        selected = ForensicReplayProvider(
            "test-model",
            tmp_path,
            rejected_response_fingerprints={request_fingerprint: path.stem},
        )
        with pytest.raises(
            ProofReviewProtocolError,
            match="reuses finding identity across rescue accounting: F1",
        ):
            selected.review_proof_turn(rescue)
        assert selected.forensic_hits == 1
        assert selected.replay_hits == 0
        assert selected.live_requests == 0


def test_forensic_replay_rejects_request_drift_and_tampered_evidence(tmp_path: Path) -> None:
    _, _, rescue = _turns()
    recorder = RecordingProvider(_Transport([_conflicting_response()]), tmp_path)
    with pytest.raises(ProofReviewProtocolError):
        recorder.review_proof_turn(rescue)

    _, _, drifted_rescue = _turns(marker=" changed")
    drifted = ForensicReplayProvider("test-model", tmp_path)
    with pytest.raises(ReplayMissError, match="no quarantined recording"):
        drifted.review_proof_turn(drifted_rescue)

    path = _rejected_paths(tmp_path, rescue)[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["request"]["user_content"] += "\nTAMPERED"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    stale = ForensicReplayProvider("test-model", tmp_path)
    with pytest.raises(ReplayStaleError, match="request payload does not match"):
        stale.review_proof_turn(rescue)


def test_forensic_replay_rejects_tampered_rejected_response_content(tmp_path: Path) -> None:
    _, _, rescue = _turns()
    recorder = RecordingProvider(_Transport([_conflicting_response()]), tmp_path)
    with pytest.raises(ProofReviewProtocolError):
        recorder.review_proof_turn(rescue)

    path = _rejected_paths(tmp_path, rescue)[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["response"]["findings"][0]["explanation"] = "Tampered."
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    forensic = ForensicReplayProvider("test-model", tmp_path)
    with pytest.raises(ReplayStaleError, match="content fingerprint does not match"):
        forensic.review_proof_turn(rescue)


def test_unstructured_provider_failure_is_safely_quarantined_without_secret_leak(
    tmp_path: Path,
) -> None:
    _, initial, _ = _turns()
    secret = "sk-super-secret-authorization-token"
    failure = RuntimeError(f"Authorization: Bearer {secret}")
    recorder = RecordingProvider(_Transport([failure]), tmp_path)

    with pytest.raises(RuntimeError, match="Authorization"):
        recorder.review_proof_turn(initial)

    rejected = _rejected_paths(tmp_path, initial)
    assert len(rejected) == 1
    text = rejected[0].read_text(encoding="utf-8")
    assert secret not in text
    assert "Authorization" not in text
    assert "Bearer" not in text
    assert "sk-delegate-secret" not in text

    exchange = RecordedRejectedExchange.model_validate_json(text)
    assert exchange.response is None
    assert exchange.rejection.kind == "provider_failure"
    assert exchange.rejection.validator_replayable is False
    assert exchange.rejection.exception_type == "RuntimeError"
    assert exchange.rejection.message == (
        "provider did not return a structured proof-review response"
    )

    forensic = ForensicReplayProvider("test-model", tmp_path)
    with pytest.raises(ReplayError, match="not validator-replayable"):
        forensic.review_proof_turn(initial)
    assert forensic.live_requests == 0
    assert forensic.replay_hits == 0
    assert forensic.forensic_hits == 0


def test_accepted_recording_does_not_serialize_delegate_secrets(tmp_path: Path) -> None:
    _, initial, _ = _turns()
    response = ProofReviewModelResponse(action="review")
    recorder = RecordingProvider(_Transport([response]), tmp_path)

    assert recorder.review_proof_turn(initial) == response

    accepted = list(tmp_path.glob("*.json"))
    assert len(accepted) == 1
    text = accepted[0].read_text(encoding="utf-8")
    assert "sk-delegate-secret" not in text
    assert not (tmp_path / "rejected").exists()
