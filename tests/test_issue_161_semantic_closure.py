from __future__ import annotations

from pathlib import Path

from declaration_contract_frontend import DeclarationContractFrontend
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.semantic_dependencies import (
    close_project_symbol_dependencies,
    project_symbol_dependency_ids,
    result_project_symbol_dependency_ids,
    semantic_symbol_sort_key,
)


def _write_main(path: Path, body: str) -> None:
    path.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body.strip()}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )


def test_result_and_dependency_order_follow_workspace_not_file_names(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    z_first = tmp_path / "z_first.tex"
    a_second = tmp_path / "a_second.tex"

    _write_main(
        main,
        r"""
\input{z_first}
\input{a_second}
\begin{theorem}\label{thm:main}
The conclusion follows from Lemmas~\ref{lem:z} and~\ref{lem:a}.
\end{theorem}
\begin{proof}
Apply Lemma~\ref{lem:z}, then Lemma~\ref{lem:a}.
\end{proof}
""",
    )
    z_first.write_text(
        r"""\begin{lemma}\label{lem:z}
The first included fact holds.
\end{lemma}
\begin{proof}Immediate.\end{proof}
""",
        encoding="utf-8",
    )
    a_second.write_text(
        r"""\begin{lemma}\label{lem:a}
The second included fact holds.
\end{lemma}
\begin{proof}Immediate.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main)

    assert [unit.identifier for unit in project.units] == ["lem:z", "lem:a", "thm:main"]
    assert project.dependency_graph.direct_dependency_ids("thm:main") == ["lem:z", "lem:a"]

    item = build_result_review_context(project, "thm:main").items[0]
    assert [dependency.identifier for dependency in item.dependencies] == ["lem:z", "lem:a"]


def test_result_review_closes_canonical_project_symbol_dependencies(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    first = "A transformation is called nonsingular when its determinant is nonzero."
    second = (
        "A transformation is called regular when it is nonsingular on every invariant subspace."
    )
    _write_main(
        main,
        rf"""
{first}
{second}

\begin{{theorem}}\label{{thm:main}}
The transformation $T$ is regular.
\end{{theorem}}
\begin{{proof}}Use the construction.\end{{proof}}
""",
    )

    project = extract_project(
        main,
        linguistic_frontend=DeclarationContractFrontend(),
    )
    table = project.symbol_table

    direct_ids = result_project_symbol_dependency_ids(project, "thm:main")
    assert [table.symbol(identifier).name for identifier in direct_ids] == ["regular"]

    regular_identifier = direct_ids[0]
    upstream_ids = project_symbol_dependency_ids(project, regular_identifier)
    assert [table.symbol(identifier).name for identifier in upstream_ids] == ["nonsingular"]

    closed_ids = close_project_symbol_dependencies(project, direct_ids)
    closed_symbols = sorted(
        (table.symbol(identifier) for identifier in closed_ids),
        key=lambda symbol: (*semantic_symbol_sort_key(project, symbol), symbol.identifier),
    )
    assert [symbol.name for symbol in closed_symbols] == ["nonsingular", "regular"]

    item = build_result_review_context(project, "thm:main").items[0]
    project_symbols = [
        symbol.name
        for symbol in item.symbols
        if table.scope(symbol.scope_identifier).kind.value == "project"
    ]
    assert project_symbols == ["nonsingular", "regular"]
