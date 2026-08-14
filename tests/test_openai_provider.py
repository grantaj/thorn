from __future__ import annotations

from types import SimpleNamespace

import pytest

from thorn.audit import audit_unit
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
from thorn.providers import openai as openai_provider


class FakeResponses:
    def __init__(self, outputs: list[object | None]) -> None:
        self.outputs = iter(outputs)
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=next(self.outputs))


class FakeClient:
    def __init__(self, outputs: list[object | None]) -> None:
        self.responses = FakeResponses(outputs)


def _unit() -> TheoremUnit:
    return TheoremUnit(
        identifier="thm:test",
        environment="theorem",
        statement="Every widget is stable.",
        proof="Apply Lemma 1 to the widget.",
        statement_range=SourceRange(file="paper.tex", start_line=20, end_line=22),
        proof_range=SourceRange(file="paper.tex", start_line=23, end_line=25),
        local_context="Assume widgets are finite dimensional.",
        referenced_results=["[lemma lem:one]\nFinite-dimensional widgets are bounded."],
    )


def _finding(
    finding_id: str,
    title: str,
    category: FindingCategory = FindingCategory.INVALID_IMPLICATION,
) -> CandidateFinding:
    return CandidateFinding(
        id=finding_id,
        category=category,
        severity=Severity.ERROR,
        title=title,
        explanation="The supplied implication does not follow.",
        evidence=["Apply Lemma 1 to the widget."],
        counterexample="A two-dimensional widget.",
        confidence=0.9,
    )


def test_openai_provider_attack_defend_pipeline_is_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    attack = AttackReport(findings=[_finding("F1", "Real defect"), _finding("F2", "False alarm")])
    defense = DefenseReport(
        verdicts=[
            DefenseItem(
                finding_id="F1",
                verdict=DefenseVerdict.SURVIVES,
                explanation="No stated hypothesis repairs the implication.",
                confidence=0.85,
            ),
            DefenseItem(
                finding_id="F2",
                verdict=DefenseVerdict.DISMISSED,
                explanation="The local definition resolves this objection.",
                confidence=0.95,
            ),
        ]
    )
    client = FakeClient([attack, defense])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)

    provider = openai_provider.OpenAIProvider(model="fake-model")
    result = audit_unit(_unit(), provider, use_defender=True, cache=None)

    assert [finding.title for finding in result.findings] == ["Real defect"]
    assert result.findings[0].defender_verdict == DefenseVerdict.SURVIVES
    assert result.findings[0].confidence == 0.85

    assert len(client.responses.calls) == 2
    attacker_call, defender_call = client.responses.calls

    assert attacker_call["model"] == "fake-model"
    assert attacker_call["text_format"] is AttackReport
    attacker_input = attacker_call["input"]
    assert isinstance(attacker_input, list)
    assert "hostile mathematical correctness checker" in attacker_input[0]["content"]
    attacker_packet = attacker_input[1]["content"]
    assert "ID: thm:test" in attacker_packet
    assert "Every widget is stable." in attacker_packet
    assert "Apply Lemma 1 to the widget." in attacker_packet
    assert "Assume widgets are finite dimensional." in attacker_packet
    assert "Finite-dimensional widgets are bounded." in attacker_packet

    assert defender_call["model"] == "fake-model"
    assert defender_call["text_format"] is DefenseReport
    defender_input = defender_call["input"]
    assert isinstance(defender_input, list)
    assert "Thorn's defender" in defender_input[0]["content"]
    defender_packet = defender_input[1]["content"]
    assert "# Proposed findings to defend against" in defender_packet
    assert "[F1] Real defect" in defender_packet
    assert "[F2] False alarm" in defender_packet


def test_empty_attack_skips_defender_call(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient([AttackReport(findings=[])])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)

    provider = openai_provider.OpenAIProvider(model="fake-model")
    result = audit_unit(_unit(), provider, use_defender=True, cache=None)

    assert result.findings == []
    assert len(client.responses.calls) == 1


def test_missing_structured_attacker_result_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient([None])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="fake-model")

    with pytest.raises(RuntimeError, match="attacker returned no structured result"):
        provider.attack(_unit())
