from __future__ import annotations

from test_semantic_review import make_project

from thorn.eval_review import build_result_review_context
from thorn.semantic_review import ReviewTargetKind, build_review_context
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import (
    build_semantic_review_request,
    render_semantic_review_request,
)


def test_normal_review_is_result_level_even_without_uncertainty_trigger() -> None:
    project = make_project(include_uncertain=False)

    context = build_result_review_context(project, "thm:main")

    assert len(context.items) == 1
    item = context.items[0]
    assert item.target_kind == ReviewTargetKind.RESULT
    assert item.trigger_relation_identifiers == []
    assert item.identifier == "semantic-review-eval:thm:main"

    rendered = render_semantic_review_request(build_semantic_review_request(item))
    assert "Target kind: result" in rendered
    assert "canonical result-level review view" in rendered
    assert "did not gate or cause the review request" in rendered
    assert "reason this targeted view was selected" not in rendered


def test_targeted_selector_remains_explicit_diagnostic_projection() -> None:
    project = make_project()

    context = build_review_context(project)

    assert context.items
    assert all(item.target_kind == ReviewTargetKind.SUPPORT_RELATION for item in context.items)
    item = context.items[0]
    assert item.identifier.startswith("semantic-review:thm:main:")

    rendered = render_semantic_review_request(build_semantic_review_request(item))
    assert "Target kind: support_relation" in rendered
    assert "reason this targeted view was selected" in rendered
    assert "## Relations that caused semantic escalation" in rendered


def test_compact_renderer_does_not_call_result_uncertainty_escalation() -> None:
    project = make_project()
    result_item = build_result_review_context(project, "thm:main").items[0]
    targeted_item = build_review_context(project).items[0]

    result_rendered = render_compact_semantic_review_request(
        build_semantic_review_request(result_item)
    )
    targeted_rendered = render_compact_semantic_review_request(
        build_semantic_review_request(targeted_item)
    )

    assert "# Uncertain support relations" in result_rendered
    assert "# Escalated support questions" not in result_rendered
    assert "# Escalated support questions" in targeted_rendered
