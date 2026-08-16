from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from thorn.eval import CaseExpectation
from thorn.linguistic import LinguisticFrontend
from thorn.llm_proof_language import LLMProofLanguage
from thorn.local_nlp import select_linguistic_frontend
from thorn.models import TheoremUnit
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
from thorn.proof_review_eval import (
    ProofReviewChallengeEntry,
    build_case_proof_document,
    current_thorn_revision,
    load_proof_review_manifest,
)
from thorn.providers.base import EvaluationProvider
from thorn.providers.replay import RecordingProvider, ReplayProvider
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.spacy_linguistic import SpacyLinguisticFrontend


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
            "Run the frozen proof-review A/B/C experiment live or from exact replay. "
            "Live use requires explicit --live and should only be used after authorization."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval/proof-review-challenge.json"),
    )
    parser.add_argument("--model", default="gpt-5.6")
    parser.add_argument("--seed", type=int, default=78)
    parser.add_argument("--structural-only", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay-dir", type=Path)
    parser.add_argument(
        "--record-dir",
        type=Path,
        help="required with --live; exact exchanges are written here",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _usage(provider: EvaluationProvider) -> dict[str, int]:
    return {
        "requests": provider.requests,
        "input_tokens": provider.input_tokens,
        "output_tokens": provider.output_tokens,
        "total_tokens": provider.total_tokens,
    }


def _usage_delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


def _single_turn_findings(response: ProofReviewModelResponse) -> list[dict[str, object]]:
    if response.action != "review":
        raise ProofReviewProtocolError(
            "model requested source in an experiment arm where rescue is disabled"
        )
    return [finding.model_dump(mode="json") for finding in response.findings]


def _rescue_payload(turn: ProofReviewTurnRequest) -> str:
    if turn.stage != "rescue":
        return ""
    parts = turn.user_content.split("\n\n", 1)
    if len(parts) != 2:
        raise ProofReviewProtocolError("rescue turn is missing its exact source payload")
    return parts[1]


def _metric_int(item: dict[str, object], key: str) -> int:
    value = item[key]
    if not isinstance(value, int):
        raise TypeError(f"result metric {key!r} is not an integer")
    return value


def _arm_metrics(
    results: list[dict[str, object]],
) -> dict[ProofReviewExperimentArm, dict[str, object]]:
    metrics: dict[ProofReviewExperimentArm, dict[str, object]] = {}
    for arm in PROOF_REVIEW_EXPERIMENT_ARMS:
        arm_results = [item for item in results if item["arm"] == arm]
        runs = len(arm_results)
        rescues = sum(bool(item["source_rescued"]) for item in arm_results)
        clean_controls = [item for item in arm_results if item["expected_clean"] is True]
        defect_cases = [item for item in arm_results if item["expected_clean"] is False]
        metrics[arm] = {
            "runs": runs,
            "clean_controls": len(clean_controls),
            "defect_cases": len(defect_cases),
            "candidate_clean_findings": sum(
                _metric_int(item, "finding_count") for item in clean_controls
            ),
            "candidate_defect_cases_with_findings": sum(
                _metric_int(item, "finding_count") > 0 for item in defect_cases
            ),
            "planted_defect_recall": None,
            "false_positives_on_clean_controls": None,
            "mathematical_explanation_correct": None,
            "adjudication_status": (
                "pending manual mathematical reasoning review; category/finding presence "
                "alone is not scored as correctness"
            ),
            "source_rescue_frequency": rescues / runs if runs else 0.0,
            "source_rescue_runs": rescues,
            "initial_characters": sum(
                _metric_int(item, "initial_characters") for item in arm_results
            ),
            "initial_utf8_bytes": sum(
                _metric_int(item, "initial_utf8_bytes") for item in arm_results
            ),
            "rescued_source_characters": sum(
                _metric_int(item, "rescued_source_characters") for item in arm_results
            ),
            "rescued_source_utf8_bytes": sum(
                _metric_int(item, "rescued_source_utf8_bytes") for item in arm_results
            ),
            "requests": sum(_metric_int(item, "requests") for item in arm_results),
            "input_tokens": sum(_metric_int(item, "input_tokens") for item in arm_results),
            "output_tokens": sum(_metric_int(item, "output_tokens") for item in arm_results),
            "total_tokens": sum(_metric_int(item, "total_tokens") for item in arm_results),
            "cost": None,
        }
    return metrics


def _build_provider(args: argparse.Namespace) -> tuple[EvaluationProvider, str, str]:
    if args.live and args.record_dir is None:
        raise SystemExit("--record-dir is required with --live")
    if args.live:
        from thorn.providers.openai import OpenAIProvider

        provider: EvaluationProvider = RecordingProvider(
            OpenAIProvider(model=args.model),
            args.record_dir,
        )
        return provider, "live", str(args.record_dir)

    if args.record_dir is not None:
        raise SystemExit("--record-dir is only valid with --live")
    if args.replay_dir is None:
        raise SystemExit("--replay-dir is required unless --live is selected")
    return ReplayProvider(args.model, args.replay_dir), "replay", str(args.replay_dir)


def _build_cases(
    manifest_path: Path,
    *,
    structural_only: bool,
) -> tuple[
    dict[
        str,
        tuple[
            CaseExpectation,
            TheoremUnit,
            LLMProofLanguage,
            ProofReviewChallengeEntry,
        ],
    ],
    LinguisticFrontend | None,
]:
    manifest = load_proof_review_manifest(manifest_path)
    linguistic_frontend = select_linguistic_frontend(
        structural_only=structural_only,
        factory=SpacyLinguisticFrontend,
    )
    case_data: dict[
        str,
        tuple[
            CaseExpectation,
            TheoremUnit,
            LLMProofLanguage,
            ProofReviewChallengeEntry,
        ],
    ] = {}
    for entry in manifest.cases:
        expectation, unit, document = build_case_proof_document(
            Path(entry.metadata),
            linguistic_frontend=linguistic_frontend,
        )
        case_data[entry.metadata] = (expectation, unit, document, entry)
    return case_data, linguistic_frontend


def main() -> int:
    args = _parser().parse_args()
    provider, mode_name, recording_directory = _build_provider(args)
    case_data, _linguistic_frontend = _build_cases(
        args.manifest,
        structural_only=args.structural_only,
    )

    work: list[tuple[str, ProofReviewExperimentArm]] = [
        (metadata, arm)
        for metadata in case_data
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS
    ]
    random.Random(args.seed).shuffle(work)
    results: list[dict[str, object]] = []
    rescue_count = 0

    for metadata, arm in work:
        expectation, unit, document, entry = case_data[metadata]
        capture = _CaptureTransport(provider)
        before = _usage(provider)
        protocol_error: str | None = None
        findings: list[dict[str, object]] = []
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
        envelopes = [
            proof_review_request_envelope(turn, args.model) for turn in capture.turns
        ]
        rescue_turns = [turn for turn in capture.turns if turn.stage == "rescue"]
        model_requested_addresses = [
            address
            for response in capture.responses
            if response.action == "need_source"
            for address in response.source_addresses
        ]
        rescued_addresses = [
            address
            for turn in rescue_turns
            for address in turn.requested_source_addresses
        ]
        rescued_payloads = [_rescue_payload(turn) for turn in rescue_turns]
        rescued_source_characters = sum(len(payload) for payload in rescued_payloads)
        rescued_source_bytes = sum(
            len(payload.encode("utf-8")) for payload in rescued_payloads
        )
        rescue_turn_characters = sum(len(turn.user_content) for turn in rescue_turns)
        rescue_turn_bytes = sum(
            len(turn.user_content.encode("utf-8")) for turn in rescue_turns
        )
        if rescue_turns:
            rescue_count += 1

        initial = proof_review_experiment_turn(unit, document, arm)
        initial_envelope = proof_review_request_envelope(initial, args.model)
        results.append(
            {
                "metadata": metadata,
                "case_name": expectation.name,
                "target_identifier": unit.identifier,
                "role": entry.role,
                "expected_issue": entry.expected_issue,
                "expected_clean": entry.role == "clean",
                "arm": arm,
                "protocol_error": protocol_error,
                "findings": findings,
                "finding_count": len(findings),
                "source_rescued": bool(rescue_turns),
                "source_addresses_requested": model_requested_addresses,
                "source_addresses_rescued": rescued_addresses,
                "initial_characters": len(initial_envelope.user_content),
                "initial_utf8_bytes": len(initial_envelope.user_content.encode("utf-8")),
                "rescued_source_characters": rescued_source_characters,
                "rescued_source_utf8_bytes": rescued_source_bytes,
                "rescue_turn_characters": rescue_turn_characters,
                "rescue_turn_utf8_bytes": rescue_turn_bytes,
                "requests": usage["requests"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "total_tokens": usage["total_tokens"],
                "cost": None,
                "request_fingerprints": [
                    envelope.fingerprint() for envelope in envelopes
                ],
                "initial_packet_fingerprint": initial.initial_packet_fingerprint,
                "mathematical_explanation_correct": None,
                "scoring_note": (
                    "manual adjudication required: taxonomy agreement alone is not correctness"
                ),
            }
        )

    output = {
        "issue": 78,
        "mode": mode_name,
        "manifest": str(args.manifest),
        "thorn_revision": current_thorn_revision(),
        "model": args.model,
        "seed": args.seed,
        "arms": list(PROOF_REVIEW_EXPERIMENT_ARMS),
        "system_prompt_policy": "identical across all arms",
        "response_schema_policy": "identical across all arms",
        "defender": False,
        "recording_directory": recording_directory,
        "cases": len(case_data),
        "arm_runs": len(results),
        "source_rescue_runs": rescue_count,
        "provider_requests": provider.requests,
        "live_requests": provider.live_requests,
        "input_tokens": provider.input_tokens,
        "output_tokens": provider.output_tokens,
        "total_tokens": provider.total_tokens,
        "cost": None,
        "cost_note": (
            "not available from the provider response; fill only from authoritative billing data"
        ),
        "requires_manual_mathematical_adjudication": True,
        "arm_metrics": _arm_metrics(results),
        "results": results,
    }
    rendered = json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
