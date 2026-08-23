from __future__ import annotations

from thorn.candidate_review import prepare_candidate_proof_review
from thorn.context_retrieval import (
    ContextCandidate,
    ContextRank,
    ContextRanker,
    build_result_context_pools,
    rank_context_pool,
)


class SourceOrderRanker:
    """Test-only total ordering with no relevance or authority semantics."""

    name = "contract-source-order"

    def rank(
        self,
        query: str,
        candidates: tuple[ContextCandidate, ...],
    ) -> tuple[ContextRank, ...]:
        del query
        return tuple(
            ContextRank(candidate_identifier=candidate.identifier, score=-float(index))
            for index, candidate in enumerate(candidates)
        )


def prepare_all_prior_context(project, result_identifier: str):
    """Prepare one occurrence with every eligible prior statement advertised.

    This deliberately avoids relevance selection. Tests using it verify source/provenance
    and closed-world rescue semantics; production ranking quality is covered separately.
    """

    pools = build_result_context_pools(project, result_identifier)
    assert len(pools) == 1
    pool = pools[0]
    assert pool.candidates
    ranker: ContextRanker = SourceOrderRanker()
    proposal = rank_context_pool(pool, ranker)
    bounded = proposal.bounded(len(proposal.ranking))
    assert not bounded.truncated
    return prepare_candidate_proof_review(
        project,
        project.unit(result_identifier),
        bounded,
    )
