from pathlib import Path

from thorn.eval import _load_cases
from thorn.latex import extract_units


def test_eval_corpus_is_well_formed() -> None:
    cases = _load_cases(Path("eval/cases"))
    assert len(cases) >= 5

    bad = 0
    clean = 0
    for tex_path, expectation in cases:
        units = extract_units(tex_path)
        assert len(units) == 1
        assert units[0].proof is not None
        if expectation.kind == "finding":
            bad += 1
            assert expectation.accepted_categories
        else:
            clean += 1

    assert bad >= 3
    assert clean >= 2
