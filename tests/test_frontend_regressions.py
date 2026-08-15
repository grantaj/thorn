from pathlib import Path

from thorn.frontends import RegexLatexFrontend
from thorn.latex import extract_units


def test_known_macro_does_not_absorb_following_group(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    source = "\\label{item:a}\n{This group is document content.}\n"
    tex.write_text(source, encoding="utf-8")

    parsed = RegexLatexFrontend().parse_project(tex)
    label = next(macro for macro in parsed.files[0].macros if macro.name == "label")

    assert [argument.value for argument in label.arguments] == ["item:a"]
    assert label.raw == r"\label{item:a}"
    assert label.span.text(source) == label.raw


def test_environment_body_can_start_with_brace_group(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    source = "\\begin{theorem}{Grouped body}\\end{theorem}\n"
    tex.write_text(source, encoding="utf-8")

    parsed = RegexLatexFrontend().parse_project(tex)
    theorem = next(
        environment for environment in parsed.files[0].environments if environment.name == "theorem"
    )

    assert theorem.arguments == []
    assert theorem.body(source) == "{Grouped body}"
    assert extract_units(tex)[0].statement == "{Grouped body}"


def test_starred_newtheorem_declaration_remains_extractable(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        "\\newtheorem*{remark}{Remark}\n"
        "\\begin{remark}A custom unnumbered result.\\end{remark}\n",
        encoding="utf-8",
    )

    parsed = RegexLatexFrontend().parse_project(tex)
    declaration = next(macro for macro in parsed.files[0].macros if macro.name == "newtheorem")
    units = extract_units(tex)

    assert declaration.starred is True
    assert [argument.value for argument in declaration.arguments[:2]] == ["remark", "Remark"]
    assert len(units) == 1
    assert units[0].environment == "remark"
