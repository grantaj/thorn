import builtins
import json
from pathlib import Path

from thorn import cli
from thorn.spacy_linguistic import LinguisticFrontendUnavailable


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


def _write_clean_project(path: Path) -> None:
    path.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:ok}
Let $x$ be real. Then $x=x$.
\end{theorem}
""",
        encoding="utf-8",
    )


def test_check_uses_local_linguistic_frontend_by_default(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    tex = tmp_path / "main.tex"
    _write_clean_project(tex)
    sentinel = object()
    constructed: list[object] = []
    observed: list[object | None] = []

    def make_frontend() -> object:
        constructed.append(sentinel)
        return sentinel

    real_extract_project = cli.extract_project

    def capture_extract_project(main_file, *, frontend=None, linguistic_frontend=None):
        observed.append(linguistic_frontend)
        # The test is about CLI plumbing, so keep the extraction itself parser-neutral.
        return real_extract_project(main_file, frontend=frontend)

    monkeypatch.setattr(cli, "SpacyLinguisticFrontend", make_frontend, raising=False)
    monkeypatch.setattr(cli, "extract_project", capture_extract_project)

    assert cli.main(["check", str(tex)]) == 0
    assert constructed == [sentinel]
    assert observed == [sentinel]
    assert "no deterministic structural diagnostics" in capsys.readouterr().out


def test_structural_only_does_not_construct_linguistic_frontend(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    tex = tmp_path / "main.tex"
    _write_clean_project(tex)
    observed: list[object | None] = []

    def forbidden_frontend() -> object:
        raise AssertionError("--structural-only attempted to construct the NLP frontend")

    real_extract_project = cli.extract_project

    def capture_extract_project(main_file, *, frontend=None, linguistic_frontend=None):
        observed.append(linguistic_frontend)
        return real_extract_project(main_file, frontend=frontend)

    monkeypatch.setattr(cli, "SpacyLinguisticFrontend", forbidden_frontend, raising=False)
    monkeypatch.setattr(cli, "extract_project", capture_extract_project)

    assert cli.main(["check", str(tex), "--structural-only"]) == 0
    assert observed == [None]
    assert "no deterministic structural diagnostics" in capsys.readouterr().out


def test_missing_local_nlp_explains_structural_only_escape_hatch(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    tex = tmp_path / "main.tex"
    _write_clean_project(tex)

    def unavailable() -> object:
        raise LinguisticFrontendUnavailable("spaCy model 'en_core_web_sm' is not installed locally")

    monkeypatch.setattr(cli, "SpacyLinguisticFrontend", unavailable, raising=False)

    assert cli.main(["check", str(tex)]) == 2
    error = capsys.readouterr().err
    assert "local linguistic frontend" in error
    assert "--structural-only" in error


def test_structural_only_check_requires_no_key_and_cannot_import_model_path(
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

    assert cli.main(["check", str(tex), "--structural-only"]) == 1
    output = capsys.readouterr().out
    assert "TH103" in output
    assert "Missing internal reference" in output


def test_check_json_and_fail_on_never(tmp_path: Path, capsys) -> None:
    tex = tmp_path / "main.tex"
    _write_missing_reference(tex)

    assert (
        cli.main(
            [
                "check",
                str(tex),
                "--structural-only",
                "--format",
                "json",
                "--fail-on",
                "never",
            ]
        )
        == 0
    )
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

    assert cli.main(["review", str(tex), "--structural-only"]) == 2
    assert "run `thorn check`" in capsys.readouterr().err

    assert cli.main([str(tex), "--structural-only"]) == 2
    assert "run `thorn check`" in capsys.readouterr().err


def test_clean_structural_only_check_returns_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    tex = tmp_path / "main.tex"
    _write_clean_project(tex)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert cli.main(["check", str(tex), "--structural-only"]) == 0
    assert "no deterministic structural diagnostics" in capsys.readouterr().out
