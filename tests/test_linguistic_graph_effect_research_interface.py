import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.research.graph_effects import (
    CONDITIONS,
    HYPOTHETICAL,
    INTRODUCE,
    NAME,
    SUPPORT_NOUNS,
    SUPPORT_VERBS,
    build_case,
    compile_effects,
)


def _token(
    index: int,
    text: str,
    lemma: str,
    pos: str,
    dependency: str,
    head_index: int,
    start: int,
    end: int,
) -> LinguisticToken:
    return LinguisticToken(
        index=index,
        text=text,
        lemma=lemma,
        pos=pos,
        dependency=dependency,
        head_index=head_index,
        sentence_index=0,
        start=start,
        end=end,
    )


def test_frozen_operator_inventory_is_exposed_unchanged() -> None:
    assert {"assume", "define", "fix", "let", "set", "suppose"} == INTRODUCE
    assert {"call", "mean", "say", "term"} == NAME
    assert {"apply", "follow", "invoke", "use"} == SUPPORT_VERBS
    assert {"consequence"} == SUPPORT_NOUNS
    assert {"if", "provided", "when", "whenever"} == CONDITIONS
    assert {"could", "might", "would"} == HYPOTHETICAL


def test_research_interface_preserves_exact_reference_grounding() -> None:
    case = build_case(
        {
            "segments": [
                "Using ",
                {"raw": r"\ref{lem:key}", "projected": "THORNREF1"},
                ", we obtain ",
                {"raw": "x>0", "projected": "THORNMATH1"},
                ".",
            ]
        }
    )
    document = LinguisticDocument(
        text=case.projected,
        tokens=[
            _token(0, "Using", "use", "VERB", "ROOT", 0, 0, 5),
            _token(1, "THORNREF1", "THORNREF1", "PROPN", "pobj", 0, 6, 15),
            _token(2, "we", "we", "PRON", "nsubj", 3, 17, 19),
            _token(3, "obtain", "obtain", "VERB", "conj", 0, 20, 26),
            _token(4, "THORNMATH1", "THORNMATH1", "PROPN", "dobj", 3, 27, 37),
            _token(5, ".", ".", "PUNCT", "punct", 0, 37, 38),
        ],
    )

    frames = compile_effects(case, document)

    assert len(frames) == 1
    frame = frames[0]
    assert frame.operation == "require"
    assert frame.rule == "support-operator"
    assert [item.text for item in frame.prerequisites] == ["THORNREF1"]
    assert frame.prerequisites[0].source == (6, 19)
    assert frame.exact


def test_research_interface_preserves_noninvertible_projection_as_ungrounded() -> None:
    case = build_case(
        {
            "segments": [
                {"raw": r"\ref{lem:key}", "projected": "THORNREF1"},
            ]
        }
    )

    assert case.source_span(0, len("THORNREF1")) == (0, len(r"\ref{lem:key}"))
    assert case.source_span(1, 5) is None


def test_frozen_measurement_is_exactly_reproducible(tmp_path: Path) -> None:
    if importlib.util.find_spec("en_core_web_sm") is None:
        pytest.skip("exact #215 replay requires the normal local spaCy model")

    output = tmp_path / "structural-effect-measurements.json"
    subprocess.run(
        [
            sys.executable,
            "research/dependency-semantics/run_structural_effect_screen.py",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    expected = json.loads(
        Path("research/dependency-semantics/structural_effect_measurements.json").read_text()
    )
    assert json.loads(output.read_text()) == expected
