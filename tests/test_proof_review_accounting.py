from __future__ import annotations

import json
from pathlib import Path

import pytest

from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
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
from thorn.providers.replay import RecordingProvider, ReplayProvider


def _document() -> LLMProofLanguage:
    return LLMProofLanguage(
        result_identifier="thm:test",
        lines=(
            "THORN-PROOF 1",
            "T0 Q(a)",
            "C1 Q(a) <- ? @E1",
            "GOAL G0 T0: Q(a) | open @C1",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="E1",
                ir_identifier="edge:E1",
                text="By Lemma 4, Q(a).",
            ),
            ProofLanguageSourceHandle(
                address="C1",
                ir_identifier="claim:C1",
                text="Therefore Q(a).",
            ),
        ),
    )


def _finding(finding_id: str) -> CandidateFinding:
    return CandidateFinding(
        id=finding_id,
        category=FindingCategory.UNSUPPORTED_CLAIM,
        severity=Severity.ERROR,
        title=f"Finding {finding_id}",
        explanation=f"Explanation for {finding_id}.",
        confidence=0.9,
    )


def _need(item_count: int = 1) -> ProofReviewModelResponse:
    items = tuple(
        ProofReviewItem(
            id=f"RV{index}",
            kind="concern",
            summary=f"Carried concern {index}.",
        )
        for index in range(1, item_count + 1)
    )
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=("E1",),
        review_items=items,
        source_review_item_ids=tuple(item.id for item in items),
    )


def _rescue_turn(item_count: int = 1):
    request = ProofLanguageReviewRequest(document=_document())
    initial = build_proof_review_turn(request)
    return request, build_rescue_turn(request, initial, _need(item_count))


class _Transport:
    def __init__(self, responses: list[ProofReviewModelResponse]) -> None:
        self.model = "test-model"
        self.responses = list(responses)
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


@pytest.mark.parametrize("status", ["confirmed", "revised"])
def test_rescue_normalizes_exact_finding_repeated_across_accounting(
    status: str,
) -> None:
    _, rescue = _rescue_turn()
    duplicated = _finding("F1")
    response = ProofReviewModelResponse(
        action="review",
        findings=(duplicated,),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status=status,
                explanation="The carried concern is settled.",
                finding=duplicated,
            ),
        ),
    )

    normalized = validate_proof_review_response(rescue, response)

    assert normalized.findings == ()
    assert normalized.dispositions[0].finding == duplicated


def test_rescue_rejects_incompatible_payload_for_carried_finding_identity() -> None:
    _, rescue = _rescue_turn()
    carried = _finding("F1")
    incompatible = carried.model_copy(
        update={"category": FindingCategory.INVALID_IMPLICATION}
    )
    response = ProofReviewModelResponse(
        action="review",
        findings=(incompatible,),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="The carried concern is confirmed.",
                finding=carried,
            ),
        ),
    )

    with pytest.raises(
        ProofReviewProtocolError,
        match="incompatible finding identity across rescue accounting: F1",
    ):
        validate_proof_review_response(rescue, response)


def test_rescue_normalization_preserves_new_finding_order() -> None:
    _, rescue = _rescue_turn()
    duplicated = _finding("F1")
    response = ProofReviewModelResponse(
        action="review",
        findings=(_finding("F2"), duplicated, _finding("F3")),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="The carried concern is confirmed.",
                finding=duplicated,
            ),
        ),
    )

    first = validate_proof_review_response(rescue, response)
    second = validate_proof_review_response(rescue, response)

    assert [finding.id for finding in first.findings] == ["F2", "F3"]
    assert first == second


def test_rescue_rejects_duplicate_top_level_finding_identity() -> None:
    _, rescue = _rescue_turn()
    duplicated = _finding("F2")
    response = ProofReviewModelResponse(
        action="review",
        findings=(duplicated, duplicated),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="discharged",
                explanation="The carried concern is discharged.",
            ),
        ),
    )

    with pytest.raises(
        ProofReviewProtocolError,
        match="reuses finding identity across rescue accounting: F2",
    ):
        validate_proof_review_response(rescue, response)


def test_rescue_preserves_carried_and_genuinely_new_findings_once() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    transport = _Transport(
        [
            _need(),
            ProofReviewModelResponse(
                action="review",
                findings=(_finding("F2"),),
                dispositions=(
                    ProofReviewDisposition(
                        item_id="RV1",
                        status="confirmed",
                        explanation="The carried concern is confirmed.",
                        finding=_finding("F1"),
                    ),
                ),
            ),
        ]
    )

    report = review_proof_language(request, transport)
    assert [finding.id for finding in report.findings] == ["F1", "F2"]


def test_multiple_carried_items_keep_distinct_finding_identities() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    transport = _Transport(
        [
            _need(2),
            ProofReviewModelResponse(
                action="review",
                dispositions=(
                    ProofReviewDisposition(
                        item_id="RV1",
                        status="confirmed",
                        explanation="First concern confirmed.",
                        finding=_finding("F1"),
                    ),
                    ProofReviewDisposition(
                        item_id="RV2",
                        status="revised",
                        explanation="Second concern revised.",
                        finding=_finding("F2"),
                    ),
                ),
            ),
        ]
    )

    report = review_proof_language(request, transport)
    assert [finding.id for finding in report.findings] == ["F1", "F2"]


def test_rescue_allows_exact_same_finding_identity_for_two_carried_items() -> None:
    _, rescue = _rescue_turn(2)
    shared = _finding("F1")
    response = ProofReviewModelResponse(
        action="review",
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="First concern confirmed.",
                finding=shared,
            ),
            ProofReviewDisposition(
                item_id="RV2",
                status="revised",
                explanation="Second concern converges on the same finding.",
                finding=shared,
            ),
        ),
    )

    normalized = validate_proof_review_response(rescue, response)

    assert [item.finding for item in normalized.dispositions] == [shared, shared]


def test_duplicate_rescue_finding_is_normalized_before_recording_and_replays_exactly(
    tmp_path: Path,
) -> None:
    request = ProofLanguageReviewRequest(document=_document())
    duplicated = _finding("F1")
    final = ProofReviewModelResponse(
        action="review",
        findings=(duplicated,),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="Concern confirmed.",
                finding=duplicated,
            ),
        ),
    )
    recorder = RecordingProvider(_Transport([_need(), final]), tmp_path)

    live_report = review_proof_language(request, recorder)
    assert [finding.id for finding in live_report.findings] == ["F1"]

    recordings = [
        json.loads(path.read_text(encoding="utf-8")) for path in tmp_path.glob("*.json")
    ]
    assert len(recordings) == 2
    final_recording = next(
        recording for recording in recordings if recording["response"]["dispositions"]
    )
    assert final_recording["response"]["findings"] == []
    assert final_recording["response"]["dispositions"][0]["finding"]["id"] == "F1"

    replay = ReplayProvider("test-model", tmp_path)
    replay_report = review_proof_language(request, replay)
    assert replay_report == live_report
    assert replay.requests == 2
    assert replay.replay_hits == 2
    assert replay.live_requests == 0


def test_valid_rescue_finding_record_replay_remains_exact(tmp_path: Path) -> None:
    request = ProofLanguageReviewRequest(document=_document())
    final = ProofReviewModelResponse(
        action="review",
        findings=(_finding("F2"),),
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="confirmed",
                explanation="Concern confirmed.",
                finding=_finding("F1"),
            ),
        ),
    )
    recorder = RecordingProvider(_Transport([_need(), final]), tmp_path)

    live_report = review_proof_language(request, recorder)
    assert [finding.id for finding in live_report.findings] == ["F1", "F2"]
    assert len(tuple(tmp_path.glob("*.json"))) == 2

    replay = ReplayProvider("test-model", tmp_path)
    replay_report = review_proof_language(request, replay)
    assert replay_report == live_report
    assert replay.requests == 2
    assert replay.replay_hits == 2
    assert replay.live_requests == 0
