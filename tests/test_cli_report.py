from __future__ import annotations

import builtins
from pathlib import Path

from thorn import cli


def _write_clean_project(path: Path) -> None:
    path.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:ok}
Let $x$ be real. Then $x=x$.
\end{theorem}
""",
        encoding="utf-8",
    )


def test_report_mode_is_keyless_and_uses_predictable_output_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    tex = tmp_path / "paper.tex"
    _write_clean_project(tex)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"thorn.audit", "thorn.providers.openai", "openai"}:
            raise AssertionError(f"report attempted model-backed import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert cli.main(["report", str(tex), "--structural-only"]) == 0
    destination = tmp_path / "paper.thorn-report.html"
    assert destination.exists()
    assert f"Report: {destination.resolve()}" in capsys.readouterr().out
    html = destination.read_text(encoding="utf-8")
    assert "thm:ok" in html
    assert "No current result is marked for attention" in html


def test_analyze_can_emit_report_without_corrupting_json_stdout(tmp_path: Path, capsys) -> None:
    tex = tmp_path / "paper.tex"
    _write_clean_project(tex)
    destination = tmp_path / "custom.html"

    assert (
        cli.main(
            [
                "analyze",
                str(tex),
                "--structural-only",
                "--format",
                "json",
                "--report",
                str(destination),
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.out.lstrip().startswith("{")
    assert "Report:" not in captured.out
    assert f"Report: {destination.resolve()}" in captured.err
    assert destination.exists()


def test_open_is_explicit_and_uses_default_browser(tmp_path: Path, monkeypatch, capsys) -> None:
    tex = tmp_path / "paper.tex"
    _write_clean_project(tex)
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda uri: opened.append(uri) or True)

    assert cli.main(["report", str(tex), "--structural-only", "--open"]) == 0
    capsys.readouterr()
    assert opened == [(tmp_path / "paper.thorn-report.html").resolve().as_uri()]


def test_open_without_report_is_rejected(tmp_path: Path, capsys) -> None:
    tex = tmp_path / "paper.tex"
    _write_clean_project(tex)

    assert cli.main(["analyze", str(tex), "--structural-only", "--open"]) == 2
    assert "--open requires" in capsys.readouterr().err
