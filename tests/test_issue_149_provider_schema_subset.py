from __future__ import annotations

import copy

import pytest

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewItem,
    ProofReviewModelResponse,
    build_proof_review_turn,
    build_rescue_turn,
)
from thorn.providers.execution_contract import build_provider_execution_contract
from thorn.providers.openai_schema import (
    OpenAIStructuredOutputsSchemaError,
    validate_openai_structured_outputs_schema,
)
from thorn.providers.request_envelope import proof_review_request_envelope


def _document() -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:a3",
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


def _strict_object() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "value": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": ["value"],
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


def test_root_anyof_canary_shape_is_rejected_before_contract_identity() -> None:
    schema = _strict_object()
    schema["anyOf"] = [copy.deepcopy(schema), copy.deepcopy(schema)]

    with pytest.raises(
        OpenAIStructuredOutputsSchemaError,
        match=r"at \$: root schema must not contain anyOf",
    ):
        validate_openai_structured_outputs_schema(schema)


def test_repaired_a3_initial_schema_passes_keyless_gate() -> None:
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=_document()))

    schema = _wire_schema(turn)

    assert schema["type"] == "object"
    assert "anyOf" not in schema
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert schema["required"] == list(properties)
    assert schema["additionalProperties"] is False


def test_repaired_synthetic_rescue_schema_passes_keyless_gate() -> None:
    request = ProofLanguageReviewRequest(document=_document())
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


def test_object_closure_and_required_shape_are_checked() -> None:
    open_object = _strict_object()
    open_object["additionalProperties"] = True
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="additionalProperties"):
        validate_openai_structured_outputs_schema(open_object)

    partial_required = _strict_object()
    partial_required["required"] = []
    with pytest.raises(OpenAIStructuredOutputsSchemaError, match="required must contain"):
        validate_openai_structured_outputs_schema(partial_required)


def test_execution_and_transport_identity_change_with_wire_schema_projection() -> None:
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=_document()))
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
