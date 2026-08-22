from pathlib import Path

import pytest

import thorn.latex as latex_module
from thorn.frontends import DEFAULT_FRONTEND_NAME, get_default_frontend, get_frontend


def test_frontend_default_is_one_explicit_runtime_choice() -> None:
    assert DEFAULT_FRONTEND_NAME == "tree-sitter"
    assert get_default_frontend().name == DEFAULT_FRONTEND_NAME
    assert get_frontend("current").name == DEFAULT_FRONTEND_NAME


def test_extract_project_resolves_default_frontend_at_call_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "paper.tex"
    source.write_text(
        "\\documentclass{article}\n\\begin{document}\n\\end{document}\n",
        encoding="utf-8",
    )
    calls = 0

    def replacement() -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("fresh default sentinel")

    monkeypatch.setattr(latex_module, "get_default_frontend", replacement)
    with pytest.raises(RuntimeError, match="fresh default sentinel"):
        latex_module.extract_project(source)

    assert calls == 1
