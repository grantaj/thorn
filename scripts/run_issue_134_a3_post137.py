#!/usr/bin/env python3
"""Freeze, run, or replay issue #134's post-#137 A3-only continuation.

Preflight is keyless. Live mode is intentionally fail-closed until the manifest
is frozen and a later, separate paid execution is explicitly authorized.
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
MANIFEST = EXPERIMENT / "a3_post137_manifest.json"
SERIALIZATION_FRAMING_RESERVE_TOKENS = 2_048
FROZEN_STATUS = "frozen-keylessly-live-not-authorized"
CANDIDATE_STATUS = "candidate-keyless-live-not-authorized"


@dataclass(frozen=True)
class _PreparedCase:
    metadata: dict[str, Any]
    project: Any
    prepared: PreparedProofReview
    initial_turn: ProofReviewTurnRequest
    initial_envelope: ProviderRequestEnvelope


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
            raise RuntimeError("A3 post-#137 provider-request ceiling would be exceeded")
        input_bound = _conservative_input_token_bound(envelope)
        if self.input_tokens + input_bound > self.max_input_tokens:
            raise RuntimeError("A3 post-#137 input-token ceiling would be exceeded")
        if envelope.max_output_tokens != self.max_output_tokens_per_request:
            raise RuntimeError("A3 post-#137 per-request output cap drifted")
        if self.output_tokens + envelope.max_output_tokens > self.max_output_tokens:
            raise RuntimeError("A3 post-#137 aggregate output-token ceiling would be exceeded")
        self.attempts += 1

    def commit_usage(self, before: dict[str, int], after: dict[str, int]) -> None:
        requests = after["requests"] - before["requests"]
        input_tokens = after["input_tokens"] - before["input_tokens"]
        output_tokens = after["output_tokens"] - before["output_tokens"]
        if requests > 0 and input_tokens <= 0:
            raise RuntimeError("completed provider request lacks input-token accounting")
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if self.input_tokens > self.max_input_tokens:
            raise RuntimeError("provider-reported input usage exceeded A3 ceiling")
        if self.output_tokens > self.max_output_tokens:
            raise RuntimeError("provider-reported output usage exceeded A3 ceiling")


class _GuardedTransport:
    def __init__(
        self,
        delegate: Any,
        budget: _Budget,
        *,
        expected_initial_fingerprint: str,
    ) -> None:
        self.delegate = delegate
        self.budget = budget
        self.model = delegate.model
        self.expected_initial_fingerprint = expected_initial_fingerprint
        self.envelopes: list[ProviderRequestEnvelope] = []

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse:
        envelope = proof_review_request_envelope(request, self.model)
        if request.stage == "initial" and envelope.fingerprint() != self.expected_initial_fingerprint:
            raise RuntimeError("A3 frozen initial request fingerprint drifted")
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
    return len(envelope.canonical_json().encode("utf-8")) + SERIALIZATION_FRAMING_RESERVE_TOKENS


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manifest() -> dict[str, Any]:
    manifest = _load_json(MANIFEST)
    if manifest["issue"] != 134:
        raise RuntimeError("A3 continuation issue identity drifted")
    if manifest["experiment_id"] != "issue-134-a3-post137-pre125":
        raise RuntimeError("A3 continuation experiment identity drifted")
    if manifest["status"] not in {CANDIDATE_STATUS, FROZEN_STATUS}:
        raise RuntimeError("A3 continuation has an unknown freeze status")
    if manifest["repairs_included"] != [128, 132, 137]:
        raise RuntimeError("A3 continuation repair boundary drifted")
    if manifest["blocked_implementation_issue"] != 125:
        raise RuntimeError("A3 continuation must remain pre-#125")
    if manifest["model"] != "gpt-5.6":
        raise RuntimeError("A3 continuation model contract drifted")
    if manifest["representation"] != FORMAT_VERSION:
        raise RuntimeError("A3 continuation representation contract drifted")
    if manifest["protocol"] != PROTOCOL_VERSION:
        raise RuntimeError("A3 continuation protocol contract drifted")
    if manifest["prompt_version"] != PROMPT_VERSION:
        raise RuntimeError("A3 continuation prompt version drifted")
    prompt = files("thorn.prompts").joinpath(f"{PROMPT_VERSION}.md")
    if hashlib.sha256(prompt.read_bytes()).hexdigest() != manifest["prompt_sha256"]:
        raise RuntimeError("A3 continuation prompt bytes drifted")
    if manifest["source_rescue"] != {
        "allowed_once": True,
        "max_addresses": DEFAULT_MAX_SOURCE_REQUESTS,
    }:
        raise RuntimeError("A3 continuation source-rescue contract drifted")
    if manifest["provider_retries"] != 0:
        raise RuntimeError("A3 continuation requires zero implicit provider retries")
    if manifest["paid_execution_authorized"] is not False:
        raise RuntimeError("freeze manifest must not itself authorize paid execution")
    limits = manifest["limits"]
    if limits["max_cases"] != 1 or limits["max_provider_requests"] != 2:
        raise RuntimeError("A3 continuation case/request ceiling drifted")
    if limits["max_output_tokens_per_request"] != PROOF_REVIEW_MAX_OUTPUT_TOKENS:
        raise RuntimeError("A3 continuation output-token cap drifted")
    if limits["max_output_tokens"] != 2 * PROOF_REVIEW_MAX_OUTPUT_TOKENS:
        raise RuntimeError("A3 continuation aggregate output-token ceiling drifted")
    return manifest


def _assert_assurance_tree(manifest: dict[str, Any]) -> None:
    current = _src_tree_sha()
    expected = str(manifest["assurance_src_tree_sha"])
    if current != expected:
        raise RuntimeError(
            "production src/thorn tree differs from the frozen post-#137/pre-#125 "
            "assurance tree; preserve this experiment and freeze a new one instead"
        )


def _prepare_case(manifest: dict[str, Any]) -> _PreparedCase:
    _assert_assurance_tree(manifest)
    metadata = manifest["case"]
    if metadata["id"] != "A3":
        raise RuntimeError("A3 continuation must contain exactly A3")

    predecessor = _load_json(ROOT / str(manifest["predecessor_manifest"]))
    predecessor_case = next(case for case in predecessor["cases"] if case["id"] == "A3")
    for field in ("path", "source_sha256", "target", "variation_family"):
        if metadata[field] != predecessor_case[field]:
            raise RuntimeError(f"A3 {field} differs from preserved pre-#137 experiment")
    if metadata["predecessor_initial_request_fingerprint"] != predecessor_case["initial_request_fingerprint"]:
        raise RuntimeError("A3 predecessor fingerprint was not preserved exactly")

    path = ROOT / str(metadata["path"])
    if _sha256(path) != metadata["source_sha256"]:
        raise RuntimeError("A3 frozen source hash drifted")
    project = extract_project(path)
    prepared = prepare_proof_review(project, project.unit(str(metadata["target"])))
    if prepared.document.format_version != manifest["representation"]:
        raise RuntimeError("A3 prepared representation drifted")
    initial_turn = build_proof_review_turn(ProofLanguageReviewRequest(document=prepared.document))
    if initial_turn.protocol_version != manifest["protocol"]:
        raise RuntimeError("A3 initial protocol drifted")
    if initial_turn.representation != manifest["representation"]:
        raise RuntimeError("A3 initial representation drifted")
    if not initial_turn.source_rescue_allowed:
        raise RuntimeError("A3 source rescue unexpectedly disabled")
    if initial_turn.max_source_addresses != manifest["source_rescue"]["max_addresses"]:
        raise RuntimeError("A3 source-rescue cap drifted")
    envelope = proof_review_request_envelope(initial_turn, manifest["model"])
    if envelope.max_output_tokens != manifest["limits"]["max_output_tokens_per_request"]:
        raise RuntimeError("A3 production output-token cap drifted")

    frozen_fingerprint = metadata["initial_request_fingerprint"]
    if manifest["status"] == FROZEN_STATUS:
        if not isinstance(frozen_fingerprint, str) or len(frozen_fingerprint) != 64:
            raise RuntimeError("A3 frozen manifest lacks a valid request fingerprint")
        if envelope.fingerprint() != frozen_fingerprint:
            raise RuntimeError("A3 frozen initial request fingerprint drifted")
    elif frozen_fingerprint is not None:
        raise RuntimeError("A3 candidate manifest must not pre-populate its new fingerprint")

    return _PreparedCase(
        metadata=metadata,
        project=project,
        prepared=prepared,
        initial_turn=initial_turn,
        initial_envelope=envelope,
    )


def _hypothetical_two_turn_input_bound(case: _PreparedCase) -> int:
    initial = _conservative_input_token_bound(case.initial_envelope)
    all_source_bytes = sum(len(source.text.encode("utf-8")) for source in case.prepared.document.sources)
    rescue = initial + all_source_bytes + PROOF_REVIEW_MAX_OUTPUT_TOKENS + SERIALIZATION_FRAMING_RESERVE_TOKENS
    return initial + rescue


def preflight() -> dict[str, object]:
    manifest = _load_manifest()
    case = _prepare_case(manifest)
    limits = manifest["limits"]
    initial_bound = _conservative_input_token_bound(case.initial_envelope)
    two_turn_bound = _hypothetical_two_turn_input_bound(case)
    if initial_bound > limits["max_input_tokens"]:
        raise RuntimeError("A3 initial request cannot fit the frozen input ceiling")
    fingerprint = case.initial_envelope.fingerprint()
    frozen = manifest["status"] == FROZEN_STATUS
    return {
        "format_version": 1,
        "issue": 134,
        "experiment_id": manifest["experiment_id"],
        "mode": "preflight",
        "status": manifest["status"],
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
        "case": {
            "id": "A3",
            "path": case.metadata["path"],
            "review_result_identifier": case.prepared.document.result_identifier,
            "source_sha256": case.metadata["source_sha256"],
            "predecessor_initial_request_fingerprint": case.metadata["predecessor_initial_request_fingerprint"],
            "initial_request_fingerprint": fingerprint,
            "fingerprint_changed_by_post137_contract": fingerprint
            != case.metadata["predecessor_initial_request_fingerprint"],
            "frozen_request_contract_verified": frozen,
            "initial_input_token_upper_bound": initial_bound,
            "hypothetical_maximal_two_turn_input_upper_bound": two_turn_bound,
            "max_output_tokens_per_request": case.initial_envelope.max_output_tokens,
        },
        "limits": {
            **limits,
            "initial_request_input_upper_bound": initial_bound,
            "hypothetical_maximal_two_turn_input_upper_bound": two_turn_bound,
            "input_guard": (
                "before each actual request, cumulative provider-reported input usage plus "
                "a conservative exact-envelope upper bound must remain <= max_input_tokens"
            ),
        },
        "provider_instantiated": False,
        "provider_requests": 0,
        "live_requests": 0,
        "live_authorized": False,
    }


def _write_report(
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


def _run(provider: Any, *, mode: str, report_path: Path | None) -> dict[str, object]:
    manifest = _load_manifest()
    if manifest["status"] != FROZEN_STATUS:
        raise RuntimeError("A3 live/replay is forbidden until the new request contract is frozen")
    case = _prepare_case(manifest)
    limits = manifest["limits"]
    budget = _Budget(
        max_provider_requests=int(limits["max_provider_requests"]),
        max_input_tokens=int(limits["max_input_tokens"]),
        max_output_tokens_per_request=int(limits["max_output_tokens_per_request"]),
        max_output_tokens=int(limits["max_output_tokens"]),
    )
    guarded = _GuardedTransport(
        provider,
        budget,
        expected_initial_fingerprint=str(case.metadata["initial_request_fingerprint"]),
    )
    before = _usage(provider)
    completed = run_proof_review(case.prepared, guarded)
    after = _usage(provider)
    stages = [envelope.stage for envelope in guarded.envelopes]
    if stages not in (["initial"], ["initial", "rescue"]):
        raise RuntimeError(f"A3 unexpected review-turn sequence {stages!r}")
    if len(guarded.envelopes) > 2:
        raise RuntimeError("A3 attempted more than one rescue turn")
    rescue = completed.rescue_turn
    prior_response = rescue.prior_response if rescue is not None else None

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_report(
            case,
            completed,
            report_path,
            execution=ReviewExecution.LIVE if mode == "live" else ReviewExecution.REPLAY,
            model=str(manifest["model"]),
        )

    usage = _usage(provider)
    if usage["requests"] > budget.max_provider_requests:
        raise RuntimeError("A3 provider request accounting exceeded ceiling")
    if usage["input_tokens"] > budget.max_input_tokens:
        raise RuntimeError("A3 provider input accounting exceeded ceiling")
    if usage["output_tokens"] > budget.max_output_tokens:
        raise RuntimeError("A3 provider output accounting exceeded ceiling")
    if mode == "replay" and usage["live_requests"] != 0:
        raise RuntimeError("A3 replay unexpectedly performed a live provider request")

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
        "result": {
            "id": "A3",
            "path": case.metadata["path"],
            "review_result_identifier": case.prepared.document.result_identifier,
            "request_fingerprints": [envelope.fingerprint() for envelope in guarded.envelopes],
            "request_stages": stages,
            "source_rescued": rescue is not None,
            "source_addresses_requested": list(prior_response.source_addresses) if prior_response is not None else [],
            "source_addresses_rescued": list(rescue.requested_source_addresses) if rescue is not None else [],
            "findings": [finding.model_dump(mode="json") for finding in completed.report.findings],
            "usage": _usage_delta(after, before),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight, run, or replay issue #134's post-#137 A3-only continuation."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--replay-dir", type=Path)
    parser.add_argument("--record-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.preflight:
        if args.record_dir is not None or args.replay_dir is not None:
            raise SystemExit("preflight does not accept provider recording/replay arguments")
        payload = preflight()
    elif args.live:
        manifest = _load_manifest()
        if manifest["status"] != FROZEN_STATUS:
            raise SystemExit("paid A3 run is forbidden until the post-#137 freeze is complete")
        if args.record_dir is None:
            raise SystemExit("--record-dir is required with --live")
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required with --live")
        from thorn.providers.openai import OpenAIProvider

        provider = RecordingProvider(
            OpenAIProvider(model=str(manifest["model"])),
            args.record_dir,
        )
        payload = _run(provider, mode="live", report_path=args.report)
    else:
        if args.record_dir is not None:
            raise SystemExit("--record-dir is only valid with --live")
        assert args.replay_dir is not None
        manifest = _load_manifest()
        provider = ReplayProvider(
            model=str(manifest["model"]),
            directory=args.replay_dir,
        )
        payload = _run(provider, mode="replay", report_path=args.report)

    rendered = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
