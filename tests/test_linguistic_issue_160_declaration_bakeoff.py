from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[1]
_RUNNER = _ROOT / "research" / "semantic-parser-bakeoff" / "run_declaration_bakeoff.py"
_CASES = _RUNNER.with_name("declaration_cases.json")


def _module():
    spec = importlib.util.spec_from_file_location("thorn_issue_160_bakeoff", _RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_issue_160_corpus_has_required_public_adversarial_families() -> None:
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    categories = {case["category"] for case in cases}
    assert len(cases) == 36
    assert {
        "named_definition",
        "ambient",
        "inline_math",
        "transitive",
        "negative",
        "source_exclusion",
    } <= categories
    assert sum(len(case["expected"]) for case in cases) == 21
    assert any(case.get("lexical_challenge") for case in cases)
    assert any(case.get("transitive_terms") for case in cases)
    assert any(case.get("scope_downstream_without_term") for case in cases)


def test_issue_160_projection_manifest_is_reversible_and_offset_safe() -> None:
    module = _module()
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    saw_non_identity = False
    for case in payload["cases"]:
        built = module.build_case(case)
        assert built.source
        for segment in built.segments:
            assert built.source[segment.source_start : segment.source_end] == segment.raw
            assert (
                built.projected[segment.projected_start : segment.projected_end]
                == segment.projected
            )
            saw_non_identity |= segment.raw != segment.projected
    assert saw_non_identity


def test_issue_160_frozen_phrase_baseline_is_measured_not_extended() -> None:
    module = _module()
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    report = module._evaluate_strategy("baseline", payload["cases"], None)
    assert report["true_positive_candidates"] == 13
    assert report["false_positive_candidates"] == 3
    assert report["missed_candidates"] == 8
    assert report["precision"] == 0.812
    assert report["recall"] == 0.619
    assert report["lexical_challenge_recall"] == 0.125
    assert report["provenance_failures"] == 0
    assert report["transitive_cases_satisfied"] == "1/2"


def test_issue_160_spacy_measurement_probe() -> None:
    import pytest

    from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend

    module = _module()
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    frontend = SpacyLinguisticFrontend()
    try:
        frontend.parse("A map is called balanced when THORNMATH1 holds.")
    except (LinguisticFrontendUnavailable, OSError):
        pytest.skip("local spaCy English model is not installed")
    reports = {
        name: module._evaluate_strategy(name, payload["cases"], frontend)
        for name in ("dependency", "hybrid")
    }
    summary = {
        name: {
            key: report[key]
            for key in (
                "true_positive_candidates",
                "false_positive_candidates",
                "missed_candidates",
                "precision",
                "recall",
                "lexical_challenge_recall",
                "provenance_failures",
                "ambiguity_marked_candidates",
                "transitive_cases_satisfied",
            )
        }
        for name, report in reports.items()
    }
    raise AssertionError("ISSUE160_MEASUREMENT=" + json.dumps(summary, sort_keys=True))
