from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from thorn.latex import extract_project
from thorn.proof_language_review import ProofLanguageReviewRequest, build_proof_review_turn
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.review_workflow import prepare_proof_review

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "eval" / "robustness" / "issue_101"
HISTORICAL_MANIFEST = CORPUS / "manifest.json"
POST128_MANIFEST = CORPUS / "manifest_post128.json"
MODEL = "gpt-5.6"
POST128_ASSURANCE_REVISION = "18c509f2d6414062a4da5311010c5346afd5b786"
POST128_SRC_TREE_SHA = "02d9afdd478ae1ac30692907567237536b60cc66"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cases(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = [manifest["control"], *manifest["variants"]]
    return {str(case["id"]): case for case in values}


def _src_tree_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD:src/thorn"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_post128_freeze_preserves_initial_semantic_inputs() -> None:
    historical = _load(HISTORICAL_MANIFEST)
    post128 = _load(POST128_MANIFEST)

    assert post128["experiment_id"] == "issue-101-post-128"
    assert post128["predecessor_manifest"] == "manifest.json"
    assert post128["repair_issue"] == 128
    assert post128["assurance_revision"] == POST128_ASSURANCE_REVISION
    assert post128["assurance_src_tree_sha"] == POST128_SRC_TREE_SHA
    assert _src_tree_sha() == POST128_SRC_TREE_SHA
    assert historical["assurance_src_tree_sha"] != POST128_SRC_TREE_SHA
    assert post128["defect_invariant"] == historical["defect_invariant"]

    historical_cases = _cases(historical)
    post128_cases = _cases(post128)
    assert tuple(post128_cases) == ("C0", "B0", "A1", "A2", "A3")
    assert post128_cases.keys() == historical_cases.keys()

    for case_id, case in post128_cases.items():
        historical_case = historical_cases[case_id]
        assert case["path"] == historical_case["path"]
        assert case["source_sha256"] == historical_case["source_sha256"]
        assert case["target"] == historical_case["target"]
        assert case.get("review_target") == historical_case.get("review_target")
        assert case["initial_request_fingerprint"] == historical_case[
            "initial_request_fingerprint"
        ]

        source_path = CORPUS / str(case["path"])
        assert _sha256(source_path) == case["source_sha256"]

        project = extract_project(source_path)
        review_target = str(case.get("review_target", case["target"]))
        prepared = prepare_proof_review(project, project.unit(review_target))
        initial = build_proof_review_turn(
            ProofLanguageReviewRequest(document=prepared.document)
        )
        envelope = proof_review_request_envelope(initial, MODEL)

        assert envelope.fingerprint() == case["initial_request_fingerprint"]
        assert envelope.max_output_tokens == 4096
