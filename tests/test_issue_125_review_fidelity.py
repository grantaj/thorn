from __future__ import annotations

from pathlib import Path

from thorn.latex import extract_project
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review


def _write_paper(path: Path, body: str) -> None:
    path.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body.strip()}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )


def _prepared(path: Path):
    project = extract_project(path)
    return project, prepare_proof_review(project, project.unit("thm:main"))


def _sources_containing(prepared, needle: str):
    return [source for source in prepared.document.sources if needle in source.text]


def test_semantic_prose_dependencies_are_transitively_closed(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    convention = r"Throughout, the base field is \(K=\mathbb R\)."
    definition = (
        "A map is called regular when its determinant is nonzero over the base field."
    )
    _write_paper(
        paper,
        rf"""
{convention}
{definition}

\begin{{theorem}}\label{{thm:main}}
The map \(f\) is regular.
\end{{theorem}}
\begin{{proof}}
This follows from the construction.
\end{{proof}}
""",
    )

    _, prepared = _prepared(paper)
    advertised = set(advertised_source_addresses(prepared.document))
    convention_sources = _sources_containing(prepared, "Throughout, the base field is")
    definition_sources = _sources_containing(prepared, "determinant is nonzero")

    assert len(convention_sources) == 1
    assert len(definition_sources) == 1
    assert convention_sources[0].address in advertised
    assert definition_sources[0].address in advertised
    assert convention not in prepared.document.render_initial()
    assert definition not in prepared.document.render_initial()


def test_project_semantic_dependency_crosses_input_boundary(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    results = tmp_path / "results.tex"
    definition = (
        "A map is called balanced when every fibre contains exactly two points."
    )
    _write_paper(main, f"{definition}\n\\input{{results}}")
    results.write_text(
        r"""\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}
This follows from the construction.
\end{proof}
""",
        encoding="utf-8",
    )

    _, prepared = _prepared(main)
    sources = _sources_containing(prepared, "every fibre contains exactly two points")

    assert len(sources) == 1
    assert sources[0].source_span is not None
    assert sources[0].source_span.file == str(main.resolve())
    assert sources[0].address in set(advertised_source_addresses(prepared.document))


def test_cross_file_redefinition_shadows_earlier_semantic_term(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    redefine = tmp_path / "redefine.tex"
    results = tmp_path / "results.tex"
    first = "A map is called balanced when every fibre contains exactly two points."
    second = "A map is called balanced when every fibre contains exactly three points."
    _write_paper(main, f"{first}\n\\input{{redefine}}\n\\input{{results}}")
    redefine.write_text(second + "\n", encoding="utf-8")
    results.write_text(
        r"""\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}
This follows from the construction.
\end{proof}
""",
        encoding="utf-8",
    )

    _, prepared = _prepared(main)
    source_texts = [source.text for source in prepared.document.sources]

    assert any("exactly three points" in text for text in source_texts)
    assert not any("exactly two points" in text for text in source_texts)


def test_commented_out_definition_is_not_authoritative_context(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    _write_paper(
        paper,
        r"""
% A map is called balanced when every fibre contains exactly two points.

\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}
This follows from the construction.
\end{proof}
""",
    )

    project, prepared = _prepared(paper)

    assert not any(
        symbol.identifier.startswith("semantic:") and symbol.name == "balanced"
        for symbol in project.symbol_table.symbols
    )
    assert not _sources_containing(prepared, "every fibre contains exactly two points")


def test_commented_out_result_use_does_not_activate_definition(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    definition = (
        "A map is called balanced when every fibre contains exactly two points."
    )
    _write_paper(
        paper,
        rf"""
{definition}

\begin{{theorem}}\label{{thm:main}}
The map \(f\) has finite fibres.
\end{{theorem}}
\begin{{proof}}
% The map f is balanced.
The claim follows from the construction.
\end{{proof}}
""",
    )

    project, prepared = _prepared(paper)

    assert not any(
        symbol.identifier.startswith("semantic:") and symbol.name == "balanced"
        for symbol in project.symbol_table.symbols
    )
    assert not _sources_containing(prepared, "every fibre contains exactly two points")


def test_verbatim_definition_is_not_authoritative_context(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    _write_paper(
        paper,
        r"""
\begin{verbatim}
A map is called balanced when every fibre contains exactly two points.
\end{verbatim}

\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}
This follows from the construction.
\end{proof}
""",
    )

    project, prepared = _prepared(paper)

    assert not any(
        symbol.identifier.startswith("semantic:") and symbol.name == "balanced"
        for symbol in project.symbol_table.symbols
    )
    assert not _sources_containing(prepared, "every fibre contains exactly two points")
