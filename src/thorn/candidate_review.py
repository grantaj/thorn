from __future__ import annotations

from thorn.context_retrieval import BoundedContextProposal, ContextProposalStatus
from thorn.dependencies import ExtractedProject
from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.models import TheoremUnit
from thorn.review_cache import ReviewCacheProvenance
from thorn.review_workflow import PreparedProofReview, prepare_proof_review


def attach_advisory_context(
    document: LLMProofLanguage,
    proposal: BoundedContextProposal,
) -> LLMProofLanguage:
    """Advertise ranked exact source without promoting it into mathematical IR."""

    if proposal.status != ContextProposalStatus.COMPLETE or not proposal.candidates:
        return document

    existing = {
        (
            source.source_span.file,
            source.source_span.start_offset,
            source.source_span.end_offset,
            source.text,
        )
        for source in document.sources
        if source.source_span is not None
    }
    handles: list[ProofLanguageSourceHandle] = []
    for item in proposal.candidates:
        candidate = item.candidate
        key = (
            candidate.source.file,
            candidate.source.start_offset,
            candidate.source.end_offset,
            candidate.text,
        )
        if key in existing:
            continue
        address = f"CCTX{len(handles) + 1}"
        handles.append(
            ProofLanguageSourceHandle(
                address=address,
                ir_identifier=(
                    f"advisory-context:{candidate.occurrence_id}:"
                    f"{candidate.statement_identifier}"
                ),
                text=candidate.text,
                source_span=candidate.source,
            )
        )
        existing.add(key)

    if not handles:
        return document
    addresses = ",".join(handle.address for handle in handles)
    marker = "CONTEXT_TRUNCATED" if proposal.truncated else "CONTEXT"
    line = (
        f"{marker} @{addresses} ranker={proposal.ranker or 'unknown'} "
        f"shown={len(handles)}/{proposal.total_candidate_count}"
    )
    return document.model_copy(
        update={
            "lines": (*document.lines, line),
            "sources": (*document.sources, *handles),
        }
    )


def prepare_candidate_proof_review(
    project: ExtractedProject,
    unit: TheoremUnit,
    proposal: BoundedContextProposal,
) -> PreparedProofReview:
    """Build ordinary Thorn proof state plus advisory ranked source reachability.

    Retrieval does not modify claims, symbols, dependencies, support relations or
    their certainty. It only extends the exact, closed-world source handles that a
    bounded review may request.
    """

    if proposal.result_identifier != unit.identifier:
        raise ValueError("context proposal does not match the requested result")
    prepared = prepare_proof_review(project, unit)
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
