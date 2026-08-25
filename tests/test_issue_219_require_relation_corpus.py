from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_CASES = _ROOT / "research" / "dependency-semantics" / "require_relation_cases.json"
_EXPECTED = {"REQUIRE", "NON_REQUIRE", "UNRESOLVED"}


def _load() -> dict[str, object]:
    return json.loads(_CASES.read_text(encoding="utf-8"))


def test_issue_219_require_benchmark_is_focused_and_balanced() -> None:
    payload = _load()
    assert payload["version"] == 1
    assert payload["issue"] == 219

    cases = payload["cases"]
    assert isinstance(cases, list)
    assert len(cases) == 34
    assert len({case["id"] for case in cases}) == len(cases)

    references = [
        reference
        for case in cases
        for reference in case["references"]
    ]
    assert len(references) == 39

    dispositions = [reference["expected"] for reference in references]
    assert set(dispositions) == _EXPECTED
    assert dispositions.count("REQUIRE") >= 15
    assert dispositions.count("NON_REQUIRE") >= 12
    assert dispositions.count("UNRESOLVED") >= 6


def test_issue_219_reference_provenance_is_exact_and_supplied() -> None:
    payload = _load()
    cases = payload["cases"]
    assert isinstance(cases, list)

    for case in cases:
        context = case["context"]
        assert payload["owner_surface"] not in context
        assert case["owner"] == "RESULT_CURRENT"

        for reference in case["references"]:
            placeholder = reference["placeholder"]
            provenance = reference["provenance"]
            start = provenance["char_start"]
            end = provenance["char_end"]

            assert context.count(placeholder) == 1
            assert context[start:end] == placeholder
            assert provenance["source_id"] == f"synthetic://issue-219/{case['id']}"
            assert reference["resolved_target"].startswith("RESULT_")


def test_issue_219_pressures_resolve_not_equal_require() -> None:
    payload = _load()
    cases = payload["cases"]
    assert isinstance(cases, list)

    subtypes = {case["subtype"] for case in cases}
    assert {
        "mention_only",
        "comparison",
        "historical_attribution",
        "reported_use",
        "explicit_non_use",
        "hypothetical_non_use",
        "background_reference",
        "quotation",
        "explicit_independence",
        "ambiguous_rhetorical",
        "multi_reference_discrimination",
        "joint_support",
        "alternative_support",
    } <= subtypes

    positive_operator_absent = sum(
        reference["expected"] == "REQUIRE"
        and not case["frozen_operator_present"]
        for case in cases
        for reference in case["references"]
    )
    assert positive_operator_absent >= 8

    multi_reference = [case for case in cases if len(case["references"]) > 1]
    assert len(multi_reference) >= 4
    assert any(
        {reference["expected"] for reference in case["references"]}
        == {"REQUIRE", "NON_REQUIRE"}
        for case in multi_reference
    )
