"""End-to-end regressions for project order and advisory source fidelity."""

from __future__ import annotations

from pathlib import Path

from candidate_context_contract import prepare_all_prior_context
from sentence_contract_frontend import SentenceContractFrontend
from thorn.context_retrieval import build_result_context_pools
from thorn.latex import extract_project
from thorn.proof_language_review import advertised_source_addresses


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


def _project(path: Path):
    return extract_project(path, linguistic_frontend=SentenceContractFrontend())


def _prepared(path: Path):
    project = _project(path)
    return project, prepare_all_prior_context(project, "thm:main")


def _sources_containing(prepared, needle: str):
    return [source for source in prepared.document.sources if needle in source.text]


def _assert_not_prose_authority(project, *names: str) -> None:
    lowered = {name.casefold() for name in names}
    assert not any(
        symbol.name.casefold() in lowered and symbol.scope_identifier == "project"
        for symbol in project.symbol_table.symbols
    )


def test_prior_prose_dependency_chain_is_exact_advisory_evidence(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    convention = r"Throughout, the base field is \(K=\mathbb R\)."
    definition = "A map is called regular when its determinant is nonzero over the base field."
    _write_paper(
        paper,
        rf"""
{convention}
{definition}

\begin{{theorem}}\label{{thm:main}}
The map \(f\) is regular.
\end{{theorem}}
\begin{{proof}}This follows from the construction.\end{{proof}}
""",
    )

    project, prepared = _prepared(paper)
    advertised = set(advertised_source_addresses(prepared.document))
    convention_sources = _sources_containing(prepared, "Throughout, the base field is")
    definition_sources = _sources_containing(prepared, "determinant is nonzero")

    assert len(convention_sources) == 1
    assert len(definition_sources) == 1
    assert convention_sources[0].address in advertised
    assert definition_sources[0].address in advertised
    assert convention not in prepared.document.render_initial()
    assert definition not in prepared.document.render_initial()
    _assert_not_prose_authority(project, "base field", "regular")


def test_prior_ambient_convention_is_reachable_without_becoming_scope_authority(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.tex"
    convention = "Throughout, all topological spaces are Hausdorff."
    _write_paper(
        paper,
        rf"""
{convention}

\begin{{theorem}}\label{{thm:main}}
Every compact subset is closed.
\end{{theorem}}
\begin{{proof}}This is the standard compactness argument.\end{{proof}}
""",
    )

    project, prepared = _prepared(paper)
    sources = _sources_containing(prepared, "topological spaces are Hausdorff")

    assert "topological spaces" not in project.unit("thm:main").statement
    assert len(sources) == 1
    assert sources[0].address in set(advertised_source_addresses(prepared.document))
    assert convention not in prepared.document.render_initial()
    _assert_not_prose_authority(project, "topological spaces")


def test_later_prose_is_not_prior_context(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    convention = "Throughout, all topological spaces are Hausdorff."
    _write_paper(
        paper,
        rf"""
\begin{{theorem}}\label{{thm:main}}
Every compact subset is closed.
\end{{theorem}}
\begin{{proof}}This is the standard compactness argument.\end{{proof}}

{convention}
""",
    )

    project = _project(paper)
    pools = build_result_context_pools(project, "thm:main")
    assert not any(
        "topological spaces are Hausdorff" in candidate.text
        for pool in pools
        for candidate in pool.candidates
    )


def test_prior_context_crosses_input_boundary_with_exact_origin(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    results = tmp_path / "results.tex"
    definition = "A map is called balanced when every fibre contains exactly two points."
    _write_paper(main, f"{definition}\n\\input{{results}}")
    results.write_text(
        r"""\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}This follows from the construction.\end{proof}
""",
        encoding="utf-8",
    )

    project, prepared = _prepared(main)
    sources = _sources_containing(prepared, "every fibre contains exactly two points")

    assert len(sources) == 1
    assert sources[0].source_span is not None
    assert sources[0].source_span.file == str(main.resolve())
    assert sources[0].address in set(advertised_source_addresses(prepared.document))
    _assert_not_prose_authority(project, "balanced")


def test_cross_file_redefinitions_remain_distinct_advisory_evidence(tmp_path: Path) -> None:
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
\begin{proof}This follows from the construction.\end{proof}
""",
        encoding="utf-8",
    )

    project = _project(main)
    pools = build_result_context_pools(project, "thm:main")
    texts = [candidate.text for pool in pools for candidate in pool.candidates]

    assert any("exactly two points" in text for text in texts)
    assert any("exactly three points" in text for text in texts)
    _assert_not_prose_authority(project, "balanced")


def test_commented_out_definition_is_not_candidate_context(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    _write_paper(
        paper,
        r"""
% A map is called balanced when every fibre contains exactly two points.
\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}This follows from the construction.\end{proof}
""",
    )

    project = _project(paper)
    pools = build_result_context_pools(project, "thm:main")
    assert not any(
        "every fibre contains exactly two points" in candidate.text
        for pool in pools
        for candidate in pool.candidates
    )
    _assert_not_prose_authority(project, "balanced")


def test_commented_out_result_use_does_not_create_authority(tmp_path: Path) -> None:
    paper = tmp_path / "paper.tex"
    definition = "A map is called balanced when every fibre contains exactly two points."
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

    project = _project(paper)
    pools = build_result_context_pools(project, "thm:main")
    assert any(
        "every fibre contains exactly two points" in candidate.text
        for pool in pools
        for candidate in pool.candidates
    )
    _assert_not_prose_authority(project, "balanced")


def test_verbatim_definition_is_not_candidate_context(tmp_path: Path) -> None:
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
\begin{proof}This follows from the construction.\end{proof}
""",
    )

    project = _project(paper)
    pools = build_result_context_pools(project, "thm:main")
    assert not any(
        "every fibre contains exactly two points" in candidate.text
        for pool in pools
        for candidate in pool.candidates
    )
    _assert_not_prose_authority(project, "balanced")
