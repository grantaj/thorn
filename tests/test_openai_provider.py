from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

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
from thorn.providers.base import ProviderResponseValidationError


class FakeResponses:
    def __init__(self, outputs: list[BaseModel | None]) -> None:
        self.outputs = iter(outputs)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        output = next(self.outputs)
        return SimpleNamespace(
            output_text=output.model_dump_json() if output is not None else "",
            status="completed" if output is not None else "incomplete",
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20 if output is not None else 0,
                total_tokens=120 if output is not None else 100,
            ),
        )


class FakeClient:
    def __init__(self, outputs: list[BaseModel | None]) -> None:
        self.responses = FakeResponses(outputs)
        self.max_retries = 2


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

    assert client.max_retries == 0
    assert provider.requests == provider.live_requests == provider.provider_attempts == 2
    assert provider.responses_received == provider.model_generations == 2
    assert provider.input_tokens == 200
    assert provider.output_tokens == 40
    assert provider.total_tokens == 240

    assert len(client.responses.calls) == 2
    attacker_call, defender_call = client.responses.calls

    assert attacker_call["model"] == "fake-model"
    assert attacker_call["store"] is False
    attacker_text = attacker_call["text"]
    assert isinstance(attacker_text, dict)
    attacker_format = attacker_text["format"]
    assert isinstance(attacker_format, dict)
    assert attacker_format["type"] == "json_schema"
    assert attacker_format["name"] == "AttackReport"
    assert attacker_format["strict"] is True
    attacker_schema = attacker_format["schema"]
    assert isinstance(attacker_schema, dict)
    assert attacker_schema["additionalProperties"] is False

    attacker_input = attacker_call["input"]
    assert isinstance(attacker_input, list)
    attacker_system = attacker_input[0]["content"]
    assert "hostile mathematical correctness checker" in attacker_system
    assert "Before returning an empty findings list" in attacker_system
    assert "use unproved_dependency only" in attacker_system
    attacker_packet = attacker_input[1]["content"]
    assert "ID: thm:test" in attacker_packet
    assert "Every widget is stable." in attacker_packet
    assert "Apply Lemma 1 to the widget." in attacker_packet
    assert "Assume widgets are finite dimensional." in attacker_packet
    assert "Finite-dimensional widgets are bounded." in attacker_packet

    assert defender_call["model"] == "fake-model"
    defender_text = defender_call["text"]
    assert isinstance(defender_text, dict)
    defender_format = defender_text["format"]
    assert isinstance(defender_format, dict)
    assert defender_format["name"] == "DefenseReport"
    defender_input = defender_call["input"]
    assert isinstance(defender_input, list)
    defender_system = defender_input[0]["content"]
    assert "Thorn's defender" in defender_system
    assert "semantic-emptiness findings" in defender_system
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
    assert provider.provider_attempts == 1
    assert provider.responses_received == 1
    assert provider.model_generations == 1
    assert provider.total_tokens == 120
    assert len(client.responses.calls) == 1


def test_missing_structured_attacker_result_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient([None])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="fake-model")

    with pytest.raises(ProviderResponseValidationError, match="attacker returned no structured result"):
        provider.attack(_unit())

    assert provider.provider_attempts == 1
    assert provider.responses_received == 1
    assert provider.model_generations == 0
    assert provider.input_tokens == 100
    assert provider.output_tokens == 0
    assert provider.total_tokens == 100
