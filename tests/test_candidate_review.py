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


def _context_candidate(
    number: int,
    *,
    occurrence_id: str | None = None,
    start: int | None = None,
    text: str | None = None,
    statement_identifier: str | None = None,
) -> ContextCandidate:
    path = str(Path("paper.tex").resolve())
    source_start = number * 10 if start is None else start
    source = SourceSpan(
        file=path,
        start_offset=source_start,
        end_offset=source_start + 5,
        start_line=number,
        start_column=1,
        end_line=number,
        end_column=6,
    )
    occurrence = occurrence_id or f"occ-{number}"
    statement = statement_identifier or f"statement-{number}"
    return ContextCandidate(
        identifier=f"context:{occurrence}:{statement}",
        statement_identifier=statement,
        occurrence_id=occurrence,
        text=text or f"exact source {number}",
        source=source,
    )


def _candidate(number: int) -> RankedContextCandidate:
    return RankedContextCandidate(
        candidate=_context_candidate(number),
        rank=number,
        score=1.0 / number,
    )


def _proposal(*candidates: ContextCandidate) -> BoundedContextProposal:
    ranked = tuple(
        RankedContextCandidate(candidate=candidate, rank=index, score=1.0 / index)
        for index, candidate in enumerate(candidates, start=1)
    )
    return BoundedContextProposal(
        status=ContextProposalStatus.COMPLETE,
        result_identifier="thm:main",
        target_occurrence_id="target-occ",
        ranker="test-ranker@revision",
        query="target statement",
        candidates=ranked,
        total_candidate_count=len(ranked),
        truncated=False,
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

    assert enriched.lines[-1].startswith(
        "CONTEXT_TRUNCATED target=target-occ @CCTX1,CCTX2 shown=2/5 context="
    )
    assert "test-ranker" not in enriched.render_initial()
    assert advertised_source_addresses(enriched) == ("CCTX1", "CCTX2")
    assert "exact source" not in enriched.render_initial()
    assert enriched.sources[0].ir_identifier.startswith("advisory-context:occ-1:")

    request = parse_source_rescue_request(enriched, "NEED_SOURCE CCTX1")
    rescued = render_source_rescue(enriched, request)
    assert "exact source 1" in rescued.text
    assert "exact source 2" not in rescued.text


def test_repeated_physical_source_keeps_distinct_occurrence_handles() -> None:
    document = LLMProofLanguage(result_identifier="thm:main", lines=("THORN-PROOF 1",))
    first = _context_candidate(
        1,
        occurrence_id="occ-a",
        start=10,
        text="same physical source",
        statement_identifier="statement:shared",
    )
    second = _context_candidate(
        1,
        occurrence_id="occ-b",
        start=10,
        text="same physical source",
        statement_identifier="statement:shared",
    )

    enriched = attach_advisory_context(document, _proposal(first, second))

    advisory = [
        source
        for source in enriched.sources
        if source.ir_identifier.startswith("advisory-context:")
    ]
    assert len(advisory) == 2
    assert {source.address for source in advisory} == {"CCTX1", "CCTX2"}
    assert {source.ir_identifier for source in advisory} == {
        "advisory-context:occ-a:statement:shared",
        "advisory-context:occ-b:statement:shared",
    }
    assert advertised_source_addresses(enriched) == ("CCTX1", "CCTX2")


def test_context_identity_changes_packet_fingerprint_for_same_visible_shape() -> None:
    document = LLMProofLanguage(result_identifier="thm:main", lines=("THORN-PROOF 1",))
    first = _context_candidate(
        1,
        occurrence_id="occ-a",
        start=10,
        text="same physical source",
        statement_identifier="statement:shared",
    )
    second = _context_candidate(
        1,
        occurrence_id="occ-b",
        start=10,
        text="same physical source",
        statement_identifier="statement:shared",
    )

    first_document = attach_advisory_context(document, _proposal(first))
    second_document = attach_advisory_context(document, _proposal(second))

    assert "shown=1/1" in first_document.lines[-1]
    assert "shown=1/1" in second_document.lines[-1]
    assert first_document.fingerprint() != second_document.fingerprint()
