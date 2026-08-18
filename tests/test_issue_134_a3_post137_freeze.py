from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

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
MANIFEST = ROOT / "eval/robustness/issue_134/a3_post137_manifest.json"
FROZEN_REVISION = "93cba5eec02af0c83bdcc3ea4eb54dd79efb1704"
FROZEN_SRC_TREE = "08c1ef7c0d61020424a597be344f0bb08ce10f58"
PREDECESSOR_FINGERPRINT = (
    "0c8ba6c4a8cbfc2d285384b896e65059f67d296d708f75986deaace3434d22a3"
)
FROZEN_FINGERPRINT = (
    "44e1ffa1fb17219c106af28f8e7535e70788c1f7a02b5e762bf381e3637cfb28"
)


def _load(path: Path) -> dict[str, object]:
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


def test_a3_post137_freeze_preserves_math_and_freezes_new_transport() -> None:
    manifest = _load(MANIFEST)
    case = manifest["case"]
    assert isinstance(case, dict)

    assert manifest["issue"] == 134
    assert manifest["experiment_id"] == "issue-134-a3-post137-pre125"
    assert manifest["status"] == "frozen-keylessly-live-not-authorized"
    assert manifest["assurance_revision"] == FROZEN_REVISION
    assert manifest["assurance_src_tree_sha"] == FROZEN_SRC_TREE
    assert manifest["repairs_included"] == [128, 132, 137]
    assert manifest["blocked_implementation_issue"] == 125
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
    assert manifest["paid_execution_authorized"] is False
    assert manifest["limits"] == {
        "max_cases": 1,
        "max_provider_requests": 2,
        "max_input_tokens": 40_000,
        "max_output_tokens_per_request": PROOF_REVIEW_MAX_OUTPUT_TOKENS,
        "max_output_tokens": 2 * PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    }

    predecessor = _load(ROOT / str(manifest["predecessor_manifest"]))
    predecessor_case = next(
        item for item in predecessor["cases"] if item["id"] == "A3"
    )
    for field in ("path", "source_sha256", "target", "variation_family"):
        assert case[field] == predecessor_case[field]
    assert case["predecessor_initial_request_fingerprint"] == PREDECESSOR_FINGERPRINT
    assert predecessor_case["initial_request_fingerprint"] == PREDECESSOR_FINGERPRINT
    assert case["initial_request_fingerprint"] == FROZEN_FINGERPRINT
    assert FROZEN_FINGERPRINT != PREDECESSOR_FINGERPRINT
    assert _sha256(ROOT / str(case["path"])) == case["source_sha256"]

    if _src_tree_sha() != FROZEN_SRC_TREE:
        return

    project = extract_project(ROOT / str(case["path"]))
    prepared = prepare_proof_review(project, project.unit(str(case["target"])))
    initial = build_proof_review_turn(
        ProofLanguageReviewRequest(document=prepared.document)
    )
    envelope = proof_review_request_envelope(initial, str(manifest["model"]))
    assert initial.representation == manifest["representation"]
    assert initial.protocol_version == manifest["protocol"]
    assert initial.source_rescue_allowed
    assert initial.max_source_addresses == DEFAULT_MAX_SOURCE_REQUESTS
    assert envelope.fingerprint() == FROZEN_FINGERPRINT
    assert envelope.max_output_tokens == PROOF_REVIEW_MAX_OUTPUT_TOKENS


def test_a3_post137_preflight_is_keyless_and_exact(tmp_path: Path) -> None:
    output = tmp_path / "preflight.json"
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_issue_134_a3_post137.py",
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
        f"A3 post-137 preflight failed\nstdout:\n{completed.stdout}"
        f"\nstderr:\n{completed.stderr}"
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["issue"] == 134
    assert payload["experiment_id"] == "issue-134-a3-post137-pre125"
    assert payload["status"] == "frozen-keylessly-live-not-authorized"
    assert payload["provider_instantiated"] is False
    assert payload["provider_requests"] == 0
    assert payload["live_requests"] == 0
    assert payload["live_authorized"] is False
    case = payload["case"]
    assert case["id"] == "A3"
    assert case["initial_request_fingerprint"] == FROZEN_FINGERPRINT
    assert case["predecessor_initial_request_fingerprint"] == PREDECESSOR_FINGERPRINT
    assert case["fingerprint_changed_by_post137_contract"] is True
    assert case["frozen_request_contract_verified"] is True
    assert case["initial_input_token_upper_bound"] == 10_573
    assert case["hypothetical_maximal_two_turn_input_upper_bound"] == 28_101
    assert payload["limits"]["max_input_tokens"] == 40_000


def test_a3_post137_live_without_explicit_credentials_is_fail_closed(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["OPENAI_API_KEY"] = ""
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_issue_134_a3_post137.py",
            "--live",
            "--record-dir",
            str(tmp_path / "recordings"),
            "--output",
            str(tmp_path / "live.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode != 0
    assert "OPENAI_API_KEY is required with --live" in completed.stderr
    assert not (tmp_path / "live.json").exists()
