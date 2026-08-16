from __future__ import annotations

import pytest
from pydantic import ValidationError

from thorn.formula_ir import (
    ApplyExpr,
    ExprLoweringStatus,
    IdentifierExpr,
    LogicalExpr,
    LogicalOperator,
    OpaqueExpr,
    QuantifiedExpr,
    Quantifier,
    RelationExpr,
    RelationOperator,
    SetExpr,
    TupleExpr,
    lower_math_expression,
    render_math_expr,
)


def _lower(text: str):
    return lower_math_expression(text)


def test_safe_quantifier_surface_forms_have_identical_structure() -> None:
    forms = (
        "for all x in R, P(x)",
        "for every x in R, P(x)",
        "∀ x ∈ R, P(x)",
    )

    lowered = [_lower(form) for form in forms]

    assert {item.status for item in lowered} == {ExprLoweringStatus.FULL}
    assert lowered[0].expression == lowered[1].expression == lowered[2].expression
    expression = lowered[0].expression
    assert isinstance(expression, QuantifiedExpr)
    assert expression.binder.name == IdentifierExpr(name="x")
    assert expression.binder.domain == IdentifierExpr(name="R")
    assert isinstance(expression.body, ApplyExpr)
    assert render_math_expr(expression) == "∀x∈R.P(x)"


def test_existential_binder_is_structural() -> None:
    lowered = _lower("there exists a real x such that P(x)")

    assert lowered.status == ExprLoweringStatus.FULL
    expression = lowered.expression
    assert isinstance(expression, QuantifiedExpr)
    assert expression.quantifier == Quantifier.EXISTS
    assert expression.binder.name == IdentifierExpr(name="x")
    assert expression.binder.domain == IdentifierExpr(name="R")
    assert isinstance(expression.body, ApplyExpr)
    assert render_math_expr(expression) == "∃x∈R.P(x)"


def test_typed_real_binder_and_nested_implication_are_structural() -> None:
    lowered = _lower("For every real x, if f(x) > 0 then g(x) = 0.")

    assert lowered.status == ExprLoweringStatus.FULL
    expression = lowered.expression
    assert isinstance(expression, QuantifiedExpr)
    assert expression.binder.domain == IdentifierExpr(name="R")
    assert isinstance(expression.body, LogicalExpr)
    assert expression.body.operator == LogicalOperator.IMPLIES
    antecedent, consequent = expression.body.arguments
    assert isinstance(antecedent, RelationExpr)
    assert antecedent.operator == RelationOperator.GREATER_THAN
    assert isinstance(consequent, RelationExpr)
    assert consequent.operator == RelationOperator.EQUAL
    assert render_math_expr(expression) == "∀x∈R.(f(x)>0⇒g(x)=0)"


@pytest.mark.parametrize(
    ("surface", "symbolic"),
    [
        ("if P then Q", "P ⇒ Q"),
        ("P implies Q", "P ⇒ Q"),
        ("P if and only if Q", "P ⇔ Q"),
        ("P and Q", "P ∧ Q"),
        ("P or Q", "P ∨ Q"),
        ("not P", "¬P"),
        ("x equals y", "x = y"),
        ("x is not equal to y", "x ≠ y"),
        ("x is less than y", "x < y"),
        ("x is at most y", "x ≤ y"),
        ("x is greater than y", "x > y"),
        ("x is at least y", "x ≥ y"),
        ("x belongs to X", "x ∈ X"),
        ("x does not belong to X", "x ∉ X"),
        ("A is a proper subset of B", "A ⊂ B"),
        ("A is a subset of B", "A ⊆ B"),
    ],
)
def test_safe_surface_equivalents_lower_identically(surface: str, symbolic: str) -> None:
    left = _lower(surface)
    right = _lower(symbolic)

    assert left.status == right.status == ExprLoweringStatus.FULL
    assert left.expression == right.expression


@pytest.mark.parametrize(
    ("latex", "symbolic"),
    [
        (r"x \leq y", "x ≤ y"),
        (r"x \ge y", "x ≥ y"),
        (r"x \neq y", "x ≠ y"),
        (r"x \notin X", "x ∉ X"),
        (r"A \subset B", "A ⊂ B"),
        (r"A \subseteq B", "A ⊆ B"),
    ],
)
def test_latex_operator_spellings_lower_identically(latex: str, symbolic: str) -> None:
    left = _lower(latex)
    right = _lower(symbolic)

    assert left.status == right.status == ExprLoweringStatus.FULL
    assert left.expression == right.expression


def test_application_and_nested_logic_preserve_tree_shape() -> None:
    lowered = _lower("P(x) ∧ (Q(x) ∨ R(x)) ⇒ S(x)")

    assert lowered.status == ExprLoweringStatus.FULL
    expression = lowered.expression
    assert isinstance(expression, LogicalExpr)
    assert expression.operator == LogicalOperator.IMPLIES
    conjunction, conclusion = expression.arguments
    assert isinstance(conjunction, LogicalExpr)
    assert conjunction.operator == LogicalOperator.AND
    assert isinstance(conjunction.arguments[1], LogicalExpr)
    assert conjunction.arguments[1].operator == LogicalOperator.OR
    assert isinstance(conclusion, ApplyExpr)
    assert render_math_expr(expression) == "P(x)∧(Q(x)∨R(x))⇒S(x)"


def test_partial_lowering_preserves_understood_outer_binder() -> None:
    lowered = _lower("for all x in R, this predicate is mathematically unresolved")

    assert lowered.status == ExprLoweringStatus.PARTIAL
    expression = lowered.expression
    assert isinstance(expression, QuantifiedExpr)
    assert expression.binder.name.name == "x"
    assert expression.binder.domain == IdentifierExpr(name="R")
    assert isinstance(expression.body, OpaqueExpr)
    assert expression.body.text == "this predicate is mathematically unresolved"


def test_unsupported_syntax_is_explicitly_opaque() -> None:
    lowered = _lower(r"\sum_{i=1}^n a_i has the required property")

    assert lowered.status == ExprLoweringStatus.OPAQUE
    assert isinstance(lowered.expression, OpaqueExpr)
    assert lowered.expression.text


def test_ambiguous_chained_relation_is_not_guessed() -> None:
    lowered = _lower("x < y < z")

    assert lowered.status == ExprLoweringStatus.OPAQUE
    assert isinstance(lowered.expression, OpaqueExpr)
    assert lowered.expression.text == "x < y < z"


def test_tuple_and_simple_set_forms_are_structural() -> None:
    tuple_lowered = _lower("(x,y)")
    set_lowered = _lower("{x,y}")

    assert tuple_lowered.status == ExprLoweringStatus.FULL
    assert isinstance(tuple_lowered.expression, TupleExpr)
    assert set_lowered.status == ExprLoweringStatus.FULL
    assert isinstance(set_lowered.expression, SetExpr)


def test_expression_nodes_are_value_like_and_immutable() -> None:
    expression = IdentifierExpr(name="x")

    with pytest.raises(ValidationError):
        expression.name = "y"
