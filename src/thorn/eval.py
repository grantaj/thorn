from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from thorn.analysis import AnalysisFinding, analyze_project
from thorn.dependencies import ExtractedProject
from thorn.eval_review import build_result_review_context
from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import LinguisticFrontend
from thorn.local_nlp import select_linguistic_frontend
from thorn.models import (
    AuditFinding,
    FindingCategory,
    Severity,
    TheoremUnit,
    UnitAudit,
)
from thorn.providers.base import EvaluationProvider
from thorn.semantic_audit import SemanticReviewResult, review_semantic_context
from thorn.semantic_review import ReviewContext, build_review_context
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend

# Test seam retained without importing the OpenAI provider in zero-inference modes.
OpenAIProvider: Callable[[str], EvaluationProvider] | None = None
CaseMode = Literal["analyze", "review"]
ReviewContextChoice = Literal["raw", "ir", "targeted"]
ReviewStrategy = Literal["legacy", "raw", "ir", "targeted"]
PreflightTriggerStatus = Literal["AMBIGUOUS", "UNRESOLVED"]


def _default_case_modes() -> list[CaseMode]:
    return ["analyze", "review"]


class CaseExpectation(BaseModel):
    name: str
    kind: str = Field(pattern="^(finding|clean)$")
    modes: list[CaseMode] = Field(default_factory=_default_case_modes)
    source: str | None = None
    accepted_categories: list[FindingCategory] = Field(default_factory=list)
    minimum_severity: Severity = Severity.WARNING
    level: int = Field(default=0, ge=0)
    capability: str | None = None
    target_identifier: str | None = None
    root_cause_identifier: str | None = None
    repairability: Literal[
        "trivial",
        "local",
        "statement",
        "structural",
        "none",
    ] | None = None
    family: Literal[
        "correctness",
        "specification",
        "readability",
        "scholarship",
    ] | None = None
    statement_truth: Literal[
        "true",
        "false",
        "vacuous",
        "unknown",
        "not_applicable",
    ] | None = None
    proof_status: Literal[
        "valid",
        "gap",
        "invalid",
        "circular",
        "not_applicable",
    ] | None = None
    locality: Literal["line", "proof", "section", "paper", "external"] | None = None
    fault_class: str | None = None
    detection_methods: list[str] = Field(default_factory=list)
    reader_consequence: Literal[
        "fatal",
        "risky",
        "clarity",
        "opportunity",
        "not_applicable",
    ] | None = None
    deception_level: Literal["obvious", "plausible", "sneaky"] | None = None
    downstream_impact: Literal[
        "isolated",
        "one_result",
        "multiple_results",
    ] | None = None
    scope_relation: Literal[
        "exact",
        "proof_narrower",
        "proof_stronger",
        "incomparable",
        "unknown",
        "not_applicable",
    ] | None = None
    hypothesis_relation: Literal[
        "exact",
        "proof_requires_more",
        "theorem_has_surplus",
        "unknown",
        "not_applicable",
    ] | None = None
    conclusion_relation: Literal[
        "exact",
        "proof_establishes_less",
        "proof_establishes_more",
        "incomparable",
        "unknown",
        "not_applicable",
    ] | None = None
    notes: str | None = None


class ObservedFinding(BaseModel):
    id: str
    rule: str
    category: FindingCategory
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    title: str
    review_item_identifier: str | None = None


class ProviderUsage(BaseModel):
    requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    def minus(self, earlier: ProviderUsage) -> ProviderUsage:
        return ProviderUsage(
            requests=self.requests - earlier.requests,
            input_tokens=self.input_tokens - earlier.input_tokens,
            output_tokens=self.output_tokens - earlier.output_tokens,
            total_tokens=self.total_tokens - earlier.total_tokens,
        )


class EvaluationResult(BaseModel):
    case_name: str
    fixture: str
    target_identifier: str
    review_strategy: ReviewStrategy
    expected_kind: str = Field(pattern="^(finding|clean)$")
    expectation: CaseExpectation
    passed: bool
    detail: str
    observed_findings: list[ObservedFinding] = Field(default_factory=list)
    semantic_request_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0.0)
    semantic_review_item_count: int = Field(ge=0)
    sent_review_item_identifiers: list[str] = Field(default_factory=list)
    no_semantic_escalation_required: bool | None = None
    model_identifier: str | None = None
    defender_used: bool = False


class TargetedPreflightTrigger(BaseModel):
    relation_identifier: str
    status: PreflightTriggerStatus


class TargetedPreflightItem(BaseModel):
    review_item_identifier: str
    trigger_relations: list[TargetedPreflightTrigger] = Field(default_factory=list)


class TargetedPreflightRecord(BaseModel):
    fixture: str
    case_name: str
    selected_result_identifier: str
    semantic_review_item_count: int = Field(ge=0)
    review_item_identifiers: list[str] = Field(default_factory=list)
    review_items: list[TargetedPreflightItem] = Field(default_factory=list)
    would_make_semantic_request_count: int = Field(ge=0)
    provider_request_count: int = Field(default=0, ge=0)
    no_semantic_escalation_required: bool


_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thorn-eval",
        description="Run Thorn against a directory of known regression cases.",
    )
    parser.add_argument(
        "case_dir",
        type=Path,
        nargs="?",
        default=Path("eval/cases"),
    )
    parser.add_argument("--model", default=os.getenv("THORN_MODEL", "gpt-5.6"))
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument(
        "--max-level",
        type=int,
        help="run only cases at or below this TDD ladder level",
    )
    parser.add_argument(
        "--case-filter",
        help="run only cases whose name or fixture path contains this text",
    )
    parser.add_argument(
        "--review-context",
        choices=("raw", "ir", "targeted"),
        help=(
            "select a controlled semantic-review strategy: raw and ir are attack-only "
            "one-request context A/B modes; targeted reviews only deterministic IR "
            "items selected for escalation"
        ),
    )
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help=(
            "disable the normal local linguistic frontend for semantic evaluation; intended "
            "for debugging, constrained environments, and parser-neutral unit tests"
        ),
    )
    parser.add_argument(
        "--no-defender",
        action="store_true",
        help="disable the defender in the backward-compatible default review mode",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="validate fixtures and extraction without making API calls",
    )
    mode.add_argument(
        "--analyze",
        action="store_true",
        help="run deterministic structural-analysis expectations with no model/API calls",
    )
    mode.add_argument(
        "--targeted-preflight",
        action="store_true",
        help=(
            "inspect targeted SemanticReviewItem selection through the normal local linguistic "
            "frontend without constructing or calling a semantic provider"
        ),
    )
    return parser


def _load_cases(case_dir: Path) -> list[tuple[Path, CaseExpectation]]:
    cases: list[tuple[Path, CaseExpectation]] = []
    for metadata_path in sorted(case_dir.rglob("*.json")):
        tex_path = metadata_path.with_suffix(".tex")
        if not tex_path.exists():
            raise FileNotFoundError(
                f"missing fixture for {metadata_path}: {tex_path}"
            )
        expectation = CaseExpectation.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
        if not expectation.modes:
            raise ValueError(f"evaluation case {expectation.name!r} has no enabled modes")
        cases.append((tex_path, expectation))
    if not cases:
        raise ValueError(f"no *.json evaluation cases found in {case_dir}")
    names = [expectation.name for _, expectation in cases]
    if len(names) != len(set(names)):
        raise ValueError("evaluation case names must be unique")
    return cases


def _load_analysis_expectations(
    case_dir: Path,
    cases: list[tuple[Path, CaseExpectation]],
) -> dict[str, list[str]]:
    path = case_dir.parent / "analysis-expectations.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid deterministic expectation file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"deterministic expectation file {path} must be a JSON object")

    expectations: dict[str, list[str]] = {}
    for name, rules in payload.items():
        if not isinstance(name, str) or not isinstance(rules, list) or not all(
            isinstance(rule, str) for rule in rules
        ):
            raise ValueError(
                f"deterministic expectation for {name!r} must be a list of rule codes"
            )
        expectations[name] = rules

    case_names = {
        expectation.name
        for _, expectation in cases
        if "analyze" in expectation.modes
    }
    expectation_names = set(expectations)
    missing = sorted(case_names - expectation_names)
    extra = sorted(expectation_names - case_names)
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"missing cases: {', '.join(missing)}")
        if extra:
            parts.append(f"unknown cases: {', '.join(extra)}")
        raise ValueError(
            f"deterministic expectation coverage mismatch in {path}: " + "; ".join(parts)
        )
    return expectations


def _select_unit(
    units: list[TheoremUnit],
    expectation: CaseExpectation,
) -> TheoremUnit:
    if expectation.target_identifier is not None:
        matches = [
            unit
            for unit in units
            if unit.identifier == expectation.target_identifier
        ]
        if len(matches) != 1:
            raise ValueError(
                f"target {expectation.target_identifier!r} matched "
                f"{len(matches)} theorem-like units"
            )
        return matches[0]
    if len(units) != 1:
        raise ValueError(
            "expected one theorem-like unit or target_identifier, "
            f"extracted {len(units)}"
        )
    return units[0]


def _matching_findings(
    findings: list[ObservedFinding],
    expectation: CaseExpectation,
    confidence: float,
) -> list[ObservedFinding]:
    return [
        finding
        for finding in findings
        if finding.confidence >= confidence
        and (
            not expectation.accepted_categories
            or finding.category in expectation.accepted_categories
        )
        and _SEVERITY_RANK[finding.severity]
        >= _SEVERITY_RANK[expectation.minimum_severity]
    ]


def _make_openai_provider(model: str) -> EvaluationProvider:
    if OpenAIProvider is not None:
        return OpenAIProvider(model)

    from thorn.providers.openai import OpenAIProvider as RealOpenAIProvider

    return RealOpenAIProvider(model=model)


def _audit_unit(
    unit: TheoremUnit,
    provider: EvaluationProvider,
    *,
    use_defender: bool,
) -> UnitAudit:
    from thorn.audit import audit_unit

    return audit_unit(unit, provider, use_defender=use_defender, cache=None)


def _analyze_case(
    findings: list[AnalysisFinding],
    expected_rules: list[str],
) -> tuple[bool, str]:
    observed_rules = sorted(finding.rule for finding in findings)
    wanted_rules = sorted(expected_rules)
    passed = observed_rules == wanted_rules
    if passed:
        detail = (
            ", ".join(observed_rules)
            if observed_rules
            else "no deterministic diagnostics expected or observed"
        )
    else:
        detail = (
            f"expected {wanted_rules or ['<none>']}, "
            f"observed {observed_rules or ['<none>']}"
        )
    return passed, detail


def _provider_usage_snapshot(provider: EvaluationProvider | None) -> ProviderUsage:
    if provider is None:
        return ProviderUsage()
    return ProviderUsage(
        requests=provider.requests,
        input_tokens=provider.input_tokens,
        output_tokens=provider.output_tokens,
        total_tokens=provider.total_tokens,
    )


def _provider_usage(provider: EvaluationProvider | None) -> dict[str, object]:
    if provider is None:
        return {}
    return _provider_usage_snapshot(provider).model_dump()


def _observed_audit_findings(findings: list[AuditFinding]) -> list[ObservedFinding]:
    return [
        ObservedFinding(
            id=f"{finding.unit_id}:{finding.rule}:{index}",
            rule=finding.rule,
            category=finding.category,
            severity=finding.severity,
            confidence=finding.confidence,
            title=finding.title,
        )
        for index, finding in enumerate(findings, start=1)
    ]


def _observed_semantic_findings(
    results: list[SemanticReviewResult],
) -> list[ObservedFinding]:
    observed: list[ObservedFinding] = []
    for result in results:
        for finding in result.report.findings:
            observed.append(
                ObservedFinding(
                    id=finding.id,
                    rule=finding.rule,
                    category=finding.category,
                    severity=finding.severity,
                    confidence=finding.confidence,
                    title=finding.title,
                    review_item_identifier=result.item_identifier,
                )
            )
    return observed


def _evaluate_expectation(
    findings: list[ObservedFinding],
    expectation: CaseExpectation,
    confidence: float,
) -> tuple[bool, str, list[ObservedFinding]]:
    visible = [finding for finding in findings if finding.confidence >= confidence]
    matches = _matching_findings(visible, expectation, confidence)

    if expectation.kind == "clean":
        passed = not visible
        detail = (
            "no surviving diagnostics"
            if passed
            else f"{len(visible)} unexpected diagnostic(s)"
        )
    else:
        passed = bool(matches)
        detail = (
            ", ".join(f"{item.rule}/{item.category.value}" for item in matches)
            if passed
            else "expected defect not detected"
        )
    return passed, detail, visible


def _targeted_context(project: ExtractedProject, unit: TheoremUnit) -> ReviewContext:
    generated = build_review_context(project)
    return ReviewContext(
        items=[
            item
            for item in generated.items
            if item.result.identifier == unit.identifier
        ]
    )


def _extract_evaluation_project(
    tex_path: Path,
    *,
    use_local_linguistic_frontend: bool,
    linguistic_frontend: LinguisticFrontend | None = None,
) -> ExtractedProject:
    selected_linguistic_frontend = select_linguistic_frontend(
        structural_only=not use_local_linguistic_frontend,
        injected=linguistic_frontend,
        factory=SpacyLinguisticFrontend,
    )
    return extract_project(
        tex_path,
        linguistic_frontend=selected_linguistic_frontend,
    )


def _targeted_preflight_record(
    *,
    tex_path: Path,
    project: ExtractedProject,
    unit: TheoremUnit,
    expectation: CaseExpectation,
) -> TargetedPreflightRecord:
    context = _targeted_context(project, unit)
    relation_by_identifier = {
        relation.identifier: relation
        for relation in project.proof_support_graph.edges
    }
    review_items: list[TargetedPreflightItem] = []
    for item in context.items:
        triggers: list[TargetedPreflightTrigger] = []
        for relation_identifier in item.trigger_relation_identifiers:
            relation = relation_by_identifier.get(relation_identifier)
            if relation is None:
                raise ValueError(
                    f"review item {item.identifier!r} references unknown trigger relation "
                    f"{relation_identifier!r}"
                )
            if relation.status not in {
                InferenceStatus.AMBIGUOUS,
                InferenceStatus.UNRESOLVED,
            }:
                raise ValueError(
                    f"review item {item.identifier!r} has non-uncertain trigger relation "
                    f"{relation_identifier!r} ({relation.status.value})"
                )
            trigger_status: PreflightTriggerStatus = (
                "AMBIGUOUS"
                if relation.status is InferenceStatus.AMBIGUOUS
                else "UNRESOLVED"
            )
            triggers.append(
                TargetedPreflightTrigger(
                    relation_identifier=relation_identifier,
                    status=trigger_status,
                )
            )
        review_items.append(
            TargetedPreflightItem(
                review_item_identifier=item.identifier,
                trigger_relations=triggers,
            )
        )

    identifiers = [item.review_item_identifier for item in review_items]
    item_count = len(review_items)
    return TargetedPreflightRecord(
        fixture=str(tex_path),
        case_name=expectation.name,
        selected_result_identifier=unit.identifier,
        semantic_review_item_count=item_count,
        review_item_identifiers=identifiers,
        review_items=review_items,
        would_make_semantic_request_count=item_count,
        provider_request_count=0,
        no_semantic_escalation_required=item_count == 0,
    )


def _print_targeted_preflight(record: TargetedPreflightRecord, level: int) -> None:
    print(
        f"PREFLIGHT TARGETED L{level} {record.case_name}: "
        f"target={record.selected_result_identifier} "
        f"items={record.semantic_review_item_count} "
        f"would_request={record.would_make_semantic_request_count} "
        f"provider_requests={record.provider_request_count} "
        f"no_escalation={str(record.no_semantic_escalation_required).lower()}"
    )
    for item in record.review_items:
        print(f"     item {item.review_item_identifier}")
        for trigger in item.trigger_relations:
            print(f"       trigger {trigger.relation_identifier} {trigger.status}")


def _run_review_strategy(
    *,
    tex_path: Path,
    project: ExtractedProject,
    unit: TheoremUnit,
    expectation: CaseExpectation,
    provider: EvaluationProvider,
    strategy: ReviewStrategy,
    min_confidence: float,
    use_defender: bool,
) -> tuple[EvaluationResult, list[ObservedFinding]]:
    before = _provider_usage_snapshot(provider)
    started = time.perf_counter()
    item_identifiers: list[str] = []
    item_count = 0
    no_escalation: bool | None = None
    defender_used = False

    if strategy == "legacy":
        audit = _audit_unit(unit, provider, use_defender=use_defender)
        findings = _observed_audit_findings(audit.findings)
        defender_used = use_defender
    elif strategy == "raw":
        audit = _audit_unit(unit, provider, use_defender=False)
        findings = _observed_audit_findings(audit.findings)
    else:
        if strategy == "ir":
            context = build_result_review_context(project, unit.identifier)
        else:
            context = _targeted_context(project, unit)
            no_escalation = not context.items
        item_count = len(context.items)
        semantic_results = review_semantic_context(context, provider)
        item_identifiers = [result.item_identifier for result in semantic_results]
        findings = _observed_semantic_findings(semantic_results)

    elapsed = time.perf_counter() - started
    usage = _provider_usage_snapshot(provider).minus(before)
    passed, detail, visible = _evaluate_expectation(
        findings,
        expectation,
        min_confidence,
    )
    result = EvaluationResult(
        case_name=expectation.name,
        fixture=str(tex_path),
        target_identifier=unit.identifier,
        review_strategy=strategy,
        expected_kind=expectation.kind,
        expectation=expectation.model_copy(deep=True),
        passed=passed,
        detail=detail,
        observed_findings=findings,
        semantic_request_count=usage.requests,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        elapsed_seconds=round(elapsed, 6),
        semantic_review_item_count=item_count,
        sent_review_item_identifiers=item_identifiers,
        no_semantic_escalation_required=no_escalation,
        model_identifier=provider.model,
        defender_used=defender_used,
    )
    return result, visible


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started = time.perf_counter()
    if args.targeted_preflight and args.review_context not in {None, "targeted"}:
        print("thorn-eval: --targeted-preflight is only compatible with targeted review context")
        return 2

    try:
        all_cases = _load_cases(args.case_dir)
        analysis_expectations = (
            _load_analysis_expectations(args.case_dir, all_cases) if args.analyze else None
        )
    except (OSError, ValueError) as exc:
        print(f"thorn-eval: {exc}")
        return 2

    cases = all_cases
    if args.max_level is not None:
        cases = [
            (path, expectation)
            for path, expectation in cases
            if expectation.level <= args.max_level
        ]

    if args.case_filter:
        needle = args.case_filter.casefold()
        cases = [
            (path, expectation)
            for path, expectation in cases
            if needle in expectation.name.casefold()
            or needle in str(path).casefold()
        ]
        if not cases:
            print(f"thorn-eval: no cases matched --case-filter {args.case_filter!r}")
            return 2

    if args.analyze:
        cases = [
            (path, expectation)
            for path, expectation in cases
            if "analyze" in expectation.modes
        ]
    elif not args.validate_only:
        cases = [
            (path, expectation)
            for path, expectation in cases
            if "review" in expectation.modes
        ]

    provider: EvaluationProvider | None = None
    if not args.validate_only and not args.analyze and not args.targeted_preflight:
        if OpenAIProvider is None and not os.getenv("OPENAI_API_KEY"):
            print(
                "thorn-eval: OPENAI_API_KEY is required unless --validate-only, "
                "--analyze, or --targeted-preflight is used"
            )
            return 2
        provider = _make_openai_provider(args.model)

    review_strategy: ReviewStrategy = (
        "targeted" if args.targeted_preflight else args.review_context or "legacy"
    )
    review_results: list[EvaluationResult] = []
    preflight_results: list[TargetedPreflightRecord] = []
    failures = 0
    for tex_path, expectation in cases:
        use_local_linguistic_frontend = (
            not args.structural_only
            and not args.validate_only
            and not args.analyze
        )
        try:
            project = _extract_evaluation_project(
                tex_path,
                use_local_linguistic_frontend=use_local_linguistic_frontend,
            )
        except LinguisticFrontendUnavailable as exc:
            print(
                "thorn-eval: local linguistic frontend unavailable: "
                f"{exc}. Install the local spaCy model or rerun with --structural-only."
            )
            return 2
        except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
            print(f"FAIL {expectation.name}: could not extract project: {exc}")
            failures += 1
            continue

        units = project.units
        try:
            unit = _select_unit(units, expectation)
        except ValueError as exc:
            print(f"FAIL {expectation.name}: {exc}")
            failures += 1
            continue

        if expectation.root_cause_identifier is not None:
            root_units = [
                candidate
                for candidate in units
                if candidate.identifier == expectation.root_cause_identifier
            ]
            if len(root_units) != 1:
                print(
                    f"FAIL {expectation.name}: root cause "
                    f"{expectation.root_cause_identifier!r} matched "
                    f"{len(root_units)} theorem-like units"
                )
                failures += 1
                continue
            if not any(
                expectation.root_cause_identifier in reference
                for reference in unit.referenced_results
            ):
                print(
                    f"FAIL {expectation.name}: target does not reference "
                    f"declared root cause {expectation.root_cause_identifier!r}"
                )
                failures += 1
                continue

        if args.validate_only:
            print(
                f"OK   L{expectation.level} {expectation.name}: "
                f"target {unit.identifier} extracts as {unit.environment}"
            )
            continue

        if args.analyze:
            assert analysis_expectations is not None
            analysis_findings = analyze_project(project)
            passed, detail = _analyze_case(
                analysis_findings,
                analysis_expectations[expectation.name],
            )
            status = "PASS" if passed else "FAIL"
            print(f"{status} ANALYZE L{expectation.level} {expectation.name}: {detail}")
            if not passed:
                failures += 1
                for analysis_finding in analysis_findings:
                    print(
                        "     observed "
                        f"{analysis_finding.rule}/{analysis_finding.category.value}/"
                        f"{analysis_finding.severity.value}: {analysis_finding.title} "
                        f"at {analysis_finding.source.file}:"
                        f"{analysis_finding.source.start_line}"
                    )
            continue

        if args.targeted_preflight:
            try:
                preflight = _targeted_preflight_record(
                    tex_path=tex_path,
                    project=project,
                    unit=unit,
                    expectation=expectation,
                )
            except ValueError as exc:
                print(f"FAIL {expectation.name}: targeted preflight: {exc}")
                failures += 1
                continue
            preflight_results.append(preflight)
            _print_targeted_preflight(preflight, expectation.level)
            continue

        assert provider is not None
        result, visible = _run_review_strategy(
            tex_path=tex_path,
            project=project,
            unit=unit,
            expectation=expectation,
            provider=provider,
            strategy=review_strategy,
            min_confidence=args.min_confidence,
            use_defender=not args.no_defender,
        )
        review_results.append(result)

        status = "PASS" if result.passed else "FAIL"
        if review_strategy == "legacy":
            print(f"{status} L{expectation.level} {expectation.name}: {result.detail}")
        else:
            print(
                f"{status} {review_strategy.upper()} L{expectation.level} "
                f"{expectation.name}: {result.detail}"
            )
        if not result.passed:
            failures += 1
            for finding in visible:
                print(
                    "     observed "
                    f"{finding.rule}/{finding.category.value}/"
                    f"{finding.severity.value} confidence={finding.confidence:.2f}: "
                    f"{finding.title}"
                )

    if args.targeted_preflight:
        mode = "targeted-preflight"
    elif args.analyze:
        mode = "analyze"
    elif args.validate_only:
        mode = "validate"
    else:
        mode = "review"

    defender = (
        not args.no_defender
        if mode == "review" and review_strategy == "legacy"
        else False
    )
    summary: dict[str, object] = {
        "cases": len(cases),
        "failures": failures,
        "mode": mode,
        "review_context": (
            "targeted"
            if mode == "targeted-preflight"
            else None if mode != "review" else review_strategy
        ),
        "model": None if mode != "review" else args.model,
        "min_confidence": args.min_confidence,
        "defender": defender,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    summary.update(_provider_usage(provider))
    if mode == "review":
        summary["results"] = [
            result.model_dump(mode="json")
            for result in review_results
        ]
    elif mode == "targeted-preflight":
        summary.update(
            {
                "provider_instantiated": False,
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "results": [
                    result.model_dump(mode="json")
                    for result in preflight_results
                ],
            }
        )

    print()
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
