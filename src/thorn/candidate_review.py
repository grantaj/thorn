from __future__ import annotations

import hashlib
import json

from thorn.context_retrieval import (
    BoundedContextProposal,
    ContextCandidate,
    ContextProposalStatus,
    ResultContextPool,
)
from thorn.dependencies import ExtractedProject
from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.models import TheoremUnit
from thorn.review_cache import ReviewCacheProvenance
from thorn.review_workflow import PreparedProofReview, prepare_proof_review


def _advisory_identifier(candidate: ContextCandidate) -> str:
    return (
        f"advisory-context:{candidate.occurrence_id}:"
        f"{candidate.statement_identifier}"
    )


def _context_digest(
    candidates: tuple[ContextCandidate, ...],
    *,
    target_occurrence_id: str | None,
    total_candidate_count: int,
    truncated: bool,
) -> str:
    payload = {
        "target_occurrence_id": target_occurrence_id,
        "total_candidate_count": total_candidate_count,
        "truncated": truncated,
        "candidates": [
            {
                "identifier": candidate.identifier,
                "statement_identifier": candidate.statement_identifier,
                "occurrence_id": candidate.occurrence_id,
                "text": candidate.text,
                "source": candidate.source.model_dump(mode="json"),
            }
            for candidate in candidates
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _next_context_index(document: LLMProofLanguage) -> int:
    indices = [
        int(source.address.removeprefix("CCTX"))
        for source in document.sources
        if source.address.startswith("CCTX")
        and source.address.removeprefix("CCTX").isdigit()
    ]
    return max(indices, default=0) + 1


def _attach_candidates(
    document: LLMProofLanguage,
    candidates: tuple[ContextCandidate, ...],
    *,
    target_occurrence_id: str | None,
    total_candidate_count: int,
    truncated: bool,
) -> LLMProofLanguage:
    if not candidates:
        return document

    existing = {
        source.ir_identifier: source.address
        for source in document.sources
        if source.ir_identifier.startswith("advisory-context:")
    }
    handles: list[ProofLanguageSourceHandle] = []
    addresses: list[str] = []
    next_index = _next_context_index(document)

    for candidate in candidates:
        identifier = _advisory_identifier(candidate)
        address = existing.get(identifier)
        if address is None:
            address = f"CCTX{next_index}"
            next_index += 1
            handles.append(
                ProofLanguageSourceHandle(
                    address=address,
                    ir_identifier=identifier,
                    text=candidate.text,
                    source_span=candidate.source,
                    source_range=candidate.source.source_range(),
                )
            )
            existing[identifier] = address
        addresses.append(address)

    digest = _context_digest(
        candidates,
        target_occurrence_id=target_occurrence_id,
        total_candidate_count=total_candidate_count,
        truncated=truncated,
    )
    marker = "CONTEXT_TRUNCATED" if truncated else "CONTEXT"
    target = target_occurrence_id or "unknown"
    line = (
        f"{marker} target={target} @{','.join(addresses)} "
        f"shown={len(candidates)}/{total_candidate_count} context={digest}"
    )
    return document.model_copy(
        update={
            "lines": (*document.lines, line),
            "sources": (*document.sources, *handles),
        }
    )


def attach_advisory_context(
    document: LLMProofLanguage,
    proposal: BoundedContextProposal,
) -> LLMProofLanguage:
    """Advertise ranked exact source without promoting it into mathematical IR."""

    if proposal.status != ContextProposalStatus.COMPLETE or not proposal.candidates:
        return document
    return _attach_candidates(
        document,
        tuple(item.candidate for item in proposal.candidates),
        target_occurrence_id=proposal.target_occurrence_id,
        total_candidate_count=proposal.total_candidate_count,
        truncated=proposal.truncated,
    )


def attach_complete_advisory_context(
    document: LLMProofLanguage,
    pools: tuple[ResultContextPool, ...],
) -> LLMProofLanguage:
    """Advertise every eligible prior statement, preserving occurrence identity.

    This is the production correctness path. It makes no relevance judgment and does
    not truncate. Generic ranking may later provide a smaller advisory view, but
    omission from such a view must never become the only way exact prior source is
    reachable to review.
    """

    enriched = document
    for pool in pools:
        if pool.status != ContextProposalStatus.COMPLETE or not pool.candidates:
            continue
        enriched = _attach_candidates(
            enriched,
            pool.candidates,
            target_occurrence_id=pool.target_occurrence_id,
            total_candidate_count=len(pool.candidates),
            truncated=False,
        )
    return enriched


def prepare_candidate_proof_review(
    project: ExtractedProject,
    unit: TheoremUnit,
    proposal: BoundedContextProposal,
) -> PreparedProofReview:
    """Build canonical proof state plus one advisory ranked source proposal.

    Retrieval does not modify claims, symbols, dependencies, support relations or
    their certainty. It only extends the exact, closed-world source handles that a
    bounded review may request. Ranker identity remains measurement metadata rather
    than proof-language syntax.
    """

    if proposal.result_identifier != unit.identifier:
        raise ValueError("context proposal does not match the requested result")
    prepared = prepare_proof_review(
        project,
        unit,
        include_advisory_context=False,
    )
    document = attach_advisory_context(prepared.document, proposal)
    provenance = prepared.provenance
    if provenance is None:
        return PreparedProofReview(state=prepared.state, document=document)
    return PreparedProofReview(
        state=prepared.state,
        document=document,
        provenance=ReviewCacheProvenance(
            result_identifier=provenance.result_identifier,
            target_content_fingerprint=provenance.target_content_fingerprint,
            target_semantic_fingerprint=provenance.target_semantic_fingerprint,
            packet_fingerprint=document.fingerprint(),
            dependency_snapshot=provenance.dependency_snapshot,
        ),
    )
