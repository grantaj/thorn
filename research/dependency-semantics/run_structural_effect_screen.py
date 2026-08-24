from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from thorn.research.graph_effects import (
    CONDITIONS,
    HYPOTHETICAL,
    INTRODUCE,
    NAME,
    SUPPORT_NOUNS,
    SUPPORT_VERBS,
    build_case,
    compile_effects,
)
from thorn.spacy_linguistic import SpacyLinguisticFrontend


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def declaration_metrics(path: Path, frontend: SpacyLinguisticFrontend) -> dict[str, Any]:
    cases = json.loads(path.read_text())["cases"]
    tp = fp = fn = unsafe = negatives = lexical_tp = lexical_total = grounded = 0
    records: list[dict[str, Any]] = []
    for raw in cases:
        case = build_case(raw)
        frames = compile_effects(case, frontend.parse(case.projected))
        actual_frames = [
            frame for frame in frames if frame.operation == "declare" and frame.bind is not None
        ]
        expected = [" ".join(item["term"].casefold().split()) for item in raw.get("expected", [])]
        actual = [
            " ".join(frame.bind.text.casefold().split())
            for frame in actual_frames
            if frame.bind is not None
        ]
        matched = 0
        remaining = list(enumerate(actual))
        for term in expected:
            hit = next(((index, value) for index, value in remaining if value == term), None)
            if hit is None:
                continue
            matched += 1
            grounded += int(actual_frames[hit[0]].exact)
            remaining.remove(hit)
        tp += matched
        fp += len(actual) - matched
        fn += len(expected) - matched
        if raw.get("family") == "negative":
            negatives += 1
            unsafe += int(bool(actual))
        if raw.get("lexical_challenge"):
            lexical_tp += matched
            lexical_total += len(expected)
        records.append(
            {
                "id": raw["id"],
                "expected": expected,
                "actual": actual,
                "rules": [frame.rule for frame in frames],
            }
        )
    return {
        "cases": len(cases),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "unsafe_negative_cases": unsafe,
        "negative_cases": negatives,
        "false_authority_case_rate": ratio(unsafe, negatives),
        "lexical_challenge_recall": ratio(lexical_tp, lexical_total),
        "exact_grounding_rate_on_matched": ratio(grounded, tp),
        "records": records,
    }


def effect_metrics(path: Path, frontend: SpacyLinguisticFrontend) -> dict[str, Any]:
    cases = json.loads(path.read_text())["cases"]
    require_tp = require_fp = require_fn = endpoint_exact = 0
    declare_total = declare_seen = declare_payload_exact = 0
    visibility_total = visibility_exact = unsafe = negatives = 0
    baseline_tp = baseline_fp = 0
    records: list[dict[str, Any]] = []
    for raw in cases:
        case = build_case(raw)
        frames = compile_effects(case, frontend.parse(case.projected))
        expected = set(raw["expected_effects"])
        operations = {frame.operation for frame in frames}
        want_require = "require" in expected
        got_require = "require" in operations
        require_tp += int(want_require and got_require)
        require_fp += int(not want_require and got_require)
        require_fn += int(want_require and not got_require)

        resolved_ref_baseline = "THORNREF" in case.projected
        baseline_tp += int(want_require and resolved_ref_baseline)
        baseline_fp += int(not want_require and resolved_ref_baseline)

        if want_require:
            actual_refs = {
                item.text
                for frame in frames
                if frame.operation == "require"
                for item in frame.prerequisites
            }
            endpoint_exact += int(actual_refs == set(raw.get("expected_refs", [])))
        if "declare" in expected:
            declare_total += 1
            declarations = [frame for frame in frames if frame.operation == "declare"]
            declare_seen += int(bool(declarations))
            declare_payload_exact += int(
                bool(declarations)
                and all(
                    frame.payload and all(item.exact for item in frame.payload)
                    for frame in declarations
                )
            )
        if "visibility" in expected:
            visibility_total += 1
            # Deliberately unsupported by the first structural compiler. We record
            # the gap instead of teaching the screen a phrase after seeing heldouts.
            visibility_exact += 0
        if not expected:
            negatives += 1
            unsafe += int(bool(operations))
        records.append(
            {
                "id": raw["id"],
                "expected": sorted(expected),
                "actual": sorted(operations),
                "prerequisites": [
                    item.text
                    for frame in frames
                    if frame.operation == "require"
                    for item in frame.prerequisites
                ],
                "rules": [frame.rule for frame in frames],
                "calculus_pressure": raw.get("calculus_pressure"),
            }
        )
    return {
        "cases": len(cases),
        "require_precision": ratio(require_tp, require_tp + require_fp),
        "require_recall": ratio(require_tp, require_tp + require_fn),
        "require_tp": require_tp,
        "require_fp": require_fp,
        "require_fn": require_fn,
        "require_endpoint_exact_rate": ratio(endpoint_exact, require_tp + require_fn),
        "declare_recall": ratio(declare_seen, declare_total),
        "declare_payload_exact_rate": ratio(declare_payload_exact, declare_total),
        "visibility_exact_grounding_rate": ratio(visibility_exact, visibility_total),
        "status_supported": False,
        "unsafe_negative_cases": unsafe,
        "negative_cases": negatives,
        "false_authority_case_rate": ratio(unsafe, negatives),
        "resolved_reference_implies_require_baseline": {
            "precision": ratio(baseline_tp, baseline_tp + baseline_fp),
            "recall": 1.0,
            "tp": baseline_tp,
            "fp": baseline_fp,
        },
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--declarations",
        type=Path,
        default=Path("research/semantic-parser-bakeoff/declaration_cases.json"),
    )
    parser.add_argument(
        "--effects",
        type=Path,
        default=Path("research/dependency-semantics/effect_cases.json"),
    )
    parser.add_argument("--model", default="en_core_web_sm")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    frontend = SpacyLinguisticFrontend(model_name=args.model)
    result = {
        "version": 1,
        "model": args.model,
        "operator_inventory": {
            "introduce": sorted(INTRODUCE),
            "name": sorted(NAME),
            "support_verbs": sorted(SUPPORT_VERBS),
            "support_nouns": sorted(SUPPORT_NOUNS),
            "conditions": sorted(CONDITIONS),
            "hypothetical_auxiliaries": sorted(HYPOTHETICAL),
        },
        "declarations": declaration_metrics(args.declarations, frontend),
        "effects": effect_metrics(args.effects, frontend),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
