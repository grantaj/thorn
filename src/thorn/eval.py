from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from thorn.audit import audit_unit
from thorn.latex import extract_units
from thorn.models import AuditFinding, FindingCategory, Severity
from thorn.providers.openai import OpenAIProvider


class CaseExpectation(BaseModel):
    name: str
    kind: str = Field(pattern="^(finding|clean)$")
    source: str | None = None
    accepted_categories: list[FindingCategory] = Field(default_factory=list)
    minimum_severity: Severity = Severity.WARNING


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
    parser.add_argument("case_dir", type=Path, nargs="?", default=Path("eval/cases"))
    parser.add_argument("--model", default=os.getenv("THORN_MODEL", "gpt-5.6"))
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--no-defender", action="store_true")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate fixtures and extraction without making API calls",
    )
    return parser


def _load_cases(case_dir: Path) -> list[tuple[Path, CaseExpectation]]:
    cases: list[tuple[Path, CaseExpectation]] = []
    for metadata_path in sorted(case_dir.glob("*.json")):
        tex_path = metadata_path.with_suffix(".tex")
        if not tex_path.exists():
            raise FileNotFoundError(f"missing fixture for {metadata_path}: {tex_path}")
        expectation = CaseExpectation.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        cases.append((tex_path, expectation))
    if not cases:
        raise ValueError(f"no *.json evaluation cases found in {case_dir}")
    return cases


def _matching_findings(
    findings: list[AuditFinding], expectation: CaseExpectation, confidence: float
) -> list[AuditFinding]:
    return [
        finding
        for finding in findings
        if finding.confidence >= confidence
        and (
            not expectation.accepted_categories
            or finding.category in expectation.accepted_categories
        )
        and _SEVERITY_RANK[finding.severity] >= _SEVERITY_RANK[expectation.minimum_severity]
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = _load_cases(args.case_dir)
    except (OSError, ValueError) as exc:
        print(f"thorn-eval: {exc}")
        return 2

    provider = None
    if not args.validate_only:
        if not os.getenv("OPENAI_API_KEY"):
            print("thorn-eval: OPENAI_API_KEY is required unless --validate-only is used")
            return 2
        provider = OpenAIProvider(model=args.model)

    failures = 0
    for tex_path, expectation in cases:
        units = extract_units(tex_path)
        if len(units) != 1:
            print(
                f"FAIL {expectation.name}: expected one theorem-like unit, "
                f"extracted {len(units)}"
            )
            failures += 1
            continue

        if args.validate_only:
            print(f"OK   {expectation.name}: fixture extracts one {units[0].environment}")
            continue

        assert provider is not None
        audit = audit_unit(units[0], provider, use_defender=not args.no_defender, cache=None)
        visible = [
            finding
            for finding in audit.findings
            if finding.confidence >= args.min_confidence
        ]
        matches = _matching_findings(visible, expectation, args.min_confidence)

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

        status = "PASS" if passed else "FAIL"
        print(f"{status} {expectation.name}: {detail}")
        if not passed:
            failures += 1
            for finding in visible:
                print(
                    "     observed "
                    f"{finding.rule}/{finding.category.value}/{finding.severity.value} "
                    f"confidence={finding.confidence:.2f}: {finding.title}"
                )

    print()
    print(json.dumps({"cases": len(cases), "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
