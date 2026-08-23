#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
import resource
import time
from pathlib import Path
from typing import Any

import numpy as np
from huggingface_hub import snapshot_download
from sentence_transformers import CrossEncoder

MODEL_ID = "cross-encoder/nli-deberta-v3-xsmall"
EFFECT_HYPOTHESES = {
    "declare": (
        "The author establishes a mathematical fact, assumption, definition, notation, "
        "or convention here so that later mathematical reasoning may depend on it."
    ),
    "require": (
        "The current mathematical claim is justified here by using a previously established "
        "mathematical result or fact as a direct prerequisite."
    ),
    "visibility": (
        "The author changes or specifies the scope in which a mathematical assumption, "
        "definition, notation, or convention is in force."
    ),
    "status": (
        "The author changes or states the proof-relevant status of a mathematical claim, "
        "such as whether it is assumed, unproved, unresolved, or established."
    ),
}
THRESHOLDS = (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)


def _source_text(case: dict[str, Any]) -> str:
    if "text" in case:
        return str(case["text"])
    parts: list[str] = []
    for segment in case.get("segments", []):
        if isinstance(segment, str):
            parts.append(segment)
        else:
            parts.append(str(segment.get("raw", "")))
    return "".join(parts)


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


def _base_expected_effects(case: dict[str, Any]) -> set[str]:
    roles = {str(item["role"]) for item in case.get("expected", [])}
    if not roles:
        return set()
    effects = {"declare"}
    if "ambient" in roles:
        effects.add("visibility")
    return effects


def _load_cases(base_path: Path, heldout_path: Path) -> list[dict[str, Any]]:
    base = json.loads(base_path.read_text(encoding="utf-8"))
    heldout = json.loads(heldout_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for case in base["cases"]:
        item = dict(case)
        item["source_corpus"] = "issue-160"
        item["expected_effects"] = sorted(_base_expected_effects(item))
        cases.append(item)
    for case in heldout["cases"]:
        item = dict(case)
        item["source_corpus"] = "issue-213-heldout"
        cases.append(item)
    return cases


def _label_indices(model: CrossEncoder) -> dict[str, int]:
    config = model.model.config
    id2label = {int(key): str(value).casefold() for key, value in config.id2label.items()}
    result: dict[str, int] = {}
    for index, label in id2label.items():
        for canonical in ("contradiction", "entailment", "neutral"):
            if canonical in label:
                result[canonical] = index
    if set(result) != {"contradiction", "entailment", "neutral"}:
        # This is the documented label order for the selected cross-encoder. Fail rather than
        # silently accepting another model layout.
        if list(id2label) == [0, 1, 2]:
            result = {"contradiction": 0, "entailment": 1, "neutral": 2}
        else:
            raise RuntimeError(f"unrecognized NLI label mapping: {id2label}")
    return result


def _probabilities(values: np.ndarray) -> np.ndarray:
    if (
        np.all(values >= 0.0)
        and np.all(values <= 1.0)
        and np.allclose(values.sum(axis=1), 1.0, atol=1e-5)
    ):
        return values
    shifted = values - values.max(axis=1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / exponentials.sum(axis=1, keepdims=True)


def _metrics(records: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    tp = fp = fn = 0
    safe_negative_cases = 0
    unsafe_negative_cases = 0
    exact_effect_cases = 0
    lexical_total = lexical_exact = 0
    unresolved_total = unresolved_unsafe = 0
    confusion: dict[str, dict[str, int]] = {
        effect: {"tp": 0, "fp": 0, "fn": 0} for effect in EFFECT_HYPOTHESES
    }
    false_authority_ids: list[str] = []
    missed_ids: list[str] = []

    for record in records:
        expected = set(record["expected_effects"])
        predicted = {
            effect for effect, score in record["entailment"].items() if score >= threshold
        }
        if predicted == expected:
            exact_effect_cases += 1
        if record.get("lexical_challenge"):
            lexical_total += 1
            lexical_exact += predicted == expected
        if record.get("should_remain_unresolved"):
            unresolved_total += 1
            unresolved_unsafe += bool(predicted)

        unexpected = predicted - expected
        missing = expected - predicted
        if not expected:
            safe_negative_cases += not predicted
            if predicted:
                unsafe_negative_cases += 1
                false_authority_ids.append(record["id"])
        elif unexpected:
            false_authority_ids.append(record["id"])
        if missing:
            missed_ids.append(record["id"])

        for effect in EFFECT_HYPOTHESES:
            in_expected = effect in expected
            in_predicted = effect in predicted
            if in_expected and in_predicted:
                tp += 1
                confusion[effect]["tp"] += 1
            elif not in_expected and in_predicted:
                fp += 1
                confusion[effect]["fp"] += 1
            elif in_expected and not in_predicted:
                fn += 1
                confusion[effect]["fn"] += 1

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    negative_count = sum(not record["expected_effects"] for record in records)
    return {
        "threshold": threshold,
        "precision_graph_effects": round(precision, 3),
        "recall_graph_effects": round(recall, 3),
        "false_positive_effects": fp,
        "false_negative_effects": fn,
        "unsafe_negative_cases": unsafe_negative_cases,
        "negative_case_false_authority_rate": round(
            unsafe_negative_cases / negative_count if negative_count else 0.0, 3
        ),
        "exact_effect_set_accuracy": round(exact_effect_cases / len(records), 3),
        "lexical_challenge_exact_accuracy": (
            round(lexical_exact / lexical_total, 3) if lexical_total else None
        ),
        "unresolved_lookalike_unsafe_rate": (
            round(unresolved_unsafe / unresolved_total, 3) if unresolved_total else None
        ),
        "by_effect": confusion,
        "false_authority_ids": sorted(set(false_authority_ids)),
        "missed_ids": sorted(set(missed_ids)),
    }


def run(base_path: Path, heldout_path: Path, *, model_id: str, revision: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    snapshot_path = Path(snapshot_download(repo_id=model_id, revision=revision))
    resolved_revision = snapshot_path.name
    snapshot_bytes = sum(
        path.stat().st_size for path in snapshot_path.rglob("*") if path.is_file()
    )
    model = CrossEncoder(str(snapshot_path))
    label_indices = _label_indices(model)
    cases = _load_cases(base_path, heldout_path)

    pairs: list[tuple[str, str]] = []
    pair_keys: list[tuple[int, str]] = []
    for index, case in enumerate(cases):
        premise = _projected_text(case)
        for effect, hypothesis in EFFECT_HYPOTHESES.items():
            pairs.append((premise, hypothesis))
            pair_keys.append((index, effect))

    inference_started = time.perf_counter()
    raw_scores = np.asarray(model.predict(pairs, show_progress_bar=False))
    inference_seconds = time.perf_counter() - inference_started
    if raw_scores.ndim != 2 or raw_scores.shape[1] != 3:
        raise RuntimeError(f"expected NLI logits [n,3], received {raw_scores.shape}")
    probabilities = _probabilities(raw_scores)
    entailment_index = label_indices["entailment"]

    records: list[dict[str, Any]] = []
    for case in cases:
        records.append(
            {
                "id": str(case["id"]),
                "source_corpus": str(case["source_corpus"]),
                "category": str(case.get("category", "heldout")),
                "family": str(case.get("family", "heldout")),
                "source_text": _source_text(case),
                "projected_text": _projected_text(case),
                "expected_effects": sorted(case.get("expected_effects", [])),
                "lexical_challenge": bool(case.get("lexical_challenge", False)),
                "should_remain_unresolved": bool(case.get("should_remain_unresolved", False)),
                "calculus_pressure": case.get("calculus_pressure"),
                "expected_refs": list(case.get("expected_refs", [])),
                "entailment": {},
            }
        )
    for row, (case_index, effect) in enumerate(pair_keys):
        records[case_index]["entailment"][effect] = round(
            float(probabilities[row, entailment_index]), 8
        )

    total_seconds = time.perf_counter() - started
    max_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    positive_records = [record for record in records if record["expected_effects"]]
    projected_segment_cases = sum(bool(case.get("segments")) for case in cases)
    return {
        "format_version": 1,
        "experiment": "issue-213-nli-graph-effect-screen",
        "model": model_id,
        "resolved_model_revision": resolved_revision,
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("sentence-transformers", "transformers", "torch", "huggingface-hub")
        },
        "cases": len(cases),
        "issue_160_cases": sum(case["source_corpus"] == "issue-160" for case in cases),
        "heldout_cases": sum(case["source_corpus"] == "issue-213-heldout" for case in cases),
        "candidate_effects": EFFECT_HYPOTHESES,
        "dictionary_free": True,
        "authority": "non-authoritative candidate effects only",
        "grounding_measurement": {
            "source_sentence_provenance": "exact source/projection text retained for every case",
            "source_projection_segment_cases": projected_segment_cases,
            "positive_effect_cases": len(positive_records),
            "model_argument_spans_returned": 0,
            "positive_cases_with_exact_semantic_argument_grounding": 0,
            "semantic_argument_grounding_rate": 0.0,
            "interpretation": (
                "the cross-encoder emits sentence-pair effect scores only; reversible typed "
                "placeholders preserve source anchors but do not identify bind/payload/require "
                "roles, so no candidate is eligible for production authority"
            ),
        },
        "model_snapshot_bytes": snapshot_bytes,
        "offline_feasibility": {
            "initial_snapshot_download_required": True,
            "subsequent_cached_execution_expected": True,
        },
        "runtime": {
            "total_seconds_including_model_load": round(total_seconds, 3),
            "inference_seconds": round(inference_seconds, 3),
            "pair_count": len(pairs),
            "max_rss_kib": max_rss_kib,
        },
        "metrics": [_metrics(records, threshold) for threshold in THRESHOLDS],
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-corpus",
        type=Path,
        default=Path("research/semantic-parser-bakeoff/declaration_cases.json"),
    )
    parser.add_argument(
        "--heldout-corpus",
        type=Path,
        default=Path("research/dependency-semantics/effect_cases.json"),
    )
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run(
        args.base_corpus,
        args.heldout_corpus,
        model_id=args.model,
        revision=args.revision,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
