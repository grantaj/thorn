from __future__ import annotations

import copy
import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pydantic import BaseModel, ConfigDict

from thorn.providers.request_envelope import ProviderRequestEnvelope, RequestKind

EXECUTION_CONTRACT_VERSION = "thorn-provider-execution/2"
PROOF_REVIEW_VALIDATOR_CONTRACT = "thorn-proof-review-validator/2"
LOCAL_STRUCTURED_VALIDATOR_CONTRACT = "thorn-local-structured-validator/1"


class ProviderRuntimeIdentity(BaseModel):
    """Provider-sensitive runtime versions that can change transport semantics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    python: str
    openai: str
    pydantic: str
    pydantic_core: str
    execution_contract: str = EXECUTION_CONTRACT_VERSION


class ProviderExecutionContract(BaseModel):
    """Canonical identity of exactly one provider execution.

    ``wire_request`` is the complete kwargs object passed to ``responses.create``.
    Thorn performs no provider-significant transformation after this object is
    fingerprinted. Acceptance semantics and provider-sensitive runtime versions are
    deliberately part of the execution identity even though they are not sent over
    the wire.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: int = 2
    provider: str = "openai"
    endpoint: str = "responses.create"
    kind: RequestKind
    wire_request: dict[str, Any]
    acceptance_contract: str
    runtime: ProviderRuntimeIdentity
    semantic_envelope_sha256: str

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def provider_kwargs(self) -> dict[str, Any]:
        """Return an exact copy of the already-canonical provider kwargs."""

        return copy.deepcopy(self.wire_request)


def _installed_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not-installed"


def current_provider_runtime() -> ProviderRuntimeIdentity:
    return ProviderRuntimeIdentity(
        python=platform.python_version(),
        openai=_installed_version("openai"),
        pydantic=_installed_version("pydantic"),
        pydantic_core=_installed_version("pydantic-core"),
    )


def strict_json_schema(schema: dict[str, object]) -> dict[str, object]:
    """Return Thorn's final strict Structured Outputs schema.

    This is provider construction, not an SDK-side helper. The returned schema is
    embedded into the execution contract before fingerprinting and recording.
    """

    strict = copy.deepcopy(schema)

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                value["additionalProperties"] = False
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


def _schema_name(envelope: ProviderRequestEnvelope) -> str:
    title = envelope.response_schema.get("title")
    if isinstance(title, str) and title:
        return title
    return {
        "attack": "AttackReport",
        "semantic": "AttackReport",
        "defend": "DefenseReport",
        "proof_review": "ProofReviewModelResponse",
    }[envelope.kind]


def _acceptance_contract(envelope: ProviderRequestEnvelope) -> str:
    if envelope.kind == "proof_review":
        protocol = envelope.protocol_version or "missing-protocol-version"
        return f"{protocol}:{PROOF_REVIEW_VALIDATOR_CONTRACT}"
    return f"{envelope.kind}:{LOCAL_STRUCTURED_VALIDATOR_CONTRACT}"


def build_provider_execution_contract(
    envelope: ProviderRequestEnvelope,
    *,
    runtime: ProviderRuntimeIdentity | None = None,
) -> ProviderExecutionContract:
    """Build the final provider request before validation, identity, or dispatch."""

    wire_request: dict[str, Any] = {
        "model": envelope.model,
        "input": envelope.input_messages(),
        "text": {
            "format": {
                "type": "json_schema",
                "name": _schema_name(envelope),
                "schema": strict_json_schema(envelope.response_schema),
                "strict": True,
            }
        },
        "store": False,
    }
    if envelope.max_output_tokens is not None:
        wire_request["max_output_tokens"] = envelope.max_output_tokens

    semantic_envelope_sha256 = hashlib.sha256(
        envelope.canonical_json().encode("utf-8")
    ).hexdigest()
    return ProviderExecutionContract(
        kind=envelope.kind,
        wire_request=wire_request,
        acceptance_contract=_acceptance_contract(envelope),
        runtime=runtime or current_provider_runtime(),
        semantic_envelope_sha256=semantic_envelope_sha256,
    )
