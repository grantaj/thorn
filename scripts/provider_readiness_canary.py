from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from thorn.provider_readiness import (
    ProviderReadinessEvidence,
    preflight_readiness,
    run_live_readiness,
    verify_readiness_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_tree_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD:src/thorn"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _run_id() -> str:
    return os.getenv("GITHUB_RUN_ID", "local")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exercise Thorn's bounded synthetic provider-readiness boundary."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true", help="construct exact requests keylessly")
    mode.add_argument(
        "--live",
        action="store_true",
        help="make bounded synthetic initial and rescue provider calls",
    )
    mode.add_argument("--replay", type=Path, help="keylessly verify successful live evidence")
    parser.add_argument("--model", help="exact provider model alias for preflight/live")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--confirm-paid-readiness-canary",
        action="store_true",
        help="second explicit guard required with --live; grants no scientific authorization",
    )
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()

    if args.replay is not None:
        if args.model is not None:
            parser.error("--model is read from evidence in --replay mode")
        evidence = ProviderReadinessEvidence.model_validate_json(
            args.replay.read_text(encoding="utf-8")
        )
        initial, rescue = verify_readiness_evidence(evidence)
        _write_json(
            args.output,
            {
                "format": "thorn-provider-readiness-replay/2",
                "status": "replay-verified",
                "readiness_only": True,
                "scientific_authorization": False,
                "model": evidence.model,
                "run_id": evidence.run_id,
                "boundary_source_tree_sha": evidence.boundary_source_tree_sha,
                "execution_fingerprint": evidence.execution_fingerprint,
                "rescue_execution_fingerprint": evidence.rescue_execution_fingerprint,
                "transport_profile_fingerprints": [
                    profile.fingerprint() for profile in evidence.transport_profiles
                ],
                "normalized_response": initial.model_dump(mode="json"),
                "rescue_normalized_response": rescue.model_dump(mode="json"),
            },
        )
        return 0

    if not args.model:
        parser.error("--model is required with --preflight or --live")

    identity = {
        "boundary_source_tree_sha": _source_tree_sha(),
        "run_id": _run_id(),
    }
    if args.live:
        if not args.confirm_paid_readiness_canary:
            parser.error("--live requires --confirm-paid-readiness-canary")
        evidence = run_live_readiness(args.model, **identity)
        _write_json(args.output, evidence.model_dump(mode="json"))
        return 0 if evidence.status == "live-success" else 2

    if args.confirm_paid_readiness_canary:
        parser.error("--confirm-paid-readiness-canary is only valid with --live")
    evidence = preflight_readiness(args.model, **identity)
    _write_json(args.output, evidence.model_dump(mode="json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
