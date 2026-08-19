from __future__ import annotations

from collections.abc import Mapping, Sequence

_UNSUPPORTED_COMPOSITION_KEYWORDS = frozenset(
    {
        "allOf",
        "not",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
    }
)


class OpenAIStructuredOutputsSchemaError(ValueError):
    """Raised when a final wire schema is outside OpenAI's supported subset."""


def _pointer(path: tuple[str, ...]) -> str:
    if not path:
        return "$"
    return "$" + "".join(f"/{part.replace('~', '~0').replace('/', '~1')}" for part in path)


def _schema_error(path: tuple[str, ...], message: str) -> OpenAIStructuredOutputsSchemaError:
    return OpenAIStructuredOutputsSchemaError(
        f"OpenAI Structured Outputs schema rejected locally at {_pointer(path)}: {message}"
    )


def _visit_schema(schema: object, *, path: tuple[str, ...], root: bool = False) -> None:
    if not isinstance(schema, Mapping):
        raise _schema_error(path, "schema node must be an object")

    unsupported = sorted(_UNSUPPORTED_COMPOSITION_KEYWORDS.intersection(schema))
    if unsupported:
        raise _schema_error(
            path,
            "unsupported composition keyword(s): " + ", ".join(unsupported),
        )

    if root:
        if schema.get("type") != "object":
            raise _schema_error(path, "root schema must have type 'object'")
        if "anyOf" in schema:
            raise _schema_error(path, "root schema must not contain anyOf")

    if schema.get("type") == "object":
        properties = schema.get("properties")
        if not isinstance(properties, Mapping):
            raise _schema_error(path, "object schema must define properties")
        if schema.get("additionalProperties") is not False:
            raise _schema_error(path, "object schema must set additionalProperties to false")
        required = schema.get("required")
        if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
            raise _schema_error(path, "object schema must define required as an array")
        required_names = list(required)
        if any(not isinstance(name, str) for name in required_names):
            raise _schema_error(path, "required entries must be property names")
        if len(required_names) != len(set(required_names)):
            raise _schema_error(path, "required property names must be unique")
        if set(required_names) != set(properties):
            raise _schema_error(path, "required must contain every property exactly once")

    if schema.get("type") == "array" and not isinstance(schema.get("items"), Mapping):
        raise _schema_error(path, "array schema must define an items schema")

    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            _visit_schema(child, path=(*path, "properties", str(name)))

    definitions = schema.get("$defs")
    if isinstance(definitions, Mapping):
        for name, child in definitions.items():
            _visit_schema(child, path=(*path, "$defs", str(name)))

    items = schema.get("items")
    if isinstance(items, Mapping):
        _visit_schema(items, path=(*path, "items"))

    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if branches is None:
            continue
        if not isinstance(branches, Sequence) or isinstance(branches, (str, bytes)) or not branches:
            raise _schema_error(path, f"{keyword} must be a non-empty array of schemas")
        for index, branch in enumerate(branches):
            _visit_schema(branch, path=(*path, keyword, str(index)))


def validate_openai_structured_outputs_schema(schema: dict[str, object]) -> None:
    """Fail closed when a final provider-visible schema is outside the supported subset.

    This validates transport expressibility only. Thorn-local Pydantic and protocol
    validators remain authoritative for relational semantics that the provider schema
    intentionally over-approximates.
    """

    _visit_schema(schema, path=(), root=True)
