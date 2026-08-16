from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from thorn.eval import CaseExpectation
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.local_nlp import select_linguistic_frontend
from thorn.models import TheoremUnit
from thorn.proof_skeleton import build_proof_skeleton
from thorn.providers.request_envelope import render_theorem_unit
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import build_semantic_review_request
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure raw vs compact-IR vs source-addressable proof-skeleton size "
            "without constructing a semantic provider."
        )
    )
    parser.add_argument("case_dir", type=Path, nargs="?", default=Path("eval/cases"))
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="skip normal local spaCy enrichment; debugging/degraded path only",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional path for the full per-case JSON inventory",
    )
    return parser


def _load_cases(case_dir: Path) -> list[tuple[Path, CaseExpectation]]:
    cases: list[tuple[Path, CaseExpectation]] = []
    for metadata_path in sorted(case_dir.rglob("*.json")):
        tex_path = metadata_path.with_suffix(".tex")
        if not tex_path.exists():
            raise FileNotFoundError(f"missing fixture for {metadata_path}: {tex_path}")
        expectation = CaseExpectation.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
        cases.append((tex_path, expectation))
    if not cases:
        raise ValueError(f"no *.json evaluation cases found in {case_dir}")
    return cases


def _select_unit(units: list[TheoremUnit], expectation: CaseExpectation) -> TheoremUnit:
    if expectation.target_identifier is not None:
        matches = [
            unit for unit in units if unit.identifier == expectation.target_identifier
        ]
        if len(matches) != 1:
            raise ValueError(
                f"target {expectation.target_identifier!r} matched {len(matches)} units"
            )
        return matches[0]
    if len(units) != 1:
        raise ValueError(
            f"case {expectation.name!r} has {len(units)} units but no target_identifier"
        )
    return units[0]


def _size(text: str) -> dict[str, int]:
    return {
        "characters": len(text),
        "utf8_bytes": len(text.encode("utf-8")),
    }


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def build_inventory(case_dir: Path, *, structural_only: bool) -> dict[str, Any]:
    linguistic_frontend = select_linguistic_frontend(
        structural_only=structural_only,
        factory=SpacyLinguisticFrontend,
    )
    records: list[dict[str, Any]] = []

    for tex_path, expectation in _load_cases(case_dir):
        project = extract_project(tex_path, linguistic_frontend=linguistic_frontend)
        unit = _select_unit(project.units, expectation)
        context = build_result_review_context(project, unit.identifier)
        if len(context.items) != 1:
            raise ValueError(
                f"expected exactly one result review item for {unit.identifier!r}"
            )
        request = build_semantic_review_request(context.items[0])

        raw = render_theorem_unit(unit)
        compact = render_compact_semantic_review_request(request)
        skeleton = build_proof_skeleton(unit, request)
        initial = skeleton.render_initial()
        raw_size = _size(raw)
        compact_size = _size(compact)
        skeleton_size = _size(initial)
        withheld_lines = sum("~" in line for line in skeleton.lines)

        records.append(
            {
                "fixture": str(tex_path),
                "case_name": expectation.name,
                "target_identifier": unit.identifier,
                "raw": raw_size,
                "compact_ir": compact_size,
                "skeleton": skeleton_size,
                "raw_over_skeleton": _ratio(
                    raw_size["characters"], skeleton_size["characters"]
                ),
                "compact_over_skeleton": _ratio(
                    compact_size["characters"], skeleton_size["characters"]
                ),
                "source_addresses": len(skeleton.sources),
                "initial_lines": len(skeleton.lines),
                "withheld_lines": withheld_lines,
            }
        )

    raw_chars = sum(record["raw"]["characters"] for record in records)
    compact_chars = sum(record["compact_ir"]["characters"] for record in records)
    skeleton_chars = sum(record["skeleton"]["characters"] for record in records)
    raw_ratios = [record["raw_over_skeleton"] for record in records]
    compact_ratios = [record["compact_over_skeleton"] for record in records]

    summary = {
        "cases": len(records),
        "provider_instantiated": False,
        "provider_requests": 0,
        "live_requests": 0,
        "api_key_required": False,
        "structural_only": structural_only,
        "characters": {
            "raw": raw_chars,
            "compact_ir": compact_chars,
            "skeleton": skeleton_chars,
        },
        "aggregate_compression": {
            "raw_over_skeleton": _ratio(raw_chars, skeleton_chars),
            "compact_over_skeleton": _ratio(compact_chars, skeleton_chars),
        },
        "per_case_compression": {
            "median_raw_over_skeleton": statistics.median(raw_ratios),
            "median_compact_over_skeleton": statistics.median(compact_ratios),
            "min_raw_over_skeleton": min(raw_ratios),
            "max_raw_over_skeleton": max(raw_ratios),
            "cases_at_least_10x_raw": sum(ratio >= 10.0 for ratio in raw_ratios),
        },
        "source_addressing": {
            "addresses": sum(record["source_addresses"] for record in records),
            "initial_lines": sum(record["initial_lines"] for record in records),
            "withheld_lines": sum(record["withheld_lines"] for record in records),
        },
    }
    return {"summary": summary, "records": records}


def main() -> int:
    args = _parser().parse_args()
    try:
        inventory = build_inventory(args.case_dir, structural_only=args.structural_only)
    except LinguisticFrontendUnavailable as exc:
        print(
            "skeleton compression inventory: local linguistic frontend unavailable: "
            f"{exc}. Install en_core_web_sm or use --structural-only for debugging."
        )
        return 2

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(inventory["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
