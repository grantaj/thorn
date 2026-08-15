from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from thorn.linguistic import LinguisticDocument
from thorn.spacy_linguistic import SpacyLinguisticFrontend

_CASES = Path(__file__).with_name("cases.json")
_EXPECTED_METRICS = {
    "definition": {
        "positive_cases": 7,
        "negative_cases": 0,
        "positive_templates": 4,
        "positive_negative_collisions": 0,
    },
    "introduction": {
        "positive_cases": 13,
        "negative_cases": 0,
        "positive_templates": 3,
        "positive_negative_collisions": 0,
    },
    "prior_claim": {
        "positive_cases": 15,
        "negative_cases": 5,
        "positive_templates": 5,
        "positive_negative_collisions": 0,
    },
    "result_support": {
        "positive_cases": 16,
        "negative_cases": 8,
        "positive_templates": 11,
        "positive_negative_collisions": 3,
    },
    "trailing_binder": {
        "positive_cases": 6,
        "negative_cases": 0,
        "positive_templates": 1,
        "positive_negative_collisions": 0,
    },
}


def _signature(row: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return tuple(row["source_path"]), tuple(row["target_path"])


def _historical_path(document: LinguisticDocument, placeholder: object) -> list[str]:
    """Reproduce the checked-in #29 harness's placeholder occurrence semantics.

    The synthetic corpus can repeat the same placeholder token in one sentence.
    The original harness built a token-position dictionary, so the last repeated
    occurrence won. Production projections use unique per-occurrence placeholders,
    but this compatibility rule is required to compare against the historical
    70-case benchmark without silently changing what that experiment measured.
    """

    if placeholder is None:
        return []
    token_text = str(placeholder)
    matches = [token for token in document.tokens if token.text == token_text]
    if not matches:
        raise AssertionError(f"spaCy lost placeholder {token_text}")
    return document.root_path_signature(matches[-1].index)


def main() -> int:
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    frontend = SpacyLinguisticFrontend()
    rows: list[dict[str, Any]] = []

    for case in payload["cases"]:
        expected = case["expected"]
        document = frontend.parse(str(case["text"]))
        rows.append(
            {
                "id": case["id"],
                "task": case["task"],
                "family": case["family"],
                "source_path": _historical_path(document, expected.get("source")),
                "target_path": _historical_path(document, expected.get("target")),
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["task"])].append(row)

    actual_metrics: dict[str, dict[str, int]] = {}
    for task, items in grouped.items():
        positives = [row for row in items if row["family"] == "positive"]
        negatives = [row for row in items if row["family"] == "negative"]
        positive_templates = {_signature(row) for row in positives}
        negative_templates = {_signature(row) for row in negatives}
        actual_metrics[task] = {
            "positive_cases": len(positives),
            "negative_cases": len(negatives),
            "positive_templates": len(positive_templates),
            "positive_negative_collisions": len(positive_templates & negative_templates),
        }

    assert actual_metrics == _EXPECTED_METRICS, actual_metrics

    print(
        json.dumps(
            {
                "cases": len(rows),
                "metrics": actual_metrics,
                "note": (
                    "result_support collisions are an intentional ambiguity baseline, "
                    "not a parser defect to patch with lexical exceptions"
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
