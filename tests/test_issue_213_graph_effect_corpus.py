from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_CASES = _ROOT / "research" / "dependency-semantics" / "effect_cases.json"
_GRAPH_EFFECTS = {"declare", "require", "visibility", "status"}


def test_issue_213_heldouts_use_only_graph_semantic_effects() -> None:
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["version"] == 1
    assert len(cases) == 28
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(set(case["expected_effects"]) <= _GRAPH_EFFECTS for case in cases)
    assert all("closure" not in case["expected_effects"] for case in cases)


def test_issue_213_heldouts_pressure_false_authority_and_calculus_boundaries() -> None:
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    by_id = {case["id"]: case for case in cases}

    assert sum(not case["expected_effects"] for case in cases) >= 10
    assert sum(bool(case.get("lexical_challenge")) for case in cases) >= 10
    assert sum(bool(case.get("should_remain_unresolved")) for case in cases) >= 3
    assert {case.get("calculus_pressure") for case in cases} >= {
        "scope_termination",
        "retraction",
        "joint_support",
        "alternative_support",
        None,
    }
    assert "quotation" in by_id["negative-ref-quotation"]["text"].casefold()
    assert "another paper" in by_id["negative-ref-attribution"]["text"].casefold()
    assert by_id["negative-ref-not-used"]["expected_effects"] == []


def test_issue_213_reference_endpoints_remain_typed_source_anchors() -> None:
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]

    ref_cases = [case for case in cases if case.get("expected_refs")]
    assert ref_cases
    for case in ref_cases:
        text = case["text"]
        for reference in case["expected_refs"]:
            assert reference.startswith("THORNREF")
            assert reference in text

    assert any(len(case["expected_refs"]) == 2 for case in ref_cases)
