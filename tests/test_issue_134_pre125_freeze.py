from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

from thorn.latex import extract_project
from thorn.llm_proof_language import DEFAULT_MAX_SOURCE_REQUESTS, FORMAT_VERSION
from thorn.proof_language_review import (
    PROMPT_VERSION,
    PROTOCOL_VERSION,
    ProofLanguageReviewRequest,
    build_proof_review_turn,
)
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    proof_review_request_envelope,
)
from thorn.review_workflow import prepare_proof_review

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "eval" / "robustness" / "issue_134" / "manifest.json"
EXPECTED_CASE_IDS = ("A1", "A2", "A3")
FROZEN_REVISION = "9201b33f73b84debf088548859d360be6a350585"
FROZEN_SRC_TREE = "17b4af51d42e6c2268fff8279d5ed0edc895939c"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _predecessor_cases(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    predecessor = _load(ROOT / str(manifest["predecessor_manifest"]))
    return {
        str(case["id"]): case
        for case in [predecessor["control"], *predecessor["variants"]]
    }


def test_issue_134_freeze_preserves_post128_initial_inputs_on_post132_tree() -> None:
    manifest = _load(MANIFEST)
    predecessor_cases = _predecessor_cases(manifest)

    assert manifest["issue"] == 134
    assert manifest["experiment_id"] == "issue-134-pre-125"
    assert manifest["assurance_revision"] == FROZEN_REVISION
    assert manifest["assurance_src_tree_sha"] == FROZEN_SRC_TREE
    assert manifest["model"] == "gpt-5.6"
    assert manifest["representation"] == FORMAT_VERSION == "thorn-proof/1"
    assert manifest["protocol"] == PROTOCOL_VERSION == "thorn-proof-review/2"
    assert manifest["prompt_version"] == PROMPT_VERSION == "proof_language_reviewer_v2"
    prompt = files("thorn.prompts").joinpath(f"{PROMPT_VERSION}.md")
    assert hashlib.sha256(prompt.read_bytes()).hexdigest() == manifest["prompt_sha256"]
    assert manifest["source_rescue"] == {
        "allowed_once": True,
        "max_addresses": DEFAULT_MAX_SOURCE_REQUESTS,
    }
    assert manifest["provider_retries"] == 0
    assert manifest["limits"] == {
        "max_cases": 3,
        "max_provider_requests": 6,
        "max_input_tokens": 100_000,
        "max_output_tokens_per_request": PROOF_REVIEW_MAX_OUTPUT_TOKENS,
        "max_output_tokens": 6 * PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    }

    cases = manifest["cases"]
    assert tuple(str(case["id"]) for case in cases) == EXPECTED_CASE_IDS

    for case in cases:
        case_id = str(case["id"])
        predecessor = predecessor_cases[case_id]
        assert case["source_sha256"] == predecessor["source_sha256"]
        assert case["target"] == predecessor["target"]
        assert case.get("review_target") == predecessor.get("review_target")
        assert (
            case["initial_request_fingerprint"]
            == predecessor["initial_request_fingerprint"]
        )
        assert _sha256(ROOT / str(case["path"])) == case["source_sha256"]

    if _src_tree_sha() != FROZEN_SRC_TREE:
        return

    for case in cases:
        source_path = ROOT / str(case["path"])
        project = extract_project(source_path)
        review_target = str(case.get("review_target", case["target"]))
        prepared = prepare_proof_review(project, project.unit(review_target))
        initial = build_proof_review_turn(
            ProofLanguageReviewRequest(document=prepared.document)
        )
        envelope = proof_review_request_envelope(initial, manifest["model"])

        assert initial.representation == manifest["representation"]
        assert initial.protocol_version == manifest["protocol"]
        assert initial.source_rescue_allowed
        assert initial.max_source_addresses == DEFAULT_MAX_SOURCE_REQUESTS
        assert envelope.fingerprint() == case["initial_request_fingerprint"]
        assert envelope.max_output_tokens == PROOF_REVIEW_MAX_OUTPUT_TOKENS


def test_issue_134_preflight_is_keyless_and_refuses_assurance_drift(
    tmp_path: Path,
) -> None:
    output = tmp_path / "preflight.json"
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_issue_134_pre125.py",
            "--preflight",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    if _src_tree_sha() != FROZEN_SRC_TREE:
        assert completed.returncode != 0
        assert "production src/thorn tree differs" in completed.stderr
        assert not output.exists()
        return

    assert completed.returncode == 0, (
        f"issue-134 preflight failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["issue"] == 134
    assert payload["experiment_id"] == "issue-134-pre-125"
    assert payload["mode"] == "preflight"
    assert payload["live_authorized"] is False
    assert payload["model"] == "gpt-5.6"
    assert payload["representation"] == "thorn-proof/1"
    assert payload["protocol"] == "thorn-proof-review/2"
    assert tuple(case["id"] for case in payload["cases"]) == EXPECTED_CASE_IDS
    assert all(case["matches_post128_predecessor"] for case in payload["cases"])

    limits = payload["limits"]
    assert limits["max_provider_requests"] == 6
    assert limits["max_input_tokens"] == 100_000
    assert limits["max_output_tokens_per_request"] == 4_096
    assert limits["max_output_tokens"] == 24_576
    assert limits["all_initial_requests_input_upper_bound"] <= 100_000
    assert "before each actual request" in limits["input_guard"]
    assert all(
        case["initial_input_token_upper_bound"] <= limits["max_input_tokens"]
        for case in payload["cases"]
    )
    assert all(len(case["initial_request_fingerprint"]) == 64 for case in payload["cases"])
