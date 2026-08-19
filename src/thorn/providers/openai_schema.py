from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# OpenAI Structured Outputs limits documented by the provider. This module is
# included in Thorn's provider-adapter identity, so policy changes invalidate
# readiness/freeze evidence without changing the mathematical review protocol.
_MAX_OBJECT_PROPERTIES = 5_000
_MAX_NESTING_LEVELS = 10
_MAX_COUNTED_STRING_CHARACTERS = 120_000
_MAX_ENUM_VALUES = 1_000
_LARGE_STRING_ENUM_THRESHOLD = 250
_MAX_LARGE_STRING_ENUM_CHARACTERS = 15_000

_SUPPORTED_TYPES = frozenset(
    {"string", "number", "boolean", "integer", "object", "array", "null"}
)
_SUPPORTED_STRING_FORMATS = frozenset(
    {
        "date-time",
        "time",
        "date",
        "duration",
        "email",
        "hostname",
        "ipv4",
        "ipv6",
        "uuid",
    }
)
# Keep this allowlist deliberately small. ``title`` is retained because OpenAI's
# current Python strict-schema adapter preserves it for Pydantic schemas;
# everything else must be explicitly admitted here.
_ALLOWED_SCHEMA_KEYWORDS = frozenset(
    {
        "$defs",
        "$ref",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "anyOf",
        "description",
        "title",
        "pattern",
        "format",
        "minLength",
        "maxLength",
        "multipleOf",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
    }
)
_UNSUPPORTED_COMPOSITION_KEYWORDS = frozenset(
    {
        "oneOf",
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


@dataclass
class _SchemaStats:
    object_properties: int = 0
    counted_string_characters: int = 0
    enum_values: int = 0


def _pointer(path: tuple[str, ...]) -> str:
    if not path:
        return "$"
    return "$" + "".join(
        f"/{part.replace('~', '~0').replace('/', '~1')}" for part in path
    )


def _schema_error(
    path: tuple[str, ...],
    message: str,
) -> OpenAIStructuredOutputsSchemaError:
    return OpenAIStructuredOutputsSchemaError(
        f"OpenAI Structured Outputs schema rejected locally at {_pointer(path)}: {message}"
    )


def _type_names(type_value: object, *, path: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(type_value, str):
        if type_value not in _SUPPORTED_TYPES:
            raise _schema_error(path, f"unsupported type {type_value!r}")
        return (type_value,)

    if isinstance(type_value, Sequence) and not isinstance(type_value, (str, bytes)):
        types = list(type_value)
        if (
            len(types) != 2
            or any(not isinstance(item, str) for item in types)
            or len(set(types)) != 2
            or "null" not in types
            or any(item not in _SUPPORTED_TYPES for item in types)
        ):
            raise _schema_error(
                path,
                "type arrays are only supported as one JSON type unioned with 'null'",
            )
        return tuple(types)

    raise _schema_error(path, "type must be a supported JSON type name")


def _add_counted_characters(
    stats: _SchemaStats,
    count: int,
    *,
    path: tuple[str, ...],
) -> None:
    stats.counted_string_characters += count
    if stats.counted_string_characters > _MAX_COUNTED_STRING_CHARACTERS:
        raise _schema_error(
            path,
            "counted schema strings exceed "
            f"{_MAX_COUNTED_STRING_CHARACTERS} characters",
        )


def _non_negative_integer(
    schema: Mapping[str, object],
    keyword: str,
    *,
    path: tuple[str, ...],
) -> None:
    if keyword not in schema:
        return
    value = schema[keyword]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _schema_error(
            (*path, keyword),
            f"{keyword} must be a non-negative integer",
        )


def _number(
    schema: Mapping[str, object],
    keyword: str,
    *,
    path: tuple[str, ...],
    positive: bool = False,
) -> None:
    if keyword not in schema:
        return
    value = schema[keyword]
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise _schema_error((*path, keyword), f"{keyword} must be a finite number")
    if positive and value <= 0:
        raise _schema_error((*path, keyword), f"{keyword} must be positive")


def _check_ordered_integer_bounds(
    schema: Mapping[str, object],
    lower: str,
    upper: str,
    *,
    path: tuple[str, ...],
) -> None:
    lower_value = schema.get(lower)
    upper_value = schema.get(upper)
    if (
        isinstance(lower_value, int)
        and not isinstance(lower_value, bool)
        and isinstance(upper_value, int)
        and not isinstance(upper_value, bool)
        and lower_value > upper_value
    ):
        raise _schema_error(path, f"{lower} must not exceed {upper}")


def _visit_schema(
    schema: object,
    *,
    path: tuple[str, ...],
    depth: int,
    stats: _SchemaStats,
    root: bool = False,
) -> None:
    if not isinstance(schema, Mapping):
        raise _schema_error(path, "schema node must be an object")
    if depth > _MAX_NESTING_LEVELS:
        raise _schema_error(
            path,
            f"schema nesting exceeds {_MAX_NESTING_LEVELS} levels",
        )

    unsupported = sorted(_UNSUPPORTED_COMPOSITION_KEYWORDS.intersection(schema))
    if unsupported:
        raise _schema_error(
            path,
            "unsupported composition keyword(s): " + ", ".join(unsupported),
        )
    unknown = sorted(set(schema).difference(_ALLOWED_SCHEMA_KEYWORDS))
    if unknown:
        raise _schema_error(
            path,
            "unsupported schema keyword(s): " + ", ".join(unknown),
        )

    type_value = schema.get("type")
    type_names = (
        _type_names(type_value, path=(*path, "type"))
        if type_value is not None
        else ()
    )

    if root:
        if type_names != ("object",):
            raise _schema_error(path, "root schema must have type 'object'")
        if "anyOf" in schema:
            raise _schema_error(path, "root schema must not contain anyOf")

    ref = schema.get("$ref")
    if ref is not None:
        if not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/$defs/")):
            raise _schema_error(
                (*path, "$ref"),
                "only local root/$defs references are supported",
            )
        if len(schema) != 1:
            raise _schema_error(path, "$ref schemas must not contain sibling keywords")

    for annotation in ("description", "title"):
        value = schema.get(annotation)
        if value is not None and not isinstance(value, str):
            raise _schema_error((*path, annotation), f"{annotation} must be a string")

    if "pattern" in schema and (
        "string" not in type_names or not isinstance(schema["pattern"], str)
    ):
        raise _schema_error(
            (*path, "pattern"),
            "pattern is only supported as a string constraint",
        )
    fmt = schema.get("format")
    if fmt is not None:
        if "string" not in type_names:
            raise _schema_error((*path, "format"), "format is only supported for strings")
        if not isinstance(fmt, str) or fmt not in _SUPPORTED_STRING_FORMATS:
            raise _schema_error((*path, "format"), f"unsupported string format {fmt!r}")
    for keyword in ("minLength", "maxLength"):
        if keyword in schema and "string" not in type_names:
            raise _schema_error((*path, keyword), f"{keyword} requires type 'string'")
        _non_negative_integer(schema, keyword, path=path)
    _check_ordered_integer_bounds(schema, "minLength", "maxLength", path=path)

    numeric_types = {"number", "integer"}.intersection(type_names)
    for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if keyword in schema and not numeric_types:
            raise _schema_error((*path, keyword), f"{keyword} requires a numeric type")
        _number(schema, keyword, path=path)
    if "multipleOf" in schema and not numeric_types:
        raise _schema_error((*path, "multipleOf"), "multipleOf requires a numeric type")
    _number(schema, "multipleOf", path=path, positive=True)

    properties = schema.get("properties")
    if "object" in type_names:
        if not isinstance(properties, Mapping):
            raise _schema_error(path, "object schema must define properties")
        if schema.get("additionalProperties") is not False:
            raise _schema_error(
                path,
                "object schema must set additionalProperties to false",
            )
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
    else:
        for keyword in ("properties", "required", "additionalProperties"):
            if keyword in schema:
                raise _schema_error((*path, keyword), f"{keyword} requires type 'object'")

    if isinstance(properties, Mapping):
        if any(not isinstance(name, str) for name in properties):
            raise _schema_error((*path, "properties"), "property names must be strings")
        stats.object_properties += len(properties)
        if stats.object_properties > _MAX_OBJECT_PROPERTIES:
            raise _schema_error(
                (*path, "properties"),
                f"schema contains more than {_MAX_OBJECT_PROPERTIES} object properties",
            )
        _add_counted_characters(
            stats,
            sum(len(name) for name in properties),
            path=(*path, "properties"),
        )
        for name, child in properties.items():
            _visit_schema(
                child,
                path=(*path, "properties", name),
                depth=depth + 1,
                stats=stats,
            )

    definitions = schema.get("$defs")
    if definitions is not None and not isinstance(definitions, Mapping):
        raise _schema_error((*path, "$defs"), "$defs must be an object of schemas")
    if isinstance(definitions, Mapping):
        if any(not isinstance(name, str) for name in definitions):
            raise _schema_error((*path, "$defs"), "definition names must be strings")
        _add_counted_characters(
            stats,
            sum(len(name) for name in definitions),
            path=(*path, "$defs"),
        )
        for name, child in definitions.items():
            _visit_schema(
                child,
                path=(*path, "$defs", name),
                depth=depth + 1,
                stats=stats,
            )

    if "array" in type_names:
        items = schema.get("items")
        if not isinstance(items, Mapping):
            raise _schema_error(path, "array schema must define an items schema")
    elif "items" in schema:
        raise _schema_error((*path, "items"), "items requires type 'array'")
    for keyword in ("minItems", "maxItems"):
        if keyword in schema and "array" not in type_names:
            raise _schema_error((*path, keyword), f"{keyword} requires type 'array'")
        _non_negative_integer(schema, keyword, path=path)
    _check_ordered_integer_bounds(schema, "minItems", "maxItems", path=path)
    items = schema.get("items")
    if isinstance(items, Mapping):
        _visit_schema(
            items,
            path=(*path, "items"),
            depth=depth + 1,
            stats=stats,
        )

    enum = schema.get("enum")
    if enum is not None:
        if not isinstance(enum, Sequence) or isinstance(enum, (str, bytes)) or not enum:
            raise _schema_error((*path, "enum"), "enum must be a non-empty array")
        enum_values = list(enum)
        if any(
            value is not None and not isinstance(value, (str, int, float, bool))
            for value in enum_values
        ):
            raise _schema_error((*path, "enum"), "enum values must be JSON scalars")
        identities = {(type(value), value) for value in enum_values}
        if len(identities) != len(enum_values):
            raise _schema_error((*path, "enum"), "enum values must be unique")
        stats.enum_values += len(enum_values)
        if stats.enum_values > _MAX_ENUM_VALUES:
            raise _schema_error(
                (*path, "enum"),
                f"schema contains more than {_MAX_ENUM_VALUES} enum values",
            )
        string_characters = sum(
            len(value) for value in enum_values if isinstance(value, str)
        )
        _add_counted_characters(stats, string_characters, path=(*path, "enum"))
        if (
            len(enum_values) > _LARGE_STRING_ENUM_THRESHOLD
            and string_characters > _MAX_LARGE_STRING_ENUM_CHARACTERS
        ):
            raise _schema_error(
                (*path, "enum"),
                "string enum exceeds "
                f"{_MAX_LARGE_STRING_ENUM_CHARACTERS} characters with more than "
                f"{_LARGE_STRING_ENUM_THRESHOLD} values",
            )

    if "const" in schema:
        const = schema["const"]
        if const is not None and not isinstance(const, (str, int, float, bool)):
            raise _schema_error((*path, "const"), "const must be a JSON scalar")
        if isinstance(const, str):
            _add_counted_characters(stats, len(const), path=(*path, "const"))

    branches = schema.get("anyOf")
    if branches is not None:
        if (
            not isinstance(branches, Sequence)
            or isinstance(branches, (str, bytes))
            or not branches
        ):
            raise _schema_error((*path, "anyOf"), "anyOf must be a non-empty array of schemas")
        for index, branch in enumerate(branches):
            _visit_schema(
                branch,
                path=(*path, "anyOf", str(index)),
                depth=depth + 1,
                stats=stats,
            )


def validate_openai_structured_outputs_schema(schema: dict[str, object]) -> None:
    """Fail closed when a final provider-visible schema is outside the supported subset.

    This validates transport expressibility only. Thorn-local Pydantic and protocol
    validators remain authoritative for relational semantics that the provider schema
    intentionally over-approximates.
    """

    _visit_schema(schema, path=(), depth=1, stats=_SchemaStats(), root=True)