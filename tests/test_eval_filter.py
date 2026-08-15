import thorn.eval as eval_module


def test_case_filter_selects_one_fixture(capsys) -> None:
    assert (
        eval_module.main(
            [
                "eval/cases",
                "--validate-only",
                "--case-filter",
                "decreasing-limit clean control",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert output.count("OK   ") == 1
    assert '"cases": 1' in output


def test_case_filter_rejects_no_matches(capsys) -> None:
    assert (
        eval_module.main(
            [
                "eval/cases",
                "--validate-only",
                "--case-filter",
                "definitely-not-a-real-case",
            ]
        )
        == 2
    )
    output = capsys.readouterr().out
    assert "no cases matched --case-filter" in output
