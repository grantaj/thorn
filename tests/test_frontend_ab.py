from pathlib import Path

from thorn.frontends import RegexLatexFrontend, get_frontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project


def test_frontend_registry_selects_independent_backends() -> None:
    assert get_frontend("current").name == "regex"
    assert get_frontend("regex").name == "regex"
    assert get_frontend("pylatexenc").name == "pylatexenc"


def test_result_graph_snapshots_match_across_backends(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{lemma}\label{lem:a}A.\end{lemma}
\begin{proof}Proof A.\end{proof}
\begin{theorem}\label{thm:b}B.\end{theorem}
\begin{proof}By \ref{lem:a}.\end{proof}
""",
        encoding="utf-8",
    )

    regex = extract_project(tex, frontend=RegexLatexFrontend())
    pylatexenc = extract_project(tex, frontend=PylatexencLatexFrontend())

    assert [unit.model_dump(mode="json") for unit in pylatexenc.units] == [
        unit.model_dump(mode="json") for unit in regex.units
    ]
    assert pylatexenc.dependency_graph.model_dump(mode="json") == regex.dependency_graph.model_dump(
        mode="json"
    )


def test_unknown_mandatory_macro_disagreement_is_visible(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    source = r"Before \mystery{payload} after."
    tex.write_text(source, encoding="utf-8")

    regex_file = RegexLatexFrontend().parse_project(tex).files[0]
    pylatexenc_file = PylatexencLatexFrontend().parse_project(tex).files[0]

    regex_macro = next(macro for macro in regex_file.macros if macro.name == "mystery")
    pylatexenc_macro = next(macro for macro in pylatexenc_file.macros if macro.name == "mystery")

    # With no macro signature available, whether the brace group is an argument
    # is genuinely unknowable from LaTeX surface syntax alone. The compatibility
    # regex backend historically consumes it; pylatexenc conservatively leaves
    # it as following content. Issue #16 records this rather than forcing one
    # backend to imitate the other and hiding the parser disagreement.
    assert [argument.value for argument in regex_macro.arguments] == ["payload"]
    assert pylatexenc_macro.arguments == []
    assert regex_macro.span.end_offset > pylatexenc_macro.span.end_offset

    # Both still preserve exact provenance for the syntax they claim to own.
    assert regex_macro.span.text(source) == regex_macro.raw
    assert pylatexenc_macro.span.text(source) == pylatexenc_macro.raw
