from pathlib import Path

import pytest

from thorn.eval import _load_cases, _load_check_expectations, main


def test_check_expectations_cover_every_eval_case_exactly() -> None:
    cases = _load_cases(Path("eval/cases"))
    expectations = _load_check_expectations(Path("eval/cases"), cases)

    assert len(cases) == 46
    assert set(expectations) == {expectation.name for _, expectation in cases}


def test_deterministic_check_runs_full_matrix_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    cases = _load_cases(Path("eval/cases"))
    assert main(["eval/cases", "--check"]) == 0

    output = capsys.readouterr().out
    assert output.count("PASS CHECK ") == len(cases)
    assert '"mode": "check"' in output
    assert '"failures": 0' in output
