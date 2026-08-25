from __future__ import annotations

from thorn.frontend import SourceSpan
from thorn.research.require_relations import (
    RequireRelationQuery,
    RequireRelationScore,
    assert_exact_reference,
)


def _span(file: str, start: int, end: int) -> SourceSpan:
    return SourceSpan(
        file=file,
        start_offset=start,
        end_offset=end,
        start_line=1,
        start_column=start + 1,
        end_line=1,
        end_column=end + 1,
    )


def test_issue_219_require_query_keeps_owner_resolution_and_provenance_supplied() -> None:
    context = "By THORNREF1, the claim follows."
    reference_start = context.index("THORNREF1")
    query = RequireRelationQuery(
        owner_id="RESULT_CURRENT",
        context=context,
        context_source=_span("synthetic.tex", 100, 100 + len(context)),
        reference_token="THORNREF1",
        resolved_target_id="RESULT_A",
        reference_source=_span(
            "synthetic.tex",
            100 + reference_start,
            100 + reference_start + len("THORNREF1"),
        ),
    )

    assert_exact_reference(query)
    assert query.owner_id == "RESULT_CURRENT"
    assert query.resolved_target_id == "RESULT_A"


def test_issue_219_require_score_is_non_authoritative_and_endpoint_bound() -> None:
    score = RequireRelationScore(
        relation_label="uses as a direct prerequisite",
        score=0.91,
        reference_token="THORNREF1",
        reference_source=_span("synthetic.tex", 3, 12),
        endpoint_exact=True,
    )

    assert score.endpoint_exact is True
    assert score.reference_token == "THORNREF1"
