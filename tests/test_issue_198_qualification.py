from __future__ import annotations

import hashlib
import json
from pathlib import Path

from thorn.frontends import DEFAULT_FRONTEND_NAME
from thorn.frontends.tree_sitter_identity import (
    TREE_SITTER_LANGUAGE_PACK_RELEASE,
    TREE_SITTER_LANGUAGE_PACK_VERSION,
    TREE_SITTER_LATEX_REVISION,
    TREE_SITTER_RUNTIME_VERSION,
)
from thorn.llm_proof_language import FORMAT_VERSION
from thorn.proof_language_review import PROMPT_VERSION, PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "eval" / "robustness" / "issue_198" / "qualification_manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_issue_198_freeze_matches_production_contract() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    production = manifest["production_identity"]
    review = manifest["review_identity"]

    assert manifest["production_revision"] == "dca454190eeb7fe5a8ebda93e71b6dea2be90820"
    assert DEFAULT_FRONTEND_NAME == production["default_frontend"] == "tree-sitter"
    assert TREE_SITTER_RUNTIME_VERSION == production["tree_sitter_runtime"] == "0.26.0"
    assert (
        TREE_SITTER_LANGUAGE_PACK_VERSION
        == production["tree_sitter_language_pack"]
        == "1.14.3"
    )
    assert production["tree_sitter_language_pack_release"] == TREE_SITTER_LANGUAGE_PACK_RELEASE
    assert production["tree_sitter_latex_revision"] == TREE_SITTER_LATEX_REVISION
    assert FORMAT_VERSION == review["representation"] == "thorn-proof/1"
    assert PROTOCOL_VERSION == review["protocol"] == "thorn-proof-review/2"
    assert PROMPT_VERSION == review["prompt"] == "proof_language_reviewer_v2"


def test_issue_198_case_set_is_frozen_before_live_measurement() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = manifest["cases"]

    assert [case["id"] for case in cases] == [
        "A2-prose-uniformity-defect",
        "heldout-diagonal-regular-clean",
        "C0-matched-clean-control",
    ]
    for case in cases:
        source = ROOT / case["source"]
        assert source.is_file()
        assert _sha256(source) == case["source_sha256"]

    assert cases[0]["target"] == "thm:uniform-decay"
    assert cases[0]["expected_scientific_class"] == "correct_defect"
    assert cases[1]["target"] == "thm:main"
    assert cases[1]["expected_scientific_class"] == "correct_clean"
    assert cases[2]["target"] == "thm:uniform-decay"
    assert cases[2]["expected_scientific_class"] == "correct_clean"
