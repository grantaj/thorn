from __future__ import annotations

from dataclasses import dataclass

from thorn.formula_ir import (
    ApplyExpr,
    IdentifierExpr,
    LiteralExpr,
    LogicalExpr,
    LogicalOperator,
    MathExpr,
    NotExpr,
    OpaqueExpr,
    OperatorExpr,
    QuantifiedExpr,
    Quantifier,
    RelationExpr,
    SetExpr,
    TupleExpr,
)


@dataclass(frozen=True, slots=True)
class ResultParameterBinding:
    """One universally quantified result parameter fixed by the claimed target."""

    name: str
    parameter_path: tuple[str, ...]
    argument: MathExpr
    argument_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResultApplicationMatch:
    """Formula-shape evidence that one result can produce the claimed target.

    This records only the application shape fixed by canonical expressions.  A
    precondition being present here does not mean the local proof context
    discharges it; that remains a downstream proof-obligation question.
    """

    bindings: tuple[ResultParameterBinding, ...] = ()
    precondition: MathExpr | None = None
    precondition_path: tuple[str, ...] | None = None
    specialization: bool = False


@dataclass(frozen=True, slots=True)
class _TemplateBinding:
    argument: MathExpr
    argument_path: tuple[str, ...]


def _child_items(expression: MathExpr) -> list[tuple[tuple[str, ...], MathExpr]]:
    if isinstance(expression, ApplyExpr):
        return [
            (("function",), expression.function),
            *[
                (("arguments", str(index)), item)
                for index, item in enumerate(expression.arguments)
            ],
        ]
    if isinstance(expression, OperatorExpr | LogicalExpr):
        return [
            (("arguments", str(index)), item)
            for index, item in enumerate(expression.arguments)
        ]
    if isinstance(expression, RelationExpr):
        return [(("left",), expression.left), (("right",), expression.right)]
    if isinstance(expression, NotExpr):
        return [(("operand",), expression.operand)]
    if isinstance(expression, TupleExpr | SetExpr):
        return [
            (("items", str(index)), item)
            for index, item in enumerate(expression.items)
        ]
    return []


def _same_shape(left: MathExpr, right: MathExpr) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, IdentifierExpr | LiteralExpr | OpaqueExpr):
        return left == right
    if isinstance(left, ApplyExpr) and isinstance(right, ApplyExpr):
        return len(left.arguments) == len(right.arguments)
    if isinstance(left, OperatorExpr) and isinstance(right, OperatorExpr):
        return (
            left.operator == right.operator
            and len(left.arguments) == len(right.arguments)
        )
    if isinstance(left, LogicalExpr) and isinstance(right, LogicalExpr):
        return (
            left.operator == right.operator
            and len(left.arguments) == len(right.arguments)
        )
    if isinstance(left, RelationExpr) and isinstance(right, RelationExpr):
        return left.operator == right.operator
    if isinstance(left, NotExpr) and isinstance(right, NotExpr):
        return True
    if isinstance(left, TupleExpr) and isinstance(right, TupleExpr):
        return len(left.items) == len(right.items)
    if isinstance(left, SetExpr) and isinstance(right, SetExpr):
        return len(left.items) == len(right.items)
    return False


def _match_template(
    pattern: MathExpr,
    target: MathExpr,
    *,
    parameter_names: set[str],
    pattern_path: tuple[str, ...] = (),
    target_path: tuple[str, ...] = (),
) -> dict[str, _TemplateBinding] | None:
    bindings: dict[str, _TemplateBinding] = {}

    def match(
        left: MathExpr,
        right: MathExpr,
        left_path: tuple[str, ...],
        right_path: tuple[str, ...],
    ) -> bool:
        if isinstance(left, IdentifierExpr) and left.name in parameter_names:
            existing = bindings.get(left.name)
            if existing is None:
                bindings[left.name] = _TemplateBinding(
                    argument=right,
                    argument_path=right_path,
                )
                return True
            return existing.argument == right
        if isinstance(left, QuantifiedExpr) or isinstance(right, QuantifiedExpr):
            return False
        if not _same_shape(left, right):
            return False

        left_children = _child_items(left)
        right_children = _child_items(right)
        if len(left_children) != len(right_children):
            return False
        return all(
            left_suffix == right_suffix
            and match(
                left_child,
                right_child,
                (*left_path, *left_suffix),
                (*right_path, *right_suffix),
            )
            for (left_suffix, left_child), (right_suffix, right_child) in zip(
                left_children,
                right_children,
                strict=True,
            )
        )

    return bindings if match(pattern, target, pattern_path, target_path) else None


def _unwrap_universals(
    expression: MathExpr,
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], MathExpr, tuple[str, ...]]:
    parameters: list[tuple[str, tuple[str, ...]]] = []
    current = expression
    path: tuple[str, ...] = ()
    while isinstance(current, QuantifiedExpr) and current.quantifier == Quantifier.FOR_ALL:
        parameters.append((current.binder.name.name, (*path, "binder", "name")))
        current = current.body
        path = (*path, "body")
    return tuple(parameters), current, path


def _free_names(expression: MathExpr) -> set[str]:
    if isinstance(expression, IdentifierExpr):
        return {expression.name}
    if isinstance(expression, LiteralExpr | OpaqueExpr):
        return set()
    if isinstance(expression, QuantifiedExpr):
        bound_names = _free_names(expression.body)
        bound_names.discard(expression.binder.name.name)
        if expression.binder.domain is not None:
            bound_names.update(_free_names(expression.binder.domain))
        return bound_names

    free_names: set[str] = set()
    for _suffix, child in _child_items(expression):
        free_names.update(_free_names(child))
    return free_names


def _instantiate(
    expression: MathExpr,
    bindings: dict[str, _TemplateBinding],
) -> MathExpr | None:
    replacements = {name: item.argument for name, item in bindings.items()}

    def visit(current: MathExpr, active: dict[str, MathExpr]) -> MathExpr | None:
        if isinstance(current, IdentifierExpr):
            return active.get(current.name, current)
        if isinstance(current, LiteralExpr | OpaqueExpr):
            return current
        if isinstance(current, ApplyExpr):
            function = visit(current.function, active)
            arguments = [visit(item, active) for item in current.arguments]
            if function is None or any(item is None for item in arguments):
                return None
            return ApplyExpr(
                function=function,
                arguments=tuple(item for item in arguments if item is not None),
            )
        if isinstance(current, OperatorExpr):
            arguments = [visit(item, active) for item in current.arguments]
            if any(item is None for item in arguments):
                return None
            return OperatorExpr(
                operator=current.operator,
                arguments=tuple(item for item in arguments if item is not None),
            )
        if isinstance(current, RelationExpr):
            left = visit(current.left, active)
            right = visit(current.right, active)
            if left is None or right is None:
                return None
            return RelationExpr(operator=current.operator, left=left, right=right)
        if isinstance(current, LogicalExpr):
            arguments = [visit(item, active) for item in current.arguments]
            if any(item is None for item in arguments):
                return None
            return LogicalExpr(
                operator=current.operator,
                arguments=tuple(item for item in arguments if item is not None),
            )
        if isinstance(current, NotExpr):
            operand = visit(current.operand, active)
            return NotExpr(operand=operand) if operand is not None else None
        if isinstance(current, TupleExpr):
            items = [visit(item, active) for item in current.items]
            if any(item is None for item in items):
                return None
            return TupleExpr(items=tuple(item for item in items if item is not None))
        if isinstance(current, SetExpr):
            items = [visit(item, active) for item in current.items]
            if any(item is None for item in items):
                return None
            return SetExpr(items=tuple(item for item in items if item is not None))
        if isinstance(current, QuantifiedExpr):
            binder_name = current.binder.name.name
            remaining = {
                name: replacement
                for name, replacement in active.items()
                if name != binder_name
            }
            if any(
                binder_name in _free_names(replacement)
                for replacement in remaining.values()
            ):
                return None
            domain = (
                visit(current.binder.domain, remaining)
                if current.binder.domain is not None
                else None
            )
            body = visit(current.body, remaining)
            if body is None or (
                current.binder.domain is not None and domain is None
            ):
                return None
            return current.model_copy(
                update={
                    "binder": current.binder.model_copy(update={"domain": domain}),
                    "body": body,
                }
            )
        return None

    return visit(expression, replacements)


def match_result_application(
    result: MathExpr,
    target: MathExpr,
) -> ResultApplicationMatch | None:
    """Match a cited result to an exact claimed target without proving premises.

    The target must fix every universal parameter used by the cited result.  An
    implication precondition is instantiated and returned as an obligation
    template, but its presence in local context is deliberately not required for
    this match: identifying the application and discharging its premise are
    separate proof facts.
    """

    parameters, body, body_path = _unwrap_universals(result)
    parameter_names = {name for name, _path in parameters}

    matches = _match_template(
        body,
        target,
        parameter_names=parameter_names,
    )
    precondition: MathExpr | None = None
    precondition_path: tuple[str, ...] | None = None
    specialization = bool(parameters)

    if matches is None:
        if (
            not isinstance(body, LogicalExpr)
            or body.operator != LogicalOperator.IMPLIES
            or len(body.arguments) != 2
        ):
            return None
        antecedent, conclusion = body.arguments
        matches = _match_template(
            conclusion,
            target,
            parameter_names=parameter_names,
        )
        if matches is None:
            return None
        precondition = antecedent
        precondition_path = (*body_path, "arguments", "0")
        specialization = False

    if any(name not in matches for name, _path in parameters):
        return None

    if precondition is not None:
        precondition = _instantiate(precondition, matches)
        if precondition is None:
            return None

    bindings = tuple(
        ResultParameterBinding(
            name=name,
            parameter_path=parameter_path,
            argument=matches[name].argument,
            argument_path=matches[name].argument_path,
        )
        for name, parameter_path in parameters
    )
    return ResultApplicationMatch(
        bindings=bindings,
        precondition=precondition,
        precondition_path=precondition_path,
        specialization=specialization,
    )
