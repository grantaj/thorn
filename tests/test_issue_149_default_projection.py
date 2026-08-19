from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from thorn.latex import extract_project
from thorn.proof_language_review import ProofLanguageReviewRequest, build_proof_review_turn
from thorn.provider_readiness import build_readiness_rescue_turn, build_readiness_turn
from thorn.providers.execution_contract import (
    build_provider_execution_contract,
    strict_json_schema,
)
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


def _contains_default(value: object) -> bool:
    if isinstance(value, dict):
        return "default" in value or any(_contains_default(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_default(child) for child in value)
    return False


def _strict_object(property_schema: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {"value": property_schema},
        "required": ["value"],
        "additionalProperties": False,
    }


def test_raw_default_is_rejected_by_provider_subset_gate() -> None:
    schema = _strict_object({"type": "string", "default": "local fallback"})

    with pytest.raises(
        OpenAIStructuredOutputsSchemaError,
        match=r"unsupported schema keyword.*default",
    ):
        validate_openai_structured_outputs_schema(schema)


def test_strict_projection_strips_defaults_without_deleting_named_property() -> None:
    schema = {
        "type": "object",
        "properties": {
            "default": {"type": "string", "default": "local fallback"},
            "choice": {
                "anyOf": [
                    {"type": "string", "default": "local choice"},
                    {"type": "null", "default": None},
                ]
            },
        },
        "required": ["default", "choice"],
        "additionalProperties": False,
        "default": {},
    }

    projected = strict_json_schema(schema)

    properties = projected["properties"]
    assert isinstance(properties, dict)
    assert "default" in properties
    assert not _contains_default(properties["default"])
    assert not _contains_default(properties["choice"])
    assert "default" not in projected
    validate_openai_structured_outputs_schema(projected)


@pytest.mark.parametrize(
    "turn_builder",
    [build_readiness_turn, build_readiness_rescue_turn],
)
def test_readiness_final_wire_schema_contains_no_defaults(turn_builder) -> None:
    schema = _wire_schema(turn_builder())

    assert not _contains_default(schema)


def test_exact_a3_final_wire_schema_contains_no_defaults() -> None:
    assert hashlib.sha256(A3_PATH.read_bytes()).hexdigest() == A3_SOURCE_SHA256
    project = extract_project(A3_PATH)
    prepared = prepare_proof_review(project, project.unit(A3_TARGET))
    turn = build_proof_review_turn(
        ProofLanguageReviewRequest(document=prepared.document)
    )

    schema = _wire_schema(turn)

    assert not _contains_default(schema)
