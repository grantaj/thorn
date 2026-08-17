from __future__ import annotations

import builtins
from datetime import UTC, datetime
from pathlib import Path

from thorn.analysis import AnalysisCategory, AnalysisFinding
from thorn.latex import extract_project
from thorn.lean_export import LeanExport, LeanExportStatus, LeanFormalizationObligation
from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.models import CandidateFinding, FindingCategory, Severity
from thorn.proof_language_review import (
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewTurnRequest,
)
from thorn.report import (
    AssuranceRegime,
    FormalStatus,
    ProofReviewReportInput,
    Report,
    ReportCounts,
    ReportFinding,
    ReportGeneration,
    ReportResult,
    ReportSource,
    ReviewExecution,
    ReviewMetadata,
    build_report,
    formalization_metadata,
    stable_anchor,
)
from thorn.report_demo import representative_report
from thorn.report_html import render_report_html, write_report_html


def _write_project(path: Path) -> None:
    path.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:one}
If $P$, then $Q$.
\end{theorem}
\begin{proof}
By Theorem~\ref{thm:missing}.
\end{proof}
""",
        encoding="utf-8",
    )


def test_report_model_construction_and_serialization_are_deterministic(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_project(tex)
    project = extract_project(tex)
    source = project.unit("thm:one").statement_range
    finding = AnalysisFinding(
        rule="TH103",
        category=AnalysisCategory.MISSING_REFERENCE,
        severity=Severity.ERROR,
        title="Missing internal reference",
        explanation="The proof cites an unresolved internal label.",
        source=source,
        unit_id="thm:one",
        evidence=["target label: thm:missing"],
    )
    generated_at = datetime(2026, 8, 17, tzinfo=UTC)

    first = build_report(project, analysis_findings=[finding], generated_at=generated_at)
    second = build_report(project, analysis_findings=[finding], generated_at=generated_at)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert first.schema_version == "thorn-report/1"
    assert first.counts.results == 1
    assert first.counts.structural_findings == 1
    assert first.results[0].findings[0].assurance == AssuranceRegime.STRUCTURAL
    assert first.results[0].source.file == str(tex)
    assert first.results[0].source.start_line >= 1


def test_representative_report_has_mixed_assurance_states_and_navigation() -> None:
    report = representative_report()
    html = render_report_html(report)

    assert report.counts.results == 9
    assert "Structural" in html
    assert "Semantic review" in html
    assert "Formal / Lean" in html
    assert "Mechanically checked Lean subset" in html
    assert "Partial formalisation — open obligations remain" in html
    assert "Canonical Proof IR retains this proof obligation as unresolved." in html
    assert f'id="{stable_anchor("result", "thm:semantic")}"' in html
    assert f'href="#{stable_anchor("result", "thm:semantic")}"' in html
    assert f'id="{stable_anchor("finding", "demo-semantic")}"' in html
    assert "Needs attention" in html
    assert "No current findings" in html


def test_html_escapes_all_manuscript_and_model_controlled_text() -> None:
    malicious = '<script>alert("owned")</script><img src=x onerror=alert(1)>'
    source = ReportSource(file=malicious, start_line=1, end_line=1, excerpt=malicious)
    finding = ReportFinding(
        identifier=malicious,
        assurance=AssuranceRegime.SEMANTIC,
        category=malicious,
        severity=Severity.ERROR,
        status=malicious,
        title=malicious,
        explanation=malicious,
        source=source,
        evidence=(malicious,),
        review=ReviewMetadata(model=malicious, request_fingerprint=malicious),
    )
    result = ReportResult(
        identifier=malicious,
        kind=malicious,
        name=malicious,
        source=source,
        statement=malicious,
        findings=(finding,),
    )
    report = Report(
        manuscript=malicious,
        generation=ReportGeneration(generated_at=datetime(2026, 8, 17, tzinfo=UTC)),
        counts=ReportCounts(results=1, attention=1, semantic_findings=1),
        results=(result,),
    )

    html = render_report_html(report)

    assert malicious not in html
    assert "&lt;script&gt;alert(&quot;owned&quot;)&lt;/script&gt;" in html
    assert "onerror=alert(1)&gt;" in html


def test_renderer_never_emits_non_file_source_uri() -> None:
    report = representative_report()
    unsafe_source = report.results[0].source.model_copy(
        update={"uri": "javascript:alert(1)"}
    )
    unsafe_result = report.results[0].model_copy(update={"source": unsafe_source})
    updated = report.model_copy(update={"results": (unsafe_result, *report.results[1:])})

    html = render_report_html(updated)

    assert "javascript:alert(1)" not in html


def test_report_is_self_contained_and_has_no_network_assets(tmp_path: Path) -> None:
    destination = tmp_path / "report.html"
    write_report_html(representative_report(), destination)
    html = destination.read_text(encoding="utf-8")

    assert "<style>" in html
    assert "<script>" in html
    assert "http://" not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()


def test_source_provenance_and_rescue_are_visible_without_claiming_verification() -> None:
    html = render_report_html(representative_report())

    assert "examples/synthetic-paper.tex:63" in html
    assert "Copy location" in html
    assert "Source rescue (NEED_SOURCE)" in html
    assert "@S7" in html
    assert "Additional source supplied to the model for review" in html
    assert "not mechanically verified evidence" in html
    assert "Because $T$ is compact" in html


def test_review_provenance_supports_live_replay_and_future_cache_fields() -> None:
    report = representative_report()
    cache_review = ReviewMetadata(
        representation="thorn-proof/1",
        protocol="thorn-proof-review/1",
        model="example-model",
        execution=ReviewExecution.CACHE,
        cache_status="hit_unaffected_dependency_slice",
        recheck_reason="unchanged reachable context",
        avoided_requests=1,
    )
    cached = report.results[0].model_copy(update={"review": cache_review})
    updated = report.model_copy(update={"results": (cached, *report.results[1:])})
    html = render_report_html(updated)

    assert "replay" in html
    assert "live" in html
    assert "cache" in html
    assert "hit_unaffected_dependency_slice" in html
    assert "unchanged reachable context" in html
    assert "Avoided requests" in html


def test_partial_lean_is_never_described_as_mechanically_checked() -> None:
    report = representative_report()
    html = render_report_html(report)
    start = html.index(f'id="{stable_anchor("result", "thm:lean-partial")}"')
    end = html.index(f'id="{stable_anchor("result", "thm:unresolved-ir")}"')
    partial_section = html[start:end]

    assert "Partial formalisation" in partial_section
    assert "Mechanically checked Lean subset" not in partial_section
    assert "THORN_FORMALIZATION_OBLIGATION" not in partial_section
    assert "LH1" in partial_section


def test_formalization_adapter_requires_complete_obligation_free_export() -> None:
    complete = LeanExport(
        result_identifier="thm:one",
        status=LeanExportStatus.COMPLETE,
        source="theorem thorn_thm_one : True := by trivial\n",
    )
    partial = LeanExport(
        result_identifier="thm:one",
        status=LeanExportStatus.PARTIAL,
        source="theorem thorn_thm_one : True := by\n  sorry\n",
        obligations=(
            LeanFormalizationObligation(
                address="LH1",
                reason="missing_result_precondition",
                source_addresses=("S1",),
            ),
        ),
    )

    complete_meta = formalization_metadata(complete)
    partial_meta = formalization_metadata(partial)

    assert complete_meta.status == FormalStatus.COMPLETE
    assert complete_meta.mechanically_checkable
    assert partial_meta.status == FormalStatus.PARTIAL
    assert not partial_meta.mechanically_checkable
    assert partial_meta.obligations[0].identifier == "LH1"


def test_proof_review_adapter_preserves_need_source_and_replay_metadata(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_project(tex)
    project = extract_project(tex)
    unit = project.unit("thm:one")
    handle = ProofLanguageSourceHandle(
        address="S1",
        ir_identifier="source:S1",
        text="By the missing lemma, the claim follows.",
        source_range=unit.proof_range,
    )
    document = LLMProofLanguage(
        result_identifier=unit.identifier,
        lines=("THORN-PROOF 1", "P1 Q <- ? @S1"),
        sources=(handle,),
    )
    initial = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint=document.fingerprint(),
        user_content="initial",
        source_rescue_allowed=True,
    )
    prior = ProofReviewModelResponse(
        action="need_source",
        source_addresses=("S1",),
        review_items=(
            ProofReviewItem(
                id="RV1",
                kind="question",
                summary="Does the missing lemma establish the cited premise?",
            ),
        ),
        source_review_item_ids=("RV1",),
    )
    rescue = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="rescue",
        initial_packet_fingerprint=document.fingerprint(),
        user_content="rescued",
        source_rescue_allowed=False,
        requested_source_addresses=("S1",),
        initial_user_content="initial",
        prior_response=prior,
    )
    candidate = CandidateFinding(
        id="F1",
        category=FindingCategory.UNPROVED_DEPENDENCY,
        severity=Severity.WARNING,
        title="Dependency is not established",
        explanation="The requested source does not establish the cited premise.",
        evidence=["The rescued sentence names no proved result."],
        confidence=0.9,
    )
    review = ProofReviewReportInput(
        result_identifier=unit.identifier,
        findings=(candidate,),
        initial_turn=initial,
        model="example-model",
        execution=ReviewExecution.REPLAY,
        rescue_turn=rescue,
        document=document,
        source=unit.statement_range,
        request_fingerprint="fixed-fingerprint",
    )

    report = build_report(
        project,
        proof_reviews=(review,),
        proof_documents={unit.identifier: document},
        generated_at=datetime(2026, 8, 17, tzinfo=UTC),
    )
    html = render_report_html(report)

    assert report.results[0].review is not None
    assert report.results[0].review.representation == "thorn-proof/1"
    assert report.results[0].review.execution == ReviewExecution.REPLAY
    assert report.results[0].review.request_fingerprint == "fixed-fingerprint"
    assert report.results[0].review.source_rescue[0].address == "S1"
    assert "fixed-fingerprint" in html
    assert "By the missing lemma" in html
    assert "confidence 0.90" in html


def test_report_generation_does_not_import_or_construct_model_provider(monkeypatch) -> None:
    report = representative_report()
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"thorn.audit", "thorn.providers.openai", "openai"}:
            raise AssertionError(f"report rendering attempted model-backed import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    html = render_report_html(report)
    assert "Thorn review" in html


def test_clean_report_is_quiet_not_a_pass_fail_claim() -> None:
    report = representative_report()
    clean = report.model_copy(
        update={
            "counts": ReportCounts(results=1, clean_results=1),
            "results": (report.results[0],),
        }
    )
    html = render_report_html(clean)

    assert "No current result is marked for attention" in html
    assert "This is not a proof of correctness" in html
    assert "PASS" not in html


def test_html_rendering_is_deterministic_for_fixed_report() -> None:
    report = representative_report()
    assert render_report_html(report) == render_report_html(report)