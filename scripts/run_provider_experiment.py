from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thorn.experiment_runtime import (
    ExperimentFreezeError,
    GuardedProofReviewTransport,
    ProviderBudget,
    ProviderExperimentCase,
    ProviderExperimentManifest,
    ProviderUsageSnapshot,
    assert_manifest_runtime,
    assert_readiness_compatible,
)
from thorn.latex import extract_project
from thorn.llm_proof_language import FORMAT_VERSION
from thorn.proof_language_review import (
    PROMPT_VERSION,
    PROTOCOL_VERSION,
    ProofLanguageReviewRequest,
    build_proof_review_turn,
)
from thorn.provider_readiness import ProviderReadinessEvidence
from thorn.providers.execution_contract import (
    ProviderExecutionContract,
    build_provider_execution_contract,
)
from thorn.providers.openai import OpenAIProvider
from thorn.providers.replay import RecordingProvider, ReplayProvider
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    proof_review_request_envelope,
)
from thorn.review_workflow import PreparedProofReview, prepare_proof_review, run_proof_review

ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).resolve()
CONSTRAINTS = ROOT / "constraints" / "provider-runtime.txt"


@dataclass(frozen=True)
class PreparedExperimentCase:
    case: ProviderExperimentCase
    prepared: PreparedProofReview
    initial_contract: ProviderExecutionContract


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _assert_manifest_freeze(manifest: ProviderExperimentManifest) -> None:
    if manifest.paid_execution_authorized:
        raise ExperimentFreezeError("experiment manifest must never authorize paid execution")

    frozen_src_tree = _git("rev-parse", f"{manifest.repository_revision}:src/thorn")
    if frozen_src_tree != manifest.src_tree_sha:
        raise ExperimentFreezeError(
            "frozen repository revision does not identify the manifest src/thorn tree"
        )
    if _git("rev-parse", "HEAD:src/thorn") != manifest.src_tree_sha:
        raise ExperimentFreezeError(
            "current src/thorn tree differs from frozen experiment manifest"
        )
    if _sha256(RUNNER) != manifest.runner_sha256:
        raise ExperimentFreezeError("manifest-driven experiment runner bytes drifted")
    if _sha256(CONSTRAINTS) != manifest.constraints_sha256:
        raise ExperimentFreezeError("provider runtime constraints drifted")
    if manifest.representation != FORMAT_VERSION:
        raise ExperimentFreezeError("proof-language representation version drifted")
    if manifest.protocol != PROTOCOL_VERSION:
        raise ExperimentFreezeError("proof-review protocol version drifted")
    if manifest.prompt_version != PROMPT_VERSION:
        raise ExperimentFreezeError("proof-review prompt version drifted")
    if manifest.budget.max_output_tokens_per_request != PROOF_REVIEW_MAX_OUTPUT_TOKENS:
        raise ExperimentFreezeError(
            "scientific runner requires the production proof-review output cap"
        )
    if len(manifest.cases) > manifest.budget.max_cases:
        raise ExperimentFreezeError("manifest contains more cases than its frozen case budget")
    assert_manifest_runtime(manifest)


def _prepare_case(
    manifest: ProviderExperimentManifest,
    case: ProviderExperimentCase,
) -> PreparedExperimentCase:
    path = ROOT / case.path
    if _sha256(path) != case.source_sha256:
        raise ExperimentFreezeError(f"source hash drifted for experiment case {case.id}")
    project = extract_project(path)
    prepared = prepare_proof_review(project, project.unit(case.target))
    if prepared.document.format_version != manifest.representation:
        raise ExperimentFreezeError(f"representation drifted for experiment case {case.id}")
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=prepared.document))
    if turn.protocol_version != manifest.protocol:
        raise ExperimentFreezeError(f"protocol drifted for experiment case {case.id}")
    envelope = proof_review_request_envelope(turn, manifest.model)
    contract = build_provider_execution_contract(envelope)
    if contract.fingerprint() != case.initial_execution_fingerprint:
        raise ExperimentFreezeError(
            f"initial execution fingerprint drifted for experiment case {case.id}"
        )
    return PreparedExperimentCase(case=case, prepared=prepared, initial_contract=contract)


def _prepare_manifest(
    manifest: ProviderExperimentManifest,
) -> tuple[PreparedExperimentCase, ...]:
    _assert_manifest_freeze(manifest)
    return tuple(_prepare_case(manifest, case) for case in manifest.cases)


def _preflight_payload(
    manifest: ProviderExperimentManifest,
    prepared: tuple[PreparedExperimentCase, ...],
) -> dict[str, object]:
    return {
        "format": "thorn-provider-experiment-preflight/1",
        "status": "preflight-ready",
        "provider_instantiated": False,
        "paid_execution_authorized": False,
        "experiment_id": manifest.experiment_id,
        "production_revision": manifest.repository_revision,
        "execution_revision": _git("rev-parse", "HEAD"),
        "runtime": manifest.runtime.model_dump(mode="json"),
        "budget": manifest.budget.model_dump(mode="json"),
        "cases": [
            {
                "id": item.case.id,
                "source_sha256": item.case.source_sha256,
                "initial_execution_fingerprint": item.initial_contract.fingerprint(),
                "initial_execution_contract": item.initial_contract.model_dump(mode="json"),
            }
            for item in prepared
        ],
    }


def _run_cases(
    manifest: ProviderExperimentManifest,
    prepared: tuple[PreparedExperimentCase, ...],
    provider: Any,
) -> dict[str, object]:
    budget = ProviderBudget(manifest.budget)
    results: list[dict[str, object]] = []
    for item in prepared:
        transport = GuardedProofReviewTransport(
            delegate=provider,
            budget=budget,
            expected_initial_fingerprint=item.initial_contract.fingerprint(),
        )
        completed = run_proof_review(item.prepared, transport)
        results.append(
            {
                "id": item.case.id,
                "report": completed.report.model_dump(mode="json"),
                "execution_fingerprints": [
                    contract.fingerprint() for contract in transport.contracts
                ],
                "execution_contracts": [
                    contract.model_dump(mode="json") for contract in transport.contracts
                ],
            }
        )
    usage = ProviderUsageSnapshot.capture(provider)
    return {
        "results": results,
        "usage": usage.model_dump(mode="json"),
        "budget": {
            "reserved_turns": budget.reserved_turns,
            "provider_attempts": budget.provider_attempts,
            "input_tokens": budget.input_tokens,
            "output_tokens": budget.output_tokens,
        },
    }


def _load_readiness(path: Path) -> ProviderReadinessEvidence:
    return ProviderReadinessEvidence.model_validate_json(path.read_text(encoding="utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run new provider-backed experiments from a frozen data manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay-dir", type=Path)
    parser.add_argument("--record-dir", type=Path)
    parser.add_argument("--readiness-evidence", type=Path)
    parser.add_argument("--confirm-paid-scientific-run", action="store_true")
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    manifest = ProviderExperimentManifest.load(args.manifest)
    prepared = _prepare_manifest(manifest)

    if args.preflight:
        if args.record_dir or args.readiness_evidence or args.confirm_paid_scientific_run:
            parser.error("preflight mode does not accept live execution arguments")
        _write_json(args.output, _preflight_payload(manifest, prepared))
        return 0

    if args.live:
        if args.record_dir is None:
            parser.error("--live requires --record-dir")
        if args.readiness_evidence is None:
            parser.error("--live requires --readiness-evidence")
        if not args.confirm_paid_scientific_run:
            parser.error("--live requires --confirm-paid-scientific-run")
        if not prepared:
            raise ExperimentFreezeError("live experiment manifest contains no cases")
        readiness = _load_readiness(args.readiness_evidence)
        assert_readiness_compatible(
            readiness,
            manifest=manifest,
            scientific_contract=prepared[0].initial_contract,
        )
        delegate = OpenAIProvider(model=manifest.model)
        provider: Any = RecordingProvider(delegate, args.record_dir)
        mode_name = "live"
    else:
        if args.record_dir or args.readiness_evidence or args.confirm_paid_scientific_run:
            parser.error("replay mode does not accept live execution arguments")
        assert args.replay_dir is not None
        provider = ReplayProvider(model=manifest.model, directory=args.replay_dir)
        mode_name = "replay"

    try:
        run = _run_cases(manifest, prepared, provider)
    except Exception as exc:
        _write_json(
            args.output,
            {
                "format": "thorn-provider-experiment-result/1",
                "status": "failed",
                "mode": mode_name,
                "experiment_id": manifest.experiment_id,
                "exception_type": type(exc).__name__,
                "message": str(exc),
                "usage": ProviderUsageSnapshot.capture(provider).model_dump(mode="json"),
            },
        )
        return 2

    if mode_name == "replay" and int(getattr(provider, "legacy_replay_hits", 0)):
        raise ExperimentFreezeError(
            "new scientific experiments may not use legacy v1 replay evidence"
        )

    _write_json(
        args.output,
        {
            "format": "thorn-provider-experiment-result/1",
            "status": "completed",
            "mode": mode_name,
            "experiment_id": manifest.experiment_id,
            "production_revision": manifest.repository_revision,
            "execution_revision": _git("rev-parse", "HEAD"),
            "runtime": manifest.runtime.model_dump(mode="json"),
            **run,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
