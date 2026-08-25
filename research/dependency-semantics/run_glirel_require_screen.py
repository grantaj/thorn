#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import resource
import sys
import time
from pathlib import Path
from typing import Any

MODEL_ID = "jackboyla/glirel-large-v0"
MODEL_REVISION = "40a523e12a8432d6da364cf2a195a28755ff04d3"
BASE_MODEL_ID = "microsoft/deberta-v3-large"
DEFAULT_RELATION_LABEL = "uses as a direct prerequisite"
THRESHOLDS = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
_TOKEN_RE = re.compile(r"THORN(?:OWNER|REF\d+)|[A-Za-z]+(?:'[A-Za-z]+)?|\d+|[^\w\s]")


def _score_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _tokenize_case(owner_surface: str, context: str) -> tuple[list[str], dict[str, int]]:
    tokens = [owner_surface, ":"]
    reference_token_indices: dict[str, int] = {}
    for match in _TOKEN_RE.finditer(context):
        token = match.group(0)
        index = len(tokens)
        tokens.append(token)
        if token.startswith("THORNREF"):
            if token in reference_token_indices:
                raise ValueError(f"reference placeholder occurs more than once: {token}")
            reference_token_indices[token] = index
    return tokens, reference_token_indices


def _surface(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _relation_score(
    relations: list[dict[str, Any]],
    *,
    owner_surface: str,
    reference: str,
    label: str,
) -> tuple[float, bool, float]:
    forward = 0.0
    reverse = 0.0
    found = False
    for relation in relations:
        if relation.get("label") != label:
            continue
        head = _surface(relation.get("head_text"))
        tail = _surface(relation.get("tail_text"))
        score = float(relation.get("score", 0.0))
        if head == (owner_surface,) and tail == (reference,):
            forward = max(forward, score)
            found = True
        elif head == (reference,) and tail == (owner_surface,):
            reverse = max(reverse, score)
    return forward, found, reverse


def _threshold_metrics(
    observations: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    binary = [item for item in observations if item["expected"] != "UNRESOLVED"]
    positives = [item for item in binary if item["expected"] == "REQUIRE"]
    negatives = [item for item in binary if item["expected"] == "NON_REQUIRE"]
    unresolved = [item for item in observations if item["expected"] == "UNRESOLVED"]

    def asserted(item: dict[str, Any]) -> bool:
        return bool(item["endpoint_found"]) and float(item["score"]) >= threshold

    tp = sum(asserted(item) for item in positives)
    fp = sum(asserted(item) for item in negatives)
    fn = len(positives) - tp
    unresolved_assertions = sum(asserted(item) for item in unresolved)
    assertions = tp + fp + unresolved_assertions

    operator_present = [item for item in positives if item["frozen_operator_present"]]
    operator_absent = [item for item in positives if not item["frozen_operator_present"]]

    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _score_ratio(tp, tp + fp),
        "recall": _score_ratio(tp, len(positives)),
        "false_positive_rate": _score_ratio(fp, len(negatives)),
        "assertion_coverage": _score_ratio(assertions, len(observations)),
        "unresolved_assertions": unresolved_assertions,
        "unresolved_assertion_rate": _score_ratio(unresolved_assertions, len(unresolved)),
        "operator_present_recall": _score_ratio(
            sum(asserted(item) for item in operator_present),
            len(operator_present),
        ),
        "operator_absent_recall": _score_ratio(
            sum(asserted(item) for item in operator_absent),
            len(operator_absent),
        ),
    }


def _load_cases(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or payload.get("issue") != 219:
        raise ValueError("unexpected issue 219 benchmark format")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("require_relation_cases.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default=DEFAULT_RELATION_LABEL)
    args = parser.parse_args()

    if os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("issue 219 evaluation must remain provider-keyless")

    from glirel import GLiREL
    from huggingface_hub import model_info
    import torch

    payload = _load_cases(args.cases)
    owner_surface = str(payload["owner_surface"])
    if args.label not in payload["relation_label_candidates"]:
        raise ValueError("relation label must be frozen in the public benchmark")

    glirel_info = model_info(MODEL_ID, revision=MODEL_REVISION)
    base_info = model_info(BASE_MODEL_ID)

    load_started = time.perf_counter()
    model = GLiREL.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        map_location="cpu",
    )
    model.eval()
    load_seconds = time.perf_counter() - load_started

    observations: list[dict[str, Any]] = []
    inference_started = time.perf_counter()
    with torch.inference_mode():
        for case in payload["cases"]:
            context = str(case["context"])
            tokens, reference_indices = _tokenize_case(owner_surface, context)
            ner: list[list[Any]] = [[0, 0, "RESULT_OWNER", owner_surface]]
            for reference in case["references"]:
                placeholder = str(reference["placeholder"])
                ner.append(
                    [
                        reference_indices[placeholder],
                        reference_indices[placeholder],
                        "RESULT_REFERENCE",
                        placeholder,
                    ]
                )

            relations = model.predict_relations(
                tokens,
                [args.label],
                threshold=0.0,
                ner=ner,
                top_k=1,
            )
            for reference in case["references"]:
                placeholder = str(reference["placeholder"])
                score, endpoint_found, reverse_score = _relation_score(
                    relations,
                    owner_surface=owner_surface,
                    reference=placeholder,
                    label=args.label,
                )
                observations.append(
                    {
                        "case_id": case["id"],
                        "subtype": case["subtype"],
                        "frozen_operator_present": case["frozen_operator_present"],
                        "owner": case["owner"],
                        "reference": placeholder,
                        "resolved_target": reference["resolved_target"],
                        "expected": reference["expected"],
                        "provenance": reference["provenance"],
                        "score": score,
                        "endpoint_found": endpoint_found,
                        "reverse_score": reverse_score,
                    }
                )
    inference_seconds = time.perf_counter() - inference_started

    endpoint_found = sum(bool(item["endpoint_found"]) for item in observations)
    output = {
        "format_version": 1,
        "issue": 219,
        "keyless": True,
        "provider_calls": 0,
        "task": "grounded REQUIRE relation proposal",
        "authority": "research-only; predictions do not mutate Thorn graph state",
        "classification_policy": (
            "At a threshold the model may propose REQUIRE; otherwise Thorn abstains. "
            "The evaluator never turns a low score into canonical NON_REQUIRE."
        ),
        "relation_label": args.label,
        "model": {
            "id": MODEL_ID,
            "requested_revision": MODEL_REVISION,
            "resolved_revision": glirel_info.sha,
            "base_model_id": BASE_MODEL_ID,
            "base_model_resolved_revision": base_info.sha,
            "glirel_version": importlib.metadata.version("glirel"),
            "torch_version": torch.__version__,
        },
        "benchmark": {
            "cases": len(payload["cases"]),
            "reference_occurrences": len(observations),
            "require": sum(item["expected"] == "REQUIRE" for item in observations),
            "non_require": sum(
                item["expected"] == "NON_REQUIRE" for item in observations
            ),
            "unresolved": sum(item["expected"] == "UNRESOLVED" for item in observations),
        },
        "runtime": {
            "model_load_seconds": load_seconds,
            "inference_seconds": inference_seconds,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        },
        "endpoint_grounding": {
            "found": endpoint_found,
            "total": len(observations),
            "rate": _score_ratio(endpoint_found, len(observations)),
        },
        "threshold_sweep": [
            _threshold_metrics(observations, threshold) for threshold in THRESHOLDS
        ],
        "observations": observations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: output[key] for key in ("model", "benchmark", "runtime")},
            indent=2,
        )
    )
    print(json.dumps(output["threshold_sweep"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
