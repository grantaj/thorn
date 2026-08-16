from __future__ import annotations

import re
from pathlib import Path

from thorn.canonical_proof_ir import build_canonical_proof_ir
from thorn.canonical_typed_proof_ir import build_canonical_typed_proof_ir
from thorn.eval_review import build_result_review_context
from thorn.formula_ir import (
    ApplyExpr,
    ExprLoweringStatus,
    LogicalExpr,
    OpaqueExpr,
    QuantifiedExpr,
    RelationExpr,
)
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.semantic_review_render import build_semantic_review_request

CASES = Path("eval/cases/ladder")


class _RootedTestFrontend:
    name = "rooted-test"

    def parse(self, text: str) -> LinguisticDocument:
        matches = list(re.finditer(r"\S+", text))
        tokens: list[LinguisticToken] = []
        for index, match in enumerate(matches):
            tokens.append(
                LinguisticToken(
                    index=index,
                    text=match.group(0),
                    lemma=match.group(0).lower(),
                    pos="VERB" if index == 0 else "NOUN",
                    dependency="ROOT" if index == 0 else "dep",
                    head_index=0,
                    sentence_index=0,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return LinguisticDocument(text=text, tokens=tokens)


def _build(path: Path, target_identifier: str):
    project = extract_project(path, linguistic_frontend=_RootedTestFrontend())
    unit = project.unit(target_identifier)
    context = build_result_review_context(project, target_identifier)
    assert len(context.items) == 1
    request = build_semantic_review_request(context.items[0])
    graph = build_canonical_proof_ir(unit, request)
    typed = build_canonical_typed_proof_ir(unit, request)
    return request, graph, typed


def _write_document(path: Path, *, statement: str, proof: str) -> None:
    path.write_text(
        """\\documentclass{article}
\\usepackage{amsthm}
\\newtheorem{theorem}{Theorem}
\\begin{document}
\\begin{theorem}\\label{thm:test}
"""
        + statement
        + """
\\end{theorem}
\\begin{proof}
"""
        + proof
        + """
\\end{proof}
\\end{document}
""",
        encoding="utf-8",
    )


def _typed_payloads(ir):
    return [
        (node.address, node.kind, node.expression, node.expression_status)
        for node in ir.nodes
    ]


def test_typed_ir_keeps_graph_slice_and_legacy_rendering_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "typed.tex"
    _write_document(
        path,
        statement="For every real $x$, if $f(x)>0$ then $g(x)=0$.",
        proof="""\\[
f(x)>0 \\Rightarrow g(x)=0
\\]
""",
    )

    request, graph, typed = _build(path, "thm:test")

    assert typed.render_initial() == graph.render_initial()
    assert typed.pruned_claims == graph.pruned_claims
    assert typed.unresolved_math_claims == graph.unresolved_math_claims
    assert [(edge.address, edge.kind, edge.source, edge.target) for edge in typed.edges] == [
        (edge.address, edge.kind, edge.source, edge.target) for edge in graph.edges
    ]
    result = typed.nodes[0]
    assert result.address == "T0"
    assert result.expression_status == ExprLoweringStatus.FULL
    assert isinstance(result.expression, QuantifiedExpr)
    assert isinstance(result.expression.body, LogicalExpr)

    claim = next(node for node in typed.nodes if node.address.startswith("C"))
    assert claim.expression_status == ExprLoweringStatus.FULL
    assert isinstance(claim.expression, LogicalExpr)
    assert request.item.result.identifier == typed.result_identifier


def test_expression_and_subexpression_source_are_exactly_recoverable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "provenance.tex"
    statement = "For every real $x$, if $f(x)>0$ then $g(x)=0$."
    _write_document(
        path,
        statement=statement,
        proof="""\\[
g(x)=0
\\]
""",
    )

    _, _, typed = _build(path, "thm:test")

    root_source = typed.expression_source("T0")
    left_application_source = typed.expression_source(
        "T0",
        ("body", "arguments", "0", "left"),
    )
    assert root_source.text == statement
    assert left_application_source.text == statement
    assert root_source.source_range is not None


def test_partial_statement_keeps_understood_outer_structure(tmp_path: Path) -> None:
    path = tmp_path / "partial.tex"
    statement = "For every real $x$, this predicate is mathematically unresolved."
    _write_document(
        path,
        statement=statement,
        proof="""\\[
Q
\\]
""",
    )

    _, _, typed = _build(path, "thm:test")

    result = typed.nodes[0]
    assert result.expression_status == ExprLoweringStatus.PARTIAL
    assert isinstance(result.expression, QuantifiedExpr)
    assert isinstance(result.expression.body, OpaqueExpr)
    assert typed.expression_source("T0", ("body",)).text == statement


def test_non_load_bearing_prose_does_not_perturb_mathematical_ast(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base.tex"
    with_exposition = tmp_path / "with-exposition.tex"
    display = """\\[
Q
\\]
"""
    _write_document(base, statement="$Q$.", proof=display)
    _write_document(
        with_exposition,
        statement="$Q$.",
        proof="This sentence only orients the reader.\n" + display,
    )

    _, _, base_typed = _build(base, "thm:test")
    _, _, exposition_typed = _build(with_exposition, "thm:test")

    assert _typed_payloads(base_typed) == _typed_payloads(exposition_typed)
    assert base_typed.render_initial() == exposition_typed.render_initial()
    assert exposition_typed.pruned_claims == 1


def test_canonical_typed_lowering_does_not_mutate_math_ir(tmp_path: Path) -> None:
    path = tmp_path / "immutable-input.tex"
    _write_document(
        path,
        statement="$Q$.",
        proof="""\\[
P(x)
\\]
Therefore $Q$.
""",
    )
    project = extract_project(path, linguistic_frontend=_RootedTestFrontend())
    unit = project.unit("thm:test")
    context = build_result_review_context(project, "thm:test")
    request = build_semantic_review_request(context.items[0])
    before = request.item.model_dump(mode="json")

    build_canonical_typed_proof_ir(unit, request)

    assert request.item.model_dump(mode="json") == before


def test_public_hypothesis_payload_is_structural() -> None:
    _, _, typed = _build(
        CASES / "03_hypotheses/clean_nonzero_cancellation.tex",
        "thm:clean-nonzero",
    )

    hypotheses = [node for node in typed.nodes if node.address.startswith("H")]
    assert hypotheses
    assert all(node.expression_status == ExprLoweringStatus.FULL for node in hypotheses)
    assert all(isinstance(node.expression, RelationExpr) for node in hypotheses)


def test_function_application_is_not_left_as_a_string_payload(tmp_path: Path) -> None:
    path = tmp_path / "application.tex"
    _write_document(
        path,
        statement="$P(x)$.",
        proof="""\\[
P(x)
\\]
""",
    )

    _, _, typed = _build(path, "thm:test")

    result = typed.nodes[0]
    assert result.expression_status == ExprLoweringStatus.FULL
    assert isinstance(result.expression, ApplyExpr)
