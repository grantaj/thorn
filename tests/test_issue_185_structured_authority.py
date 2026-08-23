from __future__ import annotations

from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path

import pytest

from thorn.eval_review import build_result_review_context
from thorn.frontend import LatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.frontends.regex import RegexLatexFrontend
from thorn.latex import extract_project
from thorn.project_partiality import normalize_project_structure
from thorn.symbols import ResultRegion, extract_symbol_table
from thorn.workspace import WorkspaceResolution, build_project_workspace_facts

FrontendFactory = Callable[[], LatexFrontend]

if find_spec("tree_sitter") is not None and find_spec("tree_sitter_latex") is not None:
    from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

    _OPTIONAL_FRONTENDS: tuple[FrontendFactory, ...] = (TreeSitterLatexFrontend,)
else:
    _OPTIONAL_FRONTENDS = ()

_RETAINED_FRONTENDS: tuple[FrontendFactory, ...] = (
    RegexLatexFrontend,
    PylatexencLatexFrontend,
    *_OPTIONAL_FRONTENDS,
)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


def _main_source(body: str) -> str:
    return (
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body}"
        "\\end{document}\n"
    )


def _resolved_definition_rhs(project, *, result_identifier: str, name: str) -> str | None:
    scope_ids = {
        scope.identifier
        for scope in project.symbol_table.scopes
        if scope.result_identifier == result_identifier
    }
    uses = [
        use
        for use in project.symbol_table.uses
        if use.name == name and use.scope_identifier in scope_ids
    ]
    assert uses
    targets = {use.resolved_symbol_identifier for use in uses}
    if targets == {None}:
        return None
    assert len(targets) == 1
    target = next(iter(targets))
    assert target is not None
    definition = next(
        item
        for item in project.symbol_table.definitions
        if item.symbol_identifier == target
    )
    return definition.expression_latex


def test_cross_file_future_structured_declaration_does_not_leak_backward(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    early = tmp_path / "early.tex"
    late = tmp_path / "late.tex"
    main.write_text(
        _main_source("\\input{early}\n\\input{late}\n"),
        encoding="utf-8",
    )
    early.write_text(
        "\\begin{theorem}\\label{thm:early}\n"
        "Assume $q>0$.\n"
        "\\end{theorem}\n",
        encoding="utf-8",
    )
    late.write_text("Set $q = 1$.\n", encoding="utf-8")

    project = extract_project(main, frontend=RegexLatexFrontend())

    assert any(
        symbol.name == "q" and symbol.scope_identifier == "project"
        for symbol in project.symbol_table.symbols
    )
    assert _resolved_definition_rhs(
        project,
        result_identifier="thm:early",
        name="q",
    ) is None


def test_same_name_project_shadowing_uses_include_order_not_filename_or_byte_offset(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    first = tmp_path / "zz_first.tex"
    second = tmp_path / "aa_second.tex"
    main.write_text(
        _main_source(
            "\\input{zz_first}\n"
            "\\input{aa_second}\n"
            "\\begin{theorem}\\label{thm:after}\n"
            "Now $q>0$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )
    # Deliberately give both declarations the same local byte offset. Distinct
    # physical provenance and expanded include order must still keep them distinct.
    first.write_text("Set $q = 1$.\n", encoding="utf-8")
    second.write_text("Set $q = 2$.\n", encoding="utf-8")

    project = extract_project(main, frontend=RegexLatexFrontend())

    assert _resolved_definition_rhs(
        project,
        result_identifier="thm:after",
        name="q",
    ) == "2"


def test_parent_child_return_order_is_expanded_project_order(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        _main_source(
            "Set $q = 0$.\n"
            "\\input{child}\n"
            "\\begin{theorem}\\label{thm:return}\n"
            "On return, $q>0$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )
    child.write_text(
        "\\begin{theorem}\\label{thm:child}\n"
        "Before the child redefinition, $q>0$.\n"
        "\\end{theorem}\n"
        "Set $q = 1$.\n",
        encoding="utf-8",
    )

    project = extract_project(main, frontend=RegexLatexFrontend())

    assert _resolved_definition_rhs(
        project,
        result_identifier="thm:child",
        name="q",
    ) == "0"
    assert _resolved_definition_rhs(
        project,
        result_identifier="thm:return",
        name="q",
    ) == "1"


def test_repeated_child_under_agreeing_structured_context_collapses_safely(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        _main_source(
            "Set $q = 0$.\n"
            "\\input{child}\n"
            "\\input{child}\n"
        ),
        encoding="utf-8",
    )
    child.write_text(
        "\\begin{theorem}\\label{thm:child}\n"
        "We use $q>0$.\n"
        "\\end{theorem}\n",
        encoding="utf-8",
    )

    project = extract_project(main, frontend=RegexLatexFrontend())

    assert _resolved_definition_rhs(
        project,
        result_identifier="thm:child",
        name="q",
    ) == "0"


def test_repeated_child_across_structured_redefinition_fails_closed(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        _main_source(
            "Set $q = 0$.\n"
            "\\input{child}\n"
            "Set $q = 1$.\n"
            "\\input{child}\n"
        ),
        encoding="utf-8",
    )
    child.write_text(
        "\\begin{theorem}\\label{thm:child}\n"
        "We use $q>0$.\n"
        "\\end{theorem}\n",
        encoding="utf-8",
    )

    project = extract_project(main, frontend=RegexLatexFrontend())

    assert _resolved_definition_rhs(
        project,
        result_identifier="thm:child",
        name="q",
    ) is None


def test_workspace_partiality_blocks_project_wide_structured_authority(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        _main_source(
            "\\input{child}\n"
            "\\begin{theorem}\\label{thm:cycle}\n"
            "We use $q>0$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )
    child.write_text("$q := 1$.\n\\input{main}\n", encoding="utf-8")

    frontend = RegexLatexFrontend()
    parsed = normalize_project_structure(frontend.parse_project(main))
    workspace = build_project_workspace_facts(parsed)
    assert workspace.resolution == WorkspaceResolution.PARTIAL

    parsed_main = parsed.file(main)
    theorem = next(
        environment
        for environment in parsed_main.environments
        if environment.name == "theorem"
    )
    table = extract_symbol_table(
        parsed,
        [
            ResultRegion(
                identifier="thm:cycle",
                file=parsed_main.path,
                statement_span=theorem.span,
            )
        ],
        workspace=workspace,
    )

    assert not any(symbol.scope_identifier == "project" for symbol in table.symbols)
    assert not any(
        use.name == "q" and use.resolved_symbol_identifier is not None
        for use in table.uses
    )


@pytest.mark.parametrize(
    "frontend_factory",
    _RETAINED_FRONTENDS,
    ids=_frontend_id,
)
def test_commented_cues_and_verbatim_lookalikes_do_not_create_authority(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    main = tmp_path / "main.tex"
    main.write_text(
        _main_source(
            "% Define\n"
            "$x = 1$.\n"
            "\\begin{verbatim}\n"
            "Define $v = 2$.\n"
            "$w := 3$.\n"
            "\\end{verbatim}\n"
            "\\begin{theorem}\\label{thm:cues}\n"
            "% Let\n"
            "$y$ be real. Then $y=y$.\n"
            "\\end{theorem}\n"
        ),
        encoding="utf-8",
    )

    project = extract_project(main, frontend=frontend_factory())
    names = {symbol.name for symbol in project.symbol_table.symbols}

    assert names.isdisjoint({"x", "v", "w", "y"})


def test_structured_project_provenance_survives_result_review_selection(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    source = _main_source(
        "Set $q = 1$.\n"
        "\\begin{theorem}\\label{thm:review}\n"
        "We use $q>0$.\n"
        "\\end{theorem}\n"
    )
    main.write_text(source, encoding="utf-8")

    project = extract_project(main, frontend=RegexLatexFrontend())
    review = build_result_review_context(project, "thm:review").items[0]
    symbol = next(item for item in review.symbols if item.name == "q")
    definition = next(
        item
        for item in review.definitions
        if item.symbol_identifier == symbol.identifier
    )

    assert symbol.source.text(source) == "q"
    assert symbol.introduction_source.text(source) == "Set $q = 1$"
    assert definition.source.text(source) == "Set $q = 1$"
    assert definition.raw == "Set $q = 1$"
