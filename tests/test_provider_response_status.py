from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from thorn.models import AttackReport, SourceRange, TheoremUnit
from thorn.providers import openai as openai_provider
from thorn.providers.base import ProviderResponseValidationError
from thorn.providers.replay import RecordedRejectedExchange, RecordingProvider


class _Responses:
    def __init__(self, response: object) -> None:
        self.response = response

    def create(self, **kwargs: object) -> object:
        return self.response


class _Client:
    def __init__(self, response: object) -> None:
        self.responses = _Responses(response)
        self.max_retries = 2


def _unit() -> TheoremUnit:
    return TheoremUnit(
        identifier="thm:status",
        environment="theorem",
        statement="Synthetic status theorem.",
        proof="Synthetic proof.",
        statement_range=SourceRange(file="synthetic.tex", start_line=1, end_line=1),
    )


def test_incomplete_valid_json_is_quarantined_with_safe_status_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = SimpleNamespace(
        id="resp_incomplete",
        status="incomplete",
        output_text=AttackReport(findings=[]).model_dump_json(),
        error=SimpleNamespace(
            type="server_error",
            code="transient",
            message="Authorization: Bearer secret-must-not-persist",
        ),
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        usage=SimpleNamespace(input_tokens=12, output_tokens=4, total_tokens=16),
    )
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: _Client(response))
    recorder = RecordingProvider(
        openai_provider.OpenAIProvider(model="test-model"),
        tmp_path,
    )

    with pytest.raises(ProviderResponseValidationError) as captured:
        recorder.attack(_unit())

    assert captured.value.validation_exception_type == "ProviderResponseNotCompleted"
    assert not list(tmp_path.glob("*.json"))
    rejected_path = next((tmp_path / "rejected").glob("*/*.json"))
    serialized = rejected_path.read_text(encoding="utf-8")
    assert "secret-must-not-persist" not in serialized

    rejected = RecordedRejectedExchange.model_validate_json(serialized)
    assert rejected.rejection.kind == "response_validation"
    assert rejected.response is not None
    assert rejected.response["status"] == "incomplete"
    assert rejected.response["id"] == "resp_incomplete"
    assert rejected.response["error"] == {
        "type": "server_error",
        "code": "transient",
    }
    assert rejected.response["incomplete_details"] == {"reason": "max_output_tokens"}
    assert rejected.usage.responses_received == 1
    assert rejected.usage.model_generations == 1
    assert rejected.usage.input_tokens == 12
    assert rejected.usage.output_tokens == 4
    assert rejected.usage.total_tokens == 16
