from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.llm_proof_language import (
    ProofLanguageStyle,
    project_llm_proof_language,
    proof_language_inventory,
    render_llm_proof_language,
)
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import (
    build_semantic_review_request,
    render_semantic_review_request,
)
from thorn.semantic_transformations import build_semantic_transformation_ir


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare deterministic issue-65 proof-language renderings over the public "
            "Thorn corpus without constructing a semantic provider."
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


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def measure_llm_proof_language(case_dir: Path) -> dict[str, object]:
    metadata_paths = sorted(case_dir.rglob("*.json"))
    if not metadata_paths:
        raise ValueError(f"no public evaluation cases found in {case_dir}")

    totals: Counter[str] = Counter()
    semantic_totals: Counter[str] = Counter()
    compact_ratios: list[float] = []
    explicit_ratios: list[float] = []
    compact_smaller_cases = 0
    cases = 0

    for metadata_path in metadata_paths:
        tex_path = metadata_path.with_suffix(".tex")
        if not tex_path.exists():
            raise FileNotFoundError(f"missing fixture for {metadata_path}: {tex_path}")

        project = extract_project(tex_path, linguistic_frontend=None)
        target_identifier = _target_identifier(metadata_path, project)
        unit = project.unit(target_identifier)
        context = build_result_review_context(project, target_identifier)
        if len(context.items) != 1:
            raise AssertionError(
                f"expected one review item for {target_identifier}, got {len(context.items)}"
            )
        request = build_semantic_review_request(context.items[0])
        semantic = build_semantic_transformation_ir(
            unit,
            request,
            symbol_table=project.symbol_table,
            dependency_graph=project.dependency_graph,
        )

        raw = render_semantic_review_request(request)
        legacy_compact = render_compact_semantic_review_request(request)
        compact = render_llm_proof_language(
            semantic,
            style=ProofLanguageStyle.COMPACT,
        )
        explicit = render_llm_proof_language(
            semantic,
            style=ProofLanguageStyle.EXPLICIT,
        )
        document = project_llm_proof_language(semantic)
        if document.render_initial() != compact:
            raise AssertionError("frozen proof-language packet diverged from compact candidate")

        cases += 1
        totals["raw_chars"] += len(raw)
        totals["legacy_compact_chars"] += len(legacy_compact)
        totals["proof_compact_chars"] += len(compact)
        totals["proof_explicit_chars"] += len(explicit)
        totals["source_handles"] += len(document.sources)
        if len(compact) < len(explicit):
            compact_smaller_cases += 1
        compact_ratios.append(_ratio(len(raw), len(compact)))
        explicit_ratios.append(_ratio(len(raw), len(explicit)))
        semantic_totals.update(proof_language_inventory(semantic))

    return {
        "cases": cases,
        "selected_style": ProofLanguageStyle.COMPACT.value,
        "format_version": "thorn-proof/1",
        "characters": {
            "raw_semantic_request": totals["raw_chars"],
            "legacy_compact_request": totals["legacy_compact_chars"],
            "proof_language_compact": totals["proof_compact_chars"],
            "proof_language_explicit": totals["proof_explicit_chars"],
        },
        "aggregate_ratios": {
            "raw_to_proof_compact": _ratio(
                totals["raw_chars"], totals["proof_compact_chars"]
            ),
            "raw_to_proof_explicit": _ratio(
                totals["raw_chars"], totals["proof_explicit_chars"]
            ),
            "legacy_compact_to_proof_compact": _ratio(
                totals["legacy_compact_chars"], totals["proof_compact_chars"]
            ),
            "explicit_to_compact": _ratio(
                totals["proof_explicit_chars"], totals["proof_compact_chars"]
            ),
        },
        "median_case_ratios": {
            "raw_to_proof_compact": round(statistics.median(compact_ratios), 4),
            "raw_to_proof_explicit": round(statistics.median(explicit_ratios), 4),
        },
        "compact_smaller_than_explicit_cases": compact_smaller_cases,
        "semantic_inventory": dict(sorted(semantic_totals.items())),
        "source_handles": totals["source_handles"],
        "source_rescue_rounds": 1,
        "max_source_addresses_per_rescue": 8,
        "provider_requests": 0,
    }


def main() -> int:
    args = _parser().parse_args()
    report = measure_llm_proof_language(args.case_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
