from __future__ import annotations

from pydantic import BaseModel, Field

from thorn.models import AttackReport, SourceRange
from thorn.providers.base import SemanticReviewProvider
from thorn.semantic_review import ReviewContext
from thorn.semantic_review_render import build_semantic_review_request


class SemanticReviewResult(BaseModel):
    """Provider result associated with the bounded review item that produced it."""

    item_identifier: str
    result_identifier: str
    result_source: SourceRange
    trigger_relation_identifiers: list[str] = Field(default_factory=list)
    report: AttackReport


def review_semantic_context(
    context: ReviewContext,
    provider: SemanticReviewProvider,
) -> list[SemanticReviewResult]:
    """Review each pre-grouped IR item exactly once through a semantic provider.

    Selection and grouping stay in ``semantic_review.py``. This layer performs no
    graph traversal, linguistic inference, caching, or provider-specific rendering.
    """

    results: list[SemanticReviewResult] = []
    for item in context.items:
        request = build_semantic_review_request(item)
        report = provider.review_semantic(request)
        results.append(
            SemanticReviewResult(
                item_identifier=item.identifier,
                result_identifier=item.result.identifier,
                result_source=item.result.source,
                trigger_relation_identifiers=sorted(item.trigger_relation_identifiers),
                report=report,
            )
        )
    return results
