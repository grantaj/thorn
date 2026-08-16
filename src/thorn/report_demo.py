from __future__ import annotations

from datetime import UTC, datetime

from thorn.models import Severity
from thorn.report import (
    AssuranceRegime,
    FormalizationMetadata,
    FormalStatus,
    Report,
    ReportCounts,
    ReportFinding,
    ReportGeneration,
    ReportObligation,
    ReportResult,
    ReportSource,
    ReviewExecution,
    ReviewMetadata,
    SourceRescueContext,
)


def _source(line: int, text: str, *, addresses: tuple[str, ...] = ()) -> ReportSource:
    return ReportSource(
        file="examples/synthetic-paper.tex",
        start_line=line,
        end_line=line + max(text.count("\n"), 0),
        excerpt=text,
        uri=None,
        source_addresses=addresses,
    )


def representative_report() -> Report:
    proof_review = ReviewMetadata(
        representation="thorn-proof/1",
        protocol="thorn-proof-review/1",
        model="example-model",
        request_fingerprint="8c1d2c4f" * 8,
        execution=ReviewExecution.REPLAY,
    )
    rescued = proof_review.model_copy(
        update={
            "source_rescue": (
                SourceRescueContext(
                    address="S7",
                    text="Because $T$ is compact, the selected subnet converges in $T$.",
                    source=_source(
                        87,
                        "   87  Because $T$ is compact, the selected subnet converges in $T$.",
                        addresses=("S7",),
                    ),
                ),
            )
        }
    )
    structural = ReportFinding(
        identifier="demo-structural",
        assurance=AssuranceRegime.STRUCTURAL,
        category="missing_reference",
        severity=Severity.WARNING,
        status="diagnostic",
        title="Referenced result is unresolved",
        explanation=(
            "The proof cites Lemma~\\ref{lem:compactness}, but no matching internal label was "
            "recovered. This is a structural warning; it does not establish that the theorem "
            "is false."
        ),
        source=_source(42, "   42  By Lemma~\\ref{lem:compactness}, the claim follows."),
        evidence=("target label: lem:compactness",),
    )
    semantic = ReportFinding(
        identifier="demo-semantic",
        assurance=AssuranceRegime.SEMANTIC,
        category="hypothesis_mismatch",
        severity=Severity.ERROR,
        status="model_finding",
        title="The cited transfer lemma needs a stronger premise",
        explanation=(
            "The argument applies the transfer lemma at $x=0$, but the available local premise is "
            "$P(1)$. The supplied context does not justify replacing it by $P(0)$."
        ),
        source=_source(63, "   63  Applying Lemma~\\ref{lem:transfer} at $0$ gives $Q(0)$."),
        evidence=("Expected premise: P(0)", "Available premise: P(1)"),
        review=proof_review,
    )
    rescued_finding = ReportFinding(
        identifier="demo-rescued",
        assurance=AssuranceRegime.SEMANTIC,
        category="unsupported_claim",
        severity=Severity.WARNING,
        status="model_finding",
        title="Compactness step depends on source wording",
        explanation=(
            "The compact Proof IR did not determine whether the convergence claim was in the "
            "ambient space or in $T$. The reviewer requested the advertised source handle and then "
            "flagged the step because the rescued sentence only establishes convergence in $T$."
        ),
        source=_source(88, "   88  Hence the subnet converges to $x$ in $X$."),
        evidence=("Reviewer requested @S7 before reaching this finding.",),
        review=rescued,
    )
    formal_hole = ReportObligation(
        identifier="LH1",
        assurance=AssuranceRegime.FORMAL,
        kind="missing_result_precondition",
        status="open",
        explanation="missing result precondition",
        expected="P 0",
        source=_source(
            121,
            "  121  Applying the transfer lemma yields $Q(0)$.",
            addresses=("S12",),
        ),
        source_addresses=("S12",),
    )
    unresolved = ReportObligation(
        identifier="PO4",
        assurance=AssuranceRegime.STRUCTURAL,
        kind="proof_obligation",
        status="unresolved",
        explanation="Canonical Proof IR retains this proof obligation as unresolved.",
        expected="f(x) \\in K",
        source=_source(146, "  146  Therefore $f(x) \\in K$.", addresses=("S18",)),
        source_addresses=("S18",),
    )
    long_explanation = (
        "This deliberately long synthetic explanation exercises ordinary laptop widths and narrow "
        "screens. The point is not to create more visual decoration, but to verify that a "
        "mathematician can read a substantive paragraph without the finding panel becoming a "
        "horizontal scrolling surface or forcing protocol identifiers into the primary "
        "reading path. "
        "The report should keep the mathematical concern readable, with technical representation "
        "details available only when "
        "the user chooses to inspect them."
    )
    long_finding = ReportFinding(
        identifier="demo-long",
        assurance=AssuranceRegime.SEMANTIC,
        category="quantifier_error",
        severity=Severity.WARNING,
        status="model_finding",
        title="Quantifier order changes the claimed statement",
        explanation=long_explanation,
        source=_source(
            170,
            "  170  For every $\\varepsilon>0$ there exists $N$ such that for every $x\\in X$ ...\n"
            "  171  The proof later chooses one $N$ before fixing $\\varepsilon$, "
            "which is stronger.",
        ),
        review=ReviewMetadata(
            representation="raw",
            protocol="thorn-proof-review/1",
            model="example-model",
            execution=ReviewExecution.LIVE,
            request_fingerprint="5a" * 32,
        ),
    )
    results = (
        ReportResult(
            identifier="thm:clean",
            kind="theorem",
            name="Basic continuity",
            source=_source(12, "   12  If $f$ is continuous, then $f^{-1}(U)$ is open."),
            statement="If $f$ is continuous, then $f^{-1}(U)$ is open.",
        ),
        ReportResult(
            identifier="thm:structural",
            kind="theorem",
            name="Compact image",
            source=_source(38, "   38  The image of $K$ under $f$ is compact."),
            statement="The image of $K$ under $f$ is compact.",
            findings=(structural,),
        ),
        ReportResult(
            identifier="thm:semantic",
            kind="theorem",
            name="Transfer at the origin",
            source=_source(58, "   58  Suppose $P(1)$. Then $Q(0)$."),
            statement="Suppose $P(1)$. Then $Q(0)$.",
            dependencies=("lem:transfer",),
            findings=(semantic,),
            review=proof_review,
            proof_language=(
                "THORN-PROOF 1\n"
                "P1 P(1)\n"
                "P2 Q(0) <- R1[x:=0],?A1:P(0)\n"
                "GOAL G1 P2: Q(0) | ctx P1 | open\n"
            ),
        ),
        ReportResult(
            identifier="thm:rescued",
            kind="proposition",
            name="Subspace convergence",
            source=_source(81, "   81  Every selected subnet converges in the ambient space."),
            statement="Every selected subnet converges in the ambient space.",
            findings=(rescued_finding,),
            review=rescued,
        ),
        ReportResult(
            identifier="thm:lean-complete",
            kind="theorem",
            name="Mechanically replayed transfer",
            source=_source(102, "  102  If $P(0)$ and $\\forall x, P(x)\\to Q(x)$, then $Q(0)$."),
            statement="If $P(0)$ and $\\forall x, P(x)\\to Q(x)$, then $Q(0)$.",
            formalization=FormalizationMetadata(
                status=FormalStatus.COMPLETE,
                mechanically_checkable=True,
            ),
        ),
        ReportResult(
            identifier="thm:lean-partial",
            kind="theorem",
            name="Transfer with missing premise",
            source=_source(116, "  116  Suppose $P(1)$. Then $Q(0)$."),
            statement="Suppose $P(1)$. Then $Q(0)$.",
            formalization=FormalizationMetadata(
                status=FormalStatus.PARTIAL,
                mechanically_checkable=False,
                obligations=(formal_hole,),
            ),
        ),
        ReportResult(
            identifier="thm:unresolved-ir",
            kind="lemma",
            name="Invariant preservation",
            source=_source(141, "  141  The iteration preserves $K$."),
            statement="The iteration preserves $K$.",
            proof_obligations=(unresolved,),
        ),
        ReportResult(
            identifier="thm:long",
            kind="theorem",
            name="Uniform choice",
            source=_source(165, "  165  A uniform choice of $N$ is possible for all tolerances."),
            statement="A uniform choice of $N$ is possible for all tolerances.",
            findings=(long_finding,),
            review=long_finding.review,
        ),
        ReportResult(
            identifier="cor:quiet",
            kind="corollary",
            name="Immediate corollary",
            source=_source(
                190,
                "  190  The stated corollary follows from Theorem~\\ref{thm:clean}.",
            ),
            statement="The stated corollary follows from Theorem~\\ref{thm:clean}.",
            dependencies=("thm:clean",),
        ),
    )
    return Report(
        manuscript="examples/synthetic-paper.tex",
        generation=ReportGeneration(
            generated_at=datetime(2026, 8, 17, 0, 0, tzinfo=UTC),
            thorn_version="0.1.0",
        ),
        counts=ReportCounts(
            results=len(results),
            attention=sum(item.needs_attention for item in results),
            structural_findings=1,
            semantic_findings=3,
            open_obligations=2,
            lean_complete=1,
            lean_partial=1,
            clean_results=3,
        ),
        results=results,
    )
