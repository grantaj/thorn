from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from thorn.latex import extract_project
from thorn.proof_language_review import ProofLanguageReviewRequest, build_proof_review_turn
from thorn.providers.openai import _strict_json_schema
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.review_workflow import prepare_proof_review

ROOT = Path(__file__).resolve().parents[1]
A3 = ROOT / "eval" / "robustness" / "issue_101" / "variant_result_applicability.tex"
REJECTED_A3_FINGERPRINT = (
    "44e1ffa1fb17219c106af28f8e7535e70788c1f7a02b5e762bf381e3637cfb28"
)


def _walk_dicts(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _a3_envelope():
    project = extract_project(A3)
    prepared = prepare_proof_review(project, project.unit("thm:uniform-decay"))
    turn = build_proof_review_turn(
        ProofLanguageReviewRequest(document=prepared.document)
    )
    return proof_review_request_envelope(turn, "gpt-5.6")


def test_a3_provider_visible_schema_closes_every_object_shape() -> None:
    envelope = _a3_envelope()
    strict = _strict_json_schema(envelope.response_schema)

    for node in _walk_dicts(strict):
        properties = node.get("properties")
        if properties is None:
            continue
        assert isinstance(properties, dict)
        assert node.get("type") == "object"
        assert node.get("additionalProperties") is False
        assert node.get("required") == list(properties)


def test_a3_action_branches_are_complete_closed_objects() -> None:
    envelope = _a3_envelope()
    schema = envelope.response_schema
    root_properties = schema.get("properties")
    branches = schema.get("anyOf")
    assert isinstance(root_properties, dict)
    assert isinstance(branches, list)
    assert len(branches) == 2

    actions: set[str] = set()
    for branch in branches:
        assert isinstance(branch, dict)
        assert branch.get("type") == "object"
        assert branch.get("additionalProperties") is False
        properties = branch.get("properties")
        assert isinstance(properties, dict)
        assert set(properties) == set(root_properties)
        action_schema = properties.get("action")
        assert isinstance(action_schema, dict)
        action = action_schema.get("const")
        assert isinstance(action, str)
        actions.add(action)

    assert actions == {"review", "need_source"}


def test_issue_143_repair_changes_the_rejected_a3_request_identity() -> None:
    envelope = _a3_envelope()
    assert envelope.fingerprint() != REJECTED_A3_FINGERPRINT
