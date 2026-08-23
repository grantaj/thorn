#!/usr/bin/env python3
"""Build the keyless production-boundary evidence required by issue #198."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from thorn.frontends import DEFAULT_FRONTEND_NAME, get_frontend
from thorn.frontends.tree_sitter_identity import (
    TREE_SITTER_LANGUAGE_PACK_RELEASE,
    TREE_SITTER_LANGUAGE_PACK_VERSION,
    TREE_SITTER_LATEX_REVISION,
    TREE_SITTER_RUNTIME_VERSION,
)
from thorn.latex import extract_project
from thorn.llm_proof_language import (
    FORMAT_VERSION,
    parse_source_rescue_request,
    render_source_rescue,
)
from thorn.proof_language_review import (
    PROMPT_VERSION,
    PROTOCOL_VERSION,
    ProofLanguageReviewRequest,
    advertised_source_addresses,
    build_proof_review_turn,
)
from thorn.providers.execution_contract import (
    build_provider_execution_contract,
    provider_runtime_matches_lock,
)
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.review_workflow import prepare_proof_review
from thorn.spacy_linguistic import SpacyLinguisticFrontend

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "eval" / "robustness" / "issue_198" / "qualification_manifest.json"
DEFAULT_OUTPUT = ROOT / "eval" / "robustness" / "issue_198" / "preflight.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).strip()


def _relative_file(value: str) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _normalize_paths(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"file", "root_file", "resolved_file"} and isinstance(item, str):
                normalized[key] = _relative_file(item)
            else:
                normalized[key] = _normalize_paths(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_paths(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_paths(item) for item in value]
    return value


def _installed_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not-installed"


def _runtime_identity() -> dict[str, str]:
    return {
        "spacy": _installed_version("spacy"),
        "spacy_model": "en_core_web_sm",
        "spacy_model_version": _installed_version("en-core-web-sm"),
        "tree_sitter_runtime": _installed_version("tree-sitter"),
        "tree_sitter_language_pack": _installed_version("tree-sitter-language-pack"),
    }


def _expect_equal(errors: list[str], label: str, actual: object, expected: object) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def _matching_sources(document: Any, needle: str) -> list[Any]:
    return [source for source in document.sources if needle in source.text]


def _case_evidence(case: dict[str, Any], model: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    source = ROOT / case["source"]
    if not source.is_file():
        return {"id": case["id"], "source": case["source"]}, [
            f"{case['id']}: missing source {case['source']}"
        ]

    actual_hash = _sha256(source)
    _expect_equal(
        errors,
        f"{case['id']} source sha256",
        actual_hash,
        case["source_sha256"],
    )

    project = extract_project(
        source,
        frontend=get_frontend(DEFAULT_FRONTEND_NAME),
        linguistic_frontend=SpacyLinguisticFrontend(model_name="en_core_web_sm"),
    )
    workspace = project.workspace
    if workspace is None:
        errors.append(f"{case['id']}: project workspace facts are unavailable")
    elif workspace.resolution.value != "resolved":
        errors.append(
            f"{case['id']}: workspace resolution is {workspace.resolution.value!r}, "
            "expected 'resolved'"
        )

    prose = project.prose_declarations
    if prose is None:
        errors.append(f"{case['id']}: prose declaration inventory is unavailable")
    elif prose.capability.value != "complete":
        errors.append(
            f"{case['id']}: prose declaration capability is {prose.capability.value!r}, "
            "expected 'complete'"
        )

    unit = project.unit(case["target"])
    prepared = prepare_proof_review(project, unit)
    document = prepared.document
    packet = document.render_initial()
    advertised = tuple(advertised_source_addresses(document))
    advertised_set = set(advertised)

    reachable: list[dict[str, Any]] = []
    for needle in case["required_reachable_sources"]:
        matches = _matching_sources(document, needle)
        if len(matches) != 1:
            errors.append(
                f"{case['id']}: expected exactly one semantic source containing {needle!r}, "
                f"got {len(matches)}"
            )
            continue
        handle = matches[0]
        if handle.address not in advertised_set:
            errors.append(
                f"{case['id']}: semantic source {handle.address!r} for {needle!r} is not advertised"
            )
            continue
        rescue = render_source_rescue(
            document,
            parse_source_rescue_request(document, f"NEED_SOURCE {handle.address}"),
        )
        if needle not in rescue.text:
            errors.append(
                f"{case['id']}: bounded rescue for {handle.address!r} omitted {needle!r}"
            )
        reachable.append(
            {
                "needle": needle,
                "address": handle.address,
                "source": _normalize_paths(handle.model_dump(mode="json")),
                "rescue": rescue.text,
            }
        )

    for needle in case["required_absent_from_initial"]:
        if needle in packet:
            errors.append(
                f"{case['id']}: source-only semantic context leaked into initial packet: {needle!r}"
            )

    all_source_text = "\n".join(item.text for item in document.sources)
    for needle in case["irrelevant_source_needles"]:
        if needle in all_source_text or needle in packet:
            errors.append(
                f"{case['id']}: irrelevant nearby prose was retained in review reachability: "
                f"{needle!r}"
            )

    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=document))
    envelope = proof_review_request_envelope(turn, model)
    contract = build_provider_execution_contract(envelope)
    if not provider_runtime_matches_lock(contract.runtime):
        errors.append(f"{case['id']}: provider runtime does not match the packaged lock")

    evidence = {
        "id": case["id"],
        "source": case["source"],
        "source_sha256": actual_hash,
        "target": case["target"],
        "expected_scientific_class": case["expected_scientific_class"],
        "target_source": _normalize_paths(unit.statement_range.model_dump(mode="json")),
        "workspace": (
            _normalize_paths(workspace.model_dump(mode="json")) if workspace is not None else None
        ),
        "prose_declarations": (
            _normalize_paths(prose.model_dump(mode="json")) if prose is not None else None
        ),
        "thorn_proof": {
            "format": document.format_version,
            "fingerprint": document.fingerprint(),
            "initial_packet": packet,
            "source_handles": [
                _normalize_paths(item.model_dump(mode="json")) for item in document.sources
            ],
            "advertised_source_addresses": list(advertised),
            "validated_reachable_context": reachable,
        },
        "review_request": {
            "protocol": turn.protocol_version,
            "representation": turn.representation,
            "stage": turn.stage,
            "initial_packet_fingerprint": turn.initial_packet_fingerprint,
            "semantic_envelope_fingerprint": envelope.fingerprint(),
            "execution_fingerprint": contract.fingerprint(),
            "transport_profile": contract.transport_profile().model_dump(mode="json"),
            "provider_runtime": contract.runtime.model_dump(mode="json"),
        },
        "checks": {
            "status": "pass" if not errors else "fail",
            "errors": errors,
        },
    }
    return evidence, errors


def build_preflight(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if os.environ.get("OPENAI_API_KEY"):
        errors.append("OPENAI_API_KEY must be absent/empty for issue #198 Phase 1")

    production = manifest["production_identity"]
    review = manifest["review_identity"]
    runtime = _runtime_identity()

    _expect_equal(errors, "default frontend", DEFAULT_FRONTEND_NAME, production["default_frontend"])
    _expect_equal(
        errors,
        "tree-sitter runtime constant",
        TREE_SITTER_RUNTIME_VERSION,
        production["tree_sitter_runtime"],
    )
    _expect_equal(
        errors,
        "tree-sitter language-pack constant",
        TREE_SITTER_LANGUAGE_PACK_VERSION,
        production["tree_sitter_language_pack"],
    )
    _expect_equal(
        errors,
        "tree-sitter language-pack release",
        TREE_SITTER_LANGUAGE_PACK_RELEASE,
        production["tree_sitter_language_pack_release"],
    )
    _expect_equal(
        errors,
        "tree-sitter-latex revision",
        TREE_SITTER_LATEX_REVISION,
        production["tree_sitter_latex_revision"],
    )
    _expect_equal(errors, "installed spaCy", runtime["spacy"], production["spacy"])
    _expect_equal(
        errors,
        "installed spaCy model",
        runtime["spacy_model_version"],
        production["spacy_model_version"],
    )
    _expect_equal(
        errors,
        "installed tree-sitter",
        runtime["tree_sitter_runtime"],
        production["tree_sitter_runtime"],
    )
    _expect_equal(
        errors,
        "installed tree-sitter-language-pack",
        runtime["tree_sitter_language_pack"],
        production["tree_sitter_language_pack"],
    )
    _expect_equal(errors, "review representation", FORMAT_VERSION, review["representation"])
    _expect_equal(errors, "review protocol", PROTOCOL_VERSION, review["protocol"])
    _expect_equal(errors, "review prompt", PROMPT_VERSION, review["prompt"])

    baseline = manifest["production_revision"]
    try:
        baseline_src_tree = _git("rev-parse", f"{baseline}:src/thorn")
        current_src_tree = _git("rev-parse", "HEAD:src/thorn")
    except subprocess.CalledProcessError as exc:
        baseline_src_tree = "unavailable"
        current_src_tree = "unavailable"
        errors.append(f"could not compare frozen/current src/thorn trees: {exc}")
    else:
        _expect_equal(
            errors,
            "current production source tree",
            current_src_tree,
            baseline_src_tree,
        )

    cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        try:
            evidence, case_errors = _case_evidence(case, review["prospective_model"])
        except Exception as exc:
            evidence = {
                "id": case["id"],
                "source": case["source"],
                "target": case["target"],
                "checks": {
                    "status": "fail",
                    "errors": [f"{type(exc).__name__}: {exc}"],
                },
            }
            case_errors = [f"{case['id']}: {type(exc).__name__}: {exc}"]
        cases.append(evidence)
        errors.extend(case_errors)

    return {
        "format": "thorn-issue-198-preflight/1",
        "issue": 198,
        "phase": "keyless-production-preflight",
        "status": "pass" if not errors else "blocked",
        "provider_instantiated": False,
        "provider_call_made": False,
        "paid_execution_authorized": False,
        "production_revision": baseline,
        "execution_revision": _git("rev-parse", "HEAD"),
        "production_src_tree": baseline_src_tree,
        "execution_src_tree": current_src_tree,
        "production_identity": production,
        "runtime_identity": runtime,
        "review_identity": review,
        "manifest_sha256": _sha256(manifest_path),
        "cases": cases,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    result = build_preflight(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
