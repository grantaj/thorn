from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from thorn.linguistic_declarations import propose_linguistic_declarations
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend

_ROOT = Path(__file__).parents[1]
_RUNNER = _ROOT / "research" / "semantic-parser-bakeoff" / "run_declaration_bakeoff.py"
_CASES = _RUNNER.with_name("declaration_cases.json")


def _runner_module():
    spec = importlib.util.spec_from_file_location("thorn_issue_160_candidate_corpus", _RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _spacy_frontend_or_skip() -> SpacyLinguisticFrontend:
    frontend = SpacyLinguisticFrontend()
    try:
        frontend.parse("Thorn normalizes local linguistic evidence.")
    except (LinguisticFrontendUnavailable, OSError) as exc:
        pytest.skip(str(exc))
    return frontend


def test_production_candidate_core_preserves_issue_160_hybrid_disposition() -> None:
    runner = _runner_module()
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    frontend = _spacy_frontend_or_skip()

    true_positive = false_positive = missed = 0
    false_positive_ids: set[str] = set()
    missed_ids: set[str] = set()
    for case in payload["cases"]:
        built = runner.build_case(case)
        proposals = propose_linguistic_declarations(frontend.parse(built.projected))
        expected = {
            (item["role"], item["term"].casefold()) for item in case.get("expected", [])
        }
        actual = {(item.role.value, item.term.casefold()) for item in proposals}
        true_positive += len(expected & actual)
        false_positive += len(actual - expected)
        missed += len(expected - actual)
        if actual - expected:
            false_positive_ids.add(case["id"])
        if expected - actual:
            missed_ids.add(case["id"])

    # Slice C productionizes the bounded #160 hybrid; it does not grow grammar
    # to chase the deliberately held-out misses or turn proposals into authority.
    assert true_positive == 18
    assert false_positive == 6
    assert missed == 3
    assert false_positive_ids == {
        "named-math-before",
        "transitive-hybrid",
        "negative-useful",
        "negative-display-label",
        "negative-quotation",
        "negative-called-metaphor",
    }
    assert missed_ids == {
        "named-deemed",
        "named-math-before",
        "transitive-hybrid",
    }
