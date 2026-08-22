from __future__ import annotations

from pathlib import Path

from thorn.canonical_proof_ir import build_canonical_proof_ir
from thorn.eval_review import build_result_review_context
from thorn.frontends.regex import RegexLatexFrontend
from thorn.latex import extract_project
from thorn.review_workflow import prepare_proof_review
from thorn.semantic_dependencies import project_source_sort_key, semantic_symbol_sort_key
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import (
    build_semantic_review_request,
    render_semantic_review_request,
)


def _write_project(tmp_path: Path) -> Path:
    main = tmp_path / "main.tex"
    first = tmp_path / "zz_first.tex"
    second = tmp_path / "aa_second.tex"

    main.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\input{zz_first}
\input{aa_second}
\begin{theorem}\label{thm:target}
We have $z+a=3$.
\end{theorem}
\begin{proof}
By Lemma~\ref{lem:z-first} and Lemma~\ref{lem:a-second}, $z+a=3$.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )
    first.write_text(
        r"""Set $z := 1$.
\begin{lemma}\label{lem:z-first}
We have $z=1$.
\end{lemma}
\begin{proof}
$z=1$.
\end{proof}
""",
        encoding="utf-8",
    )
    second.write_text(
        r"""Set $a := 2$.
\begin{lemma}\label{lem:a-second}
We have $a=2$.
\end{lemma}
\begin{proof}
$a=2$.
\end{proof}
""",
        encoding="utf-8",
    )
    return main


def test_workspace_order_survives_review_render_and_thorn_proof(tmp_path: Path) -> None:
    main = _write_project(tmp_path)
    project = extract_project(main, frontend=RegexLatexFrontend())

    # Physical filenames sort aa_second before zz_first, while the manuscript
    # includes zz_first first. Canonical result/dependency order must follow the
    # expanded project, not the filesystem spelling.
    assert [unit.identifier for unit in project.units] == [
        "lem:z-first",
        "lem:a-second",
        "thm:target",
    ]

    project_symbols = [
        symbol
        for symbol in project.symbol_table.symbols
        if symbol.scope_identifier == "project" and symbol.name in {"z", "a"}
    ]
    assert [
        symbol.name
        for symbol in sorted(
            project_symbols,
            key=lambda symbol: semantic_symbol_sort_key(project, symbol),
        )
    ] == ["z", "a"]

    context = build_result_review_context(project, "thm:target")
    assert len(context.items) == 1
    item = context.items[0]
    assert [dependency.identifier for dependency in item.dependencies] == [
        "lem:z-first",
        "lem:a-second",
    ]

    selected_definitions = [
        definition
        for definition in item.definitions
        if next(
            symbol
            for symbol in item.symbols
            if symbol.identifier == definition.symbol_identifier
        ).name
        in {"z", "a"}
    ]
    assert [
        next(
            symbol
            for symbol in item.symbols
            if symbol.identifier == definition.symbol_identifier
        ).name
        for definition in selected_definitions
    ] == ["z", "a"]

    request = build_semantic_review_request(item)
    assert [dependency.identifier for dependency in request.item.dependencies] == [
        "lem:z-first",
        "lem:a-second",
    ]

    verbose = render_semantic_review_request(request)
    assert verbose.index("Dependency ID: lem:z-first") < verbose.index(
        "Dependency ID: lem:a-second"
    )
    compact = render_compact_semantic_review_request(request)
    assert compact.index("lem:z-first") < compact.index("lem:a-second")

    canonical = build_canonical_proof_ir(project.unit("thm:target"), request)
    dependency_sources = [
        source
        for source in canonical.sources
        if source.referenced_result_identifier is not None
        and source.address.startswith("R")
    ]
    assert [
        (source.address, source.referenced_result_identifier)
        for source in dependency_sources
    ] == [
        ("R1", "lem:z-first"),
        ("R2", "lem:a-second"),
    ]

    prepared = prepare_proof_review(project, project.unit("thm:target"))
    thorn_proof_dependencies = [
        source
        for source in prepared.document.sources
        if source.referenced_result_identifier in {"lem:z-first", "lem:a-second"}
        and source.address.startswith("R")
    ]
    assert [
        (source.address, source.referenced_result_identifier)
        for source in thorn_proof_dependencies
    ] == [
        ("R1", "lem:z-first"),
        ("R2", "lem:a-second"),
    ]
    assert prepared.document.fingerprint() == prepare_proof_review(
        project,
        project.unit("thm:target"),
    ).document.fingerprint()


def test_project_source_sort_key_has_deterministic_no_workspace_fallback(
    tmp_path: Path,
) -> None:
    main = _write_project(tmp_path)
    project = extract_project(main, frontend=RegexLatexFrontend())
    no_workspace = project.model_copy(update={"workspace": None})

    symbols = {
        symbol.name: symbol
        for symbol in project.symbol_table.symbols
        if symbol.scope_identifier == "project" and symbol.name in {"z", "a"}
    }
    assert set(symbols) == {"z", "a"}

    ordered = sorted(
        (symbols["z"], symbols["a"]),
        key=lambda symbol: project_source_sort_key(
            no_workspace,
            symbol.source,
            symbol.identifier,
        ),
    )
    assert [symbol.name for symbol in ordered] == ["a", "z"]
