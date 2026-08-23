from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from thorn.frontends import get_default_frontend
from thorn.latex import extract_project
from thorn.linguistic_statements import StatementScopeKind
from thorn.project_partiality import normalize_project_structure
from thorn.spacy_linguistic import SpacyLinguisticFrontend
from thorn.workspace import ProjectPositionLookup, WorkspaceResolution

_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
_RERANKER_REVISION = "c5f2b386de279a97c53a702dd5189d1c407160dc"

_SYNTHETIC_CASES = [
    {
        "id": "paraphrased-safe-region",
        "query": "Every admissible path remains inside the safe set.",
        "positive": "No trajectory starting in the permitted region can leave that region.",
        "negatives": [
            "A path may be drawn with several different parameterizations.",
            "The numerical example uses a square plotting window.",
            "The appendix records the software version used for the figures.",
        ],
    },
    {
        "id": "inverse-paraphrase",
        "query": "The transformation has a unique inverse.",
        "positive": "There is exactly one map that undoes this operation.",
        "negatives": [
            "The transformation is written in block matrix notation.",
            "The next example compares two transformations of equal dimension.",
            "The operation is evaluated from left to right in the table.",
        ],
    },
    {
        "id": "orthogonality-lexical-trap",
        "query": "The operator preserves orthogonality.",
        "positive": (
            "Whenever two inputs have zero inner product, their images also have zero "
            "inner product."
        ),
        "negatives": [
            "The operator preserves the order of the matrix entries.",
            "Orthogonality is illustrated by the grey lines in Figure 2.",
            "The matrix entries are listed in increasing order.",
        ],
    },
    {
        "id": "graph-language-paraphrase",
        "query": "Every finite tree with at least two vertices has at least two leaves.",
        "positive": (
            "A finite connected acyclic graph with more than one vertex contains at least "
            "two vertices of degree one."
        ),
        "negatives": [
            "The tree in the illustration has two colours of vertices.",
            "Finite graphs are stored as adjacency lists in the implementation.",
            "The following table contains degree statistics for several random graphs.",
        ],
    },
]


def _rank(scores: list[float]) -> list[int]:
    order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    ranks = [0] * len(scores)
    for rank, index in enumerate(order, start=1):
        ranks[index] = rank
    return ranks


def _semantic_scores(
    embedder: SentenceTransformer,
    reranker: CrossEncoder,
    query: str,
    documents: list[str],
) -> tuple[list[float], list[float]]:
    if not documents:
        return [], []
    vectors = embedder.encode(
        [query, *documents],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    query_vector = vectors[0]
    document_vectors = vectors[1:]
    embedding_scores = np.asarray(document_vectors @ query_vector).reshape(-1).tolist()
    reranker_scores = np.asarray(
        reranker.predict(
            [(query, document) for document in documents],
            show_progress_bar=False,
        )
    ).reshape(-1).tolist()
    return [float(score) for score in embedding_scores], [float(score) for score in reranker_scores]


def _synthetic_measurements(
    embedder: SentenceTransformer,
    reranker: CrossEncoder,
) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    for case in _SYNTHETIC_CASES:
        documents = [case["positive"], *case["negatives"]]
        embedding_scores, reranker_scores = _semantic_scores(
            embedder,
            reranker,
            case["query"],
            documents,
        )
        embedding_ranks = _rank(embedding_scores)
        reranker_ranks = _rank(reranker_scores)
        measurements.append(
            {
                "id": case["id"],
                "query": case["query"],
                "positive_rank": {
                    "embedding": embedding_ranks[0],
                    "reranker": reranker_ranks[0],
                },
                "documents": [
                    {
                        "label": "positive" if index == 0 else "distractor",
                        "text": document,
                        "embedding_score": embedding_scores[index],
                        "embedding_rank": embedding_ranks[index],
                        "reranker_score": reranker_scores[index],
                        "reranker_rank": reranker_ranks[index],
                    }
                    for index, document in enumerate(documents)
                ],
            }
        )
    return measurements


def _visible_project_statements(project: Any, target: str) -> tuple[list[Any], list[Any]]:
    inventory = project.linguistic_statements
    workspace = project.workspace
    if inventory is None or not inventory.complete:
        raise RuntimeError("linguistic statement inventory is unavailable or partial")
    if workspace is None or workspace.resolution != WorkspaceResolution.RESOLVED:
        raise RuntimeError("workspace facts are unavailable or partial")

    target_statements = [
        statement
        for statement in inventory.statements
        if statement.result_identifier == target
        and statement.scope_kind
        in {StatementScopeKind.RESULT_STATEMENT, StatementScopeKind.RESULT_PROOF}
    ]
    if not target_statements:
        raise RuntimeError(f"no target statements found for {target!r}")

    lookup = ProjectPositionLookup(workspace)
    target_positions = [
        position
        for statement in target_statements
        for position in lookup.positions(statement.source.file, statement.source.start_offset)
    ]
    if not target_positions:
        raise RuntimeError(f"no target project positions found for {target!r}")

    visible: list[Any] = []
    for statement in inventory.statements:
        if statement.scope_kind != StatementScopeKind.PROJECT:
            continue
        candidate_positions = lookup.positions(
            statement.source.file,
            statement.source.end_offset,
        )
        if not candidate_positions:
            continue
        if all(
            any(candidate < target_position for candidate in candidate_positions)
            for target_position in target_positions
        ):
            visible.append(statement)

    visible.sort(
        key=lambda statement: lookup.sort_key(
            statement.source.file,
            statement.source.start_offset,
        )
    )
    return target_statements, visible


def _case_measurement(
    case: dict[str, Any],
    embedder: SentenceTransformer,
    reranker: CrossEncoder,
) -> dict[str, Any]:
    source = Path(case["source"])
    parser = get_default_frontend()
    parsed = normalize_project_structure(parser.parse_project(source))
    project = extract_project(
        source,
        frontend=parser,
        linguistic_frontend=SpacyLinguisticFrontend(),
    )
    target_statements, candidates = _visible_project_statements(project, case["target"])

    query = " ".join(statement.text for statement in target_statements)
    documents = [statement.text for statement in candidates]
    embedding_scores, reranker_scores = _semantic_scores(
        embedder,
        reranker,
        query,
        documents,
    )
    embedding_ranks = _rank(embedding_scores)
    reranker_ranks = _rank(reranker_scores)

    target_terms = {
        term
        for statement in target_statements
        for term in statement.content_terms
    }
    required_needles = list(case.get("required_reachable_sources", []))
    irrelevant_needles = list(case.get("irrelevant_source_needles", []))

    rows: list[dict[str, Any]] = []
    for index, statement in enumerate(candidates):
        overlap = sorted(target_terms.intersection(statement.content_terms))
        required_matches = [needle for needle in required_needles if needle in statement.text]
        irrelevant_matches = [needle for needle in irrelevant_needles if needle in statement.text]
        rows.append(
            {
                "identifier": statement.identifier,
                "source": statement.source.model_dump(mode="json"),
                "text": statement.text,
                "paragraph_breaks": statement.text.count("\n\n"),
                "current_lexical_selector": {
                    "selected": bool(overlap),
                    "overlap_terms": overlap,
                },
                "labels": {
                    "required_needles": required_matches,
                    "irrelevant_needles": irrelevant_matches,
                },
                "embedding_score": embedding_scores[index],
                "embedding_rank": embedding_ranks[index],
                "reranker_score": reranker_scores[index],
                "reranker_rank": reranker_ranks[index],
            }
        )

    required_rows = [row for row in rows if row["labels"]["required_needles"]]
    irrelevant_rows = [row for row in rows if row["labels"]["irrelevant_needles"]]
    unresolved_required = [
        needle
        for needle in required_needles
        if not any(needle in row["text"] for row in rows)
    ]
    unresolved_irrelevant = [
        needle
        for needle in irrelevant_needles
        if not any(needle in row["text"] for row in rows)
    ]

    math_diagnostics = [
        {
            "file": math.span.file,
            "start_offset": math.span.start_offset,
            "end_offset": math.span.end_offset,
            "terminal_punctuation": (
                math.terminal_punctuation.text(file.raw)
                if math.terminal_punctuation is not None
                else None
            ),
        }
        for file in parsed.files
        for math in file.math
        if math.span.start_offset < max(
            statement.source.start_offset
            for statement in target_statements
            if statement.source.file == file.path
        )
    ]

    return {
        "id": case["id"],
        "source": case["source"],
        "target": case["target"],
        "query": query,
        "candidate_count": len(rows),
        "required_candidate_ranks": [
            {
                "needle": needle,
                "embedding_rank": row["embedding_rank"],
                "reranker_rank": row["reranker_rank"],
            }
            for row in required_rows
            for needle in row["labels"]["required_needles"]
        ],
        "irrelevant_candidate_ranks": [
            {
                "needle": needle,
                "embedding_rank": row["embedding_rank"],
                "reranker_rank": row["reranker_rank"],
                "paragraph_breaks": row["paragraph_breaks"],
            }
            for row in irrelevant_rows
            for needle in row["labels"]["irrelevant_needles"]
        ],
        "unresolved_required_needles": unresolved_required,
        "unresolved_irrelevant_needles": unresolved_irrelevant,
        "candidates": rows,
        "math_terminal_punctuation": math_diagnostics,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    embedder = SentenceTransformer(
        _EMBEDDING_MODEL,
        revision=_EMBEDDING_REVISION,
    )
    reranker = CrossEncoder(
        _RERANKER_MODEL,
        revision=_RERANKER_REVISION,
    )

    frozen = [
        _case_measurement(case, embedder, reranker)
        for case in manifest["cases"]
    ]
    synthetic = _synthetic_measurements(embedder, reranker)
    report = {
        "format": "thorn-context-retrieval-spike/1",
        "issue": 198,
        "status": "measurement_complete",
        "provider_call_made": False,
        "production_dependency_changed": False,
        "retrieval_identity": {
            "sentence_transformers": "5.7.0",
            "embedding_model": _EMBEDDING_MODEL,
            "embedding_revision": _EMBEDDING_REVISION,
            "reranker_model": _RERANKER_MODEL,
            "reranker_revision": _RERANKER_REVISION,
        },
        "frozen_cases": frozen,
        "synthetic_cases": synthetic,
        "summary": {
            "synthetic_embedding_rank1": all(
                case["positive_rank"]["embedding"] == 1 for case in synthetic
            ),
            "synthetic_reranker_rank1": all(
                case["positive_rank"]["reranker"] == 1 for case in synthetic
            ),
            "frozen_required_resolved": all(
                not case["unresolved_required_needles"] for case in frozen
            ),
            "frozen_irrelevant_resolved": all(
                not case["unresolved_irrelevant_needles"] for case in frozen
            ),
        },
    }
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
