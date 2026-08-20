from pathlib import Path

import pytest

from thorn.frontend import FrontendDiagnosticKind, FrontendFile, FrontendRegionKind
from thorn.frontends.tree_sitter import TreeSitterLatexFrontend


def _frontend() -> TreeSitterLatexFrontend:
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_latex")
    return TreeSitterLatexFrontend()


def _eligible_text(file: FrontendFile) -> str:
    return "".join(
        region.span.text(file.raw)
        for region in file.regions
        if region.kind == FrontendRegionKind.DOCUMENT_TEXT
    )


def test_tree_sitter_recovers_source_structure_and_eligible_regions(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    source = r"""\documentclass{article}
\newtheorem{fact}{Fact}
Preamble declaration-looking prose must stay out.
\begin{document}
Visible café text with an escaped percent \%.
% Hidden comment declaration: let Shadow mean bad.
\begin{comment}
Hidden comment environment: let CommentShadow mean bad.
\end{comment}
\begin{verbatim}
\input{not-a-real-file}
Hidden verbatim declaration: let VerbatimShadow mean bad.
\end{verbatim}
\begin{verbatim*}
\input{also-not-a-real-file}
Hidden starred verbatim declaration: let StarShadow mean bad.
\end{verbatim*}
\begin{lstlisting}
\label{fake:list}
Hidden listing declaration: let ListingShadow mean bad.
\end{lstlisting}
\begin{minted}{python}
print(r"\ref{fake:minted}")
Hidden minted declaration: let MintedShadow mean bad.
\end{minted}
\begin{fact}[Small]\label{fact:one}
Let $x\in\mathbb R$ and use \foo[alpha]{a{b}c}.
\[
x^2 \ge 0.
\]
\end{fact}
\begin{proof}
Indeed, by \ref{fact:one}.
\end{proof}
\end{document}
"""
    tex.write_text(source, encoding="utf-8")

    parsed = _frontend().parse_project(tex)
    assert not [item for item in parsed.diagnostics if item.kind == FrontendDiagnosticKind.MISSING_FILE]
    file = parsed.files[0]

    names = [macro.name for macro in file.macros]
    assert "%" in names
    assert "label" in names
    assert "ref" in names
    assert "input" not in names

    newtheorem = next(macro for macro in file.macros if macro.name == "newtheorem")
    assert [argument.value for argument in newtheorem.arguments] == ["fact", "Fact"]
    foo = next(macro for macro in file.macros if macro.name == "foo")
    assert [argument.value for argument in foo.arguments] == ["alpha", "a{b}c"]
    assert [argument.optional for argument in foo.arguments] == [True, False]

    env_names = {environment.name for environment in file.environments}
    assert {"document", "comment", "verbatim", "verbatim*", "lstlisting", "minted", "fact", "proof"} <= env_names
    fact = next(environment for environment in file.environments if environment.name == "fact")
    assert fact.arguments[0].value == "Small"
    assert fact.body(source).startswith(r"\label{fact:one}")

    assert any(item.delimiter == "$" and "x\\in" in item.raw for item in file.math)
    assert any(item.delimiter == r"\[\]" and "x^2" in item.raw for item in file.math)

    kinds = {region.kind for region in file.regions}
    assert {
        FrontendRegionKind.PREAMBLE,
        FrontendRegionKind.DOCUMENT_TEXT,
        FrontendRegionKind.COMMENT,
        FrontendRegionKind.VERBATIM,
        FrontendRegionKind.LISTING,
        FrontendRegionKind.MINTED,
        FrontendRegionKind.MATH,
    } <= kinds
    eligible = _eligible_text(file)
    assert "Visible café text" in eligible
    assert "Indeed, by" in eligible
    assert "Preamble declaration-looking prose" not in eligible
    assert "Hidden comment declaration" not in eligible
    assert "CommentShadow" not in eligible
    assert "VerbatimShadow" not in eligible
    assert "StarShadow" not in eligible
    assert "ListingShadow" not in eligible
    assert "MintedShadow" not in eligible
    assert "x\\in\\mathbb" not in eligible


def test_tree_sitter_follows_real_includes_but_not_opaque_fake_includes(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        "\\input{child}\n"
        "\\begin{verbatim*}\\input{fake}\\end{verbatim*}\n",
        encoding="utf-8",
    )
    child.write_text("Child.\n", encoding="utf-8")

    parsed = _frontend().parse_project(main)
    assert {Path(file.path).name for file in parsed.files} == {"main.tex", "child.tex"}
    assert not [item for item in parsed.diagnostics if item.kind == FrontendDiagnosticKind.MISSING_FILE]
    include = next(macro for macro in parsed.files[0].macros if macro.name == "input")
    assert include.span.start_line == 1
    assert include.arguments[0].value == "child"


def test_tree_sitter_malformed_environment_fails_closed(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        "\\begin{document}\n\\begin{proof}\nunfinished\n\\end{document}\n",
        encoding="utf-8",
    )

    parsed = _frontend().parse_project(tex)
    errors = [item for item in parsed.diagnostics if item.kind == FrontendDiagnosticKind.PARSE_ERROR]
    assert errors
    assert any("proof" in item.message or item.source and item.source.start_line == 2 for item in errors)
    assert not any(environment.name == "proof" for environment in parsed.files[0].environments)


def test_tree_sitter_normalizes_utf8_byte_offsets_to_character_offsets(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    source = "αβ café\n\\label{item:one}\n"
    tex.write_text(source, encoding="utf-8")

    file = _frontend().parse_project(tex).files[0]
    label = next(macro for macro in file.macros if macro.name == "label")
    expected = source.index(r"\label{item:one}")
    assert label.span.start_offset == expected
    assert label.span.start_line == 2
    assert label.span.start_column == 1
    assert label.span.text(source) == r"\label{item:one}"


def test_tree_sitter_returns_only_thorn_owned_models(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text("\\begin{theorem}A.\\end{theorem}\n", encoding="utf-8")
    parsed = _frontend().parse_project(tex)

    dumped = parsed.model_dump(mode="json")
    assert isinstance(dumped, dict)
    assert "tree_sitter" not in repr(dumped)
    assert "Node" not in repr(dumped)
