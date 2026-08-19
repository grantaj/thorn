from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from thorn.experiment_runtime import (
    ExperimentFreezeError,
    ProviderBudgetSpec,
    ProviderExperimentCase,
    ProviderExperimentManifest,
    ProviderReadinessFreeze,
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
from thorn.provider_readiness import ProviderReadinessEvidence, verify_readiness_evidence
from thorn.providers.execution_contract import (
    ProviderExecutionContract,
    build_provider_execution_contract,
    current_provider_runtime,
    provider_adapter_sha256,
    provider_lock_sha256,
    provider_runtime_matches_lock,
)
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    proof_review_request_envelope,
)
from thorn.review_workflow import prepare_proof_review

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_provider_experiment.py"
CONSTRAINTS = ROOT / "constraints" / "provider-runtime.txt"


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


def _relative_source(path_text: str) -> tuple[Path, str]:
    requested = Path(path_text)
    absolute = requested if requested.is_absolute() else ROOT / requested
    resolved = absolute.resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ExperimentFreezeError("experiment source must be inside the repository") from exc
    if not resolved.is_file():
        raise ExperimentFreezeError(f"experiment source does not exist: {relative}")
    return resolved, relative.as_posix()


def _case_contract(
    *,
    case_id: str,
    path_text: str,
    target: str,
    model: str,
) -> tuple[ProviderExperimentCase, ProviderExecutionContract]:
    source, relative = _relative_source(path_text)
    project = extract_project(source)
    prepared = prepare_proof_review(project, project.unit(target))
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=prepared.document))
    envelope = proof_review_request_envelope(
        turn,
        model,
        max_output_tokens=PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    )
    contract = build_provider_execution_contract(envelope)
    return (
        ProviderExperimentCase(
            id=case_id,
            path=relative,
            target=target,
            source_sha256=_sha256(source),
            initial_execution_fingerprint=contract.fingerprint(),
        ),
        contract,
    )


def _load_readiness(path: Path) -> ProviderReadinessEvidence:
    evidence = ProviderReadinessEvidence.model_validate_json(path.read_text(encoding="utf-8"))
    verify_readiness_evidence(evidence)
    return evidence


def _build_manifest(args: argparse.Namespace) -> ProviderExperimentManifest:
    readiness_path = args.readiness_evidence.resolve()
    readiness = _load_readiness(readiness_path)
    if readiness.model != args.model:
        raise ExperimentFreezeError("selected model differs from readiness evidence")

    runtime = current_provider_runtime()
    if not provider_runtime_matches_lock(runtime):
        raise ExperimentFreezeError(
            "installed provider dependency closure does not match Thorn's packaged runtime lock"
        )
    if _sha256(CONSTRAINTS) != provider_lock_sha256():
        raise ExperimentFreezeError(
            "repository provider constraints differ from Thorn's packaged runtime lock"
        )

    revision = _git("rev-parse", "HEAD")
    src_tree_sha = _git("rev-parse", "HEAD:src/thorn")
    if readiness.boundary_source_tree_sha != src_tree_sha:
        raise ExperimentFreezeError(
            "readiness evidence did not exercise the current production src/thorn tree"
        )
    if readiness.adapter_sha256 != provider_adapter_sha256():
        raise ExperimentFreezeError("readiness provider adapter is stale")
    if readiness.provider_lock_sha256 != provider_lock_sha256():
        raise ExperimentFreezeError("readiness provider runtime lock is stale")

    frozen_cases: list[ProviderExperimentCase] = []
    contracts: list[ProviderExecutionContract] = []
    seen_ids: set[str] = set()
    for case_id, path_text, target in args.case:
        if case_id in seen_ids:
            raise ExperimentFreezeError(f"duplicate experiment case id: {case_id}")
        seen_ids.add(case_id)
        frozen, contract = _case_contract(
            case_id=case_id,
            path_text=path_text,
            target=target,
            model=args.model,
        )
        frozen_cases.append(frozen)
        contracts.append(contract)

    if not frozen_cases:
        raise ExperimentFreezeError("at least one --case is required")
    if args.max_provider_attempts < len(frozen_cases):
        raise ExperimentFreezeError(
            "provider-attempt budget is smaller than the number of initial case turns"
        )

    budget = ProviderBudgetSpec(
        max_cases=len(frozen_cases),
        max_provider_attempts=args.max_provider_attempts,
        max_input_tokens=args.max_input_tokens,
        max_output_tokens_per_request=PROOF_REVIEW_MAX_OUTPUT_TOKENS,
        max_output_tokens=args.max_output_tokens,
    )
    readiness_freeze = ProviderReadinessFreeze(
        evidence_sha256=_sha256(readiness_path),
        run_id=readiness.run_id,
        generated_at=readiness.generated_at,
        boundary_source_tree_sha=readiness.boundary_source_tree_sha,
        adapter_sha256=readiness.adapter_sha256,
        provider_lock_sha256=readiness.provider_lock_sha256,
        transport_profile_fingerprints=tuple(
            profile.fingerprint() for profile in readiness.transport_profiles
        ),
        max_age_hours=args.max_readiness_age_hours,
    )
    manifest = ProviderExperimentManifest(
        experiment_id=args.experiment_id,
        repository_revision=revision,
        src_tree_sha=src_tree_sha,
        runner_sha256=_sha256(RUNNER),
        constraints_sha256=_sha256(CONSTRAINTS),
        model=args.model,
        representation=FORMAT_VERSION,
        protocol=PROTOCOL_VERSION,
        prompt_version=PROMPT_VERSION,
        runtime=runtime,
        readiness=readiness_freeze,
        budget=budget,
        cases=tuple(frozen_cases),
    )
    assert_readiness_compatible(
        readiness,
        evidence_sha256=readiness_freeze.evidence_sha256,
        manifest=manifest,
        scientific_contracts=tuple(contracts),
    )
    return manifest


def _round_trip_preflight(manifest_path: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="thorn-provider-preflight-") as temporary:
        output = Path(temporary) / "preflight.json"
        subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--manifest",
                str(manifest_path),
                "--output",
                str(output),
                "--preflight",
            ],
            cwd=ROOT,
            check=True,
        )
        payload = json.loads(output.read_text(encoding="utf-8"))
        if payload.get("status") != "preflight-ready":
            raise ExperimentFreezeError("generated manifest failed generic runner preflight")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze a provider experiment from human-selected cases/budgets plus successful "
            "readiness evidence. All reproducibility hashes are derived automatically."
        )
    )
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--readiness-evidence", required=True, type=Path)
    parser.add_argument(
        "--case",
        action="append",
        nargs=3,
        metavar=("ID", "PATH", "TARGET"),
        default=[],
        help="repeat for each scientific case; PATH must be repository-relative or inside repo",
    )
    parser.add_argument("--max-provider-attempts", required=True, type=int)
    parser.add_argument("--max-input-tokens", required=True, type=int)
    parser.add_argument("--max-output-tokens", required=True, type=int)
    parser.add_argument("--max-readiness-age-hours", type=int, default=24)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest = _build_manifest(args)
    _write_json(args.output, manifest.model_dump(mode="json"))
    _round_trip_preflight(args.output.resolve())
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
