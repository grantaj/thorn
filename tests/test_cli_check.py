import builtins
import json
from pathlib import Path

from thorn import cli


def _write_missing_reference(path: Path) -> None:
    path.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:missing}
A statement.
\end{theorem}
\begin{proof}
By Theorem~\ref{thm:not-there}.
\end{proof}
""",
        encoding="utf-8",
    )


def test_check_requires_no_key_and_cannot_import_model_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    tex = tmp_path / "main.tex"
    _write_missing_reference(tex)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"thorn.audit", "thorn.providers.openai"}:
            raise AssertionError(f"check attempted model-backed import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert cli.main(["check", str(tex)]) == 1
    output = capsys.readouterr().out
    assert "TH103" in output
    assert "Missing internal reference" in output


def test_check_json_and_fail_on_never(tmp_path: Path, capsys) -> None:
    tex = tmp_path / "main.tex"
    _write_missing_reference(tex)

    assert cli.main(["check", str(tex), "--format", "json", "--fail-on", "never"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "check"
    assert payload["findings"][0]["rule"] == "TH103"


def test_review_and_legacy_mode_still_require_key(tmp_path: Path, monkeypatch, capsys) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:ok}
$1=1$.
\end{theorem}
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert cli.main(["review", str(tex)]) == 2
    assert "run `thorn check`" in capsys.readouterr().err

    assert cli.main([str(tex)]) == 2
    assert "run `thorn check`" in capsys.readouterr().err


def test_clean_check_returns_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:ok}
Let $x$ be real. Then $x=x$.
\end{theorem}
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert cli.main(["check", str(tex)]) == 0
    assert "no deterministic structural diagnostics" in capsys.readouterr().out
