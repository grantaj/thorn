from __future__ import annotations

from pydantic import BaseModel

from thorn.models import AttackReport, SourceRange
from thorn.providers.base import SemanticReviewProvider
from thorn.semantic_review import ReviewContext
from thorn.semantic_review_render import SemanticReviewRequest, build_semantic_review_request


class SemanticReviewResult(BaseModel):
    """Provider result retaining the exact bounded request and its provenance."""

    request: SemanticReviewRequest
    report: AttackReport

    @property
    def item_identifier(self) -> str:
        return self.request.item.identifier

    @property
    def result_identifier(self) -> str:
        return self.request.item.result.identifier

    @property
    def result_source(self) -> SourceRange:
        return self.request.item.result.source

    @property
    def trigger_relation_identifiers(self) -> list[str]:
        return sorted(self.request.item.trigger_relation_identifiers)


def review_semantic_context(
    context: ReviewContext,
    provider: SemanticReviewProvider,
) -> list[SemanticReviewResult]:
    """Review each already-selected Thorn IR item exactly once.

    Selection is complete before this boundary: normal review supplies one
    canonical result-level item, while ``thorn-eval`` may supply an explicitly
    targeted diagnostic projection. This layer performs no graph traversal,
    linguistic inference, caching, or provider-specific selection. The result
    retains the exact request so provenance remains available downstream.
    """

    results: list[SemanticReviewResult] = []
    for item in context.items:
        request = build_semantic_review_request(item)
        report = provider.review_semantic(request)
        results.append(SemanticReviewResult(request=request, report=report))
    return results
