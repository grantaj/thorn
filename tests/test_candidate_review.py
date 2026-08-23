from __future__ import annotations

from pathlib import Path

from thorn.candidate_review import attach_advisory_context
from thorn.context_retrieval import (
    BoundedContextProposal,
    ContextCandidate,
    ContextProposalStatus,
    RankedContextCandidate,
)
from thorn.frontend import SourceSpan
from thorn.llm_proof_language import (
    LLMProofLanguage,
    parse_source_rescue_request,
    render_source_rescue,
)
from thorn.proof_language_review import advertised_source_addresses


def _candidate(number: int) -> RankedContextCandidate:
    path = str(Path("paper.tex").resolve())
    start = number * 10
    source = SourceSpan(
        file=path,
        start_offset=start,
        end_offset=start + 5,
        start_line=number,
        start_column=1,
        end_line=number,
        end_column=6,
    )
    return RankedContextCandidate(
        candidate=ContextCandidate(
            identifier=f"context:occ-{number}:statement-{number}",
            statement_identifier=f"statement-{number}",
            occurrence_id=f"occ-{number}",
            text=f"exact source {number}",
            source=source,
        ),
        rank=number,
        score=1.0 / number,
    )


def test_advisory_context_is_bounded_closed_world_source_not_math_authority() -> None:
    document = LLMProofLanguage(result_identifier="thm:main", lines=("THORN-PROOF 1",))
    proposal = BoundedContextProposal(
        status=ContextProposalStatus.COMPLETE,
        result_identifier="thm:main",
        target_occurrence_id="target-occ",
        ranker="test-ranker@revision",
        query="target statement",
        candidates=(_candidate(1), _candidate(2)),
        total_candidate_count=5,
        truncated=True,
    )

    enriched = attach_advisory_context(document, proposal)

    assert enriched.lines[-1] == "CONTEXT_TRUNCATED @CCTX1,CCTX2 shown=2/5"
    assert "test-ranker" not in enriched.render_initial()
    assert advertised_source_addresses(enriched) == ("CCTX1", "CCTX2")
    assert "exact source" not in enriched.render_initial()
    assert enriched.sources[0].ir_identifier.startswith("advisory-context:occ-1:")

    request = parse_source_rescue_request(enriched, "NEED_SOURCE CCTX1")
    rescued = render_source_rescue(enriched, request)
    assert "exact source 1" in rescued.text
    assert "exact source 2" not in rescued.text
