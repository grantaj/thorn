#!/usr/bin/env python3
"""Freeze, run, or replay issue #134's pre-#125 A1/A2/A3 continuation.

Preflight is entirely keyless. Live mode exists only so a later separately
authorized run can use the exact frozen harness; invoking this file during the
freeze does not itself authorize provider calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from thorn.analysis import analyze_project
from thorn.latex import extract_project
from thorn.llm_proof_language import DEFAULT_MAX_SOURCE_REQUESTS, FORMAT_VERSION
from thorn.proof_language_review import (
    PROMPT_VERSION,
    PROTOCOL_VERSION,
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    ProofReviewTurnRequest,
    build_proof_review_turn,
)
from thorn.providers.replay import RecordingProvider, ReplayProvider
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    ProviderRequestEnvelope,
    proof_review_request_envelope,
)
from thorn.report import ProofReviewReportInput, ReviewExecution, build_report
from thorn.report_html import write_report_html
from thorn.review_workflow import PreparedProofReview, prepare_proof_review, run_proof_review

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "eval" / "robustness" / "issue_134"
MANIFEST = EXPERIMENT / "manifest.json"
EXPECTED_CASE_IDS = ("A1", "A2", "A3")
SERIALIZATION_FRAMING_RESERVE_TOKENS = 2_048


@dataclass(frozen=True)
class _PreparedCase:
    metadata: dict[str, Any]
    project: Any
    prepared: PreparedProofReview
    initial_turn: ProofReviewTurnRequest
    initial_envelope: ProviderRequestEnvelope

    @property
    def id(self) -> str:
        return str(self.metadata["id"])


@dataclass
class _Budget:
    max_provider_requests: int
    max_input_tokens: int
    max_output_tokens_per_request: int
    max_output_tokens: int
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def reserve(self, envelope: ProviderRequestEnvelope) -> None:
        if self.attempts + 1 > self.max_provider_requests:
            raise RuntimeError("issue #134 provider-request ceiling would be exceeded")
        input_bound = _conservative_input_token_bound(envelope)
        if self.input_tokens + input_bound > self.max_input_tokens:
            raise RuntimeError(
                "issue #134 input-token ceiling would be exceeded by the next exact request"
            )
        max_output = envelope.max_output_tokens
        if max_output != self.max_output_tokens_per_request:
            raise RuntimeError(
                "issue #134 request output cap drifted: "
                f"expected {self.max_output_tokens_per_request}, got {max_output}"
            )
        if self.output_tokens + max_output > self.max_output_tokens:
            raise RuntimeError("issue #134 aggregate output-token ceiling would be exceeded")
        self.attempts += 1

    def commit_usage(self, before: dict[str, int], after: dict[str, int]) -> None:
        requests = after["requests"] - before["requests"]
        input_tokens = after["input_tokens"] - before["input_tokens"]
        output_tokens = after["output_tokens"] - before["output_tokens"]
        if requests > 0 and input_tokens <= 0:
            raise RuntimeError(
                "provider returned no input-token accounting for a completed request"
            )
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.input_tokens > self.max_input_tokens:
            raise RuntimeError("provider-reported input usage exceeded issue #134 ceiling")
        if self.output_tokens > self.max_output_tokens:
            raise RuntimeError("provider-reported output usage exceeded issue #134 ceiling")


class _GuardedTransport:
    def __init__(
        self,
        delegate: Any,
        budget: _Budget,
        *,
        case_id: str,
        expected_initial_fingerprint: str,
    ) -> None:
        self.delegate = delegate
        self.budget = budget
        self.model = delegate.model
        self.case_id = case_id
        self.expected_initial_fingerprint = expected_initial_fingerprint
        self.envelopes: list[ProviderRequestEnvelope] = []

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(request, self.model)
        if (
            request.stage == "initial"
            and envelope.fingerprint() != self.expected_initial_fingerprint
        ):
            raise RuntimeError(f"{self.case_id}: frozen initial request fingerprint drifted")
        self.budget.reserve(envelope)
        before = _usage(self.delegate)
        try:
            response = self.delegate.review_proof_turn(request)
        finally:
            self.budget.commit_usage(before, _usage(self.delegate))
        self.envelopes.append(envelope)
        return response


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _runner_revision() -> str:
    return _git("rev-parse", "HEAD")


def _src_tree_sha() -> str:
    return _git("rev-parse", "HEAD:src/thorn")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _usage(provider: Any) -> dict[str, int]:
    return {
        "requests": int(provider.requests),
        "live_requests": int(provider.live_requests),
        "replay_hits": int(provider.replay_hits),
        "input_tokens": int(provider.input_tokens),
        "output_tokens": int(provider.output_tokens),
        "total_tokens": int(provider.total_tokens),
    }


def _usage_delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


def _conservative_input_token_bound(envelope: ProviderRequestEnvelope) -> int:
    return (
        len(envelope.canonical_json().encode("utf-8"))
        + SERIALIZATION_FRAMING_RESERVE_TOKENS
    )


def _load_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["issue"] != 134:
        raise RuntimeError("issue #134 manifest identity drifted")
    if manifest["experiment_id"] != "issue-134-pre-125":
        raise RuntimeError("issue #134 experiment identity drifted")
    if manifest["model"] != "gpt-5.6":
        raise RuntimeError("issue #134 model contract drifted")
    if manifest["representation"] != FORMAT_VERSION:
        raise RuntimeError("issue #134 representation contract drifted")
    if manifest["protocol"] != PROTOCOL_VERSION:
        raise RuntimeError("issue #134 review protocol contract drifted")
    if manifest["prompt_version"] != PROMPT_VERSION:
        raise RuntimeError("issue #134 prompt version drifted")
    prompt = files("thorn.prompts").joinpath(f"{PROMPT_VERSION}.md")
    if hashlib.sha256(prompt.read_bytes()).hexdigest() != manifest["prompt_sha256"]:
        raise RuntimeError("issue #134 prompt bytes drifted")
    rescue = manifest["source_rescue"]
    if rescue != {"allowed_once": True, "max_addresses": DEFAULT_MAX_SOURCE_REQUESTS}:
        raise RuntimeError("issue #134 source-rescue contract drifted")
    if manifest["provider_retries"] != 0:
        raise RuntimeError("issue #134 provider retry policy drifted")
    limits = manifest["limits"]
    if limits["max_cases"] != len(EXPECTED_CASE_IDS):
        raise RuntimeError("issue #134 case ceiling drifted")
    if limits["max_provider_requests"] != 2 * len(EXPECTED_CASE_IDS):
        raise RuntimeError("issue #134 provider-request ceiling drifted")
    if limits["max_output_tokens_per_request"] != PROOF_REVIEW_MAX_OUTPUT_TOKENS:
        raise RuntimeError("issue #134 output-token cap drifted")
    if (
        limits["max_output_tokens"]
        != limits["max_provider_requests"] * PROOF_REVIEW_MAX_OUTPUT_TOKENS
    ):
        raise RuntimeError("issue #134 aggregate output-token ceiling drifted")
    return manifest


def _predecessor_cases(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    predecessor_path = ROOT / str(manifest["predecessor_manifest"])
    predecessor = json.loads(predecessor_path.read_text(encoding="utf-8"))
    values = [predecessor["control"], *predecessor["variants"]]
    return {str(case["id"]): case for case in values}


def _assert_assurance_tree(manifest: dict[str, Any]) -> None:
    current = _src_tree_sha()
    expected = str(manifest["assurance_src_tree_sha"])
    if current != expected:
        raise RuntimeError(
            "production src/thorn tree differs from the frozen post-#132/pre-#125 "
            "assurance tree; preserve this experiment and freeze a new one instead"
        )


def _load_cases() -> tuple[dict[str, Any], list[_PreparedCase]]:
    manifest = _load_manifest()
    _assert_assurance_tree(manifest)
    predecessor_cases = _predecessor_cases(manifest)
    raw_cases = manifest["cases"]
    case_ids = tuple(str(case["id"]) for case in raw_cases)
    if case_ids != EXPECTED_CASE_IDS:
        raise RuntimeError(
            f"expected exactly frozen cases {EXPECTED_CASE_IDS}, found {case_ids}"
        )

    cases: list[_PreparedCase] = []
    for metadata in raw_cases:
        case_id = str(metadata["id"])
        predecessor = predecessor_cases[case_id]
        for field in ("source_sha256", "target", "initial_request_fingerprint"):
            if metadata[field] != predecessor[field]:
                raise RuntimeError(
                    f"{case_id}: {field} differs from the post-#128 predecessor freeze"
                )
        if metadata.get("review_target") != predecessor.get("review_target"):
            raise RuntimeError(
                f"{case_id}: review target differs from the post-#128 predecessor freeze"
            )

        path = ROOT / str(metadata["path"])
        if _sha256(path) != metadata["source_sha256"]:
            raise RuntimeError(f"{case_id}: frozen source hash drifted")
        project = extract_project(path)
        review_target = str(metadata.get("review_target", metadata["target"]))
        prepared = prepare_proof_review(project, project.unit(review_target))
        if prepared.document.format_version != manifest["representation"]:
            raise RuntimeError(f"{case_id}: prepared representation drifted")
        initial_turn = build_proof_review_turn(
            ProofLanguageReviewRequest(document=prepared.document)
        )
        if initial_turn.protocol_version != manifest["protocol"]:
            raise RuntimeError(f"{case_id}: initial protocol drifted")
        if initial_turn.representation != manifest["representation"]:
            raise RuntimeError(f"{case_id}: initial representation drifted")
        if not initial_turn.source_rescue_allowed:
            raise RuntimeError(f"{case_id}: initial source rescue unexpectedly disabled")
        if initial_turn.max_source_addresses != manifest["source_rescue"]["max_addresses"]:
            raise RuntimeError(f"{case_id}: initial source-rescue cap drifted")

        envelope = proof_review_request_envelope(initial_turn, manifest["model"])
        if envelope.fingerprint() != metadata["initial_request_fingerprint"]:
            raise RuntimeError(f"{case_id}: frozen initial request fingerprint drifted")
        if envelope.max_output_tokens != manifest["limits"]["max_output_tokens_per_request"]:
            raise RuntimeError(f"{case_id}: production output-token cap drifted")
        cases.append(
            _PreparedCase(
                metadata=metadata,
                project=project,
                prepared=prepared,
                initial_turn=initial_turn,
                initial_envelope=envelope,
            )
        )

    return manifest, cases


def _hypothetical_two_turn_input_bound(case: _PreparedCase) -> int:
    initial = _conservative_input_token_bound(case.initial_envelope)
    all_source_bytes = sum(
        len(source.text.encode("utf-8")) for source in case.prepared.document.sources
    )
    rescue = (
        initial
        + all_source_bytes
        + PROOF_REVIEW_MAX_OUTPUT_TOKENS
        + SERIALIZATION_FRAMING_RESERVE_TOKENS
    )
    return initial + rescue


def preflight() -> dict[str, object]:
    manifest, cases = _load_cases()
    limits = manifest["limits"]
    initial_bounds = [_conservative_input_token_bound(case.initial_envelope) for case in cases]
    if any(bound > limits["max_input_tokens"] for bound in initial_bounds):
        raise RuntimeError("a frozen initial request cannot fit the issue #134 input ceiling")

    return {
        "format_version": 1,
        "issue": 134,
        "experiment_id": manifest["experiment_id"],
        "mode": "preflight",
        "assurance_revision": manifest["assurance_revision"],
        "assurance_src_tree_sha": manifest["assurance_src_tree_sha"],
        "runner_revision": _runner_revision(),
        "model": manifest["model"],
        "representation": manifest["representation"],
        "protocol": manifest["protocol"],
        "prompt_version": manifest["prompt_version"],
        "prompt_sha256": manifest["prompt_sha256"],
        "source_rescue": manifest["source_rescue"],
        "provider_retries": manifest["provider_retries"],
        "cases": [
            {
                "id": case.id,
                "path": case.metadata["path"],
                "review_result_identifier": case.prepared.document.result_identifier,
                "initial_request_fingerprint": case.initial_envelope.fingerprint(),
                "matches_post128_predecessor": True,
                "initial_input_token_upper_bound": _conservative_input_token_bound(
                    case.initial_envelope
                ),
                "hypothetical_maximal_two_turn_input_upper_bound": (
                    _hypothetical_two_turn_input_bound(case)
                ),
                "max_output_tokens_per_request": case.initial_envelope.max_output_tokens,
            }
            for case in cases
        ],
        "limits": {
            **limits,
            "all_initial_requests_input_upper_bound": sum(initial_bounds),
            "hypothetical_all_maximal_two_turn_input_upper_bound": sum(
                _hypothetical_two_turn_input_bound(case) for case in cases
            ),
            "input_guard": (
                "before each actual request, cumulative provider-reported input usage plus "
                "a conservative exact-envelope upper bound must remain <= max_input_tokens"
            ),
        },
        "reference_standard_pricing": manifest["reference_standard_pricing"],
        "live_authorized": False,
    }


def _write_case_report(
    case: _PreparedCase,
    completed: Any,
    destination: Path,
    *,
    execution: ReviewExecution,
    model: str,
) -> None:
    unit = case.project.unit(case.prepared.document.result_identifier)
    source = unit.proof_range or unit.statement_range
    review = ProofReviewReportInput(
        result_identifier=unit.identifier,
        findings=tuple(completed.report.findings),
        initial_turn=completed.initial_turn,
        rescue_turn=completed.rescue_turn,
        document=case.prepared.document,
        model=model,
        execution=execution,
        source=source,
    )
    report = build_report(
        case.project,
        analysis_findings=analyze_project(case.project),
        proof_reviews=(review,),
        proof_states={unit.identifier: case.prepared.state},
        proof_documents={unit.identifier: case.prepared.document},
        min_confidence=0.0,
        thorn_version=_runner_revision(),
    )
    write_report_html(report, destination)


def _run(provider: Any, *, mode: str, report_dir: Path | None) -> dict[str, object]:
    manifest, cases = _load_cases()
    limits = manifest["limits"]
    budget = _Budget(
        max_provider_requests=int(limits["max_provider_requests"]),
        max_input_tokens=int(limits["max_input_tokens"]),
        max_output_tokens_per_request=int(limits["max_output_tokens_per_request"]),
        max_output_tokens=int(limits["max_output_tokens"]),
    )
    results: list[dict[str, object]] = []
    execution = ReviewExecution.LIVE if mode == "live" else ReviewExecution.REPLAY

    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)

    for case in cases:
        guarded = _GuardedTransport(
            provider,
            budget,
            case_id=case.id,
            expected_initial_fingerprint=str(case.metadata["initial_request_fingerprint"]),
        )
        before = _usage(provider)
        completed = run_proof_review(case.prepared, guarded)
        after = _usage(provider)
        stages = [envelope.stage for envelope in guarded.envelopes]
        if stages not in (["initial"], ["initial", "rescue"]):
            raise RuntimeError(f"{case.id}: unexpected review-turn sequence {stages!r}")
        if len(guarded.envelopes) > 2:
            raise RuntimeError(f"{case.id}: more than one rescue turn was attempted")

        rescue = completed.rescue_turn
        prior_response = rescue.prior_response if rescue is not None else None
        results.append(
            {
                "id": case.id,
                "path": case.metadata["path"],
                "review_result_identifier": case.prepared.document.result_identifier,
                "request_fingerprints": [
                    envelope.fingerprint() for envelope in guarded.envelopes
                ],
                "request_stages": stages,
                "source_rescued": rescue is not None,
                "source_addresses_requested": (
                    list(prior_response.source_addresses) if prior_response is not None else []
                ),
                "source_addresses_rescued": (
                    list(rescue.requested_source_addresses) if rescue is not None else []
                ),
                "findings": [
                    finding.model_dump(mode="json") for finding in completed.report.findings
                ],
                "usage": _usage_delta(after, before),
            }
        )
        if report_dir is not None:
            _write_case_report(
                case,
                completed,
                report_dir / f"{case.id}.html",
                execution=execution,
                model=str(manifest["model"]),
            )

    usage = _usage(provider)
    if budget.attempts > budget.max_provider_requests:
        raise RuntimeError("guarded provider attempts exceeded issue #134 ceiling")
    if budget.input_tokens > budget.max_input_tokens:
        raise RuntimeError("guarded input accounting exceeded issue #134 ceiling")
    if budget.output_tokens > budget.max_output_tokens:
        raise RuntimeError("guarded output accounting exceeded issue #134 ceiling")
    if usage["requests"] > budget.max_provider_requests:
        raise RuntimeError("provider request accounting exceeded issue #134 ceiling")
    if usage["input_tokens"] > budget.max_input_tokens:
        raise RuntimeError("provider input accounting exceeded issue #134 ceiling")
    if usage["output_tokens"] > budget.max_output_tokens:
        raise RuntimeError("provider output accounting exceeded issue #134 ceiling")
    if mode == "replay" and usage["live_requests"] != 0:
        raise RuntimeError("replay unexpectedly performed a live provider request")

    return {
        "format_version": 1,
        "issue": 134,
        "experiment_id": manifest["experiment_id"],
        "mode": mode,
        "assurance_revision": manifest["assurance_revision"],
        "assurance_src_tree_sha": manifest["assurance_src_tree_sha"],
        "runner_revision": _runner_revision(),
        "model": manifest["model"],
        "representation": manifest["representation"],
        "protocol": manifest["protocol"],
        "prompt_version": manifest["prompt_version"],
        "limits": preflight()["limits"],
        "provider_usage": usage,
        "guarded_usage": {
            "attempts": budget.attempts,
            "input_tokens": budget.input_tokens,
            "output_tokens": budget.output_tokens,
        },
        "results": results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight, run, or exactly replay issue #134's pre-#125 semantic batch."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay-dir", type=Path)
    parser.add_argument("--record-dir", type=Path)
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.preflight:
        if args.record_dir is not None or args.replay_dir is not None:
            raise SystemExit("preflight does not accept provider recording/replay arguments")
        payload = preflight()
    elif args.live:
        if args.record_dir is None:
            raise SystemExit("--record-dir is required with --live")
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required with --live")
        from thorn.providers.openai import OpenAIProvider

        provider = RecordingProvider(
            OpenAIProvider(model=str(_load_manifest()["model"])),
            args.record_dir,
        )
        payload = _run(provider, mode="live", report_dir=args.report_dir)
    else:
        if args.record_dir is not None:
            raise SystemExit("--record-dir is only valid with --live")
        assert args.replay_dir is not None
        provider = ReplayProvider(
            model=str(_load_manifest()["model"]),
            directory=args.replay_dir,
        )
        payload = _run(provider, mode="replay", report_dir=args.report_dir)

    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
