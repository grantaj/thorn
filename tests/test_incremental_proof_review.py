from __future__ import annotations

from pathlib import Path
from typing import cast

from thorn.latex import extract_project
from thorn.llm_proof_language import LLMProofLanguage, ProofLanguageSourceHandle
from thorn.proof_language_review import (
    ProofReviewDisposition,
    ProofReviewItem,
    ProofReviewModelResponse,
)
from thorn.review_cache import (
    ProofReviewCache,
    ReviewCacheProvenance,
    ReviewCacheReason,
    ReviewCacheStatus,
    ReviewCacheSummary,
    ReviewDependencySnapshot,
    canonical_fingerprint,
)
from thorn.review_workflow import (
    PreparedProofReview,
    prepare_proof_review,
    run_cached_proof_review,
)
from thorn.semantic_transformations import SemanticTransformationIR


class _Transport:
    def __init__(self, responses: list[ProofReviewModelResponse], *, model: str = "test-model"):
        self.model = model
        self.responses = list(responses)
        self.requests = 0

    def review_proof_turn(self, request):
        self.requests += 1
        return self.responses.pop(0)


def _clean_response() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(action="review")


def _write_two_result_project(path: Path, *, lemma_proof: str, theorem_proof: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{lemma}}{{Lemma}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{lemma}}\label{{lem:base}}
$1=1$.
\end{{lemma}}
\begin{{proof}}
{lemma_proof}
\end{{proof}}
\begin{{theorem}}\label{{thm:main}}
$1=1$.
\end{{theorem}}
\begin{{proof}}
{theorem_proof}
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def _write_independent_project(path: Path, *, second_proof: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{theorem}}\label{{thm:first}}
$1=1$.
\end{{theorem}}
\begin{{proof}}
By reflexivity.
\end{{proof}}
\begin{{theorem}}\label{{thm:second}}
$2=2$.
\end{{theorem}}
\begin{{proof}}
{second_proof}
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def test_exact_review_input_is_reused_without_a_provider_request(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_independent_project(tex, second_proof="By reflexivity.")
    project = extract_project(tex)
    prepared = prepare_proof_review(project, project.unit("thm:first"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean_response()])

    first = run_cached_proof_review(prepared, transport, cache)
    second = run_cached_proof_review(prepared, transport, cache)

    assert first.cache.status == ReviewCacheStatus.RECHECKED
    assert first.cache.reason == ReviewCacheReason.RECHECK_NO_PRIOR_REVIEW
    assert second.cache.status == ReviewCacheStatus.REUSED
    assert second.cache.reason == ReviewCacheReason.CACHE_HIT_EXACT_PACKET
    assert second.cache.provider_requests_avoided == 1
    assert second.cache.estimated_input_tokens_avoided > 0
    assert transport.requests == 1


def test_unrelated_result_edit_does_not_invalidate_review(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_independent_project(tex, second_proof="By reflexivity.")
    first_project = extract_project(tex)
    first_prepared = prepare_proof_review(first_project, first_project.unit("thm:first"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean_response()])
    run_cached_proof_review(first_prepared, transport, cache)

    _write_independent_project(tex, second_proof="The equality is immediate.")
    second_project = extract_project(tex)
    second_prepared = prepare_proof_review(second_project, second_project.unit("thm:first"))
    second = run_cached_proof_review(second_prepared, transport, cache)

    assert first_prepared.document.fingerprint() == second_prepared.document.fingerprint()
    assert second.cache.status == ReviewCacheStatus.REUSED
    assert transport.requests == 1


def test_local_proof_edit_rechecks_only_the_changed_result(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_independent_project(tex, second_proof="By reflexivity.")
    first_project = extract_project(tex)
    first_prepared = prepare_proof_review(first_project, first_project.unit("thm:second"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean_response(), _clean_response()])
    run_cached_proof_review(first_prepared, transport, cache)

    _write_independent_project(tex, second_proof="Since both sides equal two, the claim follows.")
    second_project = extract_project(tex)
    second_prepared = prepare_proof_review(second_project, second_project.unit("thm:second"))
    second = run_cached_proof_review(second_prepared, transport, cache)

    assert first_prepared.document.fingerprint() != second_prepared.document.fingerprint()
    assert second.cache.status == ReviewCacheStatus.RECHECKED
    assert second.cache.reason == ReviewCacheReason.RECHECK_LOCAL_IR_CHANGED
    assert transport.requests == 2


def test_upstream_proof_edit_invalidates_downstream_dependency_slice(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    theorem_proof = r"By Lemma~\ref{lem:base}, the claim follows."
    _write_two_result_project(
        tex,
        lemma_proof="By reflexivity.",
        theorem_proof=theorem_proof,
    )
    first_project = extract_project(tex)
    assert first_project.dependency_graph.direct_dependency_ids("thm:main") == ["lem:base"]
    first_prepared = prepare_proof_review(first_project, first_project.unit("thm:main"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean_response(), _clean_response()])
    run_cached_proof_review(first_prepared, transport, cache)

    _write_two_result_project(
        tex,
        lemma_proof="Indeed, the two sides are identical.",
        theorem_proof=theorem_proof,
    )
    second_project = extract_project(tex)
    second_prepared = prepare_proof_review(second_project, second_project.unit("thm:main"))
    second = run_cached_proof_review(second_prepared, transport, cache)

    # The downstream model packet need not inline the upstream proof. The cache
    # still invalidates because mathematical dependency content changed.
    assert first_prepared.document.fingerprint() == second_prepared.document.fingerprint()
    assert second.cache.status == ReviewCacheStatus.RECHECKED
    assert second.cache.reason == ReviewCacheReason.RECHECK_UPSTREAM_DEPENDENCY_CHANGED
    assert transport.requests == 2


def test_model_change_is_review_contract_invalidation(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_independent_project(tex, second_proof="By reflexivity.")
    project = extract_project(tex)
    prepared = prepare_proof_review(project, project.unit("thm:first"))
    cache = ProofReviewCache(tmp_path / "cache")

    first_transport = _Transport([_clean_response()], model="model-a")
    second_transport = _Transport([_clean_response()], model="model-b")
    run_cached_proof_review(prepared, first_transport, cache)
    second = run_cached_proof_review, prepared, second_transport, cache)

    assert second.cache.status == ReviewCacheStatus.RECHECKED
    assert second.cache.reason == ReviewCacheReason.RECHECK_REVIEW_CONTRACT_CHANGED
    assert second_transport.requests == 1


def _synthetic_prepared(source_text: str, *, target_fingerprint: str = "target-v1") -> PreparedProofReview:
    document = LLMProofLanguage(
        result_identifier="thm:rescue",
        lines=(
            "THORN-PROOF 1",
            "T0 Q(a)",
            "C1 Q(a) <- ? @E1",
            "GOAL G0 T0: Q(a) | ctx - | open @E1",
        ),
        sources=(
            ProofLanguageSourceHandle(
                address="E1",
                ir_identifier="edge:E1",
                text=source_text,
            ),
        ),
    )
    provenance = ReviewCacheProvenance(
        result_identifier=document.result_identifier,
        target_content_fingerprint=target_fingerprint,
        packet_fingerprint=document.fingerprint(),
        dependency_snapshot=ReviewDependencySnapshot(
            edges_fingerprint=canonical_fingerprint([]),
        ),
    )
    return PreparedProofReview(
        state=cast(SemanticTransformationIR, object()),
        document=document,
        provenance=provenance,
    )


def _need_source() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="need_source",
        source_addresses=("E1",),
        review_items=(
            ProofReviewItem(
                id="RV1",
                kind="question",
                summary="Does the exact source justify this step?",
            ),
        ),
        source_review_item_ids=("RV1",),
    )


def _discharged_review() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="review",
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="discharged",
                explanation="The exact source settles the question.",
            ),
        ),
    )


def test_only_rescued_source_change_invalidates_prior_rescued_review(tmp_path: Path) -> None:
    cache = ProofReviewCache(tmp_path / "cache")
    first_transport = _Transport([_need_source(), _discharged_review()])
    first = run_cached_proof_review(
        _synthetic_prepared("By the cited lemma, Q(a)."),
        first_transport,
        cache,
     )
    assert first.review.rescue_turn is not None
    assert first_transport.requests == 2

    second_transport = _Transport([_need_source(), _discharged_review()])
    second = run_cached_proof_review(
        _synthetic_prepared("The cited lemma no longer establishes Q(a)."),
        second_transport,
        cache,
    )

    assert second.cache.status == ReviewCacheStatus.RECHECKED
    assert second.cache.reason == ReviewCacheReason.RECHECK_RESCUED_SOURCE_CHANGED
    assert second_transport.requests == 2


def test_non_material_target_change_can_reuse_identical_review_packet(tmp_path: Path) -> None:
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean_response()])
    run_cached_proof_review(
        _synthetic_prepared("Unused source text.", target_fingerprint="before"),
        transport,
        cache,
     )
    second = run_cached_proof_review(
        _synthetic_prepared("Unused source text.", target_fingerprint="after"),
        transport,
        cache,
     )

    assert second.cache.status == ReviewCacheStatus.REUSED
    assert second.cache.reason == ReviewCacheReason.CACHE_HIT_UNAFFECTED_DEPENDENCY_SLICE
    assert transport.requests == 1


def test_cache_summary_reports_avoided_provider_work() -> None:
    decisions = (
        # Reuse accounting is intentionally provider-neutral and estimated from
        # exact request envelopes rather than requiring a live tokenizer/API.
        _synthetic_decision(1, 120),
        _synthetic_decision(2, 350),
    )
    summary = ReviewCacheSummary.from_decisions(decisions)

    assert summary.review_units == 2
    assert summary.reused_units == 2
    assert summary.rechecked_units == 0
    assert summary.provider_requests_avoided == 3
    assert summary.estimated_input_tokens_avoided == 470


def _synthetic_decision(requests: int, tokens: int):
    from thorn.review_cache import ReviewCacheDecision

    return ReviewCacheDecision(
        result_identifier=f"thm:{requests}",
        status=ReviewCacheStatus.REUSED,
        reason=ReviewCacheReason.CACHE_HIT_EXACT_PACKET,
        cache_key=f"key-{requests}",
        provider_requests_avoided=requests,
        estimated_input_tokens_avoided=tokens,
    )
