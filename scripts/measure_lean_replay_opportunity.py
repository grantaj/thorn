from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.lean_export import project_lean
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import build_semantic_transformation_ir
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend

_SCHEMA = "thorn-lean-replay-opportunity/1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory canonical proof state relevant to issue #115 without performing "
            "model calls or inventing formalisation context."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval/lean-replay-opportunity-public.json"),
    )
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="skip the normal local spaCy frontend; intended for degraded/keyless smoke checks",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--thorn-revision",
        help="revision label to record in the inventory (for example GITHUB_SHA)",
    )
    return parser


def _load_manifest(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Lean replay opportunity manifest must be a JSON object")
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Lean replay opportunity manifest must contain a non-empty cases list")
    return raw


def _source_range(source: Any) -> dict[str, Any] | None:
    if source is None:
        return None
    return {
        "file": source.file,
        "start_line": source.start_line,
        "end_line": source.end_line,
    }


def _transformation_record(ir: Any, transformation: Any) -> dict[str, Any]:
    supports = []
    for address in transformation.support_atom_addresses:
        atom = ir.support_atom(address)
        supports.append(
            {
                "address": atom.address,
                "kind": atom.kind.value,
                "status": atom.status.value,
                "referenced_result_identifier": atom.referenced_result_identifier,
                "proposition_address": atom.proposition_address,
                "source_address_count": len(atom.source_addresses),
            }
        )

    obligations = []
    for address in transformation.obligation_addresses:
        obligation = ir.obligation(address)
        obligations.append(
            {
                "address": obligation.address,
                "status": obligation.status.value,
                "has_expected_proposition": obligation.expected is not None,
                "local_context_count": len(obligation.local_context),
                "satisfied_by_count": len(obligation.satisfied_by),
                "source_address_count": len(obligation.source_addresses),
            }
        )

    return {
        "address": transformation.address,
        "kind": transformation.kind.value,
        "status": transformation.status.value,
        "step_addresses": list(transformation.step_addresses),
        "supports": supports,
        "parameter_bindings": [
            {
                "status": binding.status.value,
                "has_argument": binding.argument_ref is not None,
            }
            for binding in transformation.parameter_bindings
        ],
        "obligations": obligations,
        "has_rewrite_from": transformation.rewrite_from_ref is not None,
        "has_rewrite_to": transformation.rewrite_to_ref is not None,
        "replacement_site_count": len(transformation.replacement_sites),
        "source_address_count": len(transformation.source_addresses),
        "opaque_source_address_count": len(transformation.opaque_source_addresses),
    }


def _case_record(root: Path, spec: dict[str, Any], *, structural_only: bool) -> dict[str, Any]:
    relative_path = Path(str(spec["file"]))
    path = root / relative_path
    linguistic = None if structural_only else SpacyLinguisticFrontend()
    project = extract_project(path, linguistic_frontend=linguistic)
    result_identifier = str(spec["result"])
    unit = project.unit(result_identifier)

    context = build_result_review_context(project, result_identifier)
    if not context.items:
        raise ValueError(f"no review context for {relative_path}:{result_identifier}")
    request = build_semantic_review_request(context.items[0])
    semantic = build_semantic_transformation_ir(
        unit,
        request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    export = project_lean(semantic)

    transformation_counts = Counter(
        (item.kind.value, item.status.value) for item in semantic.transformations
    )
    obligation_counts = Counter(item.status.value for item in semantic.obligations)

    return {
        "id": spec["id"],
        "lane": spec.get("lane", "public"),
        "domain": spec.get("domain"),
        "role": spec.get("role"),
        "file": relative_path.as_posix(),
        "result_identifier": result_identifier,
        "environment": unit.environment,
        "statement_range": _source_range(unit.statement_range),
        "proof_range": _source_range(unit.proof_range),
        "referenced_results": list(unit.referenced_results),
        "canonical": {
            "proposition_count": len(semantic.higher.resolved.proof.propositions),
            "proof_step_count": len(semantic.higher.resolved.proof.steps),
            "proof_obligation_count": len(semantic.higher.resolved.proof.obligations),
            "support_atom_count": len(semantic.support_atoms),
            "transformation_count": len(semantic.transformations),
            "transformation_counts": {
                f"{kind}:{status}": count
                for (kind, status), count in sorted(transformation_counts.items())
            },
            "semantic_obligation_counts": dict(sorted(obligation_counts.items())),
            "transformations": [
                _transformation_record(semantic, item) for item in semantic.transformations
            ],
        },
        "whole_result_lean": {
            "status": export.status.value,
            "is_mechanically_checkable": export.is_mechanically_checkable,
            "obligation_reasons": [item.reason for item in export.obligations],
            "obligation_source_address_counts": [
                len(item.source_addresses) for item in export.obligations
            ],
            "contains_sorry": "sorry" in export.source,
        },
    }


def build_inventory(
    manifest_path: Path,
    *,
    structural_only: bool,
    thorn_revision: str | None,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    root = manifest_path.resolve().parents[1]
    cases = [
        _case_record(root, spec, structural_only=structural_only)
        for spec in manifest["cases"]
    ]
    return {
        "schema": _SCHEMA,
        "issue": 115,
        "thorn_revision": thorn_revision or manifest.get("thorn_base_revision"),
        "mode": "structural_only" if structural_only else "normal_local_nlp",
        "case_count": len(cases),
        "cases": cases,
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        inventory = build_inventory(
            args.manifest,
            structural_only=args.structural_only,
            thorn_revision=args.thorn_revision,
        )
    except LinguisticFrontendUnavailable as exc:
        print(
            "Lean replay opportunity inventory: local linguistic frontend unavailable: "
            f"{exc}. Install en_core_web_sm or use --structural-only for a degraded smoke run."
        )
        return 2

    rendered = json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
