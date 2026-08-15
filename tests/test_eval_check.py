from pathlib import Path

import pytest

from thorn.eval import _load_cases, _load_check_expectations, main


def test_check_expectations_cover_every_check_enabled_case_exactly() -> None:
    cases = _load_cases(Path("eval/cases"))
    expectations = _load_check_expectations(Path("eval/cases"), cases)
    check_cases = [case for case in cases if "check" in case[1].modes]
    review_cases = [case for case in cases if "review" in case[1].modes]

    assert len(check_cases) >= 52
    assert len(review_cases) == 46
    assert set(expectations) == {expectation.name for _, expectation in check_cases}


def test_deterministic_check_runs_full_matrix_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    cases = _load_cases(Path("eval/cases"))
    check_cases = [case for case in cases if "check" in case[1].modes]
    assert main(["eval/cases", "--check"]) == 0

    output = capsys.readouterr().out
    assert output.count("PASS CHECK ") == len(check_cases)
    assert f'"cases": {len(check_cases)}' in output
    assert '"mode": "check"' in output
    assert '"failures": 0' in output
