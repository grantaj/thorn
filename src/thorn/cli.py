from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path

from thorn.check import CheckFinding, check_project
from thorn.frontends import get_frontend
from thorn.latex import extract_project
from thorn.models import AuditFinding, Severity, TheoremUnit, UnitAudit


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thorn",
        usage="thorn [check|review] FILE [options]",
        description="Correctness linting for mathematical LaTeX manuscripts.",
        epilog=(
            "Modes: 'check' is deterministic and makes no model calls; 'review' runs the "
            "model-backed adversarial audit. Omitting the mode preserves legacy review behavior."
        ),
    )
    parser.add_argument("file", type=Path, help="main LaTeX file")
    parser.add_argument("--dry-run", action="store_true", help="extract units without API calls")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--model", default=os.getenv("THORN_MODEL", "gpt-5.6"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-defender", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=Path(".thorn/cache"))
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--fail-on", choices=("never", "error", "warning"), default="error")
    parser.add_argument(
        "--frontend",
        choices=("current", "regex", "pylatexenc"),
        default="current",
        help="LaTeX parser frontend (development/A-B option; default: current)",
    )
    return parser


def _parse_mode(argv: list[str] | None) -> tuple[str, argparse.Namespace]:
    raw = list(sys.argv[1:] if argv is None else argv)
    mode = "review"
    if raw and raw[0] in {"check", "review"}:
        mode = raw.pop(0)
    return mode, _parser().parse_args(raw)


def _print_units(units: list[TheoremUnit], as_json: bool) -> None:
    if as_json:
        print(json.dumps([unit.model_dump(mode="json") for unit in units], indent=2))
        return
    for unit in units:
        proof = "proof" if unit.proof else "no proof"
        title = f" [{unit.title}]" if unit.title else ""
        print(
            f"{unit.statement_range.file}:{unit.statement_range.start_line} "
            f"{unit.environment}{title} ({proof}) id={unit.identifier}"
        )


def _visible_findings(audits: list[UnitAudit], threshold: float) -> list[AuditFinding]:
    return [
        finding
        for audit in audits
        for finding in audit.findings
        if finding.confidence >= threshold
    ]


def _print_review_text(audits: list[UnitAudit], threshold: float) -> None:
    findings = _visible_findings(audits, threshold)
    if not findings:
        print(f"thorn review: no surviving diagnostics above confidence {threshold:.2f}")
        return
    for finding in findings:
        source = finding.source
        print(
            f"{source.file}:{source.start_line}-{source.end_line}: "
            f"{finding.severity.value} {finding.rule} {finding.title}"
        )
        print(f"  {finding.explanation}")
        for evidence in finding.evidence:
            print(f"  evidence: {evidence}")
        if finding.counterexample:
            print(f"  counterexample: {finding.counterexample}")
        print(
            f"  defender: {finding.defender_verdict.value} "
            f"(confidence {finding.defender_confidence:.2f})"
        )
        print(f"  {finding.defender_explanation}")
        print()


def _print_review_json(audits: list[UnitAudit], threshold: float) -> None:
    payload = {
        "mode": "review",
        "audited_units": len(audits),
        "cached_units": sum(1 for audit in audits if audit.cached),
        "findings": [
            finding.model_dump(mode="json") | {"confidence": finding.confidence}
            for finding in _visible_findings(audits, threshold)
        ],
    }
    print(json.dumps(payload, indent=2))


def _print_check_text(findings: list[CheckFinding]) -> None:
    if not findings:
        print("thorn check: no deterministic structural diagnostics")
        return
    for finding in findings:
        source = finding.source
        print(
            f"{source.file}:{source.start_line}-{source.end_line}: "
            f"{finding.severity.value} {finding.rule} {finding.title}"
        )
        print(f"  {finding.explanation}")
        for evidence in finding.evidence:
            print(f"  evidence: {evidence}")
        print()


def _print_check_json(findings: list[CheckFinding]) -> None:
    print(
        json.dumps(
            {
                "mode": "check",
                "findings": [finding.model_dump(mode="json") for finding in findings],
            },
            indent=2,
        )
    )


def _exit_code(severities: Iterable[Severity], fail_on: str) -> int:
    items = list(severities)
    if fail_on == "never":
        return 0
    if fail_on == "warning":
        return 1 if any(item in (Severity.WARNING, Severity.ERROR) for item in items) else 0
    return 1 if any(item == Severity.ERROR for item in items) else 0


def main(argv: list[str] | None = None) -> int:
    mode, args = _parse_mode(argv)
    if not 0.0 <= args.min_confidence <= 1.0:
        print("thorn: --min-confidence must be between 0 and 1", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 1:
        print("thorn: --limit must be positive", file=sys.stderr)
        return 2

    try:
        frontend = get_frontend(args.frontend)
        project = extract_project(args.file, frontend=frontend)
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        print(f"thorn: could not read project: {exc}", file=sys.stderr)
        return 2

    units = project.units
    if args.limit is not None:
        units = units[: args.limit]

    if args.dry_run:
        _print_units(units, args.format == "json")
        return 0

    if mode == "check":
        check_findings = check_project(project)
        if args.format == "json":
            _print_check_json(check_findings)
        else:
            _print_check_text(check_findings)
        return _exit_code((finding.severity for finding in check_findings), args.fail_on)

    if not units:
        print("thorn: no theorem-like environments found", file=sys.stderr)
        return 0

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "thorn review: OPENAI_API_KEY is not set; run `thorn check` for local analysis",
            file=sys.stderr,
        )
        return 2

    # Model-backed dependencies are imported only after the explicit review boundary.
    from thorn.audit import audit_unit, default_cache
    from thorn.providers.openai import OpenAIProvider

    provider = OpenAIProvider(model=args.model)
    cache = None if args.no_cache else default_cache(args.cache_dir)
    audits: list[UnitAudit] = []
    for index, unit in enumerate(units, start=1):
        if args.format == "text":
            print(f"thorn: auditing {index}/{len(units)} {unit.identifier} ...", file=sys.stderr)
        try:
            audits.append(
                audit_unit(unit, provider, use_defender=not args.no_defender, cache=cache)
            )
        except Exception as exc:  # provider/network failures are CLI diagnostics, not tracebacks
            print(f"thorn: audit failed for {unit.identifier}: {exc}", file=sys.stderr)
            return 2

    if args.format == "json":
        _print_review_json(audits, args.min_confidence)
    else:
        _print_review_text(audits, args.min_confidence)

    review_findings = _visible_findings(audits, args.min_confidence)
    return _exit_code((finding.severity for finding in review_findings), args.fail_on)
