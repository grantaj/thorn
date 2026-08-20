"""Project-structure partiality cases for the semantic-dependency contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from thorn.frontend import FrontendDiagnosticKind, LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project
from thorn.project_partiality import normalize_project_structure

FrontendFactory = Callable[[], LatexFrontend]
_FRONTENDS: tuple[FrontendFactory, ...] = (RegexLatexFrontend, PylatexencLatexFrontend)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


def _normalized_project(main: Path, frontend_factory: FrontendFactory):
    return normalize_project_structure(frontend_factory().parse_project(main))


def _assert_current_extraction_fails_closed_on_project_partiality(
    main: Path,
    frontend_factory: FrontendFactory,
) -> None:
    """Characterize the current mechanism without making it the stable contract."""

    with pytest.raises(
        ValueError,
        match=r"indeterminate \\(?:input|include) project structure",
    ):
        extract_project(main, frontend=frontend_factory())


_INDETERMINATE_DIRECT_INCLUDES = (
    r"\input{",
    r"\include{chapter",
    r"\input{{chapter}",
    r"\input{\chapterfile}",
)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
@pytest.mark.parametrize("malformed", _INDETERMINATE_DIRECT_INCLUDES)
def test_malformed_direct_include_is_exact_project_partiality_not_guessed_order(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
    malformed: str,
) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "chapter.tex"
    child.write_text(
        r"""\begin{theorem}\label{thm:child}
Child authority must not be guessed into the project.
\end{theorem}
""",
        encoding="utf-8",
    )
    source = (
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{malformed}\n"
        "\\begin{theorem}\\label{thm:after}\n"
        "This result occurs after an indeterminate project boundary.\n"
        "\\end{theorem}\n"
        "\\end{document}\n"
    )
    main.write_text(source, encoding="utf-8")

    parsed = _normalized_project(main, frontend_factory)
    partiality = [
        diagnostic
        for diagnostic in parsed.diagnostics
        if diagnostic.kind == FrontendDiagnosticKind.PROJECT_PARTIALITY
    ]

    assert len(partiality) == 1
    diagnostic = partiality[0]
    assert diagnostic.source is not None
    assert diagnostic.source.text(source) == malformed
    assert diagnostic.source.start_line == 5
    assert [Path(file.path).name for file in parsed.files] == ["main.tex"]

    _assert_current_extraction_fails_closed_on_project_partiality(main, frontend_factory)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_include_like_comment_and_verbatim_are_not_project_structure(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "chapter.tex"
    child.write_text(
        r"""\begin{theorem}\label{thm:child}
Literal include-like text must not make this reachable.
\end{theorem}
""",
        encoding="utf-8",
    )
    main.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
% \input{chapter}
\begin{verbatim}
\include{chapter}
\end{verbatim}
\begin{theorem}\label{thm:main}
Only the real source structure is authoritative.
\end{theorem}
\end{document}
""",
        encoding="utf-8",
    )

    parsed = _normalized_project(main, frontend_factory)

    assert not any(
        diagnostic.kind
        in {FrontendDiagnosticKind.MISSING_FILE, FrontendDiagnosticKind.PROJECT_PARTIALITY}
        for diagnostic in parsed.diagnostics
    )
    assert [Path(file.path).name for file in parsed.files] == ["main.tex"]

    project = extract_project(main, frontend=frontend_factory())
    assert [unit.identifier for unit in project.units] == ["thm:main"]


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_unused_macro_definition_does_not_create_project_partiality(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    source = r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\newcommand{\loadchapter}[1]{\input{#1}}
\begin{document}
\begin{theorem}\label{thm:main}
An unused macro definition is not an executed project boundary.
\end{theorem}
\end{document}
"""
    main.write_text(source, encoding="utf-8")

    parsed = _normalized_project(main, frontend_factory)

    assert not any(
        diagnostic.kind == FrontendDiagnosticKind.PROJECT_PARTIALITY
        for diagnostic in parsed.diagnostics
    )
    assert [Path(file.path).name for file in parsed.files] == ["main.tex"]

    project = extract_project(main, frontend=frontend_factory())
    assert [unit.identifier for unit in project.units] == ["thm:main"]


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_static_include_target_is_not_restricted_to_ascii_filename_grammar(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "chapître+α.tex"
    child.write_text(
        r"""\begin{theorem}\label{thm:child}
Static filename spelling is workspace evidence, not Thorn mathematical semantics.
\end{theorem}
""",
        encoding="utf-8",
    )
    main.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\input{chapître+α}
""",
        encoding="utf-8",
    )

    parsed = _normalized_project(main, frontend_factory)

    assert not any(
        diagnostic.kind == FrontendDiagnosticKind.PROJECT_PARTIALITY
        for diagnostic in parsed.diagnostics
    )
    assert {Path(file.path).name for file in parsed.files} == {
        "main.tex",
        "chapître+α.tex",
    }

    project = extract_project(main, frontend=frontend_factory())
    assert [unit.identifier for unit in project.units] == ["thm:child"]
