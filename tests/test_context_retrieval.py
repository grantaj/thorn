from __future__ import annotations

from pathlib import Path

from thorn.context_retrieval import (
    ContextCandidate,
    ContextProposalStatus,
    ContextRank,
    ContextRanker,
    ResultContextPool,
    rank_context_pool,
)
from thorn.frontend import SourceSpan


class _ReverseRanker(ContextRanker):
    name = "test-reverse"

    def rank(self, query: str, candidates: tuple[ContextCandidate, ...]) -> tuple[ContextRank, ...]:
        del query
        return tuple(
            ContextRank(candidate_identifier=item.identifier, score=float(index))
            for index, item in enumerate(reversed(candidates), start=1)
        )


def _span(start: int, end: int) -> SourceSpan:
    return SourceSpan(
        file=str(Path("paper.tex").resolve()),
        start_offset=start,
        end_offset=end,
        start_line=1,
        start_column=start + 1,
        end_line=1,
        end_column=end + 1,
    )


def _candidate(number: int) -> ContextCandidate:
    return ContextCandidate(
        identifier=f"context:occ:{number}",
        statement_identifier=f"statement:{number}",
        occurrence_id="occ",
        text=f"statement {number}",
        source=_span(number * 10, number * 10 + 5),
    )


def test_ranker_must_order_every_candidate() -> None:
    class _DroppingRanker(ContextRanker):
        name = "drops-items"

        def rank(
            self, query: str, candidates: tuple[ContextCandidate, ...]
        ) -> tuple[ContextRank, ...]:
            del query
            return (ContextRank(candidate_identifier=candidates[0].identifier, score=1.0),)

    pool = ResultContextPool(
        status=ContextProposalStatus.COMPLETE,
        result_identifier="thm:main",
        target_occurrence_id="occ",
        query="target",
        candidates=(_candidate(1), _candidate(2)),
    )

    try:
        rank_context_pool(pool, _DroppingRanker())
    except ValueError as exc:
        assert "complete candidate pool" in str(exc)
    else:
        raise AssertionError("a ranker omission must not be interpreted as irrelevance")


def test_bounded_proposal_records_truncation_not_irrelevance() -> None:
    pool = ResultContextPool(
        status=ContextProposalStatus.COMPLETE,
        result_identifier="thm:main",
        target_occurrence_id="occ",
        query="target",
        candidates=(_candidate(1), _candidate(2), _candidate(3)),
    )
    ranked = rank_context_pool(pool, _ReverseRanker())
    bounded = ranked.bounded(2)

    assert [item.candidate.identifier for item in ranked.ranking] == [
        "context:occ:3",
        "context:occ:2",
        "context:occ:1",
    ]
    assert len(bounded.candidates) == 2
    assert bounded.total_candidate_count == 3
    assert bounded.truncated
