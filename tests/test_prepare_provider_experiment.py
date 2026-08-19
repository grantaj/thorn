from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from scripts import prepare_provider_experiment as prepare
from thorn.proof_language_review import ProofReviewModelResponse, validate_proof_review_response
from thorn.provider_readiness import (
    READINESS_CANARY_CARRIED_ITEMS,
    build_readiness_rescue_turn,
    build_readiness_turn,
    preflight_readiness,
)


def _src_tree_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD:src/thorn"],
        cwd=prepare.ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _synthetic_successful_readiness(path: Path, model: str) -> None:
    initial_turn = build_readiness_turn()
    initial = validate_proof_review_response(
        initial_turn,
        ProofReviewModelResponse(action="review"),
    )
    rescue_turn = build_readiness_rescue_turn()
    rescue = rescue_turn.response_model().model_validate(
        {
            "action": "review",
            "findings": [],
            "source_addresses": [],
            "review_items": [],
            "source_review_item_ids": [],
            "dispositions": [
                {
                    "item_id": f"RV{index}",
                    "status": "discharged",
                    "explanation": "Synthetic keyless builder evidence.",
                    "finding": None,
                }
                for index in range(1, READINESS_CANARY_CARRIED_ITEMS + 1)
            ],
        }
    )
    rescue = validate_proof_review_response(rescue_turn, rescue)

    evidence = preflight_readiness(
        model,
        boundary_source_tree_sha=_src_tree_sha(),
        run_id="synthetic-keyless-builder-test",
    ).model_copy(
        update={
            "mode": "live",
            "status": "live-success",
            "provider_instantiated": True,
            "generated_at": datetime.now(UTC),
            "provider_attempts": 2,
            "responses_received": 2,
            "model_generations": 2,
            "normalized_response": initial.model_dump(mode="json"),
            "rescue_normalized_response": rescue.model_dump(mode="json"),
        }
    )
    path.write_text(evidence.model_dump_json(indent=2) + "\n", encoding="utf-8")


def test_keyless_builder_derives_freeze_and_round_trips_generic_preflight(
    tmp_path: Path,
) -> None:
    model = "test-model"
    readiness = tmp_path / "readiness.json"
    output = tmp_path / "manifest.json"
    _synthetic_successful_readiness(readiness, model)

    args = argparse.Namespace(
        experiment_id="synthetic-builder-test",
        model=model,
        readiness_evidence=readiness,
        case=[
            (
                "C1",
                "eval/cases/ladder/03_hypotheses/clean_nonzero_cancellation.tex",
                "thm:clean-nonzero",
            )
        ],
        max_provider_attempts=2,
        max_input_tokens=100_000,
        max_output_tokens=8_192,
        max_readiness_age_hours=24,
        output=output,
    )

    manifest = prepare._build_manifest(args)
    prepare._write_json(output, manifest.model_dump(mode="json"))
    prepare._round_trip_preflight(output)

    loaded = prepare.ProviderExperimentManifest.load(output)
    assert loaded == manifest
    assert loaded.cases[0].source_sha256
    assert loaded.cases[0].initial_execution_fingerprint
    assert loaded.readiness.evidence_sha256
    assert loaded.src_tree_sha == _src_tree_sha()
