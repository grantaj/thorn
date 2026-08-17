from __future__ import annotations

from itertools import combinations
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
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewItem,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTurnRequest,
    advertised_source_addresses,
    build_proof_review_turn,
    build_raw_review_turn,
    build_rescue_turn,
    review_proof_language,
)
from thorn.providers.replay import RecordingProvider, ReplayMissError, ReplayProvider
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import build_semantic_transformation_ir


def _document(*addresses: str, duplicate_mentions: bool = False) -> LLMProofLanguage:
    lines = ["THORN-PROOF 1", "T0 Goal"]
    for index, address in enumerate(addresses, start=1):
        lines.append(f"P{index} Fact{index} <- ? @{address}")
        if duplicate_mentions:
            lines.append(f"NEED P{index} Fact{index} @ {address} @{address}")
    lines.append("GOAL G0 T0: Goal | ctx - | open")
    return LLMProofLanguage(
        result_identifier="thm:closed-world",
        lines=tuple(lines),
        sources=tuple(
            ProofLanguageSourceHandle(
                address=address,
                ir_identifier=f"source:{index}",
                text=f"Exact source for {address}.",
            )
            for index, address in enumerate(addresses, start=1)
        ),
    )


def _proof_document(path: Path, target: str) -> LLMProofLanguage:
    project = extract_project(path)
    unit = project.unit(target)
    context = build_result_review_context(project, target)
    semantic_request = build_semantic_review_request(context.items[0])
    semantic = build_semantic_transformation_ir(
        unit,
        semantic_request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    return project_llm_proof_language(semantic)


def _need_payload(*addresses: str) -> dict[str, object]:
    return {
        "action": "need_source",
        "findings": [],
        "source_addresses": addresses,
        "review_items": [
            {
                "id": "RV1",
                "kind": "question",
                "summary": "Does the exact source settle this review question?",
            }
        ],
        "source_review_item_ids": ["RV1"],
    }


def _need(*addresses: str) -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=addresses,
        review_items=(
            ProofReviewItem(
                id="RV1",
                kind="question",
                summary="Does the exact source settle this review question?",
            ),
        ),
        source_review_item_ids=("RV1",),
    )


def _schema_source_values(turn: ProofReviewTurnRequest) -> tuple[str, ...]:
    source_schema = turn.response_schema()["properties"]["source_addresses"]
    items = source_schema.get("items")
    if items is None:
        return ()
    if "enum" in items:
        return tuple(items["enum"])
    if "const" in items:
        return (items["const"],)
    return ()


def _assert_arrays_have_items(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "array":
            assert "items" in value
        for nested in value.values():
            _assert_arrays_have_items(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_arrays_have_items(nested)


class _Transport:
    model = "test-model"

    def __init__(self, responses: list[ProofReviewModelResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[ProofReviewTurnRequest] = []
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse:
        self.calls.append(request)
        self.requests += 1
        self.live_requests += 1
        return self.responses.pop(0)


def test_zero_advertised_handles_make_need_source_unrepresentable() -> None:
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=_document()))
    schema = turn.response_schema()

    assert turn.allowed_source_addresses == ()
    assert schema["properties"]["action"]["const"] == "review"
    assert schema["properties"]["source_addresses"]["maxItems"] == 0
    assert schema["properties"]["source_addresses"]["items"]
    assert _schema_source_values(turn) == ()
    with pytest.raises(ValidationError):
        turn.response_model().model_validate(_need_payload())


def test_every_review_response_array_declares_transport_items() -> None:
    no_rescue = build_raw_review_turn("raw theorem and proof")
    initial = build_proof_review_turn(
        ProofLanguageReviewRequest(document=_document("E1"))
    )
    rescue = build_rescue_turn(
        ProofLanguageReviewRequest(document=_document("E1")),
        initial,
        _need("E1"),
    )

    for turn in (no_rescue, initial, rescue):
        _assert_arrays_have_items(turn.response_schema())


def test_one_and_many_advertised_handles_are_exact_schema_values() -> None:
    singleton = build_proof_review_turn(
        ProofLanguageReviewRequest(document=_document("E1"))
    )
    many = build_proof_review_turn(
        ProofLanguageReviewRequest(document=_document("P2", "C1", "E1"))
    )

    assert _schema_source_values(singleton) == ("E1",)
    assert _schema_source_values(many) == ("C1", "E1", "P2")
    singleton.response_model().model_validate(_need_payload("E1"))
    addresses = many.allowed_source_addresses
    for size in range(1, len(addresses) + 1):
        for subset in combinations(addresses, size):
            many.response_model().model_validate(_need_payload(*subset))


@pytest.mark.parametrize(
    ("fixture", "target", "authoritative_address"),
    [
        (
            Path("eval/cases/ladder/02_readability/clean_unusual_notation.tex"),
            "thm:unusual-notation",
            "D1",
        ),
        (
            Path("eval/cases/ladder/02_readability/notation_collision.tex"),
            "thm:notation-collision",
            "D1",
        ),
    ],
)
def test_issue_91_authoritative_context_handles_are_selectable_by_same_contract(
    fixture: Path,
    target: str,
    authoritative_address: str,
) -> None:
    document = _proof_document(fixture, target)
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=document))

    assert authoritative_address in turn.allowed_source_addresses
    turn.response_model().model_validate(_need_payload(authoritative_address))


def test_selectable_universe_may_exceed_eight_but_one_response_may_not() -> None:
    addresses = tuple(f"A{index}" for index in range(10))
    turn = build_proof_review_turn(
        ProofLanguageReviewRequest(document=_document(*addresses))
    )
    source_schema = turn.response_schema()["properties"]["source_addresses"]

    assert set(_schema_source_values(turn)) == set(addresses)
    assert source_schema["maxItems"] == 8
    turn.response_model().model_validate(_need_payload(*addresses[:8]))
    with pytest.raises(ValidationError):
        turn.response_model().model_validate(_need_payload(*addresses[:9]))
    with pytest.raises(ValidationError):
        turn.response_model().model_validate(_need_payload(*(("A0",) * 9)))


def test_unadvertised_packet_handles_and_paths_are_rejected_by_effective_model() -> None:
    first = build_proof_review_turn(
        ProofLanguageReviewRequest(document=_document("A1", "SHARED"))
    )
    second = build_proof_review_turn(
        ProofLanguageReviewRequest(document=_document("B1", "SHARED"))
    )

    second.response_model().model_validate(_need_payload("SHARED"))
    for invalid in (
        "A1",
        "Z99",
        "README.md",
        "pyproject.toml",
        "paper.tex",
        "../paper.tex",
        "/tmp/paper.tex",
        "src/paper.tex",
    ):
        with pytest.raises(ValidationError):
            second.response_model().model_validate(_need_payload(invalid))

    assert "A1" in _schema_source_values(first)
    assert "A1" not in _schema_source_values(second)


def test_advertised_duplicates_are_unique_and_contract_order_is_stable() -> None:
    document = _document("P2", "C1", "E1", duplicate_mentions=True)
    assert advertised_source_addresses(document) == ("C1", "E1", "P2")

    first = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint="same",
        user_content="same packet",
        source_rescue_allowed=True,
        allowed_source_addresses=("P2", "C1", "E1", "C1"),
        max_source_addresses=8,
    )
    second = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint="same",
        user_content="same packet",
        source_rescue_allowed=True,
        allowed_source_addresses=("E1", "P2", "C1"),
        max_source_addresses=8,
    )

    assert first.allowed_source_addresses == second.allowed_source_addresses == (
        "C1",
        "E1",
        "P2",
    )
    assert first.response_schema() == second.response_schema()
    assert proof_review_request_envelope(first, "test-model").fingerprint() == (
        proof_review_request_envelope(second, "test-model").fingerprint()
    )


def test_changing_only_closed_world_set_changes_effective_fingerprint() -> None:
    first = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint="same",
        user_content="same packet",
        source_rescue_allowed=True,
        allowed_source_addresses=("E1",),
        max_source_addresses=8,
    )
    second = first.model_copy(update={"allowed_source_addresses": ("E2",)})

    first_envelope = proof_review_request_envelope(first, "test-model")
    second_envelope = proof_review_request_envelope(second, "test-model")
    assert first_envelope.response_schema != second_envelope.response_schema
    assert first_envelope.fingerprint() != second_envelope.fingerprint()


def test_invalid_source_request_fails_without_disclosure_or_hidden_retry() -> None:
    transport = _Transport([_need("README.md")])

    with pytest.raises(ProofReviewProtocolError, match="not advertised"):
        review_proof_language(
            ProofLanguageReviewRequest(document=_document("E1")),
            transport,
        )

    assert len(transport.calls) == 1
    assert all("SOURCE @" not in turn.user_content for turn in transport.calls)


def test_recording_replay_uses_same_effective_contract_and_no_live_calls(
    tmp_path: Path,
) -> None:
    turn = ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint="same",
        user_content="same packet",
        source_rescue_allowed=True,
        allowed_source_addresses=("E1",),
        max_source_addresses=8,
    )
    recorder = RecordingProvider(_Transport([ProofReviewModelResponse(action="review")]), tmp_path)
    assert recorder.review_proof_turn(turn) == ProofReviewModelResponse(action="review")

    replay = ReplayProvider("test-model", tmp_path)
    assert replay.review_proof_turn(turn) == ProofReviewModelResponse(action="review")
    assert replay.requests == replay.replay_hits == 1
    assert replay.live_requests == 0

    changed_contract = turn.model_copy(update={"allowed_source_addresses": ("E2",)})
    with pytest.raises(ReplayMissError):
        replay.review_proof_turn(changed_contract)
    assert replay.requests == replay.replay_hits == 1
    assert replay.live_requests == 0
