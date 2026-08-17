from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from collections.abc import Iterable, Mapping
from pathlib import Path

from thorn import __version__
from thorn.analysis import AnalysisFinding, analyze_project
from thorn.dependencies import ExtractedProject
from thorn.frontends import get_frontend
from thorn.latex import extract_project
from thorn.lean_export import LeanExport, project_lean
from thorn.llm_proof_language import LLMProofLanguage
from thorn.local_nlp import select_linguistic_frontend
from thorn.models import CandidateFinding, Severity, TheoremUnit
from thorn.proof_visualizer import write_proof_visualizer_html
from thorn.report import ProofReviewReportInput, ReviewExecution, build_report
from thorn.report_html import write_report_html
from thorn.review_workflow import PreparedProofReview, prepare_proof_review, run_proof_review
from thorn.semantic_transformations import SemanticTransformationIR
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend

_MODES = {"analyze", "ir", "review", "report", "graph", "lean"}
_DEFAULT_REPORT_SENTINEL = "__thorn_default_report__"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thorn",
        usage="thorn [analyze|ir|review|report|graph|lean] FILE [options]",
        description="Source-linked structural analysis and mathematical review for LaTeX manuscripts.",
        epilog=(
            "Modes: 'analyze' runs deterministic structural analysis; 'report' writes a "
            "self-contained local review report; 'graph' visualises the recovered proof argument; "
            "'review' runs model-backed review over thorn-proof/1; 'lean' exports the currently "
            "supported canonical Proof-IR subset to Lean; 'ir' inspects the frontend Math IR. "
            "Omitting the mode means 'review'."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("file", type=Path, help="main LaTeX file")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--model", default=os.getenv("THORN_MODEL", "gpt-5.6"))
    parser.add_argument("--limit", type=int, default=None, help="review only the first N results")
    parser.add_argument(
        "--no-defender",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".thorn/cache"),
        help=argparse.SUPPRESS,
    )
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
        help="output path for `thorn report`, `thorn graph`, or `thorn lean`",
    )
    parser.add_argument(
        "--result",
        default=None,
        metavar="ID",
        help="result identifier to export with `thorn lean`",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the generated report/graph with the operating system's default browser",
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


def _visible_proof_findings(
    reviews: Iterable[ProofReviewReportInput],
    threshold: float,
) -> list[tuple[ProofReviewReportInput, CandidateFinding]]:
    return [
        (review, finding)
        for review in reviews
        for finding in review.findings
        if finding.confidence >= threshold
    ]


def _print_review_text(reviews: list[ProofReviewReportInput], threshold: float) -> None:
    findings = _visible_proof_findings(reviews, threshold)
    if not findings:
        print(f"thorn review: no mathematical findings above confidence {threshold:.2f}")
        return
    for review, finding in findings:
        source = review.source
        print(
            f"{source.file}:{source.start_line}-{source.end_line}: "
            f"{finding.severity.value} {finding.rule} {finding.title}"
        )
        print(f"  {finding.explanation}")
        for evidence in finding.evidence:
            print(f"  evidence: {evidence}")
        if finding.counterexample:
            print(f"  counterexample: {finding.counterexample}")
        print(f"  confidence: {finding.confidence:.2f}")
        print()


def _print_review_json(reviews: list[ProofReviewReportInput], threshold: float) -> None:
    visible = _visible_proof_findings(reviews, threshold)
    payload = {
        "mode": "review",
        "representation": "thorn-proof/1",
        "protocol": "thorn-proof-review/2",
        "reviewed_results": len(reviews),
        "findings": [
            finding.model_dump(mode="json")
            | {
                "rule": finding.rule,
                "result_identifier": review.result_identifier,
                "source": review.source.model_dump(mode="json"),
            }
            for review, finding in visible
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


def _default_graph_path(main_file: Path) -> Path:
    return main_file.with_name(f"{main_file.stem}.thorn-proof-graph.html")


def _default_lean_path(main_file: Path) -> Path:
    return main_file.with_name(f"{main_file.stem}.thorn.lean")


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


def _open_local_html(written: Path, *, kind: str) -> None:
    try:
        webbrowser.open(written.resolve().as_uri())
    except (OSError, ValueError, webbrowser.Error) as exc:
        print(f"thorn: could not open {kind} browser: {exc}", file=sys.stderr)


def _emit_report(
    project: ExtractedProject,
    destination: Path,
    *,
    analysis_findings: list[AnalysisFinding],
    proof_reviews: list[ProofReviewReportInput] | None = None,
    proof_states: Mapping[str, SemanticTransformationIR] | None = None,
    proof_documents: Mapping[str, LLMProofLanguage] | None = None,
    lean_exports: Mapping[str, LeanExport] | None = None,
    min_confidence: float = 0.65,
    open_browser: bool = False,
    path_to_stderr: bool = False,
) -> Path:
    report = build_report(
        project,
        analysis_findings=analysis_findings,
        proof_reviews=proof_reviews or (),
        proof_states=proof_states,
        proof_documents=proof_documents,
        lean_exports=lean_exports,
        min_confidence=min_confidence,
        thorn_version=__version__,
    )
    written = write_report_html(report, destination)
    stream = sys.stderr if path_to_stderr else sys.stdout
    print(f"Report: {written}", file=stream)
    if open_browser:
        _open_local_html(written, kind="report")
    return written


def _emit_graph(
    project: ExtractedProject,
    destination: Path,
    *,
    open_browser: bool = False,
) -> Path:
    written = write_proof_visualizer_html(project, destination)
    print(f"Graph: {written}")
    if open_browser:
        _open_local_html(written, kind="proof graph")
    return written


def _prepare_units(
    project: ExtractedProject,
    units: Iterable[TheoremUnit],
) -> dict[str, PreparedProofReview]:
    return {unit.identifier: prepare_proof_review(project, unit) for unit in units}


def _select_lean_unit(project: ExtractedProject, result_identifier: str | None) -> TheoremUnit:
    if result_identifier is not None:
        try:
            return project.unit(result_identifier)
        except KeyError as exc:
            available = ", ".join(unit.identifier for unit in project.units) or "(none)"
            raise ValueError(
                f"unknown result identifier {result_identifier!r}; available: {available}"
            ) from exc
    if len(project.units) == 1:
        return project.units[0]
    available = ", ".join(unit.identifier for unit in project.units) or "(none)"
    raise ValueError(
        "`thorn lean` needs --result when the manuscript has more than one theorem-like result; "
        f"available: {available}"
    )


def _emit_lean(
    project: ExtractedProject,
    *,
    result_identifier: str | None,
    destination: Path,
    as_json: bool,
) -> int:
    try:
        unit = _select_lean_unit(project, result_identifier)
        prepared = prepare_proof_review(project, unit)
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"thorn lean: {exc}", file=sys.stderr)
        return 2

    export = project_lean(prepared.state)
    written = destination.expanduser().resolve()
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_text(export.source, encoding="utf-8")
    if as_json:
        print(
            json.dumps(
                {
                    "mode": "lean",
                    "result_identifier": unit.identifier,
                    "status": export.status.value,
                    "mechanically_checkable": export.is_mechanically_checkable,
                    "output": str(written),
                    "obligations": [
                        obligation.model_dump(mode="json") for obligation in export.obligations
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Lean: {written}")
        print(f"Result: {unit.identifier}")
        print(f"Status: {export.status.value}")
        if export.is_mechanically_checkable:
            print("The exported subset is complete and contains no Thorn formalisation holes.")
        elif export.obligations:
            print(f"Open formalisation obligations: {len(export.obligations)}")
            for obligation in export.obligations:
                sources = ", ".join(obligation.source_addresses) or "no source handle"
                print(f"  {obligation.address}: {obligation.reason} ({sources})")
    return 0


def main(argv: list[str] | None = None) -> int:
    mode, args = _parse_mode(argv)
    if not 0.0 <= args.min_confidence <= 1.0:
        print("thorn: --min-confidence must be between 0 and 1", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 1:
        print("thorn: --limit must be positive", file=sys.stderr)
        return 2
    if mode not in {"report", "graph", "lean"} and args.output is not None:
        print(
            "thorn: --output is only valid with `thorn report`, `thorn graph`, or `thorn lean`",
            file=sys.stderr,
        )
        return 2
    if mode in {"report", "graph", "lean"} and args.report is not None:
        if mode == "lean":
            print("thorn: --report is not supported with `thorn lean`", file=sys.stderr)
        else:
            print("thorn: use --output to choose the generated HTML destination", file=sys.stderr)
        return 2
    if mode == "ir" and args.report is not None:
        print("thorn: --report is not supported with `thorn ir`", file=sys.stderr)
        return 2
    if mode != "lean" and args.result is not None:
        print("thorn: --result is only valid with `thorn lean`", file=sys.stderr)
        return 2
    if args.open and mode not in {"report", "graph"} and args.report is None:
        print("thorn: --open requires `thorn report`, `thorn graph`, or --report", file=sys.stderr)
        return 2
    if mode == "review" and args.no_defender:
        print(
            "thorn review: --no-defender belonged to the retired legacy raw-review CLI; "
            "the normal review path now uses thorn-proof/1 and thorn-proof-review/2",
            file=sys.stderr,
        )
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

    if mode == "graph":
        _emit_graph(
            project,
            args.output or _default_graph_path(args.file),
            open_browser=args.open,
        )
        return 0

    if mode == "lean":
        return _emit_lean(
            project,
            result_identifier=args.result,
            destination=args.output or _default_lean_path(args.file),
            as_json=args.format == "json",
        )

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
            "structural diagnostics, `thorn report` for a keyless local report, `thorn graph` "
            "for the recovered proof argument, or `thorn ir --format json` to inspect the "
            "extracted IR",
            file=sys.stderr,
        )
        return 2

    # Model transport is imported only after the explicit paid-review boundary.
    from thorn.providers.openai import OpenAIProvider

    try:
        prepared_by_result = _prepare_units(project, units)
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"thorn: could not prepare canonical proof review: {exc}", file=sys.stderr)
        return 2

    provider = OpenAIProvider(model=args.model)
    proof_reviews: list[ProofReviewReportInput] = []
    for index, unit in enumerate(units, start=1):
        if args.format == "text":
            print(
                f"thorn: reviewing {index}/{len(units)} {unit.identifier} "
                "with thorn-proof/1 ...",
                file=sys.stderr,
            )
        prepared = prepared_by_result[unit.identifier]
        try:
            completed = run_proof_review(prepared, provider)
        except Exception as exc:  # provider/network/protocol failures become CLI diagnostics
            print(f"thorn: review failed for {unit.identifier}: {exc}", file=sys.stderr)
            return 2

        source = unit.proof_range or unit.statement_range
        proof_reviews.append(
            ProofReviewReportInput(
                result_identifier=unit.identifier,
                findings=tuple(completed.report.findings),
                initial_turn=completed.initial_turn,
                rescue_turn=completed.rescue_turn,
                document=prepared.document,
                model=args.model,
                execution=ReviewExecution.LIVE,
                source=source,
            )
        )

    if args.format == "json":
        _print_review_json(proof_reviews, args.min_confidence)
    else:
        _print_review_text(proof_reviews, args.min_confidence)

    if report_path is not None:
        _emit_report(
            project,
            report_path,
            analysis_findings=analysis_findings,
            proof_reviews=proof_reviews,
            proof_states={
                identifier: prepared.state for identifier, prepared in prepared_by_result.items()
            },
            proof_documents={
                identifier: prepared.document
                for identifier, prepared in prepared_by_result.items()
            },
            min_confidence=args.min_confidence,
            open_browser=args.open,
            path_to_stderr=args.format == "json",
        )

    review_findings = _visible_proof_findings(proof_reviews, args.min_confidence)
    return _exit_code((finding.severity for _, finding in review_findings), args.fail_on)
