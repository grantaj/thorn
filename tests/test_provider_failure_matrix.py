from __future__ import annotations

from types import SimpleNamespace

import pytest

from thorn.models import SourceRange, TheoremUnit
from thorn.providers import openai as openai_provider
from thorn.providers.base import ProviderTransportError


class _HTTPFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_type: str,
        code: str,
        request_id: str,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id
        self.body = {
            "error": {
                "type": error_type,
                "code": code,
                "message": message,
            }
        }
        headers = {"x-request-id": request_id}
        if retry_after is not None:
            headers["retry-after"] = retry_after
        self.response = SimpleNamespace(status_code=status_code, headers=headers)


class _FailingResponses:
    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.calls = 0

    def create(self, **kwargs: object) -> object:
        self.calls += 1
        raise self.failure


class _FailingClient:
    def __init__(self, failure: Exception) -> None:
        self.responses = _FailingResponses(failure)
        self.max_retries = 2


def _unit() -> TheoremUnit:
    return TheoremUnit(
        identifier="thm:failure-matrix",
        environment="theorem",
        statement="Synthetic provider failure test.",
        proof="Synthetic proof.",
        statement_range=SourceRange(file="synthetic.tex", start_line=1, end_line=1),
    )


@pytest.mark.parametrize(
    ("failure", "status", "error_type", "code", "retry_after"),
    [
        (
            _HTTPFailure(
                "schema rejected",
                status_code=400,
                error_type="invalid_request_error",
                code="invalid_json_schema",
                request_id="req_schema",
            ),
            400,
            "invalid_request_error",
            "invalid_json_schema",
            None,
        ),
        (
            _HTTPFailure(
                "unauthorized",
                status_code=401,
                error_type="authentication_error",
                code="invalid_api_key",
                request_id="req_auth",
            ),
            401,
            "authentication_error",
            "invalid_api_key",
            None,
        ),
        (
            _HTTPFailure(
                "rate limited",
                status_code=429,
                error_type="rate_limit_error",
                code="rate_limit_exceeded",
                request_id="req_rate",
                retry_after="3",
            ),
            429,
            "rate_limit_error",
            "rate_limit_exceeded",
            "3",
        ),
        (
            _HTTPFailure(
                "provider unavailable",
                status_code=503,
                error_type="server_error",
                code="service_unavailable",
                request_id="req_5xx",
            ),
            503,
            "server_error",
            "service_unavailable",
            None,
        ),
        (ConnectionError("network down"), None, None, None, None),
        (TimeoutError("provider timeout"), None, None, None, None),
    ],
)
def test_transport_failure_matrix_counts_attempt_before_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int | None,
    error_type: str | None,
    code: str | None,
    retry_after: str | None,
) -> None:
    client = _FailingClient(failure)
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="test-model")

    with pytest.raises(ProviderTransportError) as caught:
        provider.attack(_unit())

    evidence = caught.value.evidence
    assert evidence.status_code == status
    assert evidence.error_type == error_type
    assert evidence.code == code
    assert evidence.retry_after == retry_after
    assert provider.requests == 1
    assert provider.live_requests == 1
    assert provider.provider_attempts == 1
    assert provider.responses_received == 0
    assert provider.model_generations == 0
    assert provider.input_tokens == 0
    assert provider.output_tokens == 0
    assert provider.total_tokens == 0
    assert client.max_retries == 0
    assert client.responses.calls == 1
