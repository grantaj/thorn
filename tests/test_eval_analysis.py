from pathlib import Path

import pytest

from thorn.eval import _load_analysis_expectations, _load_cases, main


def test_analysis_expectations_cover_every_analysis_enabled_case_exactly() -> None:
    cases = _load_cases(Path("eval/cases"))
    expectations = _load_analysis_expectations(Path("eval/cases"), cases)
    analysis_cases = [case for case in cases if "analyze" in case[1].modes]
    review_cases = [case for case in cases if "review" in case[1].modes]

    assert len(analysis_cases) >= 52
    assert len(review_cases) == 54
    assert set(expectations) == {expectation.name for _, expectation in analysis_cases}


def test_deterministic_analysis_runs_full_matrix_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    cases = _load_cases(Path("eval/cases"))
    analysis_cases = [case for case in cases if "analyze" in case[1].modes]
    assert main(["eval/cases", "--analyze"]) == 0

    output = capsys.readouterr().out
    assert output.count("PASS ANALYZE ") == len(analysis_cases)
    assert f'"cases": {len(analysis_cases)}' in output
    assert '"mode": "analyze"' in output
    assert '"failures": 0' in output