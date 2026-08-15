from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from thorn.check import CheckFinding, check_project
from thorn.latex import extract_project
from thorn.models import (
    AuditFinding,
    FindingCategory,
    Severity,
    TheoremUnit,
    UnitAudit,
)
from thorn.providers.base import AuditProvider

# Test seam retained without importing the OpenAI provider in zero-inference modes.
OpenAIProvider: Callable[[str], AuditProvider] | None = None


class CaseExpectation(BaseModel):
    name: str
    kind: str = Field(pattern="^(finding|clean)$")
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
    parser.add_argument("--no-defender", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="validate fixtures and extraction without making API calls",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="run deterministic thorn check expectations with no model/API calls",
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
        cases.append((tex_path, expectation))
    if not cases:
        raise ValueError(f"no *.json evaluation cases found in {case_dir}")
    names = [expectation.name for _, expectation in cases]
    if len(names) != len(set(names)):
        raise ValueError("evaluation case names must be unique")
    return cases


def _load_check_expectations(
    case_dir: Path,
    cases: list[tuple[Path, CaseExpectation]],
) -> dict[str, list[str]]:
    path = case_dir.parent / "check-expectations.json"
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

    case_names = {expectation.name for _, expectation in cases}
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
    findings: list[AuditFinding],
    expectation: CaseExpectation,
    confidence: float,
) -> list[AuditFinding]:
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


def _make_openai_provider(model: str) -> AuditProvider:
    if OpenAIProvider is not None:
        return OpenAIProvider(model)

    from thorn.providers.openai import OpenAIProvider as RealOpenAIProvider

    return RealOpenAIProvider(model=model)


def _audit_unit(
    unit: TheoremUnit,
    provider: AuditProvider,
    *,
    use_defender: bool,
) -> UnitAudit:
    from thorn.audit import audit_unit

    return audit_unit(unit, provider, use_defender=use_defender, cache=None)


def _check_case(
    findings: list[CheckFinding],
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


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    started = time.perf_counter()
    try:
        all_cases = _load_cases(args.case_dir)
        check_expectations = (
            _load_check_expectations(args.case_dir, all_cases) if args.check else None
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

    provider: AuditProvider | None = None
    if not args.validate_only and not args.check:
        if not os.getenv("OPENAI_API_KEY"):
            print(
                "thorn-eval: OPENAI_API_KEY is required unless "
                "--validate-only or --check is used"
            )
            return 2
        provider = _make_openai_provider(args.model)

    failures = 0
    for tex_path, expectation in cases:
        project = extract_project(tex_path)
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

        if args.check:
            assert check_expectations is not None
            check_findings = check_project(project)
            passed, detail = _check_case(
                check_findings,
                check_expectations[expectation.name],
            )
            status = "PASS" if passed else "FAIL"
            print(f"{status} CHECK L{expectation.level} {expectation.name}: {detail}")
            if not passed:
                failures += 1
                for finding in check_findings:
                    print(
                        "     observed "
                        f"{finding.rule}/{finding.category.value}/"
                        f"{finding.severity.value}: {finding.title} "
                        f"at {finding.source.file}:{finding.source.start_line}"
                    )
            continue

        assert provider is not None
        audit = _audit_unit(
            unit,
            provider,
            use_defender=not args.no_defender,
        )
        visible = [
            finding
            for finding in audit.findings
            if finding.confidence >= args.min_confidence
        ]
        matches = _matching_findings(
            visible,
            expectation,
            args.min_confidence,
        )

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
                ", ".join(
                    f"{item.rule}/{item.category.value}"
                    for item in matches
                )
                if passed
                else "expected defect not detected"
            )

        status = "PASS" if passed else "FAIL"
        print(f"{status} L{expectation.level} {expectation.name}: {detail}")
        if not passed:
            failures += 1
            for finding in visible:
                print(
                    "     observed "
                    f"{finding.rule}/{finding.category.value}/"
                    f"{finding.severity.value} "
                    f"confidence={finding.confidence:.2f}: {finding.title}"
                )

    mode = "check" if args.check else "validate" if args.validate_only else "review"
    summary: dict[str, object] = {
        "cases": len(cases),
        "failures": failures,
        "mode": mode,
        "model": None if args.validate_only or args.check else args.model,
        "min_confidence": args.min_confidence,
        "defender": not args.no_defender,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    if provider is not None and hasattr(provider, "requests"):
        summary.update(
            {
                "requests": provider.requests,
                "input_tokens": provider.input_tokens,
                "output_tokens": provider.output_tokens,
                "total_tokens": provider.total_tokens,
            }
        )

    print()
    print(json.dumps(summary, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
