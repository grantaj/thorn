from __future__ import annotations

import json
from pathlib import Path

import pytest

from thorn.latex import extract_project
from thorn.models import CandidateFinding, FindingCategory, Severity
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewDisposition,
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    build_proof_review_turn,
    build_rescue_turn,
    review_proof_language,
    validate_proof_review_response,
)
from thorn.review_workflow import prepare_proof_review

FIXTURE = Path("tests/fixtures/issue_132_b0_rescue_response.json")


def _finding(
    finding_id: str,
    *,
    title: str = "Uniform conclusion is false",
    explanation: str = "The claimed uniform conclusion fails.",
    category: FindingCategory = FindingCategory.COUNTEREXAMPLE,
    severity: Severity = Severity.ERROR,
) -> CandidateFinding:
    return CandidateFinding(
        id=finding_id,
        category=category,
        severity=severity,
        title=title,
        explanation=explanation,
        confidence=0.99,
    )


def _synthetic_rescue(item_count: int = 1):
    from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle

    document = LLMProofLanguage(
        result_identifier="thm:test",
        lines=(
            "THORN-PROOF 1",
            "T0 Q <- ? @T0",
            "GOAL G0 T0: Q | ctx - | open @T0",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="T0",
                ir_identifier="result:T0",
                text="Claim Q.",
            ),
        ),
    )
    request = ProofLanguageReviewRequest(document=document)
    initial = build_proof_review_turn(request)
    items = tuple(
        ProofReviewItem(
            id=f"RV{index}",
            kind="concern",
            summary=f"Concern {index}.",
        )
        for index in range(1, item_count + 1)
    )
    need = ProofReviewModelResponse(
        action="need_source",
        source_addresses=("T0",),
        review_items=items,
        source_review_item_ids=tuple(item.id for item in items),
    )
    return request, build_rescue_turn(request, initial, need)


def test_richer_top_level_finding_is_canonical_for_same_identity() -> None:
    _, rescue = _synthetic_rescue()
    local = _finding(
        "F1",
        title="Short local summary",
        explanation="Short disposition-local explanation.",
    )
    canonical = _finding(
        "F1",
        title="Richer final statement of the same defect",
        explanation="A fuller final explanation with the mathematical witness.",
    )
    response = ProofReviewModelResponse(
        action="review",
        findings=(canonical,),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="Confirmed by the rescued source.",
                finding=local,
            ),
        ),
    )

    normalized = validate_proof_review_response(rescue, response)

    assert normalized.findings == ()
    assert normalized.dispositions[0].finding == canonical


def test_multiple_carried_items_can_converge_on_one_canonical_finding() -> None:
    _, rescue = _synthetic_rescue(2)
    canonical = _finding("F1", title="Canonical final defect")
    response = ProofReviewModelResponse(
        action="review",
        findings=(canonical,),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="First facet confirmed.",
                finding=_finding("F1", title="First facet"),
            ),
            ProofReviewDisposition(
                item_id="RV2",
                status="revised",
                explanation="Second facet resolves to the same defect.",
                finding=_finding("F1", title="Second facet"),
            ),
        ),
    )

    normalized = validate_proof_review_response(rescue, response)

    assert normalized.findings == ()
    assert [item.finding for item in normalized.dispositions] == [canonical, canonical]


def test_same_identity_with_incompatible_category_is_rejected() -> None:
    _, rescue = _synthetic_rescue()
    response = ProofReviewModelResponse(
        action="review",
        findings=(_finding("F1"),),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="Confirmed.",
                finding=_finding(
                    "F1",
                    category=FindingCategory.INVALID_IMPLICATION,
                ),
            ),
        ),
    )

    with pytest.raises(
        ProofReviewProtocolError,
        match="incompatible finding identity across rescue accounting: F1",
    ):
        validate_proof_review_response(rescue, response)


def test_nonidentical_repeated_disposition_identity_without_canonical_final_is_rejected() -> None:
    _, rescue = _synthetic_rescue(2)
    response = ProofReviewModelResponse(
        action="review",
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="First facet confirmed.",
                finding=_finding("F1", title="First payload"),
            ),
            ProofReviewDisposition(
                item_id="RV2",
                status="confirmed",
                explanation="Second facet confirmed.",
                finding=_finding("F1", title="Different payload"),
            ),
        ),
    )

    with pytest.raises(
        ProofReviewProtocolError,
        match="ambiguous disposition-only finding identity: F1",
    ):
        validate_proof_review_response(rescue, response)


class _B0Transport:
    model = "gpt-5.6"

    def __init__(self, final: ProofReviewModelResponse) -> None:
        self.responses = [
            ProofReviewModelResponse(
                action="need_source",
                source_addresses=("T0", "P2", "P3"),
                review_items=(
                    ProofReviewItem(
                        id="RV1",
                        kind="question",
                        summary=(
                            "Does ‘uniformly attenuating’ in T0 mean uniform decay of the "
                            "functions a_n(x)=x^n on I=[0,1)? If so, the claim is false "
                            "because values approach 1 as x approaches 1 for every fixed n."
                        ),
                    ),
                    ProofReviewItem(
                        id="RV2",
                        kind="concern",
                        summary=(
                            "The passage to a finite cover in U5 appears to require compactness "
                            "of I=[0,1), but this half-open interval is not compact. The exact "
                            "justification in P2 must be checked."
                        ),
                    ),
                    ProofReviewItem(
                        id="RV3",
                        kind="concern",
                        summary=(
                            "P3 may conclude the uniform theorem from C1, but C1 depends on the "
                            "unsupported finite-subcover step; inspect the exact conclusion and "
                            "dependency wording."
                        ),
                    ),
                ),
                source_review_item_ids=("RV1", "RV2", "RV3"),
            ),
            final,
        ]
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def review_proof_turn(self, request):
        self.requests += 1
        self.live_requests += 1
        return self.responses.pop(0)


def test_exact_issue_101_b0_live_response_normalizes_to_two_findings() -> None:
    project = extract_project(Path("eval/robustness/issue_101/baseline.tex"))
    unit = project.unit("thm:uniform-decay")
    prepared = prepare_proof_review(project, unit)
    request = ProofLanguageReviewRequest(document=prepared.document)
    final = ProofReviewModelResponse.model_validate(
        json.loads(FIXTURE.read_text(encoding="utf-8"))
    )

    report = review_proof_language(request, _B0Transport(final))

    assert [finding.id for finding in report.findings] == ["F1", "F2"]
    assert report.findings[0] == final.findings[0]
    assert report.findings[1] == final.findings[1]
