from __future__ import annotations

from thorn.formula_ir import (
    BuiltinDomain,
    BuiltinDomainExpr,
    IdentifierExpr,
    QuantifiedExpr,
    lower_math_expression,
    render_math_expr,
)


def test_builtin_naturals_are_distinct_from_named_domain_n() -> None:
    natural_word = lower_math_expression("For every natural x, P(x)")
    mathbb_n = lower_math_expression(r"\forall x \in \mathbb{N}, P(x)")
    named_n = lower_math_expression("For every x in N, P(x)")

    assert isinstance(natural_word.expression, QuantifiedExpr)
    assert isinstance(mathbb_n.expression, QuantifiedExpr)
    assert isinstance(named_n.expression, QuantifiedExpr)

    builtin = BuiltinDomainExpr(domain=BuiltinDomain.NATURALS)
    assert natural_word.expression.binder.domain == builtin
    assert mathbb_n.expression.binder.domain == builtin
    assert named_n.expression.binder.domain == IdentifierExpr(name="N")

    assert natural_word.expression == mathbb_n.expression
    assert natural_word.expression != named_n.expression
    assert render_math_expr(natural_word.expression) == "∀x∈ℕ.P(x)"
    assert render_math_expr(named_n.expression) == "∀x∈N.P(x)"
