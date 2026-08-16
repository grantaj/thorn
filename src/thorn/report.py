from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from thorn.analysis import AnalysisFinding
from thorn.dependencies import ExtractedProject
from thorn.formula_ir import render_math_expr
from thorn.lean_export import LeanExport, LeanExportStatus
from thorn.llm_proof_language import LLMProofLanguage
from thorn.models import AuditFinding, CandidateFinding, Severity, SourceRange, UnitAudit
from thorn.proof_language_review import ProofReviewTurnRequest
from thorn.proof_obligations import ObligationStatus
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.semantic_transformations import SemanticTransformationIR

REPORT_SCHEMA_VERSION: Literal["thorn-report/1"] = "thorn-report/1"


class AssuranceRegime(StrEnum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    FORMAL = "formal"


class ReviewExecution(StrEnum):
    LIVE = "live"
    REPLAY = "replay"
    CACHE = "cache"
    UNKNOWN = "unknown"


class FormalStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    NOT_ATTEMPTED = "not_attempted"


class ReportSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    excerpt: str | None = None
    uri: str | None = None
    source_addresses: tuple[str, ...] = ()

    @property
    def reference(self) -> str:
        if self.start_line == self.end_line:
            return f"{self.file}:{self.start_line}"
        return f"{self.file}:{self.start_line}-{self.end_line}"


class SourceRescueContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    text: str
    source: ReportSource | None = None
    referenced_result_identifier: str | None = None


class ReviewMetadata(BaseModel):
    """Provider-neutral provenance for a completed or replayed semantic review."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    representation: str | None = None
    protocol: str | None = None
    model: str | None = None
    request_fingerprint: str | None = None
    execution: ReviewExecution = ReviewExecution.UNKNOWN
    source_rescue: tuple[SourceRescueContext, ...] = ()
    cache_status: str | None = None
    recheck_reason: str | None = None
    avoided_requests: int | None = None


class ReportFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    assurance: AssuranceRegime
    category: str
    severity: Severity
    status: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    title: str
    explanation: str
    source: ReportSource
    evidence: tuple[str, ...] = ()
    related_result_identifiers: tuple[str, ...] = ()
    related_obligation_identifiers: tuple[str, ...] = ()
    review: ReviewMetadata | None = None


class ReportObligation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    assurance: AssuranceRegime
    kind: str
    status: str
    explanation: str
    source: ReportSource | None = None
    expected: str | None = None
    source_addresses: tuple[str, ...] = ()


class FormalizationMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: FormalStatus = FormalStatus.NOT_ATTEMPTED
    mechanically_checkable: bool = False
    obligations: tuple[ReportObligation, ...] = ()


class ReportResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    kind: str
    name: str | None = None
    source: ReportSource
    statement: str
    display_context: str | None = None
    dependencies: tuple[str, ...] = ()
    findings: tuple[ReportFinding, ...] = ()
    proof_obligations: tuple[ReportObligation, ...] = ()
    review: ReviewMetadata | None = None
    formalization: FormalizationMetadata = Field(default_factory=FormalizationMetadata)
    proof_language: str | None = None

    @property
    def needs_attention(self) -> bool:
        if any(item.severity in {Severity.WARNING, Severity.ERROR} for item in self.findings):
            return True
        if any(item.status not in {"discharged", "closed"} for item in self.proof_obligations):
            return True
        return self.formalization.status == FormalStatus.PARTIAL


class ReportCounts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    results: int = 0
    attention: int = 0
    structural_findings: int = 0
    semantic_findings: int = 0
    open_obligations: int = 0
    lean_complete: int = 0
    lean_partial: int = 0
    clean_results: int = 0


class ReportGeneration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    generated_at: datetime
    thorn_version: str | None = None


class Report(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["thorn-report/1"] = REPORT_SCHEMA_VERSION
    manuscript: str
    generation: ReportGeneration
    counts: ReportCounts
    results: tuple[ReportResult, ...] = ()
    manuscript_findings: tuple[ReportFinding, ...] = ()


class ProofReviewReportInput(BaseModel):
    """Adapter input over existing proof-review results; not part of report serialization."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    result_identifier: str
    findings: tuple[CandidateFinding, ...] = ()
    initial_turn: ProofReviewTurnRequest
    model: str
    execution: ReviewExecution = ReviewExecution.UNKNOWN
    rescue_turn: ProofReviewTurnRequest | None = None
    document: LLMProofLanguage | None = None
    source: SourceRange
    request_fingerprint: str | None = None


def stable_anchor(prefix: str, identifier: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in identifier)
    cleaned = "-".join(part for part in cleaned.split("-") if part) or prefix
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{cleaned}-{digest}"


def _path_uri(file: str) -> str | None:
    try:
        return Path(file).expanduser().resolve().as_uri()
    except (OSError, ValueError):
        return None


def bounded_source_excerpt(
    source: SourceRange,
    *,
    context_lines: int = 1,
    max_lines: int = 12,
) -> str | None:
    path = Path(source.file)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    start = max(1, source.start_line - context_lines)
    end = min(len(lines), source.end_line + context_lines)
    if end - start + 1 > max_lines:
        end = start + max_lines - 1
    return "\n".join(f"{index:>5}  {lines[index - 1]}" for index in range(start, end + 1))


def report_source(
    source: SourceRange,
    *,
    excerpt: str | None = None,
    source_addresses: Iterable[str] = (),
) -> ReportSource:
    return ReportSource(
        file=source.file,
        start_line=source.start_line,
        end_line=source.end_line,
        excerpt=excerpt if excerpt is not None else bounded_source_excerpt(source),
        uri=_path_uri(source.file),
        source_addresses=tuple(dict.fromkeys(source_addresses)),
    )


def _analysis_finding(item: AnalysisFinding) -> ReportFinding:
    identifier = f"structural:{item.rule}:{item.unit_id or 'manuscript'}:{item.source.start_line}"
    return ReportFinding(
        identifier=identifier,
        assurance=AssuranceRegime.STRUCTURAL,
        category=item.category.value,
        severity=item.severity,
        status="diagnostic",
        title=item.title,
        explanation=item.explanation,
        source=report_source(item.source),
        evidence=tuple(item.evidence),
    )


def _legacy_review_finding(item: AuditFinding, *, review: ReviewMetadata) -> ReportFinding:
    evidence = list(item.evidence)
    if item.counterexample:
        evidence.append(f"Counterexample: {item.counterexample}")
    evidence.append(
        f"Defender: {item.defender_verdict.value} — {item.defender_explanation}"
    )
    return ReportFinding(
        identifier=f"semantic:{item.unit_id}:{item.rule}:{item.source.start_line}",
        assurance=AssuranceRegime.SEMANTIC,
        category=item.category.value,
        severity=item.severity,
        status=item.defender_verdict.value,
        confidence=item.confidence,
        title=item.title,
        explanation=item.explanation,
        source=report_source(item.source),
        evidence=tuple(evidence),
        review=review,
    )


def _source_rescue(review: ProofReviewReportInput) -> tuple[SourceRescueContext, ...]:
    rescue = review.rescue_turn
    document = review.document
    if rescue is None or document is None:
        return ()
    items: list[SourceRescueContext] = []
    for address in rescue.requested_source_addresses:
        try:
            source = document.source(address)
        except KeyError:
            continue
        source_range = source.source_range
        items.append(
            SourceRescueContext(
                address=address,
                text=source.text,
                source=(
                    report_source(source_range, excerpt=source.text, source_addresses=(address,))
                    if source_range is not None
                    else None
                ),
                referenced_result_identifier=source.referenced_result_identifier,
            )
        )
    return tuple(items)


def proof_review_metadata(review: ProofReviewReportInput) -> ReviewMetadata:
    fingerprint = review.request_fingerprint
    if fingerprint is None:
        fingerprint = proof_review_request_envelope(review.initial_turn, review.model).fingerprint()
    return ReviewMetadata(
        representation=review.initial_turn.representation,
        protocol=review.initial_turn.protocol_version,
        model=review.model,
        request_fingerprint=fingerprint,
        execution=review.execution,
        source_rescue=_source_rescue(review),
    )


def _proof_review_finding(
    item: CandidateFinding,
    *,
    review_input: ProofReviewReportInput,
    metadata: ReviewMetadata,
) -> ReportFinding:
    return ReportFinding(
        identifier=f"semantic:{review_input.result_identifier}:{item.id}",
        assurance=AssuranceRegime.SEMANTIC,
        category=item.category.value,
        severity=item.severity,
        status="model_finding",
        confidence=item.confidence,
        title=item.title,
        explanation=item.explanation,
        source=report_source(review_input.source),
        evidence=tuple(item.evidence)
        + ((f"Counterexample: {item.counterexample}",) if item.counterexample else ()),
        review=metadata,
    )


def proof_state_obligations(
    ir: SemanticTransformationIR,
    *,
    document: LLMProofLanguage | None = None,
) -> tuple[ReportObligation, ...]:
    result: list[ReportObligation] = []
    source_by_address = (
        {item.address: item for item in document.sources} if document is not None else {}
    )

    def source_for(addresses: tuple[str, ...]) -> ReportSource | None:
        for address in addresses:
            handle = source_by_address.get(address)
            if handle is not None and handle.source_range is not None:
                return report_source(
                    handle.source_range,
                    excerpt=handle.text,
                    source_addresses=addresses,
                )
        return None

    for proof_obligation in ir.higher.resolved.proof.obligations:
        if proof_obligation.status != ObligationStatus.UNRESOLVED:
            continue
        proof_addresses = (proof_obligation.source_address,)
        expected = (
            render_math_expr(proof_obligation.expected)
            if proof_obligation.expected is not None
            else None
        )
        result.append(
            ReportObligation(
                identifier=proof_obligation.address,
                assurance=AssuranceRegime.STRUCTURAL,
                kind="proof_obligation",
                status="unresolved",
                explanation="Canonical Proof IR retains this proof obligation as unresolved.",
                source=source_for(proof_addresses),
                expected=expected,
                source_addresses=proof_addresses,
            )
        )
    for application_obligation in ir.obligations:
        if application_obligation.status != ObligationStatus.UNRESOLVED:
            continue
        application_addresses = tuple(application_obligation.source_addresses)
        expected = (
            render_math_expr(application_obligation.expected)
            if application_obligation.expected is not None
            else None
        )
        result.append(
            ReportObligation(
                identifier=application_obligation.address,
                assurance=AssuranceRegime.STRUCTURAL,
                kind="application_precondition",
                status="unresolved",
                explanation="A recovered result application still has an unresolved precondition.",
                source=source_for(application_addresses),
                expected=expected,
                source_addresses=application_addresses,
            )
        )
    return tuple(result)


def formalization_metadata(
    export: LeanExport | None,
    *,
    document: LLMProofLanguage | None = None,
) -> FormalizationMetadata:
    if export is None:
        return FormalizationMetadata()
    mapped_status = {
        LeanExportStatus.COMPLETE: FormalStatus.COMPLETE,
        LeanExportStatus.PARTIAL: FormalStatus.PARTIAL,
        LeanExportStatus.UNSUPPORTED: FormalStatus.UNSUPPORTED,
    }[export.status]
    source_by_address = (
        {item.address: item for item in document.sources} if document is not None else {}
    )
    obligations: list[ReportObligation] = []
    for item in export.obligations:
        source: ReportSource | None = None
        for address in item.source_addresses:
            handle = source_by_address.get(address)
            if handle is not None and handle.source_range is not None:
                source = report_source(
                    handle.source_range,
                    excerpt=handle.text,
                    source_addresses=item.source_addresses,
                )
                break
        expected = render_math_expr(item.expected) if item.expected is not None else item.lean_type
        obligations.append(
            ReportObligation(
                identifier=item.address,
                assurance=AssuranceRegime.FORMAL,
                kind=item.reason,
                status="open",
                explanation=item.reason.replace("_", " "),
                source=source,
                expected=expected,
                source_addresses=tuple(item.source_addresses),
            )
        )
    mechanically_checkable = export.is_mechanically_checkable
    if mapped_status != FormalStatus.COMPLETE:
        mechanically_checkable = False
    return FormalizationMetadata(
        status=mapped_status,
        mechanically_checkable=mechanically_checkable,
        obligations=tuple(obligations),
    )


def build_report(
    project: ExtractedProject,
    *,
    analysis_findings: Iterable[AnalysisFinding] = (),
    audits: Iterable[UnitAudit] = (),
    proof_reviews: Iterable[ProofReviewReportInput] = (),
    proof_states: Mapping[str, SemanticTransformationIR] | None = None,
    proof_documents: Mapping[str, LLMProofLanguage] | None = None,
    lean_exports: Mapping[str, LeanExport] | None = None,
    model: str | None = None,
    review_execution: ReviewExecution = ReviewExecution.UNKNOWN,
    min_confidence: float = 0.65,
    generated_at: datetime | None = None,
    thorn_version: str | None = None,
) -> Report:
    """Project already-computed Thorn outputs into immutable presentation data.

    This function does not run extraction, semantic review, Lean, or any provider. It only
    groups existing results and provenance for presentation.
    """

    proof_states = proof_states or {}
    proof_documents = proof_documents or {}
    lean_exports = lean_exports or {}
    structural_by_result: dict[str, list[ReportFinding]] = {}
    manuscript_findings: list[ReportFinding] = []
    for item in analysis_findings:
        finding = _analysis_finding(item)
        if item.unit_id is None:
            manuscript_findings.append(finding)
        else:
            structural_by_result.setdefault(item.unit_id, []).append(finding)

    audit_findings: dict[str, list[ReportFinding]] = {}
    audit_metadata: dict[str, ReviewMetadata] = {}
    for audit in audits:
        execution = ReviewExecution.CACHE if audit.cached else review_execution
        metadata = ReviewMetadata(
            representation="raw",
            protocol="legacy-theorem-unit-review",
            model=model,
            execution=execution,
            cache_status="hit" if audit.cached else None,
        )
        audit_metadata[audit.unit.identifier] = metadata
        visible = [item for item in audit.findings if item.confidence >= min_confidence]
        audit_findings.setdefault(audit.unit.identifier, []).extend(
            _legacy_review_finding(item, review=metadata) for item in visible
        )

    proof_review_findings: dict[str, list[ReportFinding]] = {}
    proof_review_meta: dict[str, ReviewMetadata] = {}
    for proof_review in proof_reviews:
        metadata = proof_review_metadata(proof_review)
        proof_review_meta[proof_review.result_identifier] = metadata
        proof_review_findings.setdefault(proof_review.result_identifier, []).extend(
            _proof_review_finding(item, review_input=proof_review, metadata=metadata)
            for item in proof_review.findings
        )

    results: list[ReportResult] = []
    for unit in project.units:
        document = proof_documents.get(unit.identifier)
        findings = [
            *structural_by_result.get(unit.identifier, []),
            *audit_findings.get(unit.identifier, []),
            *proof_review_findings.get(unit.identifier, []),
        ]
        findings.sort(
            key=lambda item: (item.assurance.value, item.source.start_line, item.identifier)
        )
        dependencies = tuple(
            node.identifier
            for node in project.dependency_graph.direct_dependencies(unit.identifier)
        )
        state = proof_states.get(unit.identifier)
        obligations = proof_state_obligations(state, document=document) if state is not None else ()
        formalization = formalization_metadata(lean_exports.get(unit.identifier), document=document)
        review_metadata = (
            proof_review_meta.get(unit.identifier) or audit_metadata.get(unit.identifier)
        )
        results.append(
            ReportResult(
                identifier=unit.identifier,
                kind=unit.environment,
                name=unit.title or unit.label,
                source=report_source(unit.statement_range, excerpt=unit.statement),
                statement=unit.statement,
                display_context=unit.local_context.strip() or None,
                dependencies=dependencies,
                findings=tuple(findings),
                proof_obligations=obligations,
                review=review_metadata,
                formalization=formalization,
                proof_language=document.render_initial() if document is not None else None,
            )
        )

    structural_count = sum(
        finding.assurance == AssuranceRegime.STRUCTURAL
        for result in results
        for finding in result.findings
    ) + len(manuscript_findings)
    semantic_count = sum(
        finding.assurance == AssuranceRegime.SEMANTIC
        for result in results
        for finding in result.findings
    )
    open_obligations = sum(len(result.proof_obligations) for result in results) + sum(
        len(result.formalization.obligations) for result in results
    )
    counts = ReportCounts(
        results=len(results),
        attention=sum(result.needs_attention for result in results),
        structural_findings=structural_count,
        semantic_findings=semantic_count,
        open_obligations=open_obligations,
        lean_complete=sum(
            result.formalization.status == FormalStatus.COMPLETE for result in results
        ),
        lean_partial=sum(result.formalization.status == FormalStatus.PARTIAL for result in results),
        clean_results=sum(not result.needs_attention and not result.findings for result in results),
    )
    return Report(
        manuscript=str(project.main_file),
        generation=ReportGeneration(
            generated_at=generated_at or datetime.now(UTC),
            thorn_version=thorn_version,
        ),
        counts=counts,
        results=tuple(results),
        manuscript_findings=tuple(manuscript_findings),
    )
