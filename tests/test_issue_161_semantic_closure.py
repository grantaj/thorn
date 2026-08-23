from __future__ import annotations

from pathlib import Path

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


def test_result_review_closes_explicit_project_symbol_dependencies(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    _write_main(
        main,
        r"""
Define $a:=1$.
Define $b:=a+1$.

\begin{theorem}\label{thm:main}
We have $b>0$.
\end{theorem}
\begin{proof}Use the definitions.\end{proof}
""",
    )

    project = extract_project(main)
    table = project.symbol_table

    direct_ids = result_project_symbol_dependency_ids(project, "thm:main")
    assert [table.symbol(identifier).name for identifier in direct_ids] == ["b"]

    b_identifier = direct_ids[0]
    upstream_ids = project_symbol_dependency_ids(project, b_identifier)
    assert [table.symbol(identifier).name for identifier in upstream_ids] == ["a"]

    closed_ids = close_project_symbol_dependencies(project, direct_ids)
    closed_symbols = sorted(
        (table.symbol(identifier) for identifier in closed_ids),
        key=lambda symbol: (*semantic_symbol_sort_key(project, symbol), symbol.identifier),
    )
    assert [symbol.name for symbol in closed_symbols] == ["a", "b"]

    item = build_result_review_context(project, "thm:main").items[0]
    project_symbols = [
        symbol.name
        for symbol in item.symbols
        if table.scope(symbol.scope_identifier).kind.value == "project"
    ]
    assert project_symbols == ["a", "b"]
