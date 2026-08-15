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
        "thm:converse": FindingCategory.INVALID_IMPLICATION,
        "thm:bad-wlog": FindingCategory.INVALID_IMPLICATION,
        "thm:stride-induction": FindingCategory.UNSUPPORTED_CLAIM,
        "thm:quotient-bad": FindingCategory.WELL_DEFINEDNESS,
        "thm:infimum-minimum": FindingCategory.INVALID_IMPLICATION,
        "thm:bounded-sequence": FindingCategory.CONVERGENCE_MISMATCH,
        "thm:extreme-value-gap": FindingCategory.UNSUPPORTED_CLAIM,
        "thm:quantifier-swap": FindingCategory.QUANTIFIER_ERROR,
        "thm:uniform-null-set": FindingCategory.INVALID_IMPLICATION,
        "thm:unit-ball-compact": FindingCategory.HYPOTHESIS_MISMATCH,
        "thm:local-global": FindingCategory.INVALID_IMPLICATION,
        "thm:notation-collision": FindingCategory.NOTATION_AMBIGUITY,
        "thm:ambiguous-big-o": FindingCategory.SPECIFICATION_AMBIGUITY,
        "thm:scope-extra-assumption": FindingCategory.SCOPE_MISMATCH,
        "thm:scope-surplus-hypothesis": FindingCategory.SCOPE_SURPLUS,
        "thm:scope-stronger-conclusion": FindingCategory.SCOPE_SURPLUS,
    }

    _INFO_FINDINGS = {
        "thm:scope-surplus-hypothesis",
        "thm:scope-stronger-conclusion",
    }

    def attack(self, unit: TheoremUnit) -> AttackReport:
        category = self._DEFECTS.get(unit.identifier)
        if category is None:
            return AttackReport(findings=[])
        severity = (
            Severity.INFO
            if unit.identifier in self._INFO_FINDINGS
            else Severity.ERROR
        )
        return AttackReport(
            findings=[
                CandidateFinding(
                    id="F1",
                    category=category,
                    severity=severity,
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
    assert len(cases) >= 52

    bad = 0
    clean = 0
    levels: set[int] = set()
    matrix_cases = 0
    matrix_families: set[str] = set()
    truth_values: set[str] = set()
    proof_statuses: set[str] = set()
    scope_relations: set[str] = set()
    hypothesis_relations: set[str] = set()
    conclusion_relations: set[str] = set()

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

        if expectation.family is not None:
            matrix_cases += 1
            matrix_families.add(expectation.family)
            assert expectation.statement_truth is not None
            assert expectation.proof_status is not None
            assert expectation.locality is not None
            assert expectation.fault_class is not None
            assert expectation.detection_methods
            assert expectation.reader_consequence is not None
            assert expectation.deception_level is not None
            assert expectation.downstream_impact is not None
            truth_values.add(expectation.statement_truth)
            proof_statuses.add(expectation.proof_status)

        if expectation.scope_relation is not None:
            assert expectation.hypothesis_relation is not None
            assert expectation.conclusion_relation is not None
            scope_relations.add(expectation.scope_relation)
            hypothesis_relations.add(expectation.hypothesis_relation)
            conclusion_relations.add(expectation.conclusion_relation)

        if expectation.kind == "finding":
            bad += 1
            assert expectation.accepted_categories
        else:
            clean += 1

    assert bad >= 36
    assert clean >= 10
    assert matrix_cases >= 21
    assert {"correctness", "specification", "readability"} <= matrix_families
    assert {"true", "false", "unknown"} <= truth_values
    assert {"valid", "gap", "invalid"} <= proof_statuses
    assert {"exact", "proof_narrower", "proof_stronger"} <= scope_relations
    assert {"exact", "proof_requires_more", "theorem_has_surplus"} <= hypothesis_relations
    assert {
        "exact",
        "proof_establishes_less",
        "proof_establishes_more",
    } <= conclusion_relations
    assert set(range(1, 11)).issubset(levels)


def test_eval_harness_runs_all_review_cases_without_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    cases = _load_cases(Path("eval/cases"))
    review_cases = [case for case in cases if "review" in case[1].modes]
    assert main(["eval/cases", "--model", "fixture-provider"]) == 0

    output = capsys.readouterr().out
    assert output.count("PASS ") == len(review_cases)
    assert f'"cases": {len(review_cases)}' in output
    assert '"failures": 0' in output


def test_eval_max_level_filters_the_review_ladder(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    cases = _load_cases(Path("eval/cases"))
    expected = sum(
        expectation.level <= 2 and "review" in expectation.modes
        for _, expectation in cases
    )

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
