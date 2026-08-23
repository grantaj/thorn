#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import CrossEncoder

MODEL_ID = "cross-encoder/nli-deberta-v3-xsmall"
LABELS = ("contradiction", "entailment", "neutral")
EFFECT_HYPOTHESES = {
    "binding": (
        "The author introduces a mathematical term, notation, or property here and "
        "specifies its meaning or defining condition for later mathematical reasoning."
    ),
    "ambient": (
        "The author establishes a mathematical assumption or convention here that "
        "remains in force for subsequent mathematical statements."
    ),
}
THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)


def _projected_text(case: dict[str, Any]) -> str:
    if "text" in case:
        return str(case["text"])
    parts: list[str] = []
    for segment in case.get("segments", []):
        if isinstance(segment, str):
            parts.append(segment)
        elif "token" in segment:
            parts.append(str(segment["token"]))
        else:
            parts.append(str(segment.get("projected", segment.get("raw", ""))))
    return "".join(parts)


def _expected_effect(case: dict[str, Any]) -> str:
    roles = {str(item["role"]) for item in case.get("expected", [])}
    if not roles:
        return "none"
    if roles == {"definition"}:
        return "binding"
    if roles == {"ambient"}:
        return "ambient"
    raise ValueError(f"unsupported expected roles for {case['id']}: {sorted(roles)}")


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - values.max(axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=1, keepdims=True)


def _classification(
    scores: dict[str, float],
    threshold: float,
) -> str:
    effect, score = max(scores.items(), key=lambda item: item[1])
    return effect if score >= threshold else "none"


def _metrics(records: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    expected_positive = sum(record["expected_effect"] != "none" for record in records)
    predicted_positive = 0
    true_positive = 0
    false_positive = 0
    false_negative = 0
    correct_kind = 0
    correct = 0
    false_positive_ids: list[str] = []
    false_negative_ids: list[str] = []
    wrong_kind_ids: list[str] = []

    for record in records:
        predicted = _classification(record["entailment"], threshold)
        expected = record["expected_effect"]
        predicted_positive += predicted != "none"
        if predicted == expected:
            correct += 1
        if expected != "none" and predicted != "none":
            true_positive += 1
            if predicted == expected:
                correct_kind += 1
            else:
                wrong_kind_ids.append(record["id"])
        elif expected == "none" and predicted != "none":
            false_positive += 1
            false_positive_ids.append(record["id"])
        elif expected != "none" and predicted == "none":
            false_negative += 1
            false_negative_ids.append(record["id"])

    precision = true_positive / predicted_positive if predicted_positive else 0.0
    recall = true_positive / expected_positive if expected_positive else 0.0
    kind_accuracy = correct_kind / expected_positive if expected_positive else 0.0
    return {
        "threshold": threshold,
        "accuracy": correct / len(records),
        "precision_any_effect": precision,
        "recall_any_effect": recall,
        "expected_positive": expected_positive,
        "predicted_positive": predicted_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "correct_effect_kind": correct_kind,
        "effect_kind_accuracy_on_expected_positive": kind_accuracy,
        "false_positive_ids": false_positive_ids,
        "false_negative_ids": false_negative_ids,
        "wrong_kind_ids": wrong_kind_ids,
    }


def run(corpus_path: Path, *, model_id: str) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = list(corpus["cases"])
    model = CrossEncoder(model_id)

    pairs: list[tuple[str, str]] = []
    pair_keys: list[tuple[int, str]] = []
    for index, case in enumerate(cases):
        premise = _projected_text(case)
        for effect, hypothesis in EFFECT_HYPOTHESES.items():
            pairs.append((premise, hypothesis))
            pair_keys.append((index, effect))

    raw_scores = np.asarray(model.predict(pairs, show_progress_bar=False))
    if raw_scores.ndim != 2 or raw_scores.shape[1] != len(LABELS):
        raise RuntimeError(
            f"expected NLI logits [n,{len(LABELS)}], received {raw_scores.shape}"
        )
    probabilities = _softmax(raw_scores)
    entailment_index = LABELS.index("entailment")

    records: list[dict[str, Any]] = [
        {
            "id": str(case["id"]),
            "category": str(case["category"]),
            "family": str(case["family"]),
            "expected_effect": _expected_effect(case),
            "text": _projected_text(case),
            "entailment": {},
        }
        for case in cases
    ]
    for row, (case_index, effect) in enumerate(pair_keys):
        records[case_index]["entailment"][effect] = float(
            probabilities[row, entailment_index]
        )

    return {
        "format_version": 1,
        "experiment": "dependency-semantics-nli-effect-screen",
        "model": model_id,
        "model_labels": list(LABELS),
        "corpus": str(corpus_path),
        "cases": len(cases),
        "candidate_effects": EFFECT_HYPOTHESES,
        "dictionary_free": True,
        "scope": (
            "semantic-effect classification only; candidate argument/payload extraction "
            "is deliberately not evaluated in this screen"
        ),
        "metrics": [_metrics(records, threshold) for threshold in THRESHOLDS],
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("research/semantic-parser-bakeoff/declaration_cases.json"),
    )
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run(args.corpus, model_id=args.model)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
