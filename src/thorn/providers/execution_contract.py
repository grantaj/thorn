from __future__ import annotations

import copy
import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from thorn.provider_runtime_lock import PROVIDER_RUNTIME_LOCK, PROVIDER_RUNTIME_LOCK_TEXT
from thorn.providers.openai_schema import validate_openai_structured_outputs_schema
from thorn.providers.request_envelope import ProviderRequestEnvelope, RequestKind

EXECUTION_CONTRACT_VERSION = "thorn-provider-execution/2"
PROOF_REVIEW_VALIDATOR_CONTRACT = "thorn-proof-review-validator/2"
LOCAL_STRUCTURED_VALIDATOR_CONTRACT = "thorn-local-structured-validator/1"

_PROVIDER_ADAPTER_PATHS = (
    Path(__file__),
    Path(__file__).with_name("openai.py"),
    Path(__file__).with_name("openai_schema.py"),
    Path(__file__).with_name("request_envelope.py"),
    Path(__file__).resolve().parents[1] / "proof_language_review.py",
)


class ProviderRuntimeIdentity(BaseModel):
    """Closed provider runtime identity derived from Thorn's packaged lock."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    python: str
    provider_lock_sha256: str
    locked_packages: dict[str, str]
    execution_contract: str = EXECUTION_CONTRACT_VERSION


class ProviderTransportProfile(BaseModel):
    """Provider-visible transport/schema envelope with payload literals erased.

    Shape identity is exact. Dynamic literal-set and array cardinalities are retained
    per schema path, together with provider-visible schema byte size and output cap.
    A readiness profile covers a scientific profile only when it exercised the same
    transport family and at least as demanding values at every dynamic location.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    endpoint: str
    kind: RequestKind
    message_roles: tuple[str, ...]
    max_output_tokens: int | None
    schema_shape_sha256: str
    schema_utf8_bytes: int
    literal_set_cardinalities: dict[str, int]
    literal_set_utf8_bytes: dict[str, int]
    array_bounds: dict[str, int]
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

    @staticmethod
    def _covers_bounds(ready: dict[str, int], scientific: dict[str, int]) -> bool:
        return all(path in ready and ready[path] >= bound for path, bound in scientific.items())

    def covers(self, other: ProviderTransportProfile) -> bool:
        return (
            self.provider == other.provider
            and self.endpoint == other.endpoint
            and self.kind == other.kind
            and self.message_roles == other.message_roles
            and self.max_output_tokens == other.max_output_tokens
            and self.schema_shape_sha256 == other.schema_shape_sha256
            and self.schema_utf8_bytes >= other.schema_utf8_bytes
            and self._covers_bounds(
                self.literal_set_cardinalities,
                other.literal_set_cardinalities,
            )
            and self._covers_bounds(
                self.literal_set_utf8_bytes,
                other.literal_set_utf8_bytes,
            )
            and self._covers_bounds(self.array_bounds, other.array_bounds)
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
    return PROVIDER_RUNTIME_LOCK


def provider_runtime_lock_text() -> str:
    """Return the canonical installable provider constraints carried by Thorn."""

    return PROVIDER_RUNTIME_LOCK_TEXT


def provider_lock_sha256() -> str:
    return hashlib.sha256(PROVIDER_RUNTIME_LOCK_TEXT.encode("utf-8")).hexdigest()


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
    """Build and validate the final provider request before identity or dispatch."""

    provider_schema = strict_json_schema(envelope.response_schema)
    validate_openai_structured_outputs_schema(provider_schema)

    wire_request: dict[str, Any] = {
        "model": envelope.model,
        "input": envelope.input_messages(),
        "text": {
            "format": {
                "type": "json_schema",
                "name": _schema_name(envelope),
                "schema": provider_schema,
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


def _path_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _schema_dynamic_features(
    value: object,
    *,
    path: str = "$",
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    literal_cardinalities: dict[str, int] = {}
    literal_bytes: dict[str, int] = {}
    array_bounds: dict[str, int] = {}

    if isinstance(value, dict):
        enum = value.get("enum")
        if isinstance(enum, list):
            literals = enum
        elif "const" in value:
            literals = [value["const"]]
        else:
            literals = None
        if literals is not None:
            literal_cardinalities[path] = len(literals)
            literal_bytes[path] = len(
                json.dumps(
                    literals,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            )

        for name in ("minItems", "maxItems"):
            bound = value.get(name)
            if isinstance(bound, int):
                array_bounds[f"{path}/{name}"] = bound

        for child_key, child in value.items():
            child_path = f"{path}/{_path_segment(str(child_key))}"
            child_literals, child_literal_bytes, child_arrays = _schema_dynamic_features(
                child,
                path=child_path,
            )
            literal_cardinalities.update(child_literals)
            literal_bytes.update(child_literal_bytes)
            array_bounds.update(child_arrays)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_literals, child_literal_bytes, child_arrays = _schema_dynamic_features(
                child,
                path=f"{path}/{index}",
            )
            literal_cardinalities.update(child_literals)
            literal_bytes.update(child_literal_bytes)
            array_bounds.update(child_arrays)

    return literal_cardinalities, literal_bytes, array_bounds


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
    schema_bytes = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    literal_cardinalities, literal_bytes, array_bounds = _schema_dynamic_features(schema)
    max_enum_items = max(literal_cardinalities.values(), default=0)
    max_array_bound = max(array_bounds.values(), default=0)
    max_output_tokens = contract.wire_request.get("max_output_tokens")
    if not isinstance(max_output_tokens, int):
        max_output_tokens = None

    return ProviderTransportProfile(
        provider=contract.provider,
        endpoint=contract.endpoint,
        kind=contract.kind,
        message_roles=tuple(roles),
        max_output_tokens=max_output_tokens,
        schema_shape_sha256=schema_shape_sha256,
        schema_utf8_bytes=len(schema_bytes),
        literal_set_cardinalities=literal_cardinalities,
        literal_set_utf8_bytes=literal_bytes,
        array_bounds=array_bounds,
        max_enum_items=max_enum_items,
        max_array_bound=max_array_bound,
    )
