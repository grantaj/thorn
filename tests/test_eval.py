from pathlib import Path

import pytest

import thorn.eval as eval_module
from thorn.eval import _load_cases, _select_unit, main
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
        "thm:typo": FindingCategory.DEFINITION_MISMATCH,
        "thm:repairable-algebra": FindingCategory.ALGEBRA_ERROR,
        "thm:missing-hypothesis": FindingCategory.HYPOTHESIS_MISMATCH,
        "thm:missing-zero-case": FindingCategory.BOUNDARY_CASE,
        "thm:missing-justification": FindingCategory.UNSUPPORTED_CLAIM,
        "thm:too-strong": FindingCategory.COUNTEREXAMPLE,
        "thm:false-as-stated": FindingCategory.COUNTEREXAMPLE,
        "thm:depends-bad-lemma": FindingCategory.UNSUPPORTED_CLAIM,
        "thm:true-despite-bad-lemma": FindingCategory.UNSUPPORTED_CLAIM,
        "lem:cycle-b": FindingCategory.CIRCULAR_DEPENDENCY,
        "lem:deep-cycle-c": FindingCategory.CIRCULAR_DEPENDENCY,
        "thm:fermat": FindingCategory.INVALID_IMPLICATION,
        "thm:rh-prime-window": FindingCategory.UNPROVED_DEPENDENCY,
        "thm:abc-finiteness": FindingCategory.UNPROVED_DEPENDENCY,
        "thm:choice-right-inverse": FindingCategory.UNSTATED_AXIOM,
        "thm:stable-idempotent": FindingCategory.VACUOUS_TRUTH,
        "thm:empty-class": FindingCategory.VACUOUS_TRUTH,
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

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
    ) -> DefenseReport:
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
    assert len(cases) >= 25

    bad = 0
    clean = 0
    levels: set[int] = set()
    for tex_path, expectation in cases:
        units = extract_units(tex_path)
        unit = _select_unit(units, expectation)
        assert unit.proof is not None
        levels.add(expectation.level)

        if expectation.root_cause_identifier is not None:
            assert any(
                candidate.identifier == expectation.root_cause_identifier
                for candidate in units
            )
            assert any(
                expectation.root_cause_identifier in reference
                for reference in unit.referenced_results
            )

        if expectation.kind == "finding":
            bad += 1
            assert expectation.accepted_categories
        else:
            clean += 1

    assert bad >= 20
    assert clean >= 5
    assert set(range(1, 11)).issubset(levels)


def test_eval_harness_runs_all_cases_without_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    cases = _load_cases(Path("eval/cases"))
    assert main(["eval/cases", "--model", "fixture-provider"]) == 0

    output = capsys.readouterr().out
    assert output.count("PASS ") == len(cases)
    assert '"failures": 0' in output


def test_eval_max_level_filters_the_ladder(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    cases = _load_cases(Path("eval/cases"))
    expected = sum(expectation.level <= 2 for _, expectation in cases)

    assert main(
        [
            "eval/cases",
            "--model",
            "fixture-provider",
            "--max-level",
            "2",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert output.count("PASS ") == expected
    assert f'"cases": {expected}' in output


def test_live_eval_refuses_to_start_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert main(["eval/cases", "--model", "unused"]) == 2
