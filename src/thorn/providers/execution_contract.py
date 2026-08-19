from __future__ import annotations

import copy
import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from thorn.providers.request_envelope import ProviderRequestEnvelope, RequestKind

EXECUTION_CONTRACT_VERSION = "thorn-provider-execution/2"
PROOF_REVIEW_VALIDATOR_CONTRACT = "thorn-proof-review-validator/2"
LOCAL_STRUCTURED_VALIDATOR_CONTRACT = "thorn-local-structured-validator/1"

_PROVIDER_LOCK_PATH = Path(__file__).resolve().parents[3] / "constraints" / "provider-runtime.txt"
_PROVIDER_ADAPTER_PATHS = (
    Path(__file__),
    Path(__file__).with_name("openai.py"),
    Path(__file__).with_name("request_envelope.py"),
    Path(__file__).resolve().parents[1] / "proof_language_review.py",
)


class ProviderRuntimeIdentity(BaseModel):
    """Closed provider runtime identity derived from the committed lock."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    python: str
    provider_lock_sha256: str
    locked_packages: dict[str, str]
    execution_contract: str = EXECUTION_CONTRACT_VERSION


class ProviderTransportProfile(BaseModel):
    """Provider-visible transport/schema shape with payload literals erased.

    A readiness profile can cover a scientific profile when the transport family and
    normalized schema structure are identical and the readiness probe exercised at
    least as large a literal-set/array cardinality. ``const`` and ``enum`` are
    normalized as one literal-set feature because they express the same provider
    schema capability; cardinality remains an independent monotone coverage bound.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    endpoint: str
    kind: RequestKind
    message_roles: tuple[str, ...]
    schema_shape_sha256: str
    max_enum_items: int
    max_array_bound: int

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def covers(self, other: ProviderTransportProfile) -> bool:
        return (
            self.provider == other.provider
            and self.endpoint == other.endpoint
            and self.kind == other.kind
            and self.message_roles == other.message_roles
            and self.schema_shape_sha256 == other.schema_shape_sha256
            and self.max_enum_items >= other.max_enum_items
            and self.max_array_bound >= other.max_array_bound
        )


class ProviderExecutionContract(BaseModel):
    """Canonical identity of exactly one provider execution.

    ``wire_request`` is the complete kwargs object passed to ``responses.create``.
    Thorn performs no provider-significant transformation after this object is
    fingerprinted. Acceptance semantics and the closed provider runtime are part of
    execution identity even though they are not sent over the wire.
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

    def transport_profile(self) -> ProviderTransportProfile:
        return provider_transport_profile(self)


def _installed_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not-installed"


def _lock_entries() -> tuple[tuple[str, str], ...]:
    if not _PROVIDER_LOCK_PATH.exists():
        return ()
    entries: list[tuple[str, str]] = []
    for raw_line in _PROVIDER_LOCK_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "==" not in line:
            raise RuntimeError(
                "provider runtime lock must contain only exact name==version pins"
            )
        name, pinned = line.split("==", 1)
        entries.append((name.strip(), pinned.strip()))
    return tuple(entries)


def provider_lock_sha256() -> str:
    if not _PROVIDER_LOCK_PATH.exists():
        return "missing-provider-runtime-lock"
    return hashlib.sha256(_PROVIDER_LOCK_PATH.read_bytes()).hexdigest()


def provider_adapter_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted(_PROVIDER_ADAPTER_PATHS, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def current_provider_runtime() -> ProviderRuntimeIdentity:
    entries = _lock_entries()
    return ProviderRuntimeIdentity(
        python=platform.python_version(),
        provider_lock_sha256=provider_lock_sha256(),
        locked_packages={name: _installed_version(name) for name, _ in entries},
    )


def provider_runtime_matches_lock(runtime: ProviderRuntimeIdentity | None = None) -> bool:
    runtime = runtime or current_provider_runtime()
    expected = dict(_lock_entries())
    return (
        bool(expected)
        and runtime.provider_lock_sha256 == provider_lock_sha256()
        and runtime.locked_packages == expected
    )


def strict_json_schema(schema: dict[str, object]) -> dict[str, object]:
    """Return Thorn's final strict Structured Outputs schema."""

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


def _literal_types(values: list[object]) -> list[str]:
    return sorted({type(value).__name__ for value in values})


def _schema_profile_value(value: object, *, key: str | None = None) -> object:
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        enum = value.get("enum")
        if isinstance(enum, list):
            normalized["literalSet"] = {"types": _literal_types(enum)}
        elif "const" in value:
            normalized["literalSet"] = {"types": [type(value["const"]).__name__]}

        for child_key in sorted(value):
            if child_key in {
                "title",
                "description",
                "default",
                "examples",
                "enum",
                "const",
            }:
                continue
            normalized[child_key] = _schema_profile_value(
                value[child_key],
                key=child_key,
            )
        return normalized
    if isinstance(value, list):
        return [_schema_profile_value(item, key=key) for item in value]
    if isinstance(value, int) and key in {"minItems", "maxItems"}:
        return "<array-bound>"
    return value


def _schema_cardinalities(value: object) -> tuple[int, int]:
    max_enum = 0
    max_array = 0
    if isinstance(value, dict):
        enum = value.get("enum")
        if isinstance(enum, list):
            max_enum = len(enum)
        elif "const" in value:
            max_enum = 1
        for name in ("minItems", "maxItems"):
            bound = value.get(name)
            if isinstance(bound, int):
                max_array = max(max_array, bound)
        for child in value.values():
            child_enum, child_array = _schema_cardinalities(child)
            max_enum = max(max_enum, child_enum)
            max_array = max(max_array, child_array)
    elif isinstance(value, list):
        for child in value:
            child_enum, child_array = _schema_cardinalities(child)
            max_enum = max(max_enum, child_enum)
            max_array = max(max_array, child_array)
    return max_enum, max_array


def provider_transport_profile(contract: ProviderExecutionContract) -> ProviderTransportProfile:
    input_payload = contract.wire_request.get("input")
    roles: list[str] = []
    if isinstance(input_payload, list):
        for message in input_payload:
            if isinstance(message, dict):
                role = message.get("role")
                roles.append(str(role) if role is not None else "<missing>")
            else:
                roles.append("<non-object>")

    text = contract.wire_request.get("text")
    response_format: object = None
    if isinstance(text, dict):
        response_format = text.get("format")
    schema: object = None
    if isinstance(response_format, dict):
        schema = response_format.get("schema")
    normalized_schema = _schema_profile_value(schema)
    schema_shape_sha256 = hashlib.sha256(
        json.dumps(
            normalized_schema,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    max_enum_items, max_array_bound = _schema_cardinalities(schema)
    return ProviderTransportProfile(
        provider=contract.provider,
        endpoint=contract.endpoint,
        kind=contract.kind,
        message_roles=tuple(roles),
        schema_shape_sha256=schema_shape_sha256,
        max_enum_items=max_enum_items,
        max_array_bound=max_array_bound,
    )
