import json
from pathlib import Path

import pytest

import thorn.eval as eval_module
from thorn.dependencies import DependencyNode
from thorn.eval import _load_cases, _select_unit, main
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project, extract_units
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
from thorn.semantic_review import (
    ReviewContext,
    ReviewTargetKind,
    SemanticReviewItem,
)
from thorn.semantic_review_render import SemanticReviewRequest


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
        "thm:riemannian-pythagoras-gap": FindingCategory.HYPOTHESIS_MISMATCH,
        "thm:ring-square-roots-gap": FindingCategory.HYPOTHESIS_MISMATCH,
        "thm:modular-integer-cancellation-gap": FindingCategory.HYPOTHESIS_MISMATCH,
        "thm:arbitrary-dimensional-subsequence-gap": FindingCategory.HYPOTHESIS_MISMATCH,
    }

    _INFO_FINDINGS = {
        "thm:scope-surplus-hypothesis",
        "thm:scope-stronger-conclusion",
    }

    def __init__(self) -> None:
        self.requests = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.attacked: list[str] = []
        self.semantic_requests: list[SemanticReviewRequest] = []
        self.defended = 0

    def _record_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.requests += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens

    def _attack_report(self, identifier: str) -> AttackReport:
        category = self._DEFECTS.get(identifier)
        if category is None:
            return AttackReport(findings=[])
        severity = Severity.INFO if identifier in self._INFO_FINDINGS else Severity.ERROR
        return AttackReport(
            findings=[
                CandidateFinding(
                    id="F1",
                    category=category,
                    severity=severity,
                    title=f"Synthetic finding for {identifier}",
                    explanation="Deterministic test finding.",
                    confidence=0.95,
                )
            ]
        )

    def attack(self, unit: TheoremUnit) -> AttackReport:
        self.attacked.append(unit.identifier)
        self._record_usage(input_tokens=10, output_tokens=2)
        return self._attack_report(unit.identifier)

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        self.semantic_requests.append(request)
        self._record_usage(input_tokens=7, output_tokens=2)
        return self._attack_report(request.item.result.identifier)

    def defend(
        self,
        unit: TheoremUnit,
        findings: list[CandidateFinding],
    ) -> DefenseReport:
        self.defended += 1
        self._record_usage(input_tokens=6, output_tokens=1)
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


def _review_item(identifier: str, result_identifier: str) -> SemanticReviewItem:
    return SemanticReviewItem(
        identifier=identifier,
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=DependencyNode(
            identifier=result_identifier,
            label=result_identifier,
            environment="theorem",
            statement="Synthetic evaluation result.",
            source=SourceRange(file="fixture.tex", start_line=1, end_line=2),
        ),
        trigger_relation_identifiers=[f"{identifier}:edge-a", f"{identifier}:edge-b"],
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
    assert main(
        ["eval/cases", "--model", "fixture-provider", "--structural-only"]
    ) == 0

    output = capsys.readouterr().out
    assert output.count("PASS ") == len(review_cases)
    assert f'"cases": {len(review_cases)}' in output
    assert '"failures": 0' in output
    assert '"review_context": "legacy"' in output


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
            "--structural-only",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert output.count("PASS ") == expected
    assert f'"cases": {expected}' in output


def test_controlled_raw_and_ir_compare_same_case_attack_only_and_keyless(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    assert main(
        [
            "eval/cases/level1_missing_hypothesis",
            "--model",
            "fixture-provider",
            "--compare-raw-ir",
            "--structural-only",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "CONTROLLED_RAW_IR" in output
    assert '"defend_enabled": false' in output
    assert '"source_validation_enabled": false' in output
    assert '"structural_only": true' in output
    assert provider.defended == 0
    assert provider.requests == 2


def test_dependency_aware_review_does_not_call_provider_for_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    assert main(
        [
            "eval/cases/level3_dependency",
            "--model",
            "fixture-provider",
            "--review-context",
            "dependency-aware",
            "--structural-only",
        ]
    ) == 0

    output = capsys.readouterr().out
    assert '"review_context": "dependency-aware"' in output
    assert [request.item.result.identifier for request in provider.semantic_requests] == [
        "lem:threshold",
        "thm:depends",
    ]


def test_semantic_context_taints_only_relations_that_depend_on_bad_result() -> None:
    project = extract_project(Path("eval/cases/level3_dependency/paper.tex"))
    context = build_result_review_context(project, "thm:depends")
    by_identifier = {item.identifier: item for item in context.items}

    assert by_identifier["REL1"].dependency_result_identifiers == ["lem:threshold"]
    assert by_identifier["REL2"].dependency_result_identifiers == []


def test_semantic_review_groups_findings_under_their_target_relations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider = FixtureProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(eval_module, "OpenAIProvider", lambda model: provider)

    assert main(
        [
            "eval/cases/level3_dependency",
            "--model",
            "fixture-provider",
            "--review-context",
            "dependency-aware",
            "--structural-only",
        ]
    ) == 0

    summary = _summary(capsys.readouterr().out)
    result = _single_result(summary)
    semantic_review = result["semantic_review"]
    assert isinstance(semantic_review, list)
    assert [item["identifier"] for item in semantic_review] == [
        "RESULT",
        "REL1",
        "REL2",
    ]

    by_identifier = {item["identifier"]: item for item in semantic_review}
    assert [finding["title"] for finding in by_identifier["RESULT"]["findings"]] == [
        "Synthetic finding for thm:depends-bad-lemma"
    ]
    assert by_identifier["REL1"]["findings"] == []
    assert by_identifier["REL2"]["findings"] == []


def test_review_context_rendering_contains_dependency_evidence() -> None:
    project = extract_project(Path("eval/cases/level3_dependency/paper.tex"))
    context = build_result_review_context(project, "thm:depends")

    request = next(
        request
        for request in (SemanticReviewRequest.from_item(item) for item in context.items)
        if request.item.identifier == "REL1"
    )
    rendered = request.render()
    assert "depends on lem:threshold" in rendered
    assert "0 < x < 1" in rendered


def test_review_item_relations_are_deterministically_sorted() -> None:
    context = ReviewContext(
        result_identifier="thm:synthetic",
        items=[
            _review_item("REL2", "thm:synthetic"),
            _review_item("REL10", "thm:synthetic"),
            _review_item("REL1", "thm:synthetic"),
        ],
    )
    context.sort_items()
    assert [item.identifier for item in context.items] == ["REL1", "REL2", "REL10"]
