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

MODEL_ID = "knowledgator/gliner-relex-large-v1.0"
MODEL_REVISION = "4aedc92"
ENTITY_LABELS = ("result owner", "result reference")
THRESHOLDS = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _load_cases(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or payload.get("issue") != 219:
        raise ValueError("unexpected issue 219 benchmark format")
    return payload


def _transport_case(
    owner_surface: str,
    case: dict[str, Any],
) -> tuple[str, list[dict[str, int]], dict[str, tuple[int, int]]]:
    context = str(case["context"])
    prefix = f"{owner_surface}: "
    text = prefix + context
    owner_span = (0, len(owner_surface))
    spans = [{"start": owner_span[0], "end": owner_span[1]}]
    exact_spans = {owner_surface: owner_span}

    for reference in case["references"]:
        placeholder = str(reference["placeholder"])
        provenance = reference["provenance"]
        start = len(prefix) + int(provenance["char_start"])
        end = len(prefix) + int(provenance["char_end"])
        if text[start:end] != placeholder:
            raise ValueError(
                f"transport span mismatch for {case['id']} {placeholder}: "
                f"{text[start:end]!r}"
            )
        spans.append({"start": start, "end": end})
        exact_spans[placeholder] = (start, end)

    return text, spans, exact_spans


def _has_entity(
    entities: list[dict[str, Any]],
    expected_span: tuple[int, int],
) -> bool:
    return any(
        int(entity["start"]) == expected_span[0]
        and int(entity["end"]) == expected_span[1]
        for entity in entities
    )


def _relation_score(
    relations: list[dict[str, Any]],
    *,
    owner_span: tuple[int, int],
    reference_span: tuple[int, int],
    relation_label: str,
) -> tuple[float, bool, float]:
    forward_score = 0.0
    reverse_score = 0.0
    forward_found = False
    for relation in relations:
        if str(relation.get("relation")) != relation_label:
            continue
        head = relation.get("head", {})
        tail = relation.get("tail", {})
        head_span = (int(head.get("start", -1)), int(head.get("end", -1)))
        tail_span = (int(tail.get("start", -1)), int(tail.get("end", -1)))
        score = float(relation.get("score", 0.0))
        if head_span == owner_span and tail_span == reference_span:
            forward_score = max(forward_score, score)
            forward_found = True
        elif head_span == reference_span and tail_span == owner_span:
            reverse_score = max(reverse_score, score)
    return forward_score, forward_found, reverse_score


def _threshold_metrics(
    observations: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    binary = [item for item in observations if item["expected"] != "UNRESOLVED"]
    positives = [item for item in binary if item["expected"] == "REQUIRE"]
    negatives = [item for item in binary if item["expected"] == "NON_REQUIRE"]
    unresolved = [item for item in observations if item["expected"] == "UNRESOLVED"]

    def asserted(item: dict[str, Any]) -> bool:
        return (
            bool(item["endpoint_entities_found"])
            and bool(item["relation_found"])
            and float(item["score"]) >= threshold
        )

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
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, len(positives)),
        "false_positive_rate": _ratio(fp, len(negatives)),
        "assertion_coverage": _ratio(assertions, len(observations)),
        "unresolved_assertions": unresolved_assertions,
        "unresolved_assertion_rate": _ratio(unresolved_assertions, len(unresolved)),
        "operator_present_recall": _ratio(
            sum(asserted(item) for item in operator_present),
            len(operator_present),
        ),
        "operator_absent_recall": _ratio(
            sum(asserted(item) for item in operator_absent),
            len(operator_absent),
        ),
    }


def _evaluate_label(
    *,
    model: Any,
    payload: dict[str, Any],
    owner_surface: str,
    relation_label: str,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    started = time.perf_counter()

    for case in payload["cases"]:
        text, input_spans, exact_spans = _transport_case(owner_surface, case)
        entities, relations = model.inference(
            texts=[text],
            labels=list(ENTITY_LABELS),
            relations=[relation_label],
            threshold=0.0,
            adjacency_threshold=0.0,
            relation_threshold=0.0,
            flat_ner=False,
            multi_label=False,
            batch_size=1,
            input_spans=[input_spans],
            return_relations=True,
        )
        case_entities = entities[0]
        case_relations = relations[0]
        owner_span = exact_spans[owner_surface]
        owner_found = _has_entity(case_entities, owner_span)

        for reference in case["references"]:
            placeholder = str(reference["placeholder"])
            reference_span = exact_spans[placeholder]
            reference_found = _has_entity(case_entities, reference_span)
            score, relation_found, reverse_score = _relation_score(
                case_relations,
                owner_span=owner_span,
                reference_span=reference_span,
                relation_label=relation_label,
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
                    "owner_entity_found": owner_found,
                    "reference_entity_found": reference_found,
                    "endpoint_entities_found": owner_found and reference_found,
                    "relation_found": relation_found,
                    "score": score,
                    "reverse_score": reverse_score,
                    "predicted_entities": [
                        {
                            "start": int(entity["start"]),
                            "end": int(entity["end"]),
                            "text": str(entity["text"]),
                            "label": str(entity["label"]),
                            "score": float(entity["score"]),
                        }
                        for entity in case_entities
                    ],
                }
            )

    inference_seconds = time.perf_counter() - started
    endpoint_found = sum(bool(item["endpoint_entities_found"]) for item in observations)
    relation_found = sum(bool(item["relation_found"]) for item in observations)
    return {
        "relation_label": relation_label,
        "inference_seconds": inference_seconds,
        "endpoint_grounding": {
            "found": endpoint_found,
            "total": len(observations),
            "rate": _ratio(endpoint_found, len(observations)),
        },
        "relation_candidate_grounding": {
            "found": relation_found,
            "total": len(observations),
            "rate": _ratio(relation_found, len(observations)),
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
    relation_labels = [str(item) for item in payload["relation_label_candidates"]]

    info = model_info(MODEL_ID, revision=MODEL_REVISION)
    load_started = time.perf_counter()
    model = GLiNER.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        map_location="cpu",
        low_cpu_mem_usage=True,
    )
    model.eval()
    load_seconds = time.perf_counter() - load_started

    evaluations = [
        _evaluate_label(
            model=model,
            payload=payload,
            owner_surface=owner_surface,
            relation_label=relation_label,
        )
        for relation_label in relation_labels
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
        "classification_policy": (
            "At a threshold the model may propose REQUIRE; otherwise Thorn abstains. "
            "The evaluator never turns a low score into canonical NON_REQUIRE."
        ),
        "entity_policy": (
            "Owner and reference character spans are supplied through GLiNER-RelEx "
            "input_spans. Exact span preservation is measured before relation scores."
        ),
        "model": {
            "id": MODEL_ID,
            "requested_revision": MODEL_REVISION,
            "resolved_revision": info.sha,
            "gliner_version": importlib.metadata.version("gliner"),
        },
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
        print(json.dumps(evaluation["endpoint_grounding"], indent=2))
        print(json.dumps(evaluation["relation_candidate_grounding"], indent=2))
        print(json.dumps(evaluation["threshold_sweep"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
