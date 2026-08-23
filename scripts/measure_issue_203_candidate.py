#!/usr/bin/env python3
"""Keyless #203 advisory-retrieval and legacy/candidate differential evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from thorn.candidate_review import prepare_candidate_proof_review
from thorn.context_retrieval import (
    ContextCandidate,
    ContextRank,
    ContextRanker,
    build_result_context_pools,
    rank_context_pool,
)
from thorn.frontends import get_frontend
from thorn.latex import extract_project
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review
from thorn.spacy_linguistic import SpacyLinguisticFrontend

ROOT = Path(__file__).resolve().parents[1]
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
RERANKER_REVISION = "c5f2b386de279a97c53a702dd5189d1c407160dc"
DEFAULT_BOUND = 8


class _EmbeddingRanker(ContextRanker):
    name = f"{EMBEDDING_MODEL}@{EMBEDDING_REVISION}"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_REVISION)

    def rank(
        self, query: str, candidates: tuple[ContextCandidate, ...]
    ) -> tuple[ContextRank, ...]:
        if not candidates:
            return ()
        vectors = self._model.encode(
            [query, *(item.text for item in candidates)],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        scores = vectors[1:] @ vectors[0]
        ordered = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: (-float(item[1]), item[0].identifier),
        )
        return tuple(
            ContextRank(candidate_identifier=item.identifier, score=float(score))
            for item, score in ordered
        )


class _CrossEncoderRanker(ContextRanker):
    name = f"{RERANKER_MODEL}@{RERANKER_REVISION}"

    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(RERANKER_MODEL, revision=RERANKER_REVISION)

    def rank(
        self, query: str, candidates: tuple[ContextCandidate, ...]
    ) -> tuple[ContextRank, ...]:
        if not candidates:
            return ()
        scores = self._model.predict(
            [(query, item.text) for item in candidates],
            convert_to_numpy=True,
        )
        ordered = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: (-float(item[1]), item[0].identifier),
        )
        return tuple(
            ContextRank(candidate_identifier=item.identifier, score=float(score))
            for item, score in ordered
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: str) -> str:
    value = Path(path)
    try:
        return value.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(value)


def _source_key(source: Any) -> tuple[str, int, int, str, str]:
    span = source.source_span
    assert span is not None
    return (
        _relative(span.file),
        span.start_offset,
        span.end_offset,
        source.text,
        source.ir_identifier,
    )


def _document_sources(document: Any) -> set[tuple[str, int, int, str, str]]:
    return {
        _source_key(source)
        for source in document.sources
        if source.source_span is not None
    }


def _needle_measurements(
    ranking: Any,
    bounded: Any,
    needles: list[str],
) -> list[dict[str, Any]]:
    bounded_ids = {item.candidate.identifier for item in bounded.candidates}
    result: list[dict[str, Any]] = []
    for needle in needles:
        matches = [item for item in ranking.ranking if needle in item.candidate.text]
        result.append(
            {
                "needle": needle,
                "match_count": len(matches),
                "best_rank": min((item.rank for item in matches), default=None),
                "bounded_reachable": any(
                    item.candidate.identifier in bounded_ids for item in matches
                ),
                "matches": [
                    {
                        "rank": item.rank,
                        "score": item.score,
                        "candidate_identifier": item.candidate.identifier,
                        "occurrence_id": item.candidate.occurrence_id,
                        "source": {
                            **item.candidate.source.model_dump(mode="json"),
                            "file": _relative(item.candidate.source.file),
                        },
                        "text": item.candidate.text,
                    }
                    for item in matches
                ],
            }
        )
    return result


def _case(
    case: dict[str, Any],
    rankers: list[ContextRanker],
    bound: int,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    source = ROOT / case["source"]
    project = extract_project(
        source,
        frontend=get_frontend("tree-sitter"),
        linguistic_frontend=SpacyLinguisticFrontend(model_name="en_core_web_sm"),
    )
    target = case["target"]
    pools = build_result_context_pools(project, target)
    required = list(
        case.get(
            "required_source_needles",
            case.get("required_reachable_sources", []),
        )
    )
    irrelevant = list(case.get("irrelevant_source_needles", []))

    inventory = project.linguistic_statements
    if inventory is None or not inventory.complete:
        errors.append(f"{case['id']}: statement inventory unavailable or partial")
    for needle in required:
        if not any(
            needle in candidate.text
            for pool in pools
            for candidate in pool.candidates
        ):
            errors.append(
                f"{case['id']}: required source absent from eligible pool: {needle!r}"
            )

    unit = project.unit(target)
    legacy = prepare_proof_review(
        project,
        unit,
        include_advisory_context=False,
    )
    measurements: list[dict[str, Any]] = []
    for ranker in rankers:
        proposals = [rank_context_pool(pool, ranker) for pool in pools]
        ranked_pools: list[dict[str, Any]] = []
        for proposal in proposals:
            bounded = proposal.bounded(bound)
            candidate = prepare_candidate_proof_review(project, unit, bounded)
            state_equal = (
                candidate.state.model_dump(mode="json")
                == legacy.state.model_dump(mode="json")
            )
            if not state_equal:
                errors.append(
                    f"{case['id']}: advisory retrieval changed canonical mathematical "
                    f"state for {ranker.name}"
                )

            advertised = advertised_source_addresses(candidate.document)
            unknown_advertised = [
                address
                for address in advertised
                if all(source.address != address for source in candidate.document.sources)
            ]
            if unknown_advertised:
                errors.append(
                    f"{case['id']}: advertised source handles missing from closed-world "
                    f"inventory: {unknown_advertised}"
                )

            expected_advisory_ids = {
                (
                    f"advisory-context:{item.candidate.occurrence_id}:"
                    f"{item.candidate.statement_identifier}"
                )
                for item in bounded.candidates
            }
            observed_advisory_ids = {
                source.ir_identifier
                for source in candidate.document.sources
                if source.ir_identifier.startswith("advisory-context:")
            }
            missing_advisory_ids = sorted(
                expected_advisory_ids.difference(observed_advisory_ids)
            )
            if missing_advisory_ids:
                errors.append(
                    f"{case['id']}: advisory occurrence identity lost for {ranker.name}: "
                    f"{missing_advisory_ids}"
                )

            legacy_sources = _document_sources(legacy.document)
            candidate_sources = _document_sources(candidate.document)
            ranked_pools.append(
                {
                    "target_occurrence_id": proposal.target_occurrence_id,
                    "status": proposal.status.value,
                    "partial_reason": proposal.partial_reason,
                    "total_candidates": len(proposal.ranking),
                    "bound": bound,
                    "truncated": bounded.truncated,
                    "required": _needle_measurements(proposal, bounded, required),
                    "irrelevant_controls": _needle_measurements(
                        proposal,
                        bounded,
                        irrelevant,
                    ),
                    "top": [
                        {
                            "rank": item.rank,
                            "score": item.score,
                            "candidate_identifier": item.candidate.identifier,
                            "occurrence_id": item.candidate.occurrence_id,
                            "source": {
                                **item.candidate.source.model_dump(mode="json"),
                                "file": _relative(item.candidate.source.file),
                            },
                            "text": item.candidate.text,
                        }
                        for item in bounded.candidates
                    ],
                    "differential": {
                        "canonical_mathematical_state": (
                            "agreement" if state_equal else "definite-disagreement"
                        ),
                        "legacy_only_source": sorted(
                            legacy_sources - candidate_sources
                        ),
                        "candidate_only_advisory_source": sorted(
                            candidate_sources - legacy_sources
                        ),
                        "source_provenance_loss": bool(
                            legacy_sources - candidate_sources
                        ),
                    },
                }
            )
        measurements.append({"ranker": ranker.name, "pools": ranked_pools})

    return (
        {
            "id": case["id"],
            "class": case.get("class", "issue-198-frozen"),
            "source": case["source"],
            "source_sha256": _sha256(source),
            "target": target,
            "statement_inventory_complete": bool(
                inventory is not None and inventory.complete
            ),
            "statement_count": len(inventory.statements) if inventory is not None else 0,
            "target_occurrence_count": len(pools),
            "measurements": measurements,
        },
        errors,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bound", type=int, default=DEFAULT_BOUND)
    args = parser.parse_args()

    rankers: list[ContextRanker] = [_EmbeddingRanker(), _CrossEncoderRanker()]
    cases: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    errors: list[str] = []
    for manifest_path in args.manifest:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifests.append(
            {
                "path": _relative(str(manifest_path)),
                "sha256": _sha256(manifest_path),
                "format": manifest.get("format", "issue-198-frozen"),
            }
        )
        for case in manifest["cases"]:
            try:
                evidence, case_errors = _case(case, rankers, args.bound)
            except Exception as exc:
                evidence = {
                    "id": case.get("id", "unknown"),
                    "source": case.get("source"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
                case_errors = [
                    f"{case.get('id', 'unknown')}: {type(exc).__name__}: {exc}"
                ]
            cases.append(evidence)
            errors.extend(case_errors)

    report = {
        "format": "thorn-issue-203-candidate-evidence/1",
        "issue": 203,
        "provider_call_made": False,
        "retrieval_authority": False,
        "bounded_candidate_semantics": "truncation-not-irrelevance",
        "bound": args.bound,
        "models": [ranker.name for ranker in rankers],
        "manifests": manifests,
        "cases": cases,
        "status": "pass" if not errors else "blocked",
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
