from collections.abc import Callable
from pathlib import Path

import pytest

from thorn.frontend import LatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.frontends.regex import RegexLatexFrontend
from thorn.latex import extract_project
from thorn.symbols import IntroductionKind, ScopeKind, SymbolRole

FrontendFactory = Callable[[], LatexFrontend]
_FRONTENDS: tuple[FrontendFactory, ...] = (RegexLatexFrontend, PylatexencLatexFrontend)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


def _write_fixture(path: Path) -> str:
    source = r"""\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:symbols}
Let $X$ be a compact space. Let $f:X\to\mathbb R$ be continuous.
For $\epsilon>0$, suppose $f(x)<\epsilon$.
\end{theorem}
\begin{proof}
Define $g(x,y)=f(x)+f(y)$.
Set $A := \{x\in X : f(x)>0\}$.
For $n\in\mathbb N$, write $f(x)$ again.
We also have $\forall z\in X,\ z=z$.
\end{proof}
\end{document}
"""
    path.write_text(source, encoding="utf-8")
    return source


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_extracts_high_confidence_symbols_definitions_roles_and_constraints(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    source = _write_fixture(tex)

    table = extract_project(tex, frontend=frontend_factory()).symbol_table
    by_name = {symbol.name: symbol for symbol in table.symbols}

    assert {"X", "f", r"\epsilon", "g", "A", "n", "z"} <= set(by_name)

    assert by_name["X"].role == SymbolRole.UNKNOWN
    assert by_name["f"].role == SymbolRole.MAP
    assert by_name["f"].arity == 1
    assert by_name["f"].domain_latex == "X"
    assert by_name["f"].codomain_latex == r"\mathbb R"

    assert by_name[r"\epsilon"].role == SymbolRole.SCALAR
    epsilon_constraint = next(
        item
        for item in table.constraints
        if item.symbol_identifier == by_name[r"\epsilon"].identifier
    )
    assert epsilon_constraint.relation == ">"
    assert epsilon_constraint.expression_latex == "0"

    assert by_name["g"].role == SymbolRole.FUNCTION
    assert by_name["g"].arity == 2
    g_definition = next(
        item for item in table.definitions if item.symbol_identifier == by_name["g"].identifier
    )
    assert g_definition.operator == "="
    assert g_definition.expression_latex == "f(x)+f(y)"

    a_definition = next(
        item for item in table.definitions if item.symbol_identifier == by_name["A"].identifier
    )
    assert a_definition.operator == ":="
    assert a_definition.expression_latex == r"\{x\in X : f(x)>0\}"

    n_constraint = next(
        item for item in table.constraints if item.symbol_identifier == by_name["n"].identifier
    )
    assert n_constraint.relation == r"\in"
    assert n_constraint.expression_latex == r"\mathbb N"

    for symbol in table.symbols:
        assert symbol.source.text(source) == symbol.name
        assert symbol.raw_introduction == symbol.introduction_source.text(source)
        assert symbol.source.start_line >= 1
        assert symbol.source.start_column >= 1


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_result_proof_and_local_scope_visibility(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    _write_fixture(tex)

    table = extract_project(tex, frontend=frontend_factory()).symbol_table
    by_name = {symbol.name: symbol for symbol in table.symbols}

    result_scope = table.scope(by_name["X"].scope_identifier)
    assert result_scope.kind == ScopeKind.RESULT
    assert result_scope.parent_identifier == "project"

    proof_scope = table.scope(by_name["g"].scope_identifier)
    assert proof_scope.kind == ScopeKind.PROOF
    assert proof_scope.parent_identifier == result_scope.identifier

    local_scope = table.scope(by_name["z"].scope_identifier)
    assert local_scope.kind == ScopeKind.LOCAL
    assert local_scope.parent_identifier == proof_scope.identifier
    assert by_name["z"].introduction_kind == IntroductionKind.QUANTIFIER

    proof_f_use = next(
        use
        for use in table.uses
        if use.name == "f"
        and use.source.start_line >= 8
        and use.resolved_symbol_identifier is not None
    )
    assert proof_f_use.resolved_symbol_identifier == by_name["f"].identifier

    # The quantified variable resolves inside its math-local scope only.
    z_uses = [use for use in table.uses if use.name == "z"]
    assert len(z_uses) == 2
    assert all(use.scope_identifier == local_scope.identifier for use in z_uses)
    assert all(use.resolved_symbol_identifier == by_name["z"].identifier for use in z_uses)


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_unknown_roles_stay_unknown_and_standard_notation_does_not_become_symbols(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:clean-notation}
Let $Q$ be admissible. Let $x$ be real.
Then $\sin x\in\mathbb R$ and $Q=Q$.
\end{theorem}
""",
        encoding="utf-8",
    )

    table = extract_project(tex, frontend=frontend_factory()).symbol_table
    assert [(item.name, item.role) for item in table.symbols] == [
        ("Q", SymbolRole.UNKNOWN),
        ("x", SymbolRole.UNKNOWN),
    ]
    assert not any(item.name in {r"\sin", r"\mathbb", "R"} for item in table.symbols)
    assert not any(item.name == "R" for item in table.uses)
    assert {item.name for item in table.uses} == {"Q", "x"}


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_use_before_introduction_remains_unresolved_for_later_checking(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:order}
First $q>0$. Let $q$ be a real number. Then $q>1$.
\end{theorem}
""",
        encoding="utf-8",
    )

    table = extract_project(tex, frontend=frontend_factory()).symbol_table
    q_uses = [item for item in table.uses if item.name == "q"]
    assert len(q_uses) == 2
    assert q_uses[0].resolved_symbol_identifier is None
    assert q_uses[1].resolved_symbol_identifier is not None


def test_symbol_ir_is_frontend_neutral(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_fixture(tex)

    regex_table = extract_project(tex, frontend=RegexLatexFrontend()).symbol_table
    pylatexenc_table = extract_project(tex, frontend=PylatexencLatexFrontend()).symbol_table

    assert regex_table.model_dump(mode="json") == pylatexenc_table.model_dump(mode="json")
