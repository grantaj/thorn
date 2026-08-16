from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from thorn.canonical_proof_ir import CanonicalNodeKind
from thorn.canonical_typed_proof_ir import build_canonical_typed_proof_ir
from thorn.eval_review import build_result_review_context
from thorn.formula_ir import ExprLoweringStatus, walk_math_expr
from thorn.latex import extract_project
from thorn.semantic_review_render import build_semantic_review_request


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure keyless typed-expression coverage over the public Thorn corpus "
            "without constructing a semantic provider."
        )
    )
    parser.add_argument(
        "case_dir",
        nargs="?",
        type=Path,
        default=Path("eval/cases"),
    )
    parser.add_argument("--output", type=Path)
    return parser


def _target_identifier(metadata_path: Path, project: Any) -> str:
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    target = payload.get("target_identifier")
    if isinstance(target, str):
        return target
    if len(project.units) != 1:
        raise ValueError(
            f"{metadata_path} has no target_identifier and extracted "
            f"{len(project.units)} theorem-like units"
        )
    return project.units[0].identifier


def measure_typed_formula_ir(case_dir: Path) -> dict[str, object]:
    status_counts: Counter[str] = Counter()
    node_kind_counts: Counter[str] = Counter()
    node_kind_status: Counter[str] = Counter()
    ast_node_types: Counter[str] = Counter()
    edge_expression_status: Counter[str] = Counter()
    cases = 0
    proof_nodes = 0
    mathematical_payload_nodes = 0
    pruned_claims = 0
    unresolved_math_claims = 0

    metadata_paths = sorted(case_dir.rglob("*.json"))
    if not metadata_paths:
        raise ValueError(f"no public evaluation cases found in {case_dir}")

    for metadata_path in metadata_paths:
        tex_path = metadata_path.with_suffix(".tex")
        if not tex_path.exists():
            raise FileNotFoundError(f"missing fixture for {metadata_path}: {tex_path}")

        # Structural extraction is deliberate: this metric measures the semantic
        # representation itself, not spaCy/model availability or semantic review.
        project = extract_project(tex_path, linguistic_frontend=None)
        target_identifier = _target_identifier(metadata_path, project)
        unit = project.unit(target_identifier)
        context = build_result_review_context(project, target_identifier)
        if len(context.items) != 1:
            raise AssertionError(
                f"expected one review item for {target_identifier}, got {len(context.items)}"
            )
        request = build_semantic_review_request(context.items[0])
        typed_ir = build_canonical_typed_proof_ir(unit, request)

        cases += 1
        proof_nodes += len(typed_ir.nodes)
        pruned_claims += typed_ir.pruned_claims
        unresolved_math_claims += typed_ir.unresolved_math_claims

        for node in typed_ir.nodes:
            node_kind_counts[node.kind.value] += 1
            if node.kind == CanonicalNodeKind.OPAQUE_PROSE:
                continue
            mathematical_payload_nodes += 1
            status = node.expression_status
            if status is None or node.expression is None:
                status_counts["unlowered"] += 1
                node_kind_status[f"{node.kind.value}:unlowered"] += 1
                continue
            status_counts[status.value] += 1
            node_kind_status[f"{node.kind.value}:{status.value}"] += 1
            for expression_node in walk_math_expr(node.expression):
                ast_node_types[type(expression_node).__name__] += 1

        for edge in typed_ir.edges:
            if edge.expression_status is not None:
                edge_expression_status[edge.expression_status.value] += 1

    structured = (
        status_counts[ExprLoweringStatus.FULL.value]
        + status_counts[ExprLoweringStatus.PARTIAL.value]
    )
    coverage = (
        structured / mathematical_payload_nodes if mathematical_payload_nodes else 0.0
    )

    return {
        "cases": cases,
        "proof_nodes": proof_nodes,
        "mathematical_payload_nodes": mathematical_payload_nodes,
        "structured_payload_nodes": structured,
        "structured_payload_fraction": round(coverage, 4),
        "lowering_status": dict(sorted(status_counts.items())),
        "node_kinds": dict(sorted(node_kind_counts.items())),
        "node_kind_status": dict(sorted(node_kind_status.items())),
        "ast_node_types": dict(sorted(ast_node_types.items())),
        "edge_expression_status": dict(sorted(edge_expression_status.items())),
        "pruned_claims": pruned_claims,
        "unresolved_math_claims": unresolved_math_claims,
        "provider_requests": 0,
    }


def main() -> int:
    args = _parser().parse_args()
    report = measure_typed_formula_ir(args.case_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
