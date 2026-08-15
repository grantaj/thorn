from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

_CASES = (
    Path(__file__).resolve().parents[1]
    / "research"
    / "semantic-parser-bakeoff"
    / "cases.json"
)
_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


def _cases() -> list[dict[str, object]]:
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert isinstance(cases, list)
    return cases


def test_benchmark_has_stable_parser_independent_shape() -> None:
    cases = _cases()
    assert len(cases) == 70

    identifiers = [str(case["id"]) for case in cases]
    assert len(set(identifiers)) == len(identifiers)
    assert {str(case["task"]) for case in cases} == {
        "result_support",
        "prior_claim",
        "introduction",
        "definition",
        "trailing_binder",
    }

    family_counts = Counter((str(case["task"]), str(case["family"])) for case in cases)
    assert family_counts == Counter(
        {
            ("result_support", "positive"): 16,
            ("result_support", "negative"): 8,
            ("prior_claim", "positive"): 15,
            ("prior_claim", "negative"): 5,
            ("introduction", "positive"): 13,
            ("definition", "positive"): 7,
            ("trailing_binder", "positive"): 6,
        }
    )


def test_expected_entities_are_present_in_each_case_text() -> None:
    for case in _cases():
        text = str(case["text"])
        placeholders = set(_PLACEHOLDER_RE.findall(text))
        expected = case["expected"]
        assert isinstance(expected, dict)

        source = expected.get("source")
        target = expected.get("target")
        if source is not None:
            assert str(source) in placeholders
        if target is not None:
            assert str(target) in placeholders

        relation = str(expected["relation"])
        assert relation in {"support", "none", "introduce", "define", "bind"}
