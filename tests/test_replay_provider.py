from __future__ import annotations

import json
from pathlib import Path

import pytest

import thorn.eval as eval_module
from thorn.dependencies import DependencyNode
from thorn.eval import main
from thorn.models import (
    AttackReport,
    CandidateFinding,
    DefenseItem,
    DefenseReport,
    DefenseVerdict,
    FindingCategory,
    Severity,
    SourceRange,
    TheoremUnit,
)
from thorn.providers.replay import (
    RecordedExchange,
    RecordingProvider,
    ReplayMissError,
    ReplayProvider,
)
from thorn.semantic_review import ReviewTargetKind, SemanticReviewItem
from thorn.semantic_review_render import build_semantic_review_request


class FakeLiveProvider:
    model = "fixture-model"

    def __init__(self) -> None:
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def _usage(self, input_tokens: int = 10, output_tokens: int = 2) -> None:
        self.requests += 1
        self.live_requests += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens

    @staticmethod
    def _report(identifier: str) -> AttackReport:
        if identifier != "thm:missing-hypothesis":
            return AttackReport()
        return AttackReport(
            findings=[
                CandidateFinding(
                    id="F1",
                    category=FindingCategory.HYPOTHESIS_MISMATCH,
                    severity=Severity.ERROR,
                    title="Cancellation requires a nonzero multiplier",
                    explanation="The proof cancels a without assuming a is nonzero.",
                    evidence=["Take a=0."],
                    counterexample="a=0, b=0, c=1",
                    confidence=1.0,
                )
            ]
        )

    def attack(self, unit: TheoremUnit) -> AttackReport:
        self._usage()
        return self._report(unit.identifier)

    def review_semantic(self, request: object) -> AttackReport:
        self._usage(input_tokens=8, output_tokens=3)
        item = getattr(request, "item")
        return self._report(item.result.identifier)

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
    ) -> DefenseReport:
        self._usage(input_tokens=6, output_tokens=1)
        return DefenseReport(
            verdicts=[
                DefenseItem(
                    finding_id=finding.id,
                    verdict=DefenseVerdict.SURVIVES,
                    explanation="The objection survives.",
                    confidence=0.9,
                )
                for finding in findings
            ]
        )


def _unit(statement: str = "If ab=ac then b=c.") -> TheoremUnit:
    return TheoremUnit(
        identifier="thm:missing-hypothesis",
        environment="theorem",
        statement=statement,
        proof="Cancel a from both sides.",
        statement_range=SourceRange(file="fixture.tex", start_line=1, end_line=2),
        proof_range=SourceRange(file="fixture.tex", start_line=3, end_line=4),
    )


def _semantic_request() -> object:
    item = SemanticReviewItem(
        identifier="semantic-review:test",
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=DependencyNode(
            identifier="thm:missing-hypothesis",
            label="thm:missing-hypothesis",
            environment="theorem",
            statement="If ab=ac then b=c.",
            source=SourceRange(file="fixture.tex", start_line=1, end_line=2),
        ),
    )
    return build_semantic_review_request(item)


def _summary(output: str) -> dict[str, object]:
    start = output.find("{\n")
    assert start >= 0
    payload = json.loads(output[start:])
    assert isinstance(payload, dict)
    return payload


def _single_result(summary: dict[str, object]) -> dict[str, object]:
    results = summary["results"]
    assert isinstance(results, list)
    assert len(results) == 1
    result = results[0]
    assert isinstance(result, dict)
    return result


def test_recording_and_replay_round_trip_all_provider_request_kinds(tmp_path: Path) -> None:
    live = FakeLiveProvider()
    recording = RecordingProvider(live, tmp_path)
    unit = _unit()
    request = _semantic_request()

    attack = recording.attack(unit)
    semantic = recording.review_semantic(request)  # type: ignore[arg-type]
    defense = recording.defend(unit, attack.findings)

    assert live.requests == live.live_requests == 3
    recordings = sorted(tmp_path.glob("*.json"))
    assert len(recordings) == 3
    exchanges = [
        RecordedExchange.model_validate_json(path.read_text(encoding="utf-8"))
        for path in recordings
    ]
    assert {exchange.request.kind for exchange in exchanges} == {
        "attack",
        "semantic",
        "defend",
    }
    assert sum(exchange.usage.requests for exchange in exchanges) == 3
    assert all(exchange.fingerprint == exchange.request.fingerprint() for exchange in exchanges)

    replay = ReplayProvider(model="fixture-model", directory=tmp_path)
    assert replay.attack(unit) == attack
    assert replay.review_semantic(request) == semantic  # type: ignore[arg-type]
    assert replay.defend(unit, attack.findings) == defense
    assert replay.requests == 3
    assert replay.live_requests == 0
    assert replay.replay_hits == 3
    assert replay.input_tokens == 0
    assert replay.output_tokens == 0
    assert replay.total_tokens == 0
    assert replay.recorded_total_tokens == live.total_tokens


def test_replay_fails_loudly_when_material_request_input_changes(tmp_path: Path) -> None:
    recording = RecordingProvider(FakeLiveProvider(), tmp_path)
    recording.attack(_unit())
    replay = ReplayProvider(model="fixture-model", directory=tmp_path)

    with pytest.raises(ReplayMissError, match="model, prompt, rendered input, output schema"):
        replay.attack(_unit(statement="Changed theorem statement."))

    assert replay.requests == 0
    assert replay.live_requests == 0
    assert replay.replay_hits == 0


def test_eval_can_record_then_replay_ir_keylessly_without_live_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live = FakeLiveProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: live)
    base_args = [
        "eval/cases",
        "--model",
        "fixture-model",
        "--case-filter",
        "missing_nonzero_hypothesis",
        "--review-context",
        "ir",
        "--structural-only",
    ]

    assert main([*base_args, "--record-dir", str(tmp_path)]) == 0
    recorded_summary = _summary(capsys.readouterr().out)
    recorded = _single_result(recorded_summary)
    assert recorded_summary["provider_mode"] == "record"
    assert recorded_summary["live_requests"] == 1
    assert recorded_summary["replay_hits"] == 0
    assert recorded["live_request_count"] == 1
    assert recorded["replay_hit_count"] == 0
    assert recorded["passed"] is True
    assert len(list(tmp_path.glob("*.json"))) == 1

    def live_provider_must_not_be_constructed(model: str) -> object:
        raise AssertionError(f"live provider constructed during replay for {model}")

    monkeypatch.setattr(eval_module, "OpenAIProvider", live_provider_must_not_be_constructed)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    assert main([*base_args, "--replay-dir", str(tmp_path)]) == 0
    replay_summary = _summary(capsys.readouterr().out)
    replayed = _single_result(replay_summary)
    assert replay_summary["provider_mode"] == "replay"
    assert replay_summary["requests"] == 1
    assert replay_summary["live_requests"] == 0
    assert replay_summary["replay_hits"] == 1
    assert replay_summary["input_tokens"] == 0
    assert replay_summary["output_tokens"] == 0
    assert replay_summary["total_tokens"] == 0
    assert replayed["semantic_request_count"] == 1
    assert replayed["live_request_count"] == 0
    assert replayed["replay_hit_count"] == 1
    assert replayed["observed_findings"] == recorded["observed_findings"]
    assert replayed["passed"] is True


def test_eval_replay_rejects_stale_model_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    live = FakeLiveProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: live)
    args = [
        "eval/cases",
        "--model",
        "fixture-model",
        "--case-filter",
        "missing_nonzero_hypothesis",
        "--review-context",
        "raw",
        "--structural-only",
    ]
    assert main([*args, "--record-dir", str(tmp_path)]) == 0
    capsys.readouterr()

    def live_provider_must_not_be_constructed(model: str) -> object:
        raise AssertionError(f"live provider constructed during replay for {model}")

    monkeypatch.setattr(eval_module, "OpenAIProvider", live_provider_must_not_be_constructed)
    changed = [
        *args,
        "--model",
        "different-model",
        "--replay-dir",
        str(tmp_path),
    ]
    assert main(changed) == 2
    output = capsys.readouterr().out
    assert "replay failed" in output
    assert "no recording" in output
