import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from thorn.frontend import SourceSpan
from thorn.frontends import get_default_frontend
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.research.graph_effects import (
    CONDITIONS,
    HYPOTHETICAL,
    INTRODUCE,
    NAME,
    SUPPORT_NOUNS,
    SUPPORT_VERBS,
    adapt_linguistic_span_projection,
    build_case,
    compile_effects,
)
from thorn.source_projection import (
    LinguisticSpanPlaceholder,
    LinguisticSpanProjection,
    LinguisticSpanTokenKind,
    build_linguistic_projection,
)
from thorn.spacy_linguistic import SpacyLinguisticFrontend


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


def _span(source: str, raw: str) -> SourceSpan:
    start = source.index(raw)
    end = start + len(raw)
    return SourceSpan(
        file="paper.tex",
        start_offset=start,
        end_offset=end,
        start_line=1,
        start_column=start + 1,
        end_line=1,
        end_column=end + 1,
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


def test_production_projection_adapter_preserves_result_identity() -> None:
    source = r"Using \ref{lem:key}, we obtain $x>0$."
    projected = "Using THORNRESULT1, we obtain THORNMATH1."
    result_start = projected.index("THORNRESULT1")
    math_start = projected.index("THORNMATH1")
    result_raw = r"\ref{lem:key}"
    math_raw = "$x>0$"
    projection = LinguisticSpanProjection(
        text=projected,
        placeholders=(
            LinguisticSpanPlaceholder(
                token="THORNRESULT1",
                kind=LinguisticSpanTokenKind.RESULT_REFERENCE,
                source=_span(source, result_raw),
                raw=result_raw,
                projected_start=result_start,
                projected_end=result_start + len("THORNRESULT1"),
                label="lem:key",
            ),
            LinguisticSpanPlaceholder(
                token="THORNMATH1",
                kind=LinguisticSpanTokenKind.MATH,
                source=_span(source, math_raw),
                raw=math_raw,
                projected_start=math_start,
                projected_end=math_start + len("THORNMATH1"),
            ),
        ),
    )

    adapted = adapt_linguistic_span_projection(projection)

    assert adapted.case.source == source
    assert adapted.case.projected == "Using THORNREF1, we obtain THORNMATH1."
    reference = adapted.result_reference("THORNREF1")
    assert reference.label == "lem:key"
    assert reference.raw == result_raw
    assert reference.source == _span(source, result_raw)
    assert adapted.case.source_span(6, 15) == (
        source.index(result_raw),
        source.index(result_raw) + len(result_raw),
    )


def test_production_source_projection_reaches_frozen_compiler(tmp_path: Path) -> None:
    if importlib.util.find_spec("en_core_web_sm") is None:
        pytest.skip("production projection integration requires the normal local spaCy model")

    main = tmp_path / "main.tex"
    main.write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Using \\ref{lem:key}, we obtain $x>0$.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    parsed = get_default_frontend().parse_project(main)
    file = parsed.files[0]
    start = file.raw.index("Using")
    end = file.raw.index(".", start) + 1
    projection = build_linguistic_projection(file).project_span(
        file.span(start, end),
        result_identifiers={"lem:key"},
    )
    adapted = adapt_linguistic_span_projection(projection)
    document = SpacyLinguisticFrontend().parse(adapted.case.projected)

    frames = compile_effects(adapted.case, document)
    requirements = [frame for frame in frames if frame.operation == "require"]

    assert len(requirements) == 1
    assert [item.text for item in requirements[0].prerequisites] == ["THORNREF1"]
    reference = adapted.result_reference("THORNREF1")
    assert reference.label == "lem:key"
    assert reference.raw == r"\ref{lem:key}"
    assert reference.source.text(file.raw) == r"\ref{lem:key}"
    assert requirements[0].exact


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
