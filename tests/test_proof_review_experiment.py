from __future__ import annotations

import json
from pathlib import Path

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.models import SourceRange, TheoremUnit
from thorn.proof_language_experiment import (
    PROOF_REVIEW_EXPERIMENT_ARMS,
    proof_review_experiment_envelope,
)
from thorn.proof_review_eval import build_proof_review_inventory


def _unit() -> TheoremUnit:
    return TheoremUnit(
        identifier="thm:test",
        environment="theorem",
        statement="For every a, Q(a).",
        proof="Fix a. Therefore Q(a).",
        statement_range=SourceRange(file="paper.tex", start_line=1, end_line=1),
    )


def _document(*, with_source: bool = False) -> LLMProofLanguage:
    if not with_source:
        return LLMProofLanguage(
            result_identifier="thm:test",
            lines=("THORN-PROOF 1", "T0 ∀a.Q(a)", "GOAL G0 T0: ∀a.Q(a)"),
        )
    return LLMProofLanguage(
        result_identifier="thm:test",
        lines=(
            "THORN-PROOF 1",
            "P1 Q(a) <- ? @E1",
            "T0 ∀a.Q(a)",
            "GOAL G0 T0: ∀a.Q(a) | ctx P1 | open @P1",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="E1",
                ir_identifier="edge:E1",
                text="Exact source.",
            ),
            ProofLanguageSourceHandle(
                address="P1",
                ir_identifier="claim:P1",
                text="Exact prerequisite source.",
            ),
        ),
    )


def test_abc_arms_share_prompt_model_and_provider_contract_without_source_handles() -> None:
    unit = _unit()
    document = _document()
    envelopes = {
        arm: proof_review_experiment_envelope(unit, document, "test-model", arm)
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS
    }

    assert {item.model for item in envelopes.values()} == {"test-model"}
    assert {item.system_prompt for item in envelopes.values()} == {
        envelopes["raw"].system_prompt
    }
    assert {json.dumps(item.response_schema, sort_keys=True) for item in envelopes.values()} == {
        json.dumps(envelopes["raw"].response_schema, sort_keys=True)
    }
    assert {item.kind for item in envelopes.values()} == {"proof_review"}

    assert envelopes["raw"].representation == "raw"
    assert envelopes["proof_ir"].representation == "thorn-proof/1"
    assert envelopes["proof_ir_rescue"].representation == "thorn-proof/1"
    assert "SOURCE_RESCUE disabled" in envelopes["proof_ir"].user_content
    assert "SOURCE_RESCUE disabled" in envelopes["proof_ir_rescue"].user_content
    assert "SOURCE_RESCUE allowed-once" not in envelopes["proof_ir_rescue"].user_content
    assert envelopes["proof_ir"].user_content.split("\n\n", 1)[1] == document.render_initial()
    rescue_payload = envelopes["proof_ir_rescue"].user_content.split("\n\n", 1)[1]
    assert rescue_payload == document.render_initial()


def test_rescue_arm_schema_is_request_specific_when_source_is_advertised() -> None:
    unit = _unit()
    document = _document(with_source=True)
    envelopes = {
        arm: proof_review_experiment_envelope(unit, document, "test-model", arm)
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS
    }

    assert envelopes["raw"].response_schema == envelopes["proof_ir"].response_schema
    assert envelopes["proof_ir_rescue"].response_schema != envelopes["proof_ir"].response_schema
    source_schema = envelopes["proof_ir_rescue"].response_schema["properties"][
        "source_addresses"
    ]
    assert set(source_schema["items"]["enum"]) == {"E1", "P1"}
    assert source_schema["maxItems"] == 8


def test_keyless_inventory_builds_packets_without_provider_calls(tmp_path: Path) -> None:
    source = Path("eval/proof-review-challenge.json")
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["cases"] = manifest["cases"][:1]
    manifest_path = tmp_path / "challenge.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    inventory = build_proof_review_inventory(
        manifest_path,
        model="test-model",
        structural_only=True,
    )

    assert inventory["cases"] == 1
    assert inventory["initial_packets"] == 3
    assert inventory["provider_instantiated"] is False
    assert inventory["provider_requests"] == 0
    assert inventory["live_requests"] == 0
    assert set(inventory["experiment_arms"]) == set(PROOF_REVIEW_EXPERIMENT_ARMS)
    assert inventory["response_schema_policy"] == (
        "request-specific closed-world source selection over each turn's advertised handles"
    )
    record = inventory["records"][0]
    fingerprints = {record["arms"][arm]["fingerprint"] for arm in PROOF_REVIEW_EXPERIMENT_ARMS}
    schema_hashes = {
        record["arms"][arm]["response_schema_sha256"]
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS
    }
    assert len(fingerprints) == 3
    assert schema_hashes.issubset(set(inventory["response_schema_sha256s"]))
