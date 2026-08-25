#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

MODEL_ID = "knowledgator/gliner-relex-base-v1.0"
MODEL_REVISION = "e6a880049a19c5cc222a7a479c32e84b0d8cdd9a"
THRESHOLDS = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
ENTITY_LABELS = ("result owner", "result reference")


def _score_ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


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


def _matching_entity_indices(
    entities: list[dict[str, Any]],
    *,
    text: str,
    start: int,
    end: int,
) -> set[int]:
    return {
        index
        for index, entity in enumerate(entities)
        if int(entity.get("start", -1)) == start
        and int(entity.get("end", -1)) == end
        and str(entity.get("text", "")) == text
    }


def _relation_score(
    relations: list[dict[str, Any]],
    *,
    owner_indices: set[int],
    reference_indices: set[int],
    label: str,
) -> tuple[float, float]:
    forward = 0.0
    reverse = 0.0
    for relation in relations:
        if str(relation.get("relation", "")) != label:
            continue
        head = int(relation.get("head", {}).get("entity_idx", -1))
        tail = int(relation.get("tail", {}).get("entity_idx", -1))
        score = float(relation.get("score", 0.0))
        if head in owner_indices and tail in reference_indices:
            forward = max(forward, score)
        elif head in reference_indices and tail in owner_indices:
            reverse = max(reverse, score)
    return forward, reverse


def _evaluate_label(
    *,
    model: Any,
    payload: dict[str, Any],
    owner_surface: str,
    label: str,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    inference_started = time.perf_counter()
    prefix = f"{owner_surface}: "
    for case in payload["cases"]:
        context = str(case["context"])
        text = prefix + context
        entity_batches, relation_batches = model.inference(
            texts=[text],
            labels=list(ENTITY_LABELS),
            relations=[label],
            threshold=0.0,
            adjacency_threshold=0.0,
            relation_threshold=0.0,
            return_relations=True,
            flat_ner=False,
        )
        entities = list(entity_batches[0])
        relations = list(relation_batches[0])
        owner_indices = _matching_entity_indices(
            entities,
            text=owner_surface,
            start=0,
            end=len(owner_surface),
        )
        for reference in case["references"]:
            placeholder = str(reference["placeholder"])
            expected_start = len(prefix) + int(reference["provenance"]["char_start"])
            expected_end = len(prefix) + int(reference["provenance"]["char_end"])
            if text[expected_start:expected_end] != placeholder:
                raise ValueError(f"benchmark provenance mismatch for {case['id']} {placeholder}")
            reference_indices = _matching_entity_indices(
                entities,
                text=placeholder,
                start=expected_start,
                end=expected_end,
            )
            score, reverse_score = _relation_score(
                relations,
                owner_indices=owner_indices,
                reference_indices=reference_indices,
                label=label,
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
                    "owner_entity_found": bool(owner_indices),
                    "reference_entity_found": bool(reference_indices),
                    "endpoint_found": bool(owner_indices and reference_indices),
                    "score": score,
                    "reverse_score": reverse_score,
                    "predicted_entity_count": len(entities),
                    "predicted_relation_count": len(relations),
                }
            )
    inference_seconds = time.perf_counter() - inference_started
    exact_owner = sum(bool(item["owner_entity_found"]) for item in observations)
    exact_reference = sum(bool(item["reference_entity_found"]) for item in observations)
    exact_endpoints = sum(bool(item["endpoint_found"]) for item in observations)
    total = len(observations)
    return {
        "relation_label": label,
        "inference_seconds": inference_seconds,
        "entity_grounding": {
            "owner_found": exact_owner,
            "reference_found": exact_reference,
            "endpoint_pairs_found": exact_endpoints,
            "total": total,
            "endpoint_pair_rate": _score_ratio(exact_endpoints, total),
        },
        "threshold_sweep": [
            _threshold_metrics(observations, threshold) for threshold in THRESHOLDS
        ],
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("require_relation_cases.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("issue 219 evaluation must remain provider-keyless")

    from gliner import GLiNER
    from huggingface_hub import model_info

    payload = _load_cases(args.cases)
    owner_surface = str(payload["owner_surface"])
    labels = [str(label) for label in payload["relation_label_candidates"]]
    info = model_info(MODEL_ID, revision=MODEL_REVISION)

    load_started = time.perf_counter()
    model = GLiNER.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        map_location="cpu",
    )
    model.eval()
    load_seconds = time.perf_counter() - load_started

    evaluations = [
        _evaluate_label(
            model=model,
            payload=payload,
            owner_surface=owner_surface,
            label=label,
        )
        for label in labels
    ]
    reference_occurrences = sum(
        len(case["references"]) for case in payload["cases"]
    )
    output = {
        "format_version": 1,
        "issue": 219,
        "keyless": True,
        "provider_calls": 0,
        "task": "grounded REQUIRE relation proposal",
        "authority": "research-only; predictions do not mutate Thorn graph state",
        "transport_boundary": (
            "GLiNER-RelEx has no supplied-entity inference API. The adapter accepts only "
            "model entities whose character span exactly matches Thorn's frozen owner or "
            "reference sentinel; all other discovered entities are discarded. Entity-boundary "
            "failure therefore counts as endpoint-grounding failure, never as canonical identity."
        ),
        "classification_policy": (
            "At a threshold the model may propose REQUIRE only on an exactly rediscovered "
            "owner/reference pair; otherwise Thorn abstains. Low scores never become canonical "
            "NON_REQUIRE."
        ),
        "label_policy": (
            "The three labels were frozen before this candidate and are evaluated independently "
            "against the unchanged public benchmark."
        ),
        "model": {
            "id": MODEL_ID,
            "requested_revision": MODEL_REVISION,
            "resolved_revision": info.sha,
            "gliner_version": importlib.metadata.version("gliner"),
        },
        "entity_labels": list(ENTITY_LABELS),
        "benchmark": {
            "cases": len(payload["cases"]),
            "reference_occurrences": reference_occurrences,
            "require": sum(
                reference["expected"] == "REQUIRE"
                for case in payload["cases"]
                for reference in case["references"]
            ),
            "non_require": sum(
                reference["expected"] == "NON_REQUIRE"
                for case in payload["cases"]
                for reference in case["references"]
            ),
            "unresolved": sum(
                reference["expected"] == "UNRESOLVED"
                for case in payload["cases"]
                for reference in case["references"]
            ),
        },
        "runtime": {
            "model_load_seconds": load_seconds,
            "total_inference_seconds": sum(
                float(evaluation["inference_seconds"]) for evaluation in evaluations
            ),
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
        },
        "evaluations": evaluations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "model": output["model"],
        "benchmark": output["benchmark"],
        "runtime": output["runtime"],
    }
    print(json.dumps(summary, indent=2))
    for evaluation in evaluations:
        print(evaluation["relation_label"])
        print(json.dumps(evaluation["entity_grounding"], indent=2))
        print(json.dumps(evaluation["threshold_sweep"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
