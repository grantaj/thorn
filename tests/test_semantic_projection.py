from collections.abc import Callable
from pathlib import Path

import pytest

from thorn.frontend import LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.source_projection import LinguisticSpanTokenKind, build_linguistic_projection

FrontendFactory = Callable[[], LatexFrontend]
_FRONTENDS: tuple[FrontendFactory, ...] = (RegexLatexFrontend, PylatexencLatexFrontend)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_semantic_projection_is_typed_and_reversible(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\documentclass{article}
\usepackage{amsmath,amsthm}
\newtheorem{lemma}{Lemma}
\begin{document}
\begin{lemma}\label{lem:base}
A base fact.
\end{lemma}
\begin{proof}
The base case holds.
\end{proof}
\begin{lemma}\label{lem:main}
A consequence.
\end{lemma}
\begin{proof}
By Lemma~\ref{lem:base}, $P(x)$ follows from \eqref{eq:key}; see \ref{fig:plot}.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )
    parsed = frontend_factory().parse_project(tex)
    file = parsed.files[0]
    proofs = [environment for environment in file.environments if environment.name == "proof"]
    assert len(proofs) == 2

    source_projection = build_linguistic_projection(file)
    projection = source_projection.project_span(
        proofs[1].body_span,
        result_identifiers={"lem:base", "lem:main"},
    )
    assert projection.text.strip() == (
        "By Lemma~THORNRESULT1, THORNMATH1 follows from THORNEQUATION1; "
        "see THORNREFERENCE1."
    )
    assert [item.kind for item in projection.placeholders] == [
        LinguisticSpanTokenKind.RESULT_REFERENCE,
        LinguisticSpanTokenKind.MATH,
        LinguisticSpanTokenKind.EQUATION_REFERENCE,
        LinguisticSpanTokenKind.GENERIC_REFERENCE,
    ]
    assert [item.label for item in projection.placeholders] == [
        "lem:base",
        None,
        "eq:key",
        "fig:plot",
    ]
    assert [item.raw for item in projection.placeholders] == [
        r"\ref{lem:base}",
        "$P(x)$",
        r"\eqref{eq:key}",
        r"\ref{fig:plot}",
    ]
    for item in projection.placeholders:
        assert item.source.text(file.raw) == item.raw
        assert projection.text[item.projected_start : item.projected_end] == item.token


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_math_replacement_owns_nested_reference_span(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\begin{document}
\[
x_{\ref{eq:index}} = 1
\]
\end{document}
""",
        encoding="utf-8",
    )
    parsed = frontend_factory().parse_project(tex)
    file = parsed.files[0]
    display = next(math for math in file.math if math.delimiter == r"\[\]")
    projection = build_linguistic_projection(file).project_span(
        display.span,
        result_identifiers=set(),
    )
    assert projection.text == "THORNMATH1"
    assert len(projection.placeholders) == 1
    assert projection.placeholders[0].kind == LinguisticSpanTokenKind.MATH
