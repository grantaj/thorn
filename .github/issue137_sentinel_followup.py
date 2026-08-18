from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected sentinel follow-up context missing in {path}: {old[:180]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/thorn/proof_review_sentinel.py",
    '''def _schema_sha256(schema: dict[str, object]) -> str:
    rendered = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(rendered.encode("utf-8"))


''',
    '''def _schema_sha256(schema: dict[str, object]) -> str:
    rendered = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(rendered.encode("utf-8"))


def _initial_request_contract_drift(
    expected: dict[str, dict[str, FrozenInitialRequest]],
    observed: dict[str, dict[str, FrozenInitialRequest]],
) -> list[dict[str, object]]:
    """Describe contract drift without mutating a completed historical freeze."""

    drift: list[dict[str, object]] = []
    metadata_paths = sorted(set(expected) | set(observed))
    for metadata in metadata_paths:
        expected_arms = expected.get(metadata, {})
        observed_arms = observed.get(metadata, {})
        arms = sorted(set(expected_arms) | set(observed_arms))
        for arm in arms:
            frozen = expected_arms.get(arm)
            current = observed_arms.get(arm)
            if frozen is None or current is None:
                drift.append(
                    {
                        "metadata": metadata,
                        "arm": arm,
                        "changed_fields": ["request_presence"],
                        "frozen": (
                            frozen.model_dump(mode="json") if frozen is not None else None
                        ),
                        "current": (
                            current.model_dump(mode="json") if current is not None else None
                        ),
                    }
                )
                continue
            changed_fields = [
                field
                for field in (
                    "fingerprint",
                    "packet_fingerprint",
                    "response_schema_sha256",
                )
                if getattr(frozen, field) != getattr(current, field)
            ]
            if changed_fields:
                drift.append(
                    {
                        "metadata": metadata,
                        "arm": arm,
                        "changed_fields": changed_fields,
                        "frozen": frozen.model_dump(mode="json"),
                        "current": current.model_dump(mode="json"),
                    }
                )
    return drift


''',
)

replace(
    "src/thorn/proof_review_sentinel.py",
    '''    request_freeze_verified = False
    if manifest.frozen and not structural_only:
        expected_initial = {
            metadata: {
                arm: record.model_dump(mode="json")
                for arm, record in arm_records.items()
            }
            for metadata, arm_records in manifest.initial_requests.items()
        }
        if manifest.semantic_prompt_sha256 != freeze_candidate["semantic_prompt_sha256"]:
            raise ValueError("frozen sentinel prompt hash no longer matches initial requests")
        if manifest.file_sha256 != freeze_candidate["file_sha256"]:
            raise ValueError("frozen sentinel file hashes no longer match initial requests")
        if expected_initial != freeze_candidate["initial_requests"]:
            raise ValueError("frozen sentinel initial request contracts changed")
        request_freeze_verified = True
''',
    '''    request_freeze_verified = False
    request_contract_matches_frozen: bool | None = None
    request_contract_drift: list[dict[str, object]] = []
    if manifest.frozen and not structural_only:
        if manifest.semantic_prompt_sha256 != freeze_candidate["semantic_prompt_sha256"]:
            raise ValueError("frozen sentinel prompt hash no longer matches initial requests")
        if manifest.file_sha256 != freeze_candidate["file_sha256"]:
            raise ValueError("frozen sentinel file hashes no longer match initial requests")
        request_contract_drift = _initial_request_contract_drift(
            manifest.initial_requests,
            observed_initial,
        )
        request_contract_matches_frozen = not request_contract_drift
        request_freeze_verified = request_contract_matches_frozen
''',
)

replace(
    "src/thorn/proof_review_sentinel.py",
    '''        "frozen_request_contract_verified": request_freeze_verified,
        "freeze_candidate": freeze_candidate,
''',
    '''        "frozen_request_contract_verified": request_freeze_verified,
        "frozen_request_contract_matches_current": request_contract_matches_frozen,
        "comparable_to_frozen_paid_run": (
            request_freeze_verified if manifest.frozen and not structural_only else None
        ),
        "request_contract_drift": request_contract_drift,
        "freeze_candidate": freeze_candidate,
''',
)

replace(
    "tests/test_proof_review_v2_sentinel.py",
    '''from thorn.proof_review_sentinel import (
    SENTINEL_EXPERIMENT,
    build_proof_review_sentinel_inventory,
    load_proof_review_sentinel_manifest,
)
''',
    '''from thorn.proof_review_sentinel import (
    SENTINEL_EXPERIMENT,
    FrozenInitialRequest,
    _initial_request_contract_drift,
    build_proof_review_sentinel_inventory,
    load_proof_review_sentinel_manifest,
)
''',
)

with Path("tests/test_proof_review_v2_sentinel.py").open("a", encoding="utf-8") as handle:
    handle.write(r'''


def test_v2_sentinel_reports_request_drift_without_rewriting_frozen_contract() -> None:
    frozen = FrozenInitialRequest(
        fingerprint="a" * 64,
        packet_fingerprint="b" * 64,
        response_schema_sha256="c" * 64,
    )
    changed = frozen.model_copy(update={"fingerprint": "d" * 64})

    assert _initial_request_contract_drift(
        {"case.json": {"proof_ir_rescue": frozen}},
        {"case.json": {"proof_ir_rescue": frozen}},
    ) == []

    drift = _initial_request_contract_drift(
        {"case.json": {"proof_ir_rescue": frozen}},
        {"case.json": {"proof_ir_rescue": changed}},
    )
    assert len(drift) == 1
    assert drift[0]["metadata"] == "case.json"
    assert drift[0]["arm"] == "proof_ir_rescue"
    assert drift[0]["changed_fields"] == ["fingerprint"]
    assert drift[0]["frozen"] == frozen.model_dump(mode="json")
    assert drift[0]["current"] == changed.model_dump(mode="json")
''')

with Path("eval/proof-review-v2-sentinel/README.md").open("a", encoding="utf-8") as handle:
    handle.write(r'''

## Historical freeze after a successful run

The successful GREEN run above makes this sentinel a historical experiment, not a
moving production fixture. Later general changes to Thorn may intentionally alter
the provider request contract. In that situation the keyless inventory reports
`frozen_request_contract_verified=false`,
`frozen_request_contract_matches_current=false`, and
`comparable_to_frozen_paid_run=false`, together with the exact per-arm contract
drift. It does **not** rewrite the frozen fingerprints or treat the old paid result
as comparable to the new production contract.

This informational drift reporting does not weaken the live gate:
`run_proof_review_sentinel.py --live` still refuses to construct a provider unless
the historical frozen requests verify exactly. Any future paid measurement under a
changed contract requires a new experiment/freeze rather than mutating this
completed sentinel.
''')
