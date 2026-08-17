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
    ReviewDependencySnapshot,
    canonical_fingerprint,
)
from thorn.review_workflow import PreparedProofReview, prepare_proof_review, run_cached_proof_review
from thorn.semantic_transformations import SemanticTransformationIR


class _Transport:
    def __init__(self, responses: list[ProofReviewModelResponse], *, model: str = "test-model"):
        self.model = model
        self.responses = list(responses)
        self.requests = 0

    def review_proof_turn(self, request):
        self.requests += 1
        return self.responses.pop(0)


def _clean() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(action="review")


def _independent(path: Path, second_proof: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{theorem}}\label{{thm:first}}$1=1$.\end{{theorem}}
\begin{{proof}}By reflexivity.\end{{proof}}
\begin{{theorem}}\label{{thm:second}}$2=2$.\end{{theorem}}
\begin{{proof}}{second_proof}\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def _dependent(path: Path, lemma_proof: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{lemma}}{{Lemma}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{lemma}}\label{{lem:base}}$1=1$.\end{{lemma}}
\begin{{proof}}{lemma_proof}\end{{proof}}
\begin{{theorem}}\label{{thm:main}}$1=1$.\end{{theorem}}
\begin{{proof}}By Lemma~\ref{{lem:base}}, the claim follows.\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def test_exact_input_reuses_without_provider_request(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _independent(tex, "By reflexivity.")
    project = extract_project(tex)
    prepared = prepare_proof_review(project, project.unit("thm:first"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean()])

    first = run_cached_proof_review(prepared, transport, cache)
    second = run_cached_proof_review(prepared, transport, cache)

    assert first.cache.reason == ReviewCacheReason.RECHECK_NO_PRIOR_REVIEW
    assert second.cache.status == ReviewCacheStatus.REUSED
    assert second.cache.reason == ReviewCacheReason.CACHE_HIT_EXACT_PACKET
    assert second.cache.provider_requests_avoided == 1
    assert second.cache.estimated_input_tokens_avoided > 0
    assert transport.requests == 1


def test_unrelated_edit_is_reused_but_local_proof_edit_rechecks(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _independent(tex, "By reflexivity.")
    first_project = extract_project(tex)
    first = prepare_proof_review(first_project, first_project.unit("thm:first"))
    second_target = prepare_proof_review(first_project, first_project.unit("thm:second"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean(), _clean(), _clean()])
    run_cached_proof_review(first, transport, cache)
    run_cached_proof_review(second_target, transport, cache)

    _independent(tex, "Since both sides equal two, the claim follows.")
    second_project = extract_project(tex)
    unchanged = prepare_proof_review(second_project, second_project.unit("thm:first"))
    changed = prepare_proof_review(second_project, second_project.unit("thm:second"))
    unchanged_result = run_cached_proof_review(unchanged, transport, cache)
    changed_result = run_cached_proof_review(changed, transport, cache)

    assert first.document.fingerprint() == unchanged.document.fingerprint()
    assert unchanged_result.cache.status == ReviewCacheStatus.REUSED
    assert changed_result.cache.status == ReviewCacheStatus.RECHECKED
    assert changed_result.cache.reason == ReviewCacheReason.RECHECK_LOCAL_IR_CHANGED
    assert transport.requests == 3


def test_upstream_proof_change_invalidates_identical_downstream_packet(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _dependent(tex, "By reflexivity.")
    first_project = extract_project(tex)
    assert first_project.dependency_graph.direct_dependency_ids("thm:main") == ["lem:base"]
    first = prepare_proof_review(first_project, first_project.unit("thm:main"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean(), _clean()])
    run_cached_proof_review(first, transport, cache)

    _dependent(tex, "Indeed, the two sides are identical.")
    second_project = extract_project(tex)
    second = prepare_proof_review(second_project, second_project.unit("thm:main"))
    result = run_cached_proof_review(second, transport, cache)

    assert first.document.fingerprint() == second.document.fingerprint()
    assert result.cache.reason == ReviewCacheReason.RECHECK_UPSTREAM_DEPENDENCY_CHANGED
    assert transport.requests == 2


def test_model_change_invalidates_review_contract(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _independent(tex, "By reflexivity.")
    project = extract_project(tex)
    prepared = prepare_proof_review(project, project.unit("thm:first"))
    cache = ProofReviewCache(tmp_path / "cache")

    run_cached_proof_review(prepared, _Transport([_clean()], model="model-a"), cache)
    transport = _Transport([_clean()], model="model-b")
    result = run_cached_proof_review(prepared, transport, cache)

    assert result.cache.reason == ReviewCacheReason.RECHECK_REVIEW_CONTRACT_CHANGED
    assert transport.requests == 1


def _synthetic(source_text: str, *, target_fingerprint: str = "target") -> PreparedProofReview:
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
            ProofReviewItem(id="RV1", kind="question", summary="Check the exact source."),
        ),
        source_review_item_ids=("RV1",),
    )


def _discharged() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(
        action="review",
        dispositions=(
            ProofReviewDisposition(
                item_id="RV1",
                status="discharged",
                explanation="The source settles the question.",
            ),
        ),
    )


def test_rescued_source_change_rechecks_even_when_initial_packet_is_identical(
    tmp_path: Path,
) -> None:
    cache = ProofReviewCache(tmp_path / "cache")
    first_transport = _Transport([_need_source(), _discharged()])
    run_cached_proof_review(_synthetic("By the lemma, Q(a)."), first_transport, cache)

    second_transport = _Transport([_need_source(), _discharged()])
    result = run_cached_proof_review(
        _synthetic("The lemma no longer establishes Q(a)."),
        second_transport,
        cache,
    )

    assert result.cache.reason == ReviewCacheReason.RECHECK_RESCUED_SOURCE_CHANGED
    assert second_transport.requests == 2


def test_non_material_target_change_reuses_identical_packet(tmp_path: Path) -> None:
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean()])
    run_cached_proof_review(_synthetic("Unused source.", target_fingerprint="before"), transport, cache)
    result = run_cached_proof_review(
        _synthetic("Unused source.", target_fingerprint="after"),
        transport,
        cache,
    )

    assert result.cache.reason == ReviewCacheReason.CACHE_HIT_UNAFFECTED_DEPENDENCY_SLICE
    assert transport.requests == 1
