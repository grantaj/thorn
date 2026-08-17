from __future__ import annotations

from pathlib import Path

from thorn.latex import extract_project
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    build_proof_review_turn,
)
from thorn.providers.replay import RecordedExchange, RecordedUsage, ReplayProvider
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.review_cache import ProofReviewCache, ReviewCacheReason, ReviewCacheStatus
from thorn.review_workflow import (
    prepare_proof_review,
    run_cached_proof_review,
    run_incremental_proof_reviews,
)


class _Transport:
    def __init__(self, responses: list[ProofReviewModelResponse]) -> None:
        self.model = "test-model"
        self.responses = list(responses)
        self.requests = 0

    def review_proof_turn(self, request):
        self.requests += 1
        return self.responses.pop(0)


def _clean() -> ProofReviewModelResponse:
    return ProofReviewModelResponse(action="review")


def _write_edge_project(path: Path, dependency_label: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{lemma}}{{Lemma}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{lemma}}\label{{lem:a}}$1=1$.\end{{lemma}}
\begin{{proof}}By reflexivity.\end{{proof}}
\begin{{lemma}}\label{{lem:b}}$1=1$.\end{{lemma}}
\begin{{proof}}By reflexivity.\end{{proof}}
\begin{{theorem}}\label{{thm:main}}$1=1$.\end{{theorem}}
\begin{{proof}}By Lemma~\ref{{{dependency_label}}}, the claim follows.\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def _write_exposition_project(path: Path, exposition: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
{exposition}
\begin{{theorem}}\label{{thm:main}}$1=1$.\end{{theorem}}
\begin{{proof}}By reflexivity.\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def _write_independent_project(path: Path) -> None:
    path.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:first}$1=1$.\end{theorem}
\begin{proof}By reflexivity.\end{proof}
\begin{theorem}\label{thm:second}$2=2$.\end{theorem}
\begin{proof}By reflexivity.\end{proof}
\end{document}
""",
        encoding="utf-8",
    )


def test_dependency_edge_change_has_explicit_invalidation_reason(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_edge_project(tex, "lem:a")
    first_project = extract_project(tex)
    first = prepare_proof_review(first_project, first_project.unit("thm:main"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean(), _clean()])
    run_cached_proof_review(first, transport, cache)

    _write_edge_project(tex, "lem:b")
    second_project = extract_project(tex)
    second = prepare_proof_review(second_project, second_project.unit("thm:main"))
    result = run_cached_proof_review(second, transport, cache)

    assert result.cache.status == ReviewCacheStatus.RECHECKED
    assert result.cache.reason == ReviewCacheReason.RECHECK_DEPENDENCY_EDGE_CHANGED
    assert transport.requests == 2


def test_non_load_bearing_exposition_edit_preserves_review(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_exposition_project(tex, "This paragraph introduces the paper.")
    first_project = extract_project(tex)
    first = prepare_proof_review(first_project, first_project.unit("thm:main"))
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean()])
    run_cached_proof_review(first, transport, cache)

    _write_exposition_project(tex, "This rewritten paragraph is still only exposition.")
    second_project = extract_project(tex)
    second = prepare_proof_review(second_project, second_project.unit("thm:main"))
    result = run_cached_proof_review(second, transport, cache)

    assert first.document.fingerprint() == second.document.fingerprint()
    assert result.cache.status == ReviewCacheStatus.REUSED
    assert transport.requests == 1


def test_exact_replay_and_semantic_cache_reuse_are_distinct(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_exposition_project(tex, "Replay fixture.")
    project = extract_project(tex)
    prepared = prepare_proof_review(project, project.unit("thm:main"))
    model = "test-model"
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=prepared.document))
    envelope = proof_review_request_envelope(turn, model)
    response = _clean()

    recordings = tmp_path / "recordings"
    recordings.mkdir()
    exchange = RecordedExchange(
        fingerprint=envelope.fingerprint(),
        request=envelope,
        response=response.model_dump(mode="json"),
        usage=RecordedUsage(requests=1, input_tokens=100, output_tokens=10, total_tokens=110),
    )
    (recordings / f"{envelope.fingerprint()}.json").write_text(
        exchange.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )

    replay = ReplayProvider(model=model, directory=recordings)
    cache = ProofReviewCache(tmp_path / "cache")
    first = run_cached_proof_review(prepared, replay, cache)
    second = run_cached_proof_review(prepared, replay, cache)

    assert first.cache.status == ReviewCacheStatus.RECHECKED
    assert first.cache.reason == ReviewCacheReason.RECHECK_NO_PRIOR_REVIEW
    assert replay.replay_hits == 1
    assert second.cache.status == ReviewCacheStatus.REUSED
    assert replay.replay_hits == 1


def test_incremental_run_measures_reused_units_and_avoided_work(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    _write_independent_project(tex)
    project = extract_project(tex)
    cache = ProofReviewCache(tmp_path / "cache")
    transport = _Transport([_clean(), _clean()])

    first = run_incremental_proof_reviews(project, project.units, transport, cache)
    second = run_incremental_proof_reviews(project, project.units, transport, cache)

    assert first.summary.rechecked_units == 2
    assert first.summary.reused_units == 0
    assert second.summary.review_units == 2
    assert second.summary.reused_units == 2
    assert second.summary.rechecked_units == 0
    assert second.summary.provider_requests_avoided == 2
    assert second.summary.estimated_input_tokens_avoided > 0
    assert transport.requests == 2
