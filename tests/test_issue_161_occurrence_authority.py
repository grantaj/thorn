from __future__ import annotations

from pathlib import Path

from declaration_contract_frontend import DeclarationContractFrontend
from thorn.latex import extract_project
from thorn.linguistic_declarations import ProseDeclarationCapability


def _resolved_names(project, result_identifier: str) -> list[str]:
    scope_ids = {
        scope.identifier
        for scope in project.symbol_table.scopes
        if scope.result_identifier == result_identifier
    }
    return [
        use.name
        for use in project.symbol_table.uses
        if use.scope_identifier in scope_ids and use.resolved_symbol_identifier is not None
    ]


def test_repeated_child_use_can_share_one_parent_authority(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    definition = "A map is called fibre-regular when every fibre contains two points."
    main.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{definition}\n"
        "\\input{child}\n"
        "\\input{child}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    child.write_text(
        r"""\begin{theorem}\label{thm:child}
The map $f$ is fibre-regular.
\end{theorem}
\begin{proof}Inspect the fibres.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main, linguistic_frontend=DeclarationContractFrontend())

    assert project.prose_declarations is not None
    assert project.prose_declarations.capability == ProseDeclarationCapability.COMPLETE
    assert _resolved_names(project, "thm:child").count("fibre-regular") == 1
    definitions = [
        item for item in project.symbol_table.definitions if item.raw == definition
    ]
    assert len(definitions) == 1
    assert definitions[0].symbol_identifier.startswith("semantic:o0:")


def test_repeated_child_use_fails_closed_when_occurrence_authority_differs(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    first = "A map is called fibre-regular when every fibre contains two points."
    second = "A map is called fibre-regular when every fibre contains three points."
    main.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{first}\n"
        "\\input{child}\n"
        f"{second}\n"
        "\\input{child}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    child.write_text(
        r"""\begin{theorem}\label{thm:child}
The map $f$ is fibre-regular.
\end{theorem}
\begin{proof}Inspect the fibres.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main, linguistic_frontend=DeclarationContractFrontend())

    # The current result IR is path-level. The physical theorem occurs twice with
    # different visible declarations, so Slice D must not collapse those occurrence
    # contexts into one invented mathematical authority.
    assert "fibre-regular" not in _resolved_names(project, "thm:child")
    assert not any(
        item.raw in {first, second} for item in project.symbol_table.definitions
    )
