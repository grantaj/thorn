#!/usr/bin/env python3
"""Differential #203 evidence for ablating hand-written prose interpretation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from measure_issue_203_candidate import (
    DEFAULT_BOUND,
    ROOT,
    _CrossEncoderRanker,
    _document_sources,
    _EmbeddingRanker,
    _needle_measurements,
    _relative,
    _sha256,
)

from thorn.candidate_review import prepare_candidate_proof_review
from thorn.context_retrieval import ContextRanker, build_result_context_pools, rank_context_pool
from thorn.frontends import get_frontend
from thorn.latex import extract_project
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review
from thorn.semantic_dependencies import result_project_symbol_dependency_ids
from thorn.spacy_linguistic import SpacyLinguisticFrontend


def _relative_span(span: Any) -> dict[str, Any]:
    payload = span.model_dump(mode="json")
    payload["file"] = _relative(span.file)
    return payload


def _project_symbol_record(project: Any, identifier: str) -> dict[str, Any]:
    symbol = project.symbol_table.symbol(identifier)
    return {
        "identifier": symbol.identifier,
        "name": symbol.name,
        "role": symbol.role.value,
        "introduction_kind": symbol.introduction_kind.value,
        "source": _relative_span(symbol.source),
        "introduction_source": _relative_span(symbol.introduction_source),
    }


def _target_project_dependencies(project: Any, target: str) -> list[dict[str, Any]]:
    return [
        _project_symbol_record(project, identifier)
        for identifier in result_project_symbol_dependency_ids(project, target)
    ]


def _dependency_graph_snapshot(project: Any) -> dict[str, Any]:
    return {
        "nodes": [node.model_dump(mode="json") for node in project.dependency_graph.nodes],
        "edges": [edge.model_dump(mode="json") for edge in project.dependency_graph.edges],
    }


def _generic_evidence(project: Any) -> dict[str, Any]:
    """Facts that must survive removal of the legacy English interpretation layer."""

    statements = project.linguistic_statements
    workspace = project.workspace
    return {
        "statements": (
            statements.model_dump(mode="json") if statements is not None else None
        ),
        "workspace": workspace.model_dump(mode="json") if workspace is not None else None,
        "symbol_candidates": [
            candidate.model_dump(mode="json")
            for candidate in project.symbol_table.candidates
        ],
        "scopes": [scope.model_dump(mode="json") for scope in project.symbol_table.scopes],
        "proof_support_graph": project.proof_support_graph.model_dump(mode="json"),
    }


def _legacy_declaration_count(project: Any) -> int:
    declarations = project.prose_declarations
    return len(declarations.candidates) if declarations is not None else 0


def _classify(
    *,
    state_equal: bool,
    legacy_dependencies: list[dict[str, Any]],
    candidate_dependencies: list[dict[str, Any]],
) -> str:
    if state_equal:
        return "agreement"
    legacy_ids = {item["identifier"] for item in legacy_dependencies}
    candidate_ids = {item["identifier"] for item in candidate_dependencies}
    if candidate_ids - legacy_ids:
        return "candidate-definite-legacy-ambiguous"
    if legacy_ids - candidate_ids:
        return "legacy-definite-candidate-unresolved"
    return "canonical-state-difference-without-project-dependency-change"


def _case(
    case: dict[str, Any],
    rankers: list[ContextRanker],
    bound: int,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    source = ROOT / case["source"]
    frontend = get_frontend("tree-sitter")
    linguistic = SpacyLinguisticFrontend(model_name="en_core_web_sm")

    legacy_project = extract_project(
        source,
        frontend=frontend,
        linguistic_frontend=linguistic,
        legacy_prose_semantic_context=True,
    )
    candidate_project = extract_project(
        source,
        frontend=frontend,
        linguistic_frontend=linguistic,
        legacy_prose_semantic_context=False,
    )
    target = case["target"]

    generic_evidence_equal = _generic_evidence(legacy_project) == _generic_evidence(
        candidate_project
    )
    if not generic_evidence_equal:
        errors.append(
            f"{case['id']}: declaration-grammar ablation changed generic source/NLP/workspace evidence"
        )
    if candidate_project.prose_declarations is not None:
        errors.append(
            f"{case['id']}: candidate still materialized the legacy prose declaration inventory"
        )

    dependency_graph_equal = _dependency_graph_snapshot(
        legacy_project
    ) == _dependency_graph_snapshot(candidate_project)
    if not dependency_graph_equal:
        errors.append(
            f"{case['id']}: declaration-grammar ablation changed structural theorem dependency graph"
        )

    pools = build_result_context_pools(candidate_project, target)
    required = list(
        case.get(
            "required_source_needles",
            case.get("required_reachable_sources", []),
        )
    )
    irrelevant = list(case.get("irrelevant_source_needles", []))
    for needle in required:
        if not any(
            needle in candidate.text
            for pool in pools
            for candidate in pool.candidates
        ):
            errors.append(
                f"{case['id']}: required source absent from ablated candidate pool: {needle!r}"
            )

    legacy_unit = legacy_project.unit(target)
    candidate_unit = candidate_project.unit(target)
    legacy_review = prepare_proof_review(legacy_project, legacy_unit)
    legacy_dependencies = _target_project_dependencies(legacy_project, target)
    candidate_dependencies = _target_project_dependencies(candidate_project, target)

    legacy_ids = {item["identifier"] for item in legacy_dependencies}
    candidate_ids = {item["identifier"] for item in candidate_dependencies}
    increased_certainty = sorted(candidate_ids - legacy_ids)
    if increased_certainty:
        errors.append(
            f"{case['id']}: ablation introduced new definite project dependencies: "
            f"{increased_certainty}"
        )

    measurements: list[dict[str, Any]] = []
    for ranker in rankers:
        ranked_pools: list[dict[str, Any]] = []
        for pool in pools:
            proposal = rank_context_pool(pool, ranker)
            bounded = proposal.bounded(bound)
            candidate_review = prepare_candidate_proof_review(
                candidate_project,
                candidate_unit,
                bounded,
            )
            advertised = advertised_source_addresses(candidate_review.document)
            unknown_advertised = [
                address
                for address in advertised
                if all(
                    source_handle.address != address
                    for source_handle in candidate_review.document.sources
                )
            ]
            if unknown_advertised:
                errors.append(
                    f"{case['id']}: candidate advertised unknown source handles: "
                    f"{unknown_advertised}"
                )

            legacy_sources = _document_sources(legacy_review.document)
            candidate_sources = _document_sources(candidate_review.document)
            lost_sources = sorted(legacy_sources - candidate_sources)
            if lost_sources:
                errors.append(
                    f"{case['id']}: source/provenance loss after declaration-grammar ablation under "
                    f"{ranker.name}: {lost_sources}"
                )

            state_equal = (
                legacy_review.state.model_dump(mode="json")
                == candidate_review.state.model_dump(mode="json")
            )
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
                    "differential": {
                        "classification": _classify(
                            state_equal=state_equal,
                            legacy_dependencies=legacy_dependencies,
                            candidate_dependencies=candidate_dependencies,
                        ),
                        "canonical_state_equal": state_equal,
                        "structural_dependency_graph_equal": dependency_graph_equal,
                        "generic_evidence_equal": generic_evidence_equal,
                        "legacy_project_dependencies": legacy_dependencies,
                        "candidate_project_dependencies": candidate_dependencies,
                        "legacy_only_project_dependency_ids": sorted(
                            legacy_ids - candidate_ids
                        ),
                        "candidate_only_project_dependency_ids": increased_certainty,
                        "legacy_only_source": lost_sources,
                        "candidate_only_advisory_source": sorted(
                            candidate_sources - legacy_sources
                        ),
                        "source_provenance_loss": bool(lost_sources),
                    },
                }
            )
        measurements.append({"ranker": ranker.name, "pools": ranked_pools})

    statements = candidate_project.linguistic_statements
    return (
        {
            "id": case["id"],
            "class": case.get("class", "issue-198-frozen"),
            "source": case["source"],
            "source_sha256": _sha256(source),
            "target": target,
            "statement_inventory_complete": bool(
                statements is not None and statements.complete
            ),
            "statement_count": len(statements.statements) if statements is not None else 0,
            "target_occurrence_count": len(pools),
            "legacy_prose_declaration_count": _legacy_declaration_count(legacy_project),
            "candidate_prose_declaration_inventory": candidate_project.prose_declarations,
            "legacy_project_dependency_count": len(legacy_dependencies),
            "candidate_project_dependency_count": len(candidate_dependencies),
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
        "format": "thorn-issue-203-prose-declaration-ablation/1",
        "issue": 203,
        "ablation": "legacy-prose-declaration-grammar-and-semantic-authority",
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
