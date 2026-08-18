#!/usr/bin/env python3
"""Run issue #101's frozen known-defect robustness experiment.

The default/preflight path is keyless. Live execution is deliberately explicit,
records every accepted provider exchange, enforces request/token ceilings before
each provider call, and refuses any drift from the frozen initial request
fingerprints in ``eval/robustness/issue_101/manifest.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thorn.analysis import analyze_project
from thorn.latex import extract_project
from thorn.proof_language_review import (
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
CORPUS = ROOT / "eval" / "robustness" / "issue_101"
MANIFEST = CORPUS / "manifest.json"
MODEL = "gpt-5.6"
MAX_CASES = 5
MAX_PROVIDER_REQUESTS = 10
MAX_INPUT_TOKENS = 100_000
MAX_OUTPUT_TOKENS_PER_REQUEST = PROOF_REVIEW_MAX_OUTPUT_TOKENS
MAX_OUTPUT_TOKENS = MAX_PROVIDER_REQUESTS * MAX_OUTPUT_TOKENS_PER_REQUEST
SERIALIZATION_FRAMING_RESERVE_TOKENS = 2_048
REFERENCE_PRICE_DATE = "2026-08-18"
REFERENCE_INPUT_USD_PER_MILLION = 5.0
REFERENCE_OUTPUT_USD_PER_MILLION = 30.0
REFERENCE_MAX_COST_USD = (
    MAX_INPUT_TOKENS * REFERENCE_INPUT_USD_PER_MILLION
    + MAX_OUTPUT_TOKENS * REFERENCE_OUTPUT_USD_PER_MILLION
) / 1_000_000


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
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def reserve(self, envelope: ProviderRequestEnvelope) -> None:
        if self.attempts + 1 > MAX_PROVIDER_REQUESTS:
            raise RuntimeError("issue #101 provider-request ceiling would be exceeded")
        input_bound = _conservative_input_token_bound(envelope)
        if self.input_tokens + input_bound > MAX_INPUT_TOKENS:
            raise RuntimeError(
                "issue #101 input-token ceiling would be exceeded by the next exact request"
            )
        max_output = envelope.max_output_tokens
        if max_output != MAX_OUTPUT_TOKENS_PER_REQUEST:
            raise RuntimeError(
                "issue #101 request output cap drifted: "
                f"expected {MAX_OUTPUT_TOKENS_PER_REQUEST}, got {max_output}"
            )
        if self.output_tokens + max_output > MAX_OUTPUT_TOKENS:
            raise RuntimeError("issue #101 aggregate output-token ceiling would be exceeded")
        self.attempts += 1

    def commit_usage(self, before: dict[str, int], after: dict[str, int]) -> None:
        requests = after["requests"] - before["requests"]
        input_tokens = after["input_tokens"] - before["input_tokens"]
        output_tokens = after["output_tokens"] - before["output_tokens"]
        if requests > 0 and input_tokens <= 0:
            raise RuntimeError("provider returned no input-token accounting for a completed request")
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.input_tokens > MAX_INPUT_TOKENS:
            raise RuntimeError("provider-reported input usage exceeded issue #101 ceiling")
        if self.output_tokens > MAX_OUTPUT_TOKENS:
            raise RuntimeError("provider-reported output usage exceeded issue #101 ceiling")


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
        self.responses: list[ProofReviewModelResponse] = []

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(request, self.model)
        if request.stage == "initial" and envelope.fingerprint() != self.expected_initial_fingerprint:
            raise RuntimeError(f"{self.case_id}: frozen initial request fingerprint drifted")
        self.budget.reserve(envelope)
        before = _usage(self.delegate)
        try:
            response = self.delegate.review_proof_turn(request)
        finally:
            after = _usage(self.delegate)
            self.budget.commit_usage(before, after)
        self.envelopes.append(envelope)
        self.responses.append(response)
        return response


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


def _runner_revision() -> str:
    return _git("rev-parse", "HEAD")


def _assert_assurance_code_unchanged(expected_src_tree_sha: str) -> None:
    current_src_tree_sha = _git("rev-parse", "HEAD:src/thorn")
    if current_src_tree_sha != expected_src_tree_sha:
        raise RuntimeError(
            "production src/thorn tree differs from the frozen assurance tree; "
            "freeze a new experiment instead"
        )


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
    # A tokenizer cannot produce more tokens than there are UTF-8 bytes in the
    # serialized request. Counting the full canonical envelope bytes therefore
    # safely over-bounds its token count. The extra reserve covers transport /
    # message framing that is not represented in the canonical envelope.
    return (
        len(envelope.canonical_json().encode("utf-8"))
        + SERIALIZATION_FRAMING_RESERVE_TOKENS
    )


def _load_cases() -> tuple[str, str, list[_PreparedCase]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw_cases = [manifest["control"], *manifest["variants"]]
    if len(raw_cases) != MAX_CASES:
        raise RuntimeError(f"expected exactly {MAX_CASES} frozen cases, found {len(raw_cases)}")

    cases: list[_PreparedCase] = []
    for metadata in raw_cases:
        path = CORPUS / metadata["path"]
        if _sha256(path) != metadata["source_sha256"]:
            raise RuntimeError(f"{metadata['id']}: frozen source hash drifted")
        project = extract_project(path)
        review_target = metadata.get("review_target", metadata["target"])
        unit = project.unit(review_target)
        prepared = prepare_proof_review(project, unit)
        initial_turn = build_proof_review_turn(
            ProofLanguageReviewRequest(document=prepared.document)
        )
        initial_envelope = proof_review_request_envelope(initial_turn, MODEL)
        if initial_envelope.fingerprint() != metadata["initial_request_fingerprint"]:
            raise RuntimeError(f"{metadata['id']}: frozen initial request fingerprint drifted")
        if initial_envelope.max_output_tokens != MAX_OUTPUT_TOKENS_PER_REQUEST:
            raise RuntimeError(f"{metadata['id']}: production output-token cap drifted")
        cases.append(
            _PreparedCase(
                metadata=metadata,
                project=project,
                prepared=prepared,
                initial_turn=initial_turn,
                initial_envelope=initial_envelope,
            )
        )
    return (
        str(manifest["assurance_revision"]),
        str(manifest["assurance_src_tree_sha"]),
        cases,
    )


def _hypothetical_two_turn_input_bound(case: _PreparedCase) -> int:
    initial = _conservative_input_token_bound(case.initial_envelope)
    all_source_bytes = sum(
        len(source.text.encode("utf-8")) for source in case.prepared.document.sources
    )
    # Diagnostic stress bound only: suppose the first response consumes its full
    # 4096-token output allowance and the case then requests every held source.
    # The live gate does not reserve this hypothetical amount up front; it checks
    # the exact rescue envelope if and only if the model actually asks for rescue.
    rescue = (
        initial
        + all_source_bytes
        + MAX_OUTPUT_TOKENS_PER_REQUEST
        + SERIALIZATION_FRAMING_RESERVE_TOKENS
    )
    return initial + rescue


def preflight() -> dict[str, object]:
    assurance_revision, assurance_src_tree_sha, cases = _load_cases()
    _assert_assurance_code_unchanged(assurance_src_tree_sha)
    initial_bounds = [_conservative_input_token_bound(case.initial_envelope) for case in cases]
    if any(bound > MAX_INPUT_TOKENS for bound in initial_bounds):
        raise RuntimeError("a frozen initial request cannot fit the issue #101 input-token ceiling")

    hypothetical_two_turn_bound = sum(
        _hypothetical_two_turn_input_bound(case) for case in cases
    )
    return {
        "format_version": 1,
        "issue": 101,
        "mode": "preflight",
        "assurance_revision": assurance_revision,
        "assurance_src_tree_sha": assurance_src_tree_sha,
        "runner_revision": _runner_revision(),
        "model": MODEL,
        "cases": [
            {
                "id": case.id,
                "path": case.metadata["path"],
                "initial_request_fingerprint": case.initial_envelope.fingerprint(),
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
            "max_cases": MAX_CASES,
            "max_provider_requests": MAX_PROVIDER_REQUESTS,
            "max_input_tokens": MAX_INPUT_TOKENS,
            "max_output_tokens_per_request": MAX_OUTPUT_TOKENS_PER_REQUEST,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "all_initial_requests_input_upper_bound": sum(initial_bounds),
            "hypothetical_all_maximal_two_turn_input_upper_bound": hypothetical_two_turn_bound,
            "input_guard": (
                "before each actual request, cumulative provider-reported input usage plus "
                "a conservative exact-envelope upper bound must remain <= max_input_tokens"
            ),
        },
        "reference_standard_pricing": {
            "as_of": REFERENCE_PRICE_DATE,
            "input_usd_per_million": REFERENCE_INPUT_USD_PER_MILLION,
            "output_usd_per_million": REFERENCE_OUTPUT_USD_PER_MILLION,
            "absolute_token_ceiling_usd": round(REFERENCE_MAX_COST_USD, 4),
            "note": "re-verify official pricing immediately before any later live run",
        },
    }


def _write_case_report(
    case: _PreparedCase,
    completed: Any,
    destination: Path,
    *,
    execution: ReviewExecution,
) -> None:
    unit = case.project.unit(case.prepared.document.result_identifier)
    source = unit.proof_range or unit.statement_range
    review = ProofReviewReportInput(
        result_identifier=unit.identifier,
        findings=tuple(completed.report.findings),
        initial_turn=completed.initial_turn,
        rescue_turn=completed.rescue_turn,
        document=case.prepared.document,
        model=MODEL,
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
    assurance_revision, assurance_src_tree_sha, cases = _load_cases()
    _assert_assurance_code_unchanged(assurance_src_tree_sha)
    budget = _Budget()
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
        delta = _usage_delta(after, before)
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
                "usage": delta,
            }
        )
        if report_dir is not None:
            _write_case_report(
                case,
                completed,
                report_dir / f"{case.id}.html",
                execution=execution,
            )

    usage = _usage(provider)
    if budget.attempts > MAX_PROVIDER_REQUESTS:
        raise RuntimeError("guarded provider attempts exceeded issue #101 ceiling")
    if budget.input_tokens > MAX_INPUT_TOKENS:
        raise RuntimeError("guarded input accounting exceeded issue #101 ceiling")
    if budget.output_tokens > MAX_OUTPUT_TOKENS:
        raise RuntimeError("guarded output accounting exceeded issue #101 ceiling")
    if usage["requests"] > MAX_PROVIDER_REQUESTS:
        raise RuntimeError("provider request accounting exceeded issue #101 ceiling")
    if usage["input_tokens"] > MAX_INPUT_TOKENS:
        raise RuntimeError("provider input accounting exceeded issue #101 ceiling")
    if usage["output_tokens"] > MAX_OUTPUT_TOKENS:
        raise RuntimeError("provider output accounting exceeded issue #101 ceiling")
    if mode == "replay" and usage["live_requests"] != 0:
        raise RuntimeError("replay unexpectedly performed a live provider request")

    return {
        "format_version": 1,
        "issue": 101,
        "mode": mode,
        "assurance_revision": assurance_revision,
        "assurance_src_tree_sha": assurance_src_tree_sha,
        "runner_revision": _runner_revision(),
        "model": MODEL,
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
        description="Preflight, run, or exactly replay issue #101's frozen semantic batch."
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

        provider = RecordingProvider(OpenAIProvider(model=MODEL), args.record_dir)
        payload = _run(provider, mode="live", report_dir=args.report_dir)
    else:
        if args.record_dir is not None:
            raise SystemExit("--record-dir is only valid with --live")
        assert args.replay_dir is not None
        provider = ReplayProvider(model=MODEL, directory=args.replay_dir)
        payload = _run(provider, mode="replay", report_dir=args.report_dir)

    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
