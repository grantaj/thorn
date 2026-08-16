from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from collections.abc import Iterable
from pathlib import Path

from thorn import __version__
from thorn.analysis import AnalysisFinding, analyze_project
from thorn.dependencies import ExtractedProject
from thorn.frontends import get_frontend
from thorn.latex import extract_project
from thorn.local_nlp import select_linguistic_frontend
from thorn.models import AuditFinding, Severity, TheoremUnit, UnitAudit
from thorn.report import ReviewExecution, build_report
from thorn.report_html import write_report_html
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend

_MODES = {"analyze", "ir", "review", "report"}
_DEFAULT_REPORT_SENTINEL = "__thorn_default_report__"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thorn",
        usage="thorn [analyze|ir|review|report] FILE [options]",
        description="Mathematical document analysis and semantic review for LaTeX manuscripts.",
        epilog=(
            "Modes: 'analyze' runs deterministic structural analysis over Thorn Math IR; "
            "'ir' inspects or exports that IR; 'review' runs model-backed mathematical review; "
            "'report' writes a self-contained local review report. Omitting the mode means "
            "'review'."
        ),
    )
    parser.add_argument("file", type=Path, help="main LaTeX file")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--model", default=os.getenv("THORN_MODEL", "gpt-5.6"))
    parser.add_argument("--limit", type=int, default=None, help="review only the first N results")
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
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help=(
            "disable the normal local linguistic frontend; intended for debugging, constrained "
            "environments, and lightweight deterministic tests"
        ),
    )
    parser.add_argument(
        "--report",
        nargs="?",
        const=_DEFAULT_REPORT_SENTINEL,
        default=None,
        metavar="HTML",
        help=(
            "also write a self-contained HTML report; optionally choose the path "
            "(default: <input>.thorn-report.html)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output path for `thorn report`",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the generated report with the operating system's default browser",
    )
    return parser


def _parse_mode(argv: list[str] | None) -> tuple[str, argparse.Namespace]:
    raw = list(sys.argv[1:] if argv is None else argv)
    mode = "review"
    if raw and raw[0] in _MODES:
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


def _print_ir(project: ExtractedProject, as_json: bool) -> None:
    if as_json:
        print(json.dumps(project.model_dump(mode="json"), indent=2))
        return

    print(f"Thorn Math IR: {project.main_file}")
    print(f"  theorem/result units: {len(project.units)}")
    print(f"  dependency edges: {len(project.dependency_graph.edges)}")
    print(f"  symbols: {len(project.symbol_table.symbols)}")
    if project.units:
        print()
        _print_units(project.units, False)


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


def _print_analysis_text(findings: list[AnalysisFinding]) -> None:
    if not findings:
        print("thorn analyze: no deterministic structural diagnostics")
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


def _print_analysis_json(findings: list[AnalysisFinding]) -> None:
    print(
        json.dumps(
            {
                "mode": "analyze",
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


def _default_report_path(main_file: Path) -> Path:
    return main_file.with_name(f"{main_file.stem}.thorn-report.html")


def _requested_report_path(mode: str, args: argparse.Namespace) -> Path | None:
    main_file: Path = args.file
    output: Path | None = args.output
    report_argument: str | Path | None = args.report
    if mode == "report":
        return output or _default_report_path(main_file)
    if report_argument is None:
        return None
    if report_argument == _DEFAULT_REPORT_SENTINEL:
        return _default_report_path(main_file)
    return Path(report_argument)


def _emit_report(
    project: ExtractedProject,
    destination: Path,
    *,
    analysis_findings: list[AnalysisFinding],
    audits: list[UnitAudit] | None = None,
    model: str | None = None,
    review_execution: ReviewExecution = ReviewExecution.UNKNOWN,
    min_confidence: float = 0.65,
    open_browser: bool = False,
    path_to_stderr: bool = False,
) -> Path:
    report = build_report(
        project,
        analysis_findings=analysis_findings,
        audits=audits or (),
        model=model,
        review_execution=review_execution,
        min_confidence=min_confidence,
        thorn_version=__version__,
    )
    written = write_report_html(report, destination)
    stream = sys.stderr if path_to_stderr else sys.stdout
    print(f"Report: {written}", file=stream)
    if open_browser:
        try:
            webbrowser.open(written.as_uri())
        except webbrowser.Error as exc:
            print(f"thorn: could not open report browser: {exc}", file=sys.stderr)
    return written


def main(argv: list[str] | None = None) -> int:
    mode, args = _parse_mode(argv)
    if not 0.0 <= args.min_confidence <= 1.0:
        print("thorn: --min-confidence must be between 0 and 1", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 1:
        print("thorn: --limit must be positive", file=sys.stderr)
        return 2
    if mode != "report" and args.output is not None:
        print("thorn: --output is only valid with `thorn report`", file=sys.stderr)
        return 2
    if mode == "report" and args.report is not None:
        print("thorn: use --output to choose the `thorn report` destination", file=sys.stderr)
        return 2
    if mode == "ir" and args.report is not None:
        print("thorn: --report is not supported with `thorn ir`", file=sys.stderr)
        return 2
    if args.open and mode != "report" and args.report is None:
        print("thorn: --open requires `thorn report` or --report", file=sys.stderr)
        return 2

    try:
        frontend = get_frontend(args.frontend)
        linguistic_frontend = select_linguistic_frontend(
            structural_only=args.structural_only,
            factory=SpacyLinguisticFrontend,
        )
        project = extract_project(
            args.file,
            frontend=frontend,
            linguistic_frontend=linguistic_frontend,
        )
    except LinguisticFrontendUnavailable as exc:
        print(
            "thorn: local linguistic frontend unavailable: "
            f"{exc}. Install the local spaCy model or rerun with --structural-only.",
            file=sys.stderr,
        )
        return 2
    except (OSError, UnicodeError, RuntimeError, ValueError) as exc:
        print(f"thorn: could not read project: {exc}", file=sys.stderr)
        return 2

    if mode == "ir":
        _print_ir(project, args.format == "json")
        return 0

    report_path = _requested_report_path(mode, args)
    analysis_findings = (
        analyze_project(project)
        if mode in {"analyze", "report"} or report_path is not None
        else []
    )

    if mode == "report":
        assert report_path is not None
        _emit_report(
            project,
            report_path,
            analysis_findings=analysis_findings,
            open_browser=args.open,
        )
        return _exit_code((finding.severity for finding in analysis_findings), args.fail_on)

    if mode == "analyze":
        if args.format == "json":
            _print_analysis_json(analysis_findings)
        else:
            _print_analysis_text(analysis_findings)
        if report_path is not None:
            _emit_report(
                project,
                report_path,
                analysis_findings=analysis_findings,
                open_browser=args.open,
                path_to_stderr=args.format == "json",
            )
        return _exit_code((finding.severity for finding in analysis_findings), args.fail_on)

    units = project.units
    if args.limit is not None:
        units = units[: args.limit]

    if not units:
        print("thorn: no theorem-like environments found", file=sys.stderr)
        return 0

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "thorn review: OPENAI_API_KEY is not set; use `thorn analyze` for deterministic "
            "structural diagnostics, `thorn report` for a keyless local report, or "
            "`thorn ir --format json` to inspect the extracted IR",
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

    if report_path is not None:
        _emit_report(
            project,
            report_path,
            analysis_findings=analysis_findings,
            audits=audits,
            model=args.model,
            review_execution=ReviewExecution.LIVE,
            min_confidence=args.min_confidence,
            open_browser=args.open,
            path_to_stderr=args.format == "json",
        )

    review_findings = _visible_findings(audits, args.min_confidence)
    return _exit_code((finding.severity for finding in review_findings), args.fail_on)
