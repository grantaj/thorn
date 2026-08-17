from __future__ import annotations

from dataclasses import dataclass

from thorn.dependencies import ExtractedProject
from thorn.eval_review import build_result_review_context
from thorn.llm_proof_language import LLMProofLanguage, project_llm_proof_language
from thorn.models import AttackReport, TheoremUnit
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    ProofReviewProtocolError,
    ProofReviewTransport,
    ProofReviewTurnRequest,
    build_proof_review_turn,
    build_rescue_turn,
    review_proof_language,
)
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.review_cache import (
    ProofReviewCache,
    ProofReviewCacheEntry,
    ReviewCacheDecision,
    ReviewCacheProvenance,
    ReviewCacheReason,
    ReviewCacheStatus,
    ReviewCacheSummary,
    ReviewDependencySnapshot,
    ReviewDependencyState,
    canonical_fingerprint,
    estimate_input_tokens,
    proof_review_cache_key,
    review_contract_identity,
)
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import (
    SemanticTransformationIR,
    build_semantic_transformation_ir,
)


@dataclass(frozen=True)
class PreparedProofReview:
    """Keyless canonical proof state plus its stable model-facing projection."""

    state: SemanticTransformationIR
    document: LLMProofLanguage
    provenance: ReviewCacheProvenance | None = None


@dataclass(frozen=True)
class CompletedProofReview:
    """A completed review plus the exact protocol turns used to obtain it."""

    report: AttackReport
    initial_turn: ProofReviewTurnRequest
    rescue_turn: ProofReviewTurnRequest | None = None


@dataclass(frozen=True)
class IncrementalProofReview:
    """One completed semantic review together with its cache decision."""

    review: CompletedProofReview
    cache: ReviewCacheDecision


@dataclass(frozen=True)
class IncrementalProofReviewRun:
    """Result-level incremental reviews plus aggregate avoided-work accounting."""

    results: tuple[IncrementalProofReview, ...]
    summary: ReviewCacheSummary


class _TracingTransport:
    """Observe Thorn-owned review requests without changing provider behavior."""

    def __init__(self, transport: ProofReviewTransport) -> None:
        self._transport = transport
        self.model = transport.model
        self.turns: list[ProofReviewTurnRequest] = []

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse:
        self.turns.append(request)
        return self._transport.review_proof_turn(request)


def _build_review_state(
    project: ExtractedProject,
    unit: TheoremUnit,
) -> tuple[SemanticTransformationIR, LLMProofLanguage]:
    context = build_result_review_context(project, unit.identifier)
    if len(context.items) != 1:
        raise ValueError(f"expected exactly one review item for {unit.identifier!r}")
    semantic_request = build_semantic_review_request(context.items[0])
    state = build_semantic_transformation_ir(
        unit,
        semantic_request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    return state, project_llm_proof_language(state)


def _target_content_fingerprint(unit: TheoremUnit) -> str:
    """Track source-local edits for explanations without making them a reuse gate."""

    return canonical_fingerprint(
        {
            "environment": unit.environment,
            "title": unit.title,
            "label": unit.label,
            "statement": unit.statement,
            "proof": unit.proof,
            "local_context": unit.local_context,
            "referenced_results": unit.referenced_results,
        }
    )


def _dependency_content_fingerprint(
    unit: TheoremUnit,
    document: LLMProofLanguage,
) -> str:
    """Fingerprint mathematical dependency content, including reachable source evidence."""

    return canonical_fingerprint(
        {
            "identifier": unit.identifier,
            "environment": unit.environment,
            "statement": unit.statement,
            "proof": unit.proof,
            "referenced_results": unit.referenced_results,
            "packet": document.render_initial(),
            "sources": [
                {
                    "address": source.address,
                    "ir_identifier": source.ir_identifier,
                    "text": source.text,
                    "referenced_result_identifier": source.referenced_result_identifier,
                }
                for source in document.sources
            ],
        }
    )


def _dependency_snapshot(
    project: ExtractedProject,
    result_identifier: str,
) -> ReviewDependencySnapshot:
    graph = project.dependency_graph
    dependency_ids = tuple(graph.transitive_dependency_ids(result_identifier))
    dependencies: list[ReviewDependencyState] = []
    for dependency_identifier in dependency_ids:
        dependency_unit = project.unit(dependency_identifier)
        _, dependency_document = _build_review_state(project, dependency_unit)
        dependencies.append(
            ReviewDependencyState(
                identifier=dependency_identifier,
                content_fingerprint=_dependency_content_fingerprint(
                    dependency_unit,
                    dependency_document,
                ),
            )
        )

    scope = {result_identifier, *dependency_ids}
    edges = sorted(
        (
            {
                "source_identifier": edge.source_identifier,
                "target_label": edge.target_label,
                "target_identifier": edge.target_identifier,
                "context": edge.context.value,
                "resolution": edge.resolution.value,
            }
            for edge in graph.edges
            if edge.source_identifier in scope
        ),
        key=lambda item: (
            str(item["source_identifier"]),
            str(item["target_label"]),
            str(item["target_identifier"]),
            str(item["context"]),
            str(item["resolution"]),
        ),
    )
    return ReviewDependencySnapshot(
        dependencies=tuple(dependencies),
        edges_fingerprint=canonical_fingerprint(edges),
    )


def prepare_proof_review(project: ExtractedProject, unit: TheoremUnit) -> PreparedProofReview:
    """Build canonical Proof IR and `thorn-proof/1` for one result, keylessly."""

    state, document = _build_review_state(project, unit)
    provenance = ReviewCacheProvenance(
        result_identifier=unit.identifier,
        target_content_fingerprint=_target_content_fingerprint(unit),
        packet_fingerprint=document.fingerprint(),
        dependency_snapshot=_dependency_snapshot(project, unit.identifier),
    )
    return PreparedProofReview(
        state=state,
        document=document,
        provenance=provenance,
    )


def run_proof_review(
    prepared: PreparedProofReview,
    transport: ProofReviewTransport,
) -> CompletedProofReview:
    """Run the normal v2 Proof-IR review protocol with at most one source rescue."""

    tracing = _TracingTransport(transport)
    report = review_proof_language(
        ProofLanguageReviewRequest(document=prepared.document),
        tracing,
    )
    if not tracing.turns:
        raise RuntimeError("proof review completed without a provider turn")
    if len(tracing.turns) > 2:
        raise RuntimeError("proof review exceeded the bounded two-turn protocol")
    return CompletedProofReview(
        report=report,
        initial_turn=tracing.turns[0],
        rescue_turn=tracing.turns[1] if len(tracing.turns) == 2 else None,
    )


def _completed_from_entry(entry: ProofReviewCacheEntry) -> CompletedProofReview:
    return CompletedProofReview(
        report=entry.report,
        initial_turn=entry.initial_turn,
        rescue_turn=entry.rescue_turn,
    )


def _miss_reason(
    prior: ProofReviewCacheEntry | None,
    provenance: ReviewCacheProvenance,
    contract_changed: bool,
) -> ReviewCacheReason:
    if prior is None:
        return ReviewCacheReason.RECHECK_NO_PRIOR_REVIEW

    old_dependencies = prior.provenance.dependency_snapshot
    new_dependencies = provenance.dependency_snapshot
    if old_dependencies.edges_fingerprint != new_dependencies.edges_fingerprint:
        return ReviewCacheReason.RECHECK_DEPENDENCY_EDGE_CHANGED
    if old_dependencies.content_by_identifier() != new_dependencies.content_by_identifier():
        return ReviewCacheReason.RECHECK_UPSTREAM_DEPENDENCY_CHANGED
    if prior.provenance.packet_fingerprint != provenance.packet_fingerprint:
        return ReviewCacheReason.RECHECK_LOCAL_IR_CHANGED
    if contract_changed:
        return ReviewCacheReason.RECHECK_REVIEW_CONTRACT_CHANGED
    return ReviewCacheReason.RECHECK_CACHE_IDENTITY_CHANGED


def _reuse_decision(
    entry: ProofReviewCacheEntry,
    provenance: ReviewCacheProvenance,
    *,
    cache_key: str,
    input_tokens_avoided: int,
) -> ReviewCacheDecision:
    reason = ReviewCacheReason.CACHE_HIT_EXACT_PACKET
    if entry.provenance.target_content_fingerprint != provenance.target_content_fingerprint:
        reason = ReviewCacheReason.CACHE_HIT_UNAFFECTED_DEPENDENCY_SLICE
    requests_avoided = 2 if entry.rescue_turn is not None else 1
    return ReviewCacheDecision(
        result_identifier=provenance.result_identifier,
        status=ReviewCacheStatus.REUSED,
        reason=reason,
        cache_key=cache_key,
        provider_requests_avoided=requests_avoided,
        estimated_input_tokens_avoided=input_tokens_avoided,
    )


def run_cached_proof_review(
    prepared: PreparedProofReview,
    transport: ProofReviewTransport,
    cache: ProofReviewCache,
) -> IncrementalProofReview:
    """Reuse a prior semantic judgment only when all material review inputs still match."""

    provenance = prepared.provenance
    if provenance is None:
        raise ValueError("cached proof review requires provenance from prepare_proof_review()")
    if provenance.result_identifier != prepared.document.result_identifier:
        raise ValueError("review cache provenance does not match the proof-language result")

    request = ProofLanguageReviewRequest(document=prepared.document)
    initial_turn = build_proof_review_turn(request)
    initial_envelope = proof_review_request_envelope(initial_turn, transport.model)
    initial_request_fingerprint = initial_envelope.fingerprint()
    contract = review_contract_identity(initial_turn, initial_envelope)
    cache_key = proof_review_cache_key(provenance, contract, initial_request_fingerprint)

    exact = cache.get(cache_key)
    source_changed = False
    if exact is not None:
        if exact.rescue_turn is None:
            cache.set_head(provenance.result_identifier, cache_key)
            decision = _reuse_decision(
                exact,
                provenance,
                cache_key=cache_key,
                input_tokens_avoided=estimate_input_tokens(initial_envelope),
            )
            return IncrementalProofReview(review=_completed_from_entry(exact), cache=decision)

        prior_source_request = exact.rescue_turn.prior_response
        if prior_source_request is None:
            source_changed = True
        else:
            try:
                current_rescue_turn = build_rescue_turn(
                    request,
                    initial_turn,
                    prior_source_request,
                )
            except (KeyError, ValueError, ProofReviewProtocolError):
                source_changed = True
            else:
                current_rescue_envelope = proof_review_request_envelope(
                    current_rescue_turn,
                    transport.model,
                )
                if current_rescue_envelope.fingerprint() == exact.rescue_request_fingerprint:
                    cache.set_head(provenance.result_identifier, cache_key)
                    decision = _reuse_decision(
                        exact,
                        provenance,
                        cache_key=cache_key,
                        input_tokens_avoided=(
                            estimate_input_tokens(initial_envelope)
                            + estimate_input_tokens(current_rescue_envelope)
                        ),
                    )
                    return IncrementalProofReview(
                        review=_completed_from_entry(exact),
                        cache=decision,
                    )
                source_changed = True

    prior = exact if exact is not None else cache.latest(provenance.result_identifier)
    if source_changed:
        reason = ReviewCacheReason.RECHECK_RESCUED_SOURCE_CHANGED
    elif prior is not None and prior.cache_key == cache_key and exact is None:
        reason = ReviewCacheReason.RECHECK_CACHE_ENTRY_MISSING
    else:
        reason = _miss_reason(
            prior,
            provenance,
            contract_changed=prior is not None and prior.contract != contract,
        )

    completed = run_proof_review(prepared, transport)
    completed_initial_envelope = proof_review_request_envelope(
        completed.initial_turn,
        transport.model,
    )
    if completed_initial_envelope.fingerprint() != initial_request_fingerprint:
        raise RuntimeError("proof-review request changed between cache lookup and execution")

    rescue_request_fingerprint: str | None = None
    if completed.rescue_turn is not None:
        rescue_request_fingerprint = proof_review_request_envelope(
            completed.rescue_turn,
            transport.model,
        ).fingerprint()

    entry = ProofReviewCacheEntry(
        cache_key=cache_key,
        provenance=provenance,
        contract=contract,
        initial_request_fingerprint=initial_request_fingerprint,
        rescue_request_fingerprint=rescue_request_fingerprint,
        report=completed.report,
        initial_turn=completed.initial_turn,
        rescue_turn=completed.rescue_turn,
    )
    cache.put(entry)
    decision = ReviewCacheDecision(
        result_identifier=provenance.result_identifier,
        status=ReviewCacheStatus.RECHECKED,
        reason=reason,
        cache_key=cache_key,
    )
    return IncrementalProofReview(review=completed, cache=decision)


def run_incremental_proof_reviews(
    project: ExtractedProject,
    units: list[TheoremUnit],
    transport: ProofReviewTransport,
    cache: ProofReviewCache,
) -> IncrementalProofReviewRun:
    """Review result units independently, reusing only unaffected semantic judgments."""

    results = tuple(
        run_cached_proof_review(prepare_proof_review(project, unit), transport, cache)
        for unit in units
    )
    decisions = tuple(item.cache for item in results)
    return IncrementalProofReviewRun(
        results=results,
        summary=ReviewCacheSummary.from_decisions(decisions),
    )
