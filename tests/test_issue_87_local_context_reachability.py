from __future__ import annotations

from pathlib import Path

import pytest
from candidate_context_contract import prepare_all_prior_context
from sentence_contract_frontend import SentenceContractFrontend

from thorn.eval_review import build_result_review_context
from thorn.formula_ir import ExprLoweringStatus
from thorn.latex import extract_project
from thorn.llm_proof_language import project_llm_proof_language
from thorn.proof_language_review import advertised_source_addresses
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import build_semantic_transformation_ir
from thorn.symbols import ScopeKind


def _build(path: Path, target: str):
    project = extract_project(path)
    unit = project.unit(target)
    context = build_result_review_context(project, target)
    request = build_semantic_review_request(context.items[0])
    semantic = build_semantic_transformation_ir(
        unit,
        request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    return project, semantic, project_llm_proof_language(semantic)


def _advisory(path: Path, target: str):
    project = extract_project(path, linguistic_frontend=SentenceContractFrontend())
    return project, prepare_all_prior_context(project, target)


def _definition_source(project, document, symbol_name: str):
    symbol = next(
        item
        for item in project.symbol_table.symbols
        if item.name == symbol_name and item.scope_identifier == "project"
    )
    definition = next(
        item
        for item in project.symbol_table.definitions
        if item.symbol_identifier == symbol.identifier
    )
    source = next(item for item in document.sources if item.ir_identifier == definition.identifier)
    return definition, source


def _is_represented_or_advertised(semantic, document, source_address: str) -> bool:
    proposition = semantic.higher.resolved.proof.proposition(source_address)
    represented = (
        proposition.expression is not None
        and proposition.expression_status is not None
        and proposition.expression_status != ExprLoweringStatus.OPAQUE
    )
    return represented or source_address in advertised_source_addresses(document)


def _advisory_source(prepared, needle: str):
    matches = [source for source in prepared.document.sources if needle in source.text]
    assert len(matches) == 1
    return matches[0]


def test_clean_unusual_notation_keeps_structural_authority_and_full_prose_source() -> None:
    path = Path("eval/cases/ladder/02_readability/clean_unusual_notation.tex")
    project, semantic, document = _build(path, "thm:unusual-notation")

    definition, source = _definition_source(project, document, r"\blacktriangleleft")
    assert definition.operator == ":="
    assert definition.expression_latex == "x<y"
    assert source.text.strip() == r"define $x\blacktriangleleft y$ to mean $x<y$"
    assert source.address == "D1"
    assert _is_represented_or_advertised(semantic, document, source.address)

    _, prepared = _advisory(path, "thm:unusual-notation")
    prose = _advisory_source(
        prepared,
        r"For real numbers define $x\blacktriangleleft y$ to mean $x<y$.",
    )
    assert prose.address in advertised_source_addresses(prepared.document)
    assert prose.source_span is not None
    assert prose.source_range is not None


def test_notation_collision_keeps_separate_set_map_authority_and_prose() -> None:
    path = Path("eval/cases/ladder/02_readability/notation_collision.tex")
    project, semantic, document = _build(path, "thm:notation-collision")

    definition, source = _definition_source(project, document, "C")
    assert definition.expression_latex == "[0,1]"
    assert source.text.strip() == "Let $C=[0,1]$"
    assert _is_represented_or_advertised(semantic, document, source.address)

    map_symbol = next(
        item
        for item in project.symbol_table.symbols
        if item.name == "f" and item.scope_identifier == "project"
    )
    assert map_symbol.domain_latex == "C"
    assert map_symbol.codomain_latex == r"\mathbb R"
    mapping = next(
        item
        for item in project.symbol_table.constraints
        if item.symbol_identifier == map_symbol.identifier and item.relation == ":"
    )
    map_source = next(
        item for item in document.sources if item.ir_identifier == mapping.identifier
    )
    assert map_source.text.strip() == r"let $f:C\to\mathbb R$"
    assert _is_represented_or_advertised(semantic, document, map_source.address)

    _, prepared = _advisory(path, "thm:notation-collision")
    prior_texts = [source.text for source in prepared.document.sources]
    assert any("Let $C=[0,1]$" in text for text in prior_texts)
    assert any(r"$f:C\to\mathbb R$ be continuous" in text for text in prior_texts)

    # The frozen source uses prose "There exists" rather than a mechanical
    # quantifier, so this fixture is a reachability witness, not a claim that the
    # local scalar C has already been deterministically recovered.
    assert "C" in document.render_initial()
    assert ">0" in document.render_initial().replace(" ", "")


def _write_case(path: Path, preamble: str, statement: str, proof: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
{preamble}
\begin{{theorem}}\label{{thm:main}}
{statement}
\end{{theorem}}
\begin{{proof}}
{proof}
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("preamble", "statement", "proof", "symbol_name", "structural_fragment"),
    [
        (
            r"Define $u\diamond v$ to mean $u+v$.",
            r"$1\diamond 2=3$.",
            r"By definition, $1+2=3$, hence $1\diamond 2=3$.",
            r"\diamond",
            r"Define $u\diamond v$ to mean $u+v$",
        ),
        (
            r"Let $A=[-1,1]$.",
            r"$0\in A$.",
            r"Since $0\in[-1,1]$, the claim follows.",
            "A",
            r"Let $A=[-1,1]$",
        ),
        (
            r"For every $n>0$ in what follows.",
            r"$n>0$ implies $n+1>1$.",
            r"The stated inequality is immediate.",
            "n",
            r"For every $n>0$",
        ),
        (
            r"Define $g(t)=t^2$.",
            r"$g(2)=4$.",
            r"By definition, $g(2)=2^2=4$.",
            "g",
            r"Define $g(t)=t^2$",
        ),
        (
            r"Let $h:X\to Y$ be the comparison map.",
            r"$h(x)\in Y$.",
            r"The codomain declaration gives the claim.",
            "h",
            r"Let $h:X\to Y$",
        ),
    ],
)
def test_held_out_project_authority_has_structural_and_advisory_source(
    tmp_path: Path,
    preamble: str,
    statement: str,
    proof: str,
    symbol_name: str,
    structural_fragment: str,
) -> None:
    tex = tmp_path / "context.tex"
    _write_case(tex, preamble, statement, proof)
    project, semantic, document = _build(tex, "thm:main")

    symbol = next(
        item
        for item in project.symbol_table.symbols
        if item.name == symbol_name and item.scope_identifier == "project"
    )
    canonical = [
        source
        for source in document.sources
        if structural_fragment in source.text
        and (
            source.ir_identifier == f"definition:{symbol.identifier}"
            or source.ir_identifier.startswith(f"constraint:{symbol.identifier}")
        )
    ]
    assert len(canonical) == 1
    assert _is_represented_or_advertised(semantic, document, canonical[0].address)

    _, prepared = _advisory(tex, "thm:main")
    prose = _advisory_source(prepared, preamble)
    assert prose.address in advertised_source_addresses(prepared.document)
    assert prose.source_span is not None
    assert prose.source_span.text(tex.read_text(encoding="utf-8")) == preamble


@pytest.mark.parametrize(
    "preamble",
    [
        r"For $x\in X$, consider the temporary picture below.",
        r"For every $x>0$ in this example, draw the corresponding curve.",
        r"Let $x$ vary through the following example.",
        r"Let $x>0$ for this example.",
        r"Set $x$ aside for the moment.",
        r"Define $x$ informally in the discussion below.",
    ],
)
def test_expository_project_cues_do_not_become_authoritative_scope(
    tmp_path: Path,
    preamble: str,
) -> None:
    tex = tmp_path / "expository.tex"
    _write_case(
        tex,
        preamble,
        r"$x=x$.",
        r"The displayed identity is reflexive.",
    )
    project = extract_project(tex)

    assert not any(
        symbol.name == "x" and symbol.scope_identifier == "project"
        for symbol in project.symbol_table.symbols
    )


def test_project_context_respects_explicit_local_shadowing(tmp_path: Path) -> None:
    tex = tmp_path / "shadowing.tex"
    _write_case(
        tex,
        r"Let $C=[0,1]$.",
        r"$\exists C>0:\ C=1$.",
        r"The witness in the statement is local.",
    )
    project = extract_project(tex)

    outer = next(
        symbol
        for symbol in project.symbol_table.symbols
        if symbol.name == "C" and symbol.scope_identifier == "project"
    )
    local = next(
        symbol
        for symbol in project.symbol_table.symbols
        if symbol.name == "C"
        and project.symbol_table.scope(symbol.scope_identifier).kind == ScopeKind.LOCAL
    )
    assert outer.identifier != local.identifier

    local_uses = [
        use
        for use in project.symbol_table.uses
        if use.name == "C" and use.scope_identifier == local.scope_identifier
    ]
    assert local_uses
    assert {use.resolved_symbol_identifier for use in local_uses} == {local.identifier}
