from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from thorn.latex import extract_project
from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewItem,
    ProofReviewModelResponse,
    build_proof_review_turn,
    build_rescue_turn,
)
from thorn.provider_readiness import build_readiness_turn
from thorn.providers.execution_contract import build_provider_execution_contract
from thorn.providers.openai_schema import (
    OpenAIStructuredOutputsSchemaError,
    validate_openai_structured_outputs_schema,
)
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.review_workflow import prepare_proof_review

ROOT = Path(__file__).resolve().parents[1]
A3_PATH = ROOT / "eval" / "robustness" / "issue_101" / "variant_result_applicability.tex"
A3_TARGET = "thm:uniform-decay"
A3_SOURCE_SHA256 = "f53d7c5eed1f0145406c3c4dda50680a852b14c2c4cd3705c17940ec5f27f403"


def _synthetic_document() -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:synthetic",
        lines=(
            "THORN-PROOF 1",
            "T0 Goal",
            "P1 Step <- ? @E1",
            "GOAL G0 T0: Goal | ctx P1 | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="E1",
                ir_identifier="edge:E1",
                text="Source E1.",
            ),
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="result:T0",
                text="Source T0.",
            ),
        ),
    )


def _strict_object(
    properties: dict[str, object] | None = None,
) -> dict[str, object]:
    properties = properties or {
        "value": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _nested_schema(levels: int) -> dict[str, object]:
    assert levels >= 2
    node: dict[str, object] = {"type": "string"}
    for index in range(levels - 1):
        node = _strict_object({f"level_{index}": node})
    return node


def _legacy_action_branch(
    schema: dict[str, object],
    *,
    action: str,
    constraints: dict[str, dict[str, object]],
) -> dict[str, object]:
    base_properties = schema["properties"]
    required = schema["required"]
    assert isinstance(base_properties, dict)
    assert isinstance(required, list)
    properties = copy.deepcopy(base_properties)
    action_schema = properties["action"]
    assert isinstance(action_schema, dict)
    properties["action"] = {**action_schema, "const": action}
    for name, overlay in constraints.items():
        property_schema = properties[name]
        assert isinstance(property_schema, dict)
        properties[name] = {**property_schema, **overlay}
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _wire_schema(turn) -> dict[str, object]:
    envelope = proof_review_request_envelope(turn, "test-model")
    contract = build_provider_execution_contract(envelope)
    text = contract.wire_request["text"]
    assert isinstance(text, dict)
    response_format = text["format"]
    assert isinstance(response_format, dict)
    schema = response_format["schema"]
    assert isinstance(schema, dict)
    return schema


def test_preserved_readiness_canary_root_anyof_schema_is_rejected_locally() -> None:
    turn = build_readiness_turn()
    schema = copy.deepcopy(proof_review_request_envelope(turn, "test-model").response_schema)
    schema["anyOf"] = [
        _legacy_action_branch(
            schema,
            action="review",
            constraints={
                "source_addresses": {"maxItems": 0},
                "review_items": {"maxItems": 0},
                "source_review_item_ids": {"maxItems": 0},
            },
        ),
        _legacy_action_branch(
            schema,
            action="need_source",
            constraints={
                "findings": {"maxItems": 0},
                "source_addresses": {"minItems": 1},
                "review_items": {"minItems": 1},
                "source_review_item_ids": {"minItems": 1},
            },
        ),
    ]

    with pytest.raises(
        OpenAIStructuredOutputsSchemaError,
        match=r"at \$: root schema must not contain anyOf",
    ):
        validate_openai_structured_outputs_schema(schema)


def test_repaired_exact_a3_initial_schema_passes_keyless_gate() -> None:
    assert hashlib.sha256(A3_PATH.read_bytes()).hexdigest() == A3_SOURCE_SHA256
    project = extract_project(A3_PATH)
    prepared = prepare_proof_review(project, project.unit(A3_TARGET))
    assert prepared.document.result_identifier == A3_TARGET

    turn = build_proof_review_turn(
        ProofLanguageReviewRequest(document=prepared.document)
    )
    assert turn.initial_packet_fingerprint == prepared.document.fingerprint()

    schema = _wire_schema(turn)

    assert schema["type"] == "object"
    assert "anyOf" not in schema
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert schema["required"] == list(properties)
    assert schema["additionalProperties"] is False


def test_repaired_synthetic_rescue_schema_passes_keyless_gate() -> None:
    request = ProofLanguageReviewRequest(document=_synthetic_document())
    initial = build_proof_review_turn(request)
    source_request = ProofReviewModelResponse(
        action="need_source",
        source_addresses=("E1",),
        review_items=(
            ProofReviewItem(id="RV1", kind="question", summary="Check the cited step."),
        ),
        source_review_item_ids=("RV1",),
    )
    rescue = build_rescue_turn(request, initial, source_request)

    schema = _wire_schema(rescue)

    assert schema["type"] == "object"
    assert "anyOf" not in schema


def test_nested_nullable_anyof_remains_supported() -> None:
    validate_openai_structured_outputs_schema(_strict_object())


@pytest.mark.parametrize(
    "keyword",
    [
        "oneOf",
        "allOf",
        "not",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
    ],
)
def test_unsupported_composition_keywords_fail_closed(keyword: str) -> None:
    schema = _strict_object()
    properties = schema["properties"]
    assert isinstance(properties, dict)
    value = properties["value"]
    assert isinstance(value, dict)
    value[keyword] = {}

    with pytest.raises(
        OpenAIStructuredOutputsSchemaError,
        match=f"unsupported composition keyword.*{keyword}",
    ):
        validate_openai_structured_outputs_schema(schema)


@pytest.mark.parametrize(
    ("property_schema", "match"),
    [
        ({"type": "not-a-json-type"}, "unsupported type"),
        (
            {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            "unsupported schema keyword",
        ),
        (
            {"type": "string", "format": "unknown-format"},
            "unsupported string format",
        ),
    ],
)
def test_unknown_provider_schema_constructs_fail_closed(
    property_schema: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match=match):
        validate_openai_structured_outputs_schema(
            _strict_object({"value": property_schema})
        )


def test_object_closure_and_required_shape_are_checked() -> None:
    open_object = _strict_object()
    open_object["additionalProperties"] = True
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="additionalProperties"):
        validate_openai_structured_outputs_schema(open_object)

    partial_required = _strict_object()
    partial_required["required"] = []
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="required must contain"):
        validate_openai_structured_outputs_schema(partial_required)


def test_documented_object_property_limit_boundary() -> None:
    validate_openai_structured_outputs_schema(
        _strict_object({f"p{index}": {"type": "string"} for index in range(5_000)})
    )
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="more than 5000"):
        validate_openai_structured_outputs_schema(
            _strict_object(
                {f"p{index}": {"type": "string"} for index in range(5_001)}
            )
        )


def test_documented_nesting_limit_boundary() -> None:
    validate_openai_structured_outputs_schema(_nested_schema(10))
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="nesting exceeds 10"):
        validate_openai_structured_outputs_schema(_nested_schema(11))


def test_documented_counted_string_limit_boundary() -> None:
    validate_openai_structured_outputs_schema(
        _strict_object({"x" * 120_000: {"type": "string"}})
    )
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="120000 characters"):
        validate_openai_structured_outputs_schema(
            _strict_object({"x" * 120_001: {"type": "string"}})
        )


def test_documented_total_enum_value_limit_boundary() -> None:
    validate_openai_structured_outputs_schema(
        _strict_object({"value": {"type": "integer", "enum": list(range(1_000))}})
    )
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="more than 1000"):
        validate_openai_structured_outputs_schema(
            _strict_object(
                {"value": {"type": "integer", "enum": list(range(1_001))}}
            )
        )


def test_documented_large_string_enum_character_limit_boundary() -> None:
    prefix = [f"{index:03d}" + "x" * 56 for index in range(250)]
    exactly_15_000 = [*prefix, "z" * 250]
    assert sum(map(len, exactly_15_000)) == 15_000
    validate_openai_structured_outputs_schema(
        _strict_object({"value": {"type": "string", "enum": exactly_15_000}})
    )

    over_limit = [*prefix, "z" * 251]
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="15000 characters"):
        validate_openai_structured_outputs_schema(
            _strict_object({"value": {"type": "string", "enum": over_limit}})
        )


def test_execution_and_transport_identity_change_with_wire_schema_projection() -> None:
    turn = build_proof_review_turn(
        ProofLanguageReviewRequest(document=_synthetic_document())
    )
    envelope = proof_review_request_envelope(turn, "test-model")
    baseline = build_provider_execution_contract(envelope)

    changed_schema = copy.deepcopy(envelope.response_schema)
    properties = changed_schema["properties"]
    assert isinstance(properties, dict)
    action = properties["action"]
    assert isinstance(action, dict)
    action["description"] = "Provider-visible projection change."
    changed = build_provider_execution_contract(
        envelope.model_copy(update={"response_schema": changed_schema})
    )

    assert changed.fingerprint() != baseline.fingerprint()
    assert changed.transport_profile().fingerprint() != baseline.transport_profile().fingerprint()
