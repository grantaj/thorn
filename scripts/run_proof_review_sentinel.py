from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from thorn.proof_language_experiment import (
    PROOF_REVIEW_EXPERIMENT_ARMS,
    ProofReviewExperimentArm,
    proof_review_experiment_turn,
)
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTransport,
    ProofReviewTurnRequest,
    review_proof_language,
)
from thorn.proof_review_sentinel import (
    build_proof_review_sentinel_inventory,
    build_sentinel_case_data,
    load_proof_review_sentinel_manifest,
)
from thorn.providers.base import EvaluationProvider
from thorn.providers.replay import RecordingProvider, ReplayProvider
from thorn.providers.request_envelope import proof_review_request_envelope


class _CaptureTransport:
    def __init__(self, delegate: ProofReviewTransport) -> None:
        self.delegate = delegate
        self.model = delegate.model
        self.turns: list[ProofReviewTurnRequest] = []
        self.responses: list[ProofReviewModelResponse] = []

    def review_proof_turn(
        self,
        request: ProofReviewTurnRequest,
    ) -> ProofReviewModelResponse:
        self.turns.append(request)
        response = self.delegate.review_proof_turn(request)
        self.responses.append(response)
        return response


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen post-#90 two-case proof-review v2 sentinel. "
            "Live mode is allowed only for an exact frozen keyless preflight."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval/proof-review-v2-sentinel/manifest.json"),
    )
    parser.add_argument("--structural-only", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay-dir", type=Path)
    parser.add_argument("--record-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _usage(provider: EvaluationProvider) -> dict[str, int]:
    return {
        "requests": provider.requests,
        "live_requests": provider.live_requests,
        "input_tokens": provider.input_tokens,
        "output_tokens": provider.output_tokens,
        "total_tokens": provider.total_tokens,
    }


def _usage_delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


def _single_turn_findings(response: ProofReviewModelResponse) -> list[dict[str, object]]:
    if response.action != "review":
        raise ProofReviewProtocolError(
            "model requested source in a sentinel arm where rescue is disabled"
        )
    return [finding.model_dump(mode="json") for finding in response.findings]


def _rescue_payload(turn: ProofReviewTurnRequest) -> str:
    if turn.stage != "rescue":
        return ""
    parts = turn.user_content.split("\n\n", 1)
    if len(parts) != 2:
        raise ProofReviewProtocolError("rescue turn is missing its exact source payload")
    return parts[1]


def _build_provider(
    *,
    live: bool,
    model: str,
    record_dir: Path | None,
    replay_dir: Path | None,
) -> tuple[EvaluationProvider, str, str]:
    if live:
        if record_dir is None:
            raise SystemExit("--record-dir is required with --live")
        from thorn.providers.openai import OpenAIProvider

        underlying = OpenAIProvider(model=model)
        if underlying.client.max_retries != 0:
            raise SystemExit("live sentinel requires OpenAI SDK max_retries=0")
        provider: EvaluationProvider = RecordingProvider(underlying, record_dir)
        return provider, "live", str(record_dir)

    if record_dir is not None:
        raise SystemExit("--record-dir is only valid with --live")
    if replay_dir is None:
        raise SystemExit("--replay-dir is required unless --live is selected")
    return ReplayProvider(model, replay_dir), "replay", str(replay_dir)


def _freeze_sha256(inventory: dict[str, object]) -> str:
    freeze = inventory["freeze_candidate"]
    rendered = json.dumps(
        freeze,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def main() -> int:
    args = _parser().parse_args()
    manifest = load_proof_review_sentinel_manifest(args.manifest)

    if args.live and args.structural_only:
        raise SystemExit("live sentinel must use the normal local-NLP frontend")
    if args.live and not manifest.frozen:
        raise SystemExit("live sentinel is forbidden until the manifest is frozen")

    # This keyless preflight runs before any provider is constructed. In live mode
    # it must exactly match all six request contracts frozen in the manifest.
    inventory = build_proof_review_sentinel_inventory(
        args.manifest,
        structural_only=args.structural_only,
    )
    if args.live and inventory["frozen_request_contract_verified"] is not True:
        raise SystemExit("live sentinel request freeze did not verify")

    case_data = build_sentinel_case_data(
        manifest,
        structural_only=args.structural_only,
    )
    provider, mode_name, recording_directory = _build_provider(
        live=args.live,
        model=manifest.model,
        record_dir=args.record_dir,
        replay_dir=args.replay_dir,
    )

    work: list[tuple[int, ProofReviewExperimentArm]] = [
        (case_index, arm)
        for case_index in range(len(case_data))
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS
    ]
    random.Random(manifest.seed).shuffle(work)

    results: list[dict[str, object]] = []
    for case_index, arm in work:
        entry, expectation, unit, document = case_data[case_index]
        capture = _CaptureTransport(provider)
        before = _usage(provider)
        findings: list[dict[str, object]] = []
        protocol_error: str | None = None

        try:
            if arm == "proof_ir_rescue":
                report = review_proof_language(
                    ProofLanguageReviewRequest(
                        document=document,
                        allow_source_rescue=True,
                    ),
                    capture,
                )
                findings = [
                    finding.model_dump(mode="json") for finding in report.findings
                ]
            else:
                turn = proof_review_experiment_turn(unit, document, arm)
                response = capture.review_proof_turn(turn)
                findings = _single_turn_findings(response)
        except ProofReviewProtocolError as exc:
            protocol_error = str(exc)

        after = _usage(provider)
        usage = _usage_delta(after, before)
        if provider.live_requests > manifest.max_live_requests:
            raise RuntimeError("sentinel exceeded its frozen live-request ceiling")

        envelopes = [
            proof_review_request_envelope(turn, manifest.model)
            for turn in capture.turns
        ]
        rescue_turns = [turn for turn in capture.turns if turn.stage == "rescue"]
        rescued_payloads = [_rescue_payload(turn) for turn in rescue_turns]

        results.append(
            {
                "metadata": entry.metadata,
                "case_name": expectation.name,
                "role": entry.role,
                "expected_issue": entry.expected_issue,
                "target_identifier": unit.identifier,
                "arm": arm,
                "protocol_error": protocol_error,
                "findings": findings,
                "finding_count": len(findings),
                "responses": [
                    response.model_dump(mode="json") for response in capture.responses
                ],
                "source_rescued": bool(rescue_turns),
                "source_addresses_requested": [
                    address
                    for response in capture.responses
                    if response.action == "need_source"
                    for address in response.source_addresses
                ],
                "source_addresses_rescued": [
                    address
                    for turn in rescue_turns
                    for address in turn.requested_source_addresses
                ],
                "rescued_source_payloads": rescued_payloads,
                "requests": usage["requests"],
                "live_requests": usage["live_requests"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["total_tokens"],
                "request_fingerprints": [
                    envelope.fingerprint() for envelope in envelopes
                ],
                "initial_packet_fingerprint": (
                    envelopes[0].initial_packet_fingerprint if envelopes else None
                ),
                "manual_adjudication": None,
            }
        )

    output = {
        "experiment": manifest.experiment,
        "issue": manifest.issue,
        "mode": mode_name,
        "manifest": str(args.manifest),
        "thorn_base_revision": manifest.thorn_base_revision,
        "model": manifest.model,
        "seed": manifest.seed,
        "max_output_tokens": manifest.max_output_tokens,
        "sdk_max_retries": manifest.sdk_max_retries,
        "max_live_requests": manifest.max_live_requests,
        "frozen_request_contract_verified": inventory[
            "frozen_request_contract_verified"
        ],
        "freeze_candidate_sha256": _freeze_sha256(inventory),
        "recording_directory": recording_directory,
        "cases": len(case_data),
        "arm_runs": len(results),
        "provider_requests": provider.requests,
        "live_requests": provider.live_requests,
        "input_tokens": provider.input_tokens,
        "output_tokens": provider.output_tokens,
        "total_tokens": provider.total_tokens,
        "requires_manual_mathematical_adjudication": True,
        "intended_scoring": manifest.intended_scoring,
        "results": results,
    }
    if args.live and provider.live_requests > manifest.max_live_requests:
        raise RuntimeError("live request ceiling exceeded")

    rendered = json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
