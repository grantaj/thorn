from pathlib import Path

import pytest

import thorn.eval as eval_module
from thorn.eval import _load_cases, main
from thorn.latex import extract_units
from thorn.models import (
    AttackReport,
    CandidateFinding,
    DefenseItem,
    DefenseReport,
    DefenseVerdict,
    FindingCategory,
    Severity,
    TheoremUnit,
)


class FixtureProvider:
    model = "fixture-provider"

    _DEFECTS = {
        "prop:threshold": FindingCategory.ALGEBRA_ERROR,
        "thm:contraction": FindingCategory.HYPOTHESIS_MISMATCH,
        "thm:limit": FindingCategory.CONVERGENCE_MISMATCH,
    }

    def attack(self, unit: TheoremUnit) -> AttackReport:
        category = self._DEFECTS.get(unit.identifier)
        if category is None:
            return AttackReport(findings=[])
        return AttackReport(
            findings=[
                CandidateFinding(
                    id="F1",
                    category=category,
                    severity=Severity.ERROR,
                    title=f"Synthetic finding for {unit.identifier}",
                    explanation="Deterministic test finding.",
                    confidence=0.95,
                )
            ]
        )

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport:
        return DefenseReport(
            verdicts=[
                DefenseItem(
                    finding_id=finding.id,
                    verdict=DefenseVerdict.SURVIVES,
                    explanation="Deterministic defender verdict.",
                    confidence=0.95,
                )
                for finding in findings
            ]
        )


def test_eval_corpus_is_well_formed() -> None:
    cases = _load_cases(Path("eval/cases"))
    assert len(cases) >= 5

    bad = 0
    clean = 0
    for tex_path, expectation in cases:
        units = extract_units(tex_path)
        assert len(units) == 1
        assert units[0].proof is not None
        if expectation.kind == "finding":
            bad += 1
            assert expectation.accepted_categories
        else:
            clean += 1

    assert bad >= 3
    assert clean >= 2


def test_eval_harness_runs_all_cases_without_network(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    assert main(["eval/cases", "--model", "fixture-provider"]) == 0

    output = capsys.readouterr().out
    assert output.count("PASS ") == 5
    assert '"failures": 0' in output


def test_live_eval_refuses_to_start_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert main(["eval/cases", "--model", "unused"]) == 2
