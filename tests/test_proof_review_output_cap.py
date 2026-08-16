from __future__ import annotations

from types import SimpleNamespace

import pytest

from thorn.llm_proof_language import LLMProofLanguage
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    build_proof_review_turn,
)
from thorn.providers import openai as openai_provider
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    proof_review_request_envelope,
)


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=ProofReviewModelResponse(action="review"),
            usage=SimpleNamespace(input_tokens=11, output_tokens=3, total_tokens=14),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def _turn():
    document = LLMProofLanguage(
        result_identifier="thm:test",
        lines=("THORN-PROOF 1", "T0 Q(a)", "GOAL G0 T0: Q(a)"),
    )
    return build_proof_review_turn(ProofLanguageReviewRequest(document=document))


def test_proof_review_output_cap_is_fingerprinted() -> None:
    envelope = proof_review_request_envelope(_turn(), "test-model")

    assert envelope.max_output_tokens == PROOF_REVIEW_MAX_OUTPUT_TOKENS == 4096
    changed = envelope.model_copy(update={"max_output_tokens": 2048})
    assert changed.fingerprint() != envelope.fingerprint()


def test_openai_proof_review_transport_enforces_output_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient()
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")

    provider.review_proof_turn(_turn())

    assert len(client.responses.calls) == 1
    assert (
        client.responses.calls[0]["max_output_tokens"]
        == PROOF_REVIEW_MAX_OUTPUT_TOKENS
    )
