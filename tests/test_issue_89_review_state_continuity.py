from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.llm_proof_language import (
    LLMProofLanguage,
    ProofLanguageSourceHandle,
    project_llm_proof_language,
)
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
from thorn.providers.replay import RecordingProvider, ReplayMissError, ReplayProvider
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import build_semantic_transformation_ir


def _document(*, held_only: tuple[str, ...] = ()) -> LLMProofLanguage:
    advertised = ("E1", "E2")
    return LLMProofLanguage(
        result_identifier="thm:state-continuity",
        lines=(
            "THORN-PROOF 1",
            "T0 Goal",
            "P1 Mid <- ? @E1",
            "P2 Goal <- P1 ? @E2",
            "GOAL G0 T0: Goal | ctx P1,P2 | open",
        ),
        sources=tuple(
            ProofLanguageSourceHandle(
                address=address,
                ir_identifier=f"source:{index}",
                text=f"Exact evidence {index}.",
            )
            for index, address in enumerate((*advertised, *held_only), start=1)
        ),
    )


def _project_document(path: Path, target: str) -> LLMProofLanguage:
    project = extract_project(path)
    unit = project.unit(target)
    context = build_result_review_context(project, target)
    request = build_semantic_review_request(context.items[0])
    semantic = build_semantic_transformation_ir(
        unit,
        request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    return project_llm_proof_language(semantic)


def _item(index: int, summary: str, *, kind: str = "concern") -> ProofReviewItem:
    return ProofReviewItem(id=f"R{index}", kind=kind, summary=summary)


def _need(
    *addresses: str,
    items: tuple[ProofReviewItem, ...] | None = None,
    source_items: tuple[str, ...] | None = None,
) -> ProofReviewModelResponse:
    carried = items or (
        _item(
            1,
            "Does the stated step follow from the available assumptions?",
            kind="question",
        ),
    )
    motivated = source_items or (carried[-1].id,)
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=addresses,
        review_items=carried,
        source_review_item_ids=motivated,
    )


def _finding(identifier: str, title: str) -> CandidateFinding:
    return CandidateFinding(
        id=identifier,
        category=FindingCategory.INVALID_IMPLICATION,
        severity=Severity.ERROR,
        title=title,
        explanation="The conclusion does not follow from the stated premise.",
        evidence=["P1"],
        confidence=0.95,
    )


def _disposition(
    item_id: str,
    status: str,
    *,
    finding: CandidateFinding | None = None,
) -> ProofReviewDisposition:
    return ProofReviewDisposition(
        item_id=item_id,
        status=status,
        explanation=f"Evidence {status} this review item.",
        finding=finding,
    )


class _Transport:
    model = "test-model"

    def __init__(self, responses: list[ProofReviewModelResponse]) -> None:
        self.responses = list(responses)
        self.calls = []
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def review_proof_turn(self, request):
        self.calls.append(request)
        self.requests += 1
        self.live_requests += 1
        return self.responses.pop(0)


def _rescue_turn(initial: ProofReviewModelResponse):
    request = ProofLanguageReviewRequest(document=_document())
    first = build_proof_review_turn(request)
    return request, build_rescue_turn(request, first, initial)


def test_independent_concern_survives_rescue_for_another_question() -> None:
    initial = _need(
        "E2",
        items=(
            _item(1, "An upstream implication is already unsupported."),
            _item(2, "Does the downstream definition justify this use?", kind="question"),
        ),
        source_items=("R2",),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(
            _disposition(
                "R1",
                "confirmed",
                finding=_finding("F1", "Upstream implication fails"),
            ),
            _disposition("R2", "discharged"),
        ),
    )
    transport = _Transport([initial, final])
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        transport,
    )
    assert [finding.id for finding in report.findings] == ["F1"]
    assert transport.calls[1].prior_response == initial


def test_source_exonerates_carried_concern_and_final_report_is_clean() -> None:
    initial = _need(
        "E1",
        items=(_item(1, "The step may omit a needed condition."),),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R1", "discharged"),),
    )
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        _Transport([initial, final]),
    )
    assert report.findings == []


def test_source_confirms_carried_concern_as_final_finding() -> None:
    initial = _need(
        "E1",
        items=(_item(1, "The implication appears unsupported."),),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(
            _disposition(
                "R1",
                "confirmed",
                finding=_finding("F1", "Implication is invalid"),
            ),
        ),
    )
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        _Transport([initial, final]),
    )
    assert [finding.title for finding in report.findings] == ["Implication is invalid"]


def test_source_revises_carried_concern_without_textual_identity_matching() -> None:
    initial = _need(
        "E1",
        items=(_item(1, "The first transformation may be unjustified."),),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(
            _disposition(
                "R1",
                "revised",
                finding=_finding(
                    "F1",
                    "The later transformation is the actual failure",
                ),
            ),
        ),
    )
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        _Transport([initial, final]),
    )
    assert report.findings[0].title == "The later transformation is the actual failure"


def test_source_may_reveal_genuinely_new_concern() -> None:
    initial = _need(
        "E1",
        items=(_item(1, "Does the definition settle this step?", kind="question"),),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R1", "discharged"),),
        findings=(
            _finding("F2", "Exact evidence exposes a separate invalid implication"),
        ),
    )
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        _Transport([initial, final]),
    )
    assert [finding.id for finding in report.findings] == ["F2"]


def test_multiple_dependencies_keep_upstream_concern_when_rescuing_downstream() -> None:
    initial = _need(
        "E2",
        items=(
            _item(1, "The load-bearing upstream inference is unsupported."),
            _item(2, "The downstream use needs exact evidence.", kind="question"),
        ),
        source_items=("R2",),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(
            _disposition(
                "R1",
                "confirmed",
                finding=_finding("F1", "Upstream support is invalid"),
            ),
            _disposition("R2", "discharged"),
        ),
    )
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        _Transport([initial, final]),
    )
    assert [finding.id for finding in report.findings] == ["F1"]


def test_clean_clarification_question_can_be_explicitly_discharged() -> None:
    initial = _need(
        "E1",
        items=(
            _item(1, "Does the definition establish both directions?", kind="question"),
        ),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R1", "discharged"),),
    )
    report = review_proof_language(
        ProofLanguageReviewRequest(document=_document()),
        _Transport([initial, final]),
    )
    assert report.findings == []


def test_carried_concern_cannot_be_omitted_even_via_model_copy_bypass() -> None:
    initial = _need(
        "E1",
        items=(_item(1, "Question A", kind="question"),),
    )
    _, rescue = _rescue_turn(initial)
    valid = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R1", "discharged"),),
    )
    forged = valid.model_copy(update={"dispositions": ()})
    with pytest.raises(ProofReviewProtocolError, match="omitted carried review item"):
        validate_proof_review_response(rescue, forged)


def test_duplicate_disposition_is_rejected() -> None:
    _, rescue = _rescue_turn(_need("E1"))
    response = ProofReviewModelResponse(
        action="review",
        dispositions=(
            _disposition("R1", "discharged"),
            _disposition("R1", "discharged"),
        ),
    )
    with pytest.raises(ProofReviewProtocolError, match="more than once"):
        validate_proof_review_response(rescue, response)


def test_unknown_disposition_identity_is_rejected() -> None:
    _, rescue = _rescue_turn(_need("E1"))
    response = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R2", "discharged"),),
    )
    with pytest.raises(ProofReviewProtocolError, match="unknown review item"):
        validate_proof_review_response(rescue, response)


def test_silent_rename_as_new_finding_does_not_disposition_old_item() -> None:
    _, rescue = _rescue_turn(_need("E1"))
    response = ProofReviewModelResponse(
        action="review",
        findings=(_finding("F9", "Renamed concern"),),
    )
    with pytest.raises(ProofReviewProtocolError, match="omitted carried review item"):
        validate_proof_review_response(rescue, response)


def test_confirming_one_carried_item_cannot_drop_another() -> None:
    initial = _need(
        "E1",
        items=(
            _item(1, "Concern A"),
            _item(2, "Question B", kind="question"),
        ),
        source_items=("R2",),
    )
    _, rescue = _rescue_turn(initial)
    response = ProofReviewModelResponse(
        action="review",
        dispositions=(
            _disposition(
                "R1",
                "confirmed",
                finding=_finding("F1", "A confirmed"),
            ),
        ),
    )
    with pytest.raises(ProofReviewProtocolError, match="R2"):
        validate_proof_review_response(rescue, response)


def test_discharge_without_link_to_carried_item_is_rejected() -> None:
    _, rescue = _rescue_turn(_need("E1"))
    response = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R2", "discharged"),),
    )
    with pytest.raises(ProofReviewProtocolError, match="unknown review item"):
        validate_proof_review_response(rescue, response)


def test_new_finding_cannot_reuse_carried_review_identity() -> None:
    _, rescue = _rescue_turn(_need("E1"))
    response = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R1", "discharged"),),
        findings=(_finding("R1", "Masquerading new concern"),),
    )
    with pytest.raises(
        ProofReviewProtocolError,
        match="reuses a carried review identity",
    ):
        validate_proof_review_response(rescue, response)


def test_second_need_source_is_rejected_without_third_turn() -> None:
    transport = _Transport([_need("E1"), _need("E2")])
    with pytest.raises(ProofReviewProtocolError, match="second source-rescue"):
        review_proof_language(
            ProofLanguageReviewRequest(document=_document()),
            transport,
        )
    assert len(transport.calls) == 2


def test_review_state_has_no_nested_source_address_channel() -> None:
    with pytest.raises(ValidationError):
        ProofReviewItem.model_validate(
            {
                "id": "R1",
                "kind": "question",
                "summary": "Question",
                "source_address": "E1",
            }
        )
    schema = ProofReviewModelResponse.model_json_schema()
    item_schema = schema["$defs"]["ProofReviewItem"]["properties"]
    disposition_schema = schema["$defs"]["ProofReviewDisposition"]["properties"]
    assert not {"source_address", "source_addresses"} & set(item_schema)
    assert not {"source_address", "source_addresses"} & set(disposition_schema)


def test_packet_guard_blocks_forged_held_source_before_disclosure() -> None:
    document = _document(held_only=("H1",))
    request = ProofLanguageReviewRequest(document=document)
    initial = build_proof_review_turn(request)
    forged = initial.model_copy(
        update={
            "allowed_source_addresses": (
                *initial.allowed_source_addresses,
                "H1",
            )
        }
    )
    with pytest.raises(
        ProofReviewProtocolError,
        match="source-selection contract does not match",
    ):
        build_rescue_turn(request, forged, _need("H1"))


def test_changed_carried_state_changes_rescue_fingerprint() -> None:
    request = ProofLanguageReviewRequest(document=_document())
    initial = build_proof_review_turn(request)
    first = build_rescue_turn(
        request,
        initial,
        _need(
            "E1",
            items=(_item(1, "Question one", kind="question"),),
        ),
    )
    second = build_rescue_turn(
        request,
        initial,
        _need(
            "E1",
            items=(_item(1, "Different question", kind="question"),),
        ),
    )
    first_envelope = proof_review_request_envelope(first, "test-model")
    second_envelope = proof_review_request_envelope(second, "test-model")
    assert first.requested_source_addresses == second.requested_source_addresses
    assert first_envelope.fingerprint() != second_envelope.fingerprint()
    assert first_envelope.messages != second_envelope.messages


def test_replay_rejects_same_packet_and_source_with_different_prior_state(
    tmp_path: Path,
) -> None:
    request = ProofLanguageReviewRequest(document=_document())
    initial = build_proof_review_turn(request)
    recorded = build_rescue_turn(
        request,
        initial,
        _need(
            "E1",
            items=(_item(1, "Question one", kind="question"),),
        ),
    )
    recorder = RecordingProvider(
        _Transport(
            [
                ProofReviewModelResponse(
                    action="review",
                    dispositions=(_disposition("R1", "discharged"),),
                )
            ]
        ),
        tmp_path,
    )
    recorder.review_proof_turn(recorded)

    changed = build_rescue_turn(
        request,
        initial,
        _need(
            "E1",
            items=(_item(1, "Different carried question", kind="question"),),
        ),
    )
    replay = ReplayProvider("test-model", tmp_path)
    with pytest.raises(ReplayMissError):
        replay.review_proof_turn(changed)
    assert replay.requests == 0
    assert replay.live_requests == 0


def test_clean_unusual_notation_can_carry_then_discharge_clarification() -> None:
    document = _project_document(
        Path("eval/cases/ladder/02_readability/clean_unusual_notation.tex"),
        "thm:unusual-notation",
    )
    request = ProofLanguageReviewRequest(document=document)
    initial = build_proof_review_turn(request)
    assert "D1" in initial.allowed_source_addresses
    rescue = build_rescue_turn(
        request,
        initial,
        _need(
            "D1",
            items=(
                _item(
                    1,
                    "Does authoritative source settle the notation direction?",
                    kind="question",
                ),
            ),
        ),
    )
    final = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R1", "discharged"),),
    )
    validated = validate_proof_review_response(rescue, final)
    assert validated.dispositions[0].status == "discharged"


def test_rh_witness_can_carry_upstream_scrutiny_during_downstream_rescue() -> None:
    document = _project_document(
        Path(
            "eval/cases/ladder/09_hidden_assumptions/"
            "riemann_hypothesis_dependency.tex"
        ),
        "thm:rh-prime-window",
    )
    request = ProofLanguageReviewRequest(document=document)
    initial = build_proof_review_turn(request)
    assert initial.allowed_source_addresses
    address = initial.allowed_source_addresses[-1]
    source_request = _need(
        address,
        items=(
            _item(1, "A load-bearing upstream dependency requires scrutiny."),
            _item(2, "A downstream step needs exact evidence.", kind="question"),
        ),
        source_items=("R2",),
    )
    rescue = build_rescue_turn(request, initial, source_request)
    assert rescue.prior_response is not None
    assert tuple(item.id for item in rescue.prior_response.review_items) == (
        "R1",
        "R2",
    )
    malformed = ProofReviewModelResponse(
        action="review",
        dispositions=(_disposition("R2", "discharged"),),
    )
    with pytest.raises(ProofReviewProtocolError, match="R1"):
        validate_proof_review_response(rescue, malformed)
