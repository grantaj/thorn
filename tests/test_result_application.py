from __future__ import annotations

from thorn.formula_ir import (
    ApplyExpr,
    Binder,
    IdentifierExpr,
    LogicalExpr,
    LogicalOperator,
    QuantifiedExpr,
    Quantifier,
)
from thorn.result_application import match_result_application


def _app(name: str, argument):
    return ApplyExpr(
        function=IdentifierExpr(name=name),
        arguments=(argument,),
    )


def _implies(left, right) -> LogicalExpr:
    return LogicalExpr(
        operator=LogicalOperator.IMPLIES,
        arguments=(left, right),
    )


def test_universal_specialization_records_canonical_paths() -> None:
    x = IdentifierExpr(name="x")
    a = IdentifierExpr(name="a")
    result = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x),
        body=_app("Q", x),
    )

    match = match_result_application(result, _app("Q", a))

    assert match is not None
    assert match.specialization
    assert match.precondition is None
    assert len(match.bindings) == 1
    assert match.bindings[0].name == "x"
    assert match.bindings[0].parameter_path == ("binder", "name")
    assert match.bindings[0].argument == a
    assert match.bindings[0].argument_path == ("arguments", "0")


def test_implication_application_instantiates_precondition_without_discharging_it() -> None:
    x = IdentifierExpr(name="x")
    a = IdentifierExpr(name="a")
    result = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x),
        body=_implies(_app("P", x), _app("Q", x)),
    )

    match = match_result_application(result, _app("Q", a))

    assert match is not None
    assert not match.specialization
    assert match.precondition == _app("P", a)
    assert match.precondition_path == ("body", "arguments", "0")
    assert match.bindings[0].argument == a


def test_target_must_fix_every_universal_parameter() -> None:
    x = IdentifierExpr(name="x")
    result = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x),
        body=_implies(_app("P", x), IdentifierExpr(name="Q")),
    )

    assert match_result_application(result, IdentifierExpr(name="Q")) is None
