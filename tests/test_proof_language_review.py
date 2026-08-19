from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.models import AttackReport
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewDisposition,
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    advertised_source_addresses,
    build_proof_review_turn,
    build_raw_review_turn,
    build_rescue_turn,
    review_proof_language,
)
from thorn.providers import openai as openai_provider
from thorn.providers.replay import RecordingProvider, ReplayMissError, ReplayProvider
from thorn.providers.request_envelope import (
    ProviderRequestEnvelope,
    proof_review_request_envelope,
)


def _document(*, suffix: str = "") -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:test",
        lines=(
            "THORN-PROOF 1",
            "T0 Q(a)",
            "C1 Q(a) <- ? @E1",
            "GOAL G0 T0: Q(a) | open @C1",
            suffix,
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
            ProofLanguageSourceHandle(
                address="R1",
                ir_identifier="result:R1",
                text="Lemma 4 has an unadvertised source payload.",
            ),
        ),
    )


class _Transport:
    def __init__(self, responses: list[ProofReviewModelResponse]) -> None:
        self.model = "test-model"
        self.responses = list(responses)
        self.calls = []
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def review_proof_turn(self, request):
        self.calls.append(request)
        self.requests += 1
        self.live_requests += 1
        return self.responses.pop(0)


class _FakeResponses:
    def __init__(self, response: ProofReviewModelResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self.response,
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=self.response.model_dump_json(),
            status="completed",
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )


class _FakeClient:
    def __init__(self, response: ProofReviewModelResponse) -> None:
        self.responses = _FakeResponses(response)


def _review() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(action="review")


def _need(*addresses: str) -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=addresses,
        review_items=(
            ProofReviewItem(
                id="RV1",
                kind="question",
                summary="Does the exact source settle the unresolved proof step?",
            ),
        ),
        source_review_item_ids=("RV1",),
    )


def _rescue_review() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="review",
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="discharged",
                explanation="The exact source settles the review question.",
            ),
        ),
    )


def test_deterministic_proof_review_request_and_envelope_contains_packet() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    first = build_proof_review_turn(request)
    second = build_proof_review_turn(request.model_copy(deep=True))

    assert first == second
    assert first.initial_packet_fingerprint == request.document.fingerprint()

    envelope = proof_review_request_envelope(first, "test-model")
    assert envelope.kind == "proof_review"
    assert envelope.representation == "thorn-proof/1"
    assert "THORN-PROOF 1" in envelope.user_content
    duplicate = proof_review_request_envelope(first, "test-model")
    assert envelope.fingerprint() == duplicate.fingerprint()


def test_proof_review_fingerprint_is_distinct_from_raw_and_legacy() -> None:
    proof = proof_review_request_envelope(
        build_proof_review_turn(ProofLanguageReviewRequest(document=_document())),
        "test-model",
    )
    raw_turn = build_raw_review_turn("# Result\nID: thm:test\n")
    raw = proof_review_request_envelope(raw_turn, "test-model")
    legacy = ProviderRequestEnvelope(
        kind="semantic",
        model="test-model",
        system_prompt=proof.system_prompt,
        user_content=proof.user_content,
        response_schema=AttackReport.model_json_schema(),
    )

    assert len({proof.fingerprint(), raw.fingerprint(), legacy.fingerprint()}) == 3
    assert '"protocol_version"' not in legacy.canonical_json()


def test_structured_review_completes_without_rescue() -> None:
    transport = _Transport([_review()])
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        transport,
    )

    assert report == AttackReport()
    assert len(transport.calls) == 1
    assert transport.calls[0].stage == "initial"


def test_valid_need_source_returns_only_exact_advertised_addresses() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    initial = build_proof_review_turn(request)
    rescue = build_rescue_turn(request, initial, _need("E1"))

    assert advertised_source_addresses(request.document) == ("C1", "E1")
    assert rescue.requested_source_addresses == ("E1",)
    assert "SOURCE @E1\nBy Lemma 4, Q(a).\nEND_SOURCE @E1" in rescue.user_content
    assert "SOURCE @C1" not in rescue.user_content
    assert "R1" not in rescue.user_content
    assert rescue.initial_packet_fingerprint == request.document.fingerprint()
    assert rescue.prior_response == _need("E1")


@pytest.mark.parametrize(
    ("addresses", "match"),
    [
        (("R1",), "not advertised"),
        (("Z99",), "not advertised"),
    ],
)
def test_rescue_rejects_unknown_or_unadvertised_source(
    addresses: tuple[str, ...],
    match: str,
) -> None:
    request = ProofLanguageReviewRequest(document=_document())
    with pytest.raises(ProofReviewProtocolError, match=match):
        build_rescue_turn(request, build_proof_review_turn(request), _need(*addresses))


def test_rescue_rejects_over_limit_and_is_exactly_one_round() -> None:
    request = ProofLanguageReviewRequest(document=_document(), max_source_addresses=1)
    initial = build_proof_review_turn(request)
    with pytest.raises(ProofReviewProtocolError, match="at most 1"):
        build_rescue_turn(request, initial, _need("E1", "C1"))

    transport = _Transport([_need("E1"), _need("C1")])
    with pytest.raises(ProofReviewProtocolError, match="second source-rescue"):
        review_proof_language(
            ProofLanguageReviewRequest(document=_document()),
            transport,
        )
    assert len(transport.calls) == 2
    assert transport.calls[1].source_rescue_allowed is False


def test_structured_source_request_rejects_malformed_addresses() -> None:
    with pytest.raises(ValidationError):
        ProofReviewModelResponse(
            action="need_source",
            source_addresses=("../paper.tex",),
            review_items=(
                ProofReviewItem(
                    id="RV1",
                    kind="question",
                    summary="Question requiring exact source.",
                ),
            ),
            source_review_item_ids=("RV1",),
        )
    with pytest.raises(ValidationError):
        ProofReviewModelResponse(action="need_source")


def test_rescue_fingerprint_changes_when_exact_returned_source_changes() -> None:
    first_document = _document()
    changed_sources = tuple(
        source.model_copy(
            update={"text": "Different exact source."}
            if source.address == "E1"
            else {}
        )
        for source in first_document.sources
    )
    second_document = first_document.model_copy(update={"sources": changed_sources})
    assert first_document.fingerprint() == second_document.fingerprint()

    source_request = _need("E1")
    first_request = ProofLanguageReviewRequest(document=first_document)
    second_request = ProofLanguageReviewRequest(document=second_document)
    first_rescue = build_rescue_turn(
        first_request,
        build_proof_review_turn(first_request),
        source_request,
    )
    second_rescue = build_rescue_turn(
        second_request,
        build_proof_review_turn(second_request),
        source_request,
    )
    first_envelope = proof_review_request_envelope(first_rescue, "test-model")
    second_envelope = proof_review_request_envelope(second_rescue, "test-model")

    assert first_envelope.fingerprint() != second_envelope.fingerprint()


def test_rescue_is_tied_to_exact_initial_packet_fingerprint() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    changed = ProofLanguageReviewRequest(document=_document(suffix="EXTRA"))
    initial = build_proof_review_turn(request)

    with pytest.raises(ProofReviewProtocolError, match="does not match"):
        build_rescue_turn(changed, initial, _need("E1"))


def test_proof_review_record_replay_covers_initial_and_rescue(tmp_path: Path) -> None:
    request = ProofLanguageReviewRequest(document=_document())
    delegate = _Transport([_need("E1"), _rescue_review()])
    recorder = RecordingProvider(delegate, tmp_path)

    assert review_proof_language(request, recorder) == AttackReport()
    recordings = sorted(tmp_path.glob("*.json"))
    assert len(recordings) == 2

    replay = ReplayProvider("test-model", tmp_path)
    assert review_proof_language(request, replay) == AttackReport()
    assert replay.requests == 2
    assert replay.replay_hits == 2
    assert replay.live_requests == 0


def test_changed_proof_packet_misses_replay_loudly(tmp_path: Path) -> None:
    request = ProofLanguageReviewRequest(document=_document())
    recorder = RecordingProvider(_Transport([_review()]), tmp_path)
    review_proof_language(request, recorder)

    replay = ReplayProvider("test-model", tmp_path)
    changed = ProofLanguageReviewRequest(document=_document(suffix="CHANGED"))
    with pytest.raises(ReplayMissError):
        review_proof_language(changed, replay)


def test_proof_ir_only_rejects_source_request() -> None:
    transport = _Transport([_need("E1")])
    with pytest.raises(ProofReviewProtocolError, match="source rescue is disabled"):
        review_proof_language(
            ProofLanguageReviewRequest(
                document=_document(),
                allow_source_rescue=False,
            ),
            transport,
        )
    assert len(transport.calls) == 1


def test_rescue_fingerprint_changes_with_requested_addresses() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    initial = build_proof_review_turn(request)
    first = proof_review_request_envelope(
        build_rescue_turn(request, initial, _need("E1")),
        "test-model",
    )
    second = proof_review_request_envelope(
        build_rescue_turn(request, initial, _need("C1")),
        "test-model",
    )

    assert first.fingerprint() != second.fingerprint()
    assert first.requested_source_addresses == ("E1",)
    assert second.requested_source_addresses == ("C1",)


def test_openai_provider_transports_exact_proof_review_envelope_keylessly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient(_review())
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=_document()))

    response = provider.review_proof_turn(turn)

    assert response == _review()
    assert provider.requests == 1
    assert provider.live_requests == 1
    assert provider.input_tokens == 11
    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == "test-model"
    text = call["text"]
    assert isinstance(text, dict)
    text_format = text["format"]
    assert isinstance(text_format, dict)
    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True
    schema = text_format["schema"]
    assert isinstance(schema, dict)
    assert schema["type"] == "object"
    assert "anyOf" not in schema
    assert schema["additionalProperties"] is False
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert schema["required"] == list(properties)
    messages = call["input"]
    assert isinstance(messages, list)
    assert "THORN-PROOF 1" in messages[1]["content"]
    assert "SOURCE_RESCUE allowed-once" in messages[1]["content"]
