from __future__ import annotations

from pathlib import Path

from thorn.proof_review_sentinel import (
    SENTINEL_EXPERIMENT,
    build_proof_review_sentinel_inventory,
    load_proof_review_sentinel_manifest,
)

MANIFEST = Path("eval/proof-review-v2-sentinel/manifest.json")


def test_v2_sentinel_is_one_matched_clean_defect_pair() -> None:
    manifest = load_proof_review_sentinel_manifest(MANIFEST)

    assert manifest.experiment == SENTINEL_EXPERIMENT
    assert manifest.issue == 90
    assert manifest.model == "gpt-5.6"
    assert manifest.max_live_requests == 8
    assert manifest.sdk_max_retries == 0
    assert [entry.role for entry in manifest.cases] == ["clean", "defect"]

    clean = Path("eval/proof-review-v2-sentinel/clean.tex").read_text(encoding="utf-8")
    defect = Path("eval/proof-review-v2-sentinel/defect.tex").read_text(
        encoding="utf-8"
    )
    assert clean.replace(
        "there exists a real number $u$",
        "there exists a unique real number $u$",
    ) == defect


def test_v2_sentinel_structural_preflight_is_keyless_and_source_addressable() -> None:
    inventory = build_proof_review_sentinel_inventory(
        MANIFEST,
        structural_only=True,
    )

    assert inventory["cases"] == 2
    assert inventory["initial_packets"] == 6
    assert inventory["provider_instantiated"] is False
    assert inventory["provider_requests"] == 0
    assert inventory["live_requests"] == 0
    assert inventory["structural_only"] is True

    records = inventory["records"]
    assert isinstance(records, list)
    assert len(records) == 2
    for record in records:
        assert isinstance(record, dict)
        sources = record["thorn_held_source_handles"]
        assert isinstance(sources, list)
        assert any(
            isinstance(source, dict)
            and "define $u \\triangleleft v$" in str(source["text"])
            for source in sources
        )
        arms = record["arms"]
        assert isinstance(arms, dict)
        assert arms["raw"]["source_rescue_allowed"] is False
        assert arms["proof_ir"]["source_rescue_allowed"] is False
        assert arms["proof_ir_rescue"]["source_rescue_allowed"] is True
        assert record["advertised_source_addresses"]


def test_v2_sentinel_freeze_candidate_covers_every_initial_request() -> None:
    inventory = build_proof_review_sentinel_inventory(
        MANIFEST,
        structural_only=True,
    )
    freeze = inventory["freeze_candidate"]
    assert isinstance(freeze, dict)
    initial = freeze["initial_requests"]
    assert isinstance(initial, dict)
    assert set(initial) == {
        "eval/proof-review-v2-sentinel/clean.json",
        "eval/proof-review-v2-sentinel/defect.json",
    }
    for records in initial.values():
        assert set(records) == {"raw", "proof_ir", "proof_ir_rescue"}
        for request in records.values():
            assert len(request["fingerprint"]) == 64
            assert len(request["packet_fingerprint"]) == 64
            assert len(request["response_schema_sha256"]) == 64
