from __future__ import annotations

from collections import deque
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from thorn.dependencies import DependencyGraph
from thorn.evidence import InferenceStatus
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
    RelationOperator,
    SetExpr,
    TupleExpr,
)
from thorn.higher_proof_structure import HigherProofIR, build_higher_proof_ir
from thorn.models import TheoremUnit
from thorn.proof_obligations import (
    ObligationStatus,
    ProofProposition,
    ProofRuleKind,
    ProofStepEdge,
    PropositionRole,
)
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.symbol_resolution_ir import (
    ExpressionRef,
    SymbolResolutionIR,
    alpha_equivalent,
)
from thorn.symbols import SymbolTable


class SemanticSupportKind(StrEnum):
    RESULT = "result"
    DEFINITION = "definition"
    EQUALITY = "equality"
    NAMED_PROPERTY = "named_property"


class SemanticTransformationKind(StrEnum):
    RESULT_APPLICATION = "result_application"
    RESULT_SPECIALIZATION = "result_specialization"
    DEFINITION_USE = "definition_use"
    DEFINITION_UNFOLD = "definition_unfold"
    EQUALITY_REWRITE = "equality_rewrite"
    NAMED_PROPERTY_APPLICATION = "named_property_application"


class SemanticParameterBinding(BaseModel):
    """One universal parameter mapped to a canonical target AST node."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parameter_ref: ExpressionRef
    argument_ref: ExpressionRef | None = None
    status: InferenceStatus = InferenceStatus.UNRESOLVED


class SemanticSupportAtom(BaseModel):
    """What a proof step references, separate from what it does with that support."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    kind: SemanticSupportKind
    step_address: str
    proposition_address: str | None = None
    expression_ref: ExpressionRef | None = None
    name: str | None = None
    referenced_result_identifier: str | None = None
    dependency_path: tuple[str, ...] = ()
    status: InferenceStatus = InferenceStatus.UNRESOLVED
    source_addresses: tuple[str, ...] = ()


class SemanticApplicationObligation(BaseModel):
    """A result-application precondition that must exist in local proof context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    transformation_address: str
    template_ref: ExpressionRef | None = None
    expected: MathExpr | None = None
    local_context: tuple[str, ...] = ()
    satisfied_by: tuple[str, ...] = ()
    status: ObligationStatus = ObligationStatus.UNRESOLVED
    source_addresses: tuple[str, ...] = ()


class SemanticTransformation(BaseModel):
    """A mechanically recovered semantic operation, not a validity certificate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    kind: SemanticTransformationKind
    step_addresses: tuple[str, ...] = ()
    support_atom_addresses: tuple[str, ...] = ()
    input_refs: tuple[ExpressionRef, ...] = ()
    target_ref: ExpressionRef
    parameter_bindings: tuple[SemanticParameterBinding, ...] = ()
    obligation_addresses: tuple[str, ...] = ()
    rewrite_from_ref: ExpressionRef | None = None
    rewrite_to_ref: ExpressionRef | None = None
    replacement_sites: tuple[ExpressionRef, ...] = ()
    lower_operation_address: str | None = None
    status: InferenceStatus = InferenceStatus.UNRESOLVED
    source_addresses: tuple[str, ...] = ()
    opaque_source_addresses: tuple[str, ...] = ()


class SemanticTransformationIR(BaseModel):
    """Issue-64 semantic transformations over issue-63 higher proof structure."""

    result_identifier: str
    higher: HigherProofIR
    support_atoms: list[SemanticSupportAtom] = Field(default_factory=list)
    transformations: list[SemanticTransformation] = Field(default_factory=list)
    obligations: list[SemanticApplicationObligation] = Field(default_factory=list)

    def support_atom(self, address: str) -> SemanticSupportAtom:
        for item in self.support_atoms:
            if item.address == address:
                return item
        raise KeyError(f"unknown semantic support atom {address!r}")

    def transformation(self, address: str) -> SemanticTransformation:
        for item in self.transformations:
            if item.address == address:
                return item
        raise KeyError(f"unknown semantic transformation {address!r}")

    def obligation(self, address: str) -> SemanticApplicationObligation:
        for item in self.obligations:
            if item.address == address:
                return item
        raise KeyError(f"unknown semantic application obligation {address!r}")


class _TemplateBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    argument: MathExpr
    argument_path: tuple[str, ...]


class _ReplacementMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sites: tuple[tuple[str, ...], ...]


def _dedupe(items: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _propositions(resolved: SymbolResolutionIR) -> dict[str, ProofProposition]:
    return {item.address: item for item in resolved.proof.propositions}


def _steps(resolved: SymbolResolutionIR) -> dict[str, ProofStepEdge]:
    return {item.address: item for item in resolved.proof.steps}


def _expression(proposition: ProofProposition | None) -> MathExpr | None:
    if proposition is None or proposition.expression is None:
        return None
    if proposition.role == PropositionRole.UNRESOLVED:
        return None
    return proposition.expression


def _context(resolved: SymbolResolutionIR, target: str) -> tuple[str, ...]:
    matches = [
        item
        for item in resolved.proof.obligations
        if item.proposition_address == target
    ]
    return matches[0].local_context if len(matches) == 1 else ()


def _context_matches(
    resolved: SymbolResolutionIR,
    expected: MathExpr,
    context: tuple[str, ...],
    *,
    exclude: tuple[str, ...] = (),
) -> tuple[str, ...]:
    excluded = set(exclude)
    matches: list[str] = []
    for address in context:
        if address in excluded:
            continue
        try:
            proposition = resolved.proof.proposition(address)
        except KeyError:
            continue
        candidate = _expression(proposition)
        if candidate is not None and alpha_equivalent(candidate, expected):
            matches.append(address)
    return tuple(matches)


def _dependency_path(
    result_identifier: str,
    referenced_identifier: str | None,
    graph: DependencyGraph | None,
) -> tuple[str, ...]:
    if referenced_identifier is None:
        return ()
    direct = (result_identifier, referenced_identifier)
    if graph is None:
        return direct
    try:
        graph.node(result_identifier)
        graph.node(referenced_identifier)
    except KeyError:
        return direct

    pending: deque[tuple[str, tuple[str, ...]]] = deque(
        [(result_identifier, (result_identifier,))]
    )
    visited = {result_identifier}
    while pending:
        current, path = pending.popleft()
        if current == referenced_identifier:
            return path
        for target in graph.direct_dependency_ids(current):
            if target in visited:
                continue
            visited.add(target)
            pending.append((target, (*path, target)))
    return direct


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

    return bindings if match(pattern, target, (), ()) else None


def _unwrap_universals(
    expression: MathExpr,
) -> tuple[list[tuple[str, tuple[str, ...]]], MathExpr, tuple[str, ...]]:
    parameters: list[tuple[str, tuple[str, ...]]] = []
    current = expression
    path: tuple[str, ...] = ()
    while isinstance(current, QuantifiedExpr) and current.quantifier == Quantifier.FOR_ALL:
        parameters.append((current.binder.name.name, (*path, "binder", "name")))
        current = current.body
        path = (*path, "body")
    return parameters, current, path


def _free_names(expression: MathExpr) -> set[str]:
    if isinstance(expression, IdentifierExpr):
        return {expression.name}
    if isinstance(expression, LiteralExpr | OpaqueExpr):
        return set()
    if isinstance(expression, QuantifiedExpr):
        names = _free_names(expression.body)
        names.discard(expression.binder.name.name)
        if expression.binder.domain is not None:
            names.update(_free_names(expression.binder.domain))
        return names

    names: set[str] = set()
    for _suffix, child in _child_items(expression):
        names.update(_free_names(child))
    return names


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


def _replacement(
    source: MathExpr,
    target: MathExpr,
    *,
    old: MathExpr,
    new: MathExpr,
) -> _ReplacementMatch | None:
    sites: list[tuple[str, ...]] = []

    def match(
        left: MathExpr,
        right: MathExpr,
        left_path: tuple[str, ...],
        right_path: tuple[str, ...],
    ) -> bool:
        if left == old and right == new:
            sites.append(right_path)
            return True
        if left == right:
            return True
        if isinstance(left, QuantifiedExpr) or isinstance(right, QuantifiedExpr):
            return False
        if not _same_shape(left, right):
            return False
        left_children = _child_items(left)
        right_children = _child_items(right)
        return len(left_children) == len(right_children) and all(
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

    return (
        _ReplacementMatch(sites=tuple(sites))
        if match(source, target, (), ()) and sites
        else None
    )


def _atom(
    resolved: SymbolResolutionIR,
    step: ProofStepEdge,
    proposition: ProofProposition | None,
    *,
    address: str,
    kind: SemanticSupportKind,
    graph: DependencyGraph | None = None,
    name: str | None = None,
) -> SemanticSupportAtom:
    proposition_address = None
    expression_ref = None
    referenced_result_identifier = None
    source_addresses = list(step.source_addresses)

    if proposition is not None:
        proposition_address = proposition.address
        if proposition.expression is not None:
            expression_ref = ExpressionRef(owner_address=proposition.address)
        source_addresses.append(proposition.source_address)
        source = resolved.proof.source(proposition.source_address)
        referenced_result_identifier = source.referenced_result_identifier

    if kind == SemanticSupportKind.RESULT and referenced_result_identifier is None:
        try:
            source = resolved.proof.source(step.canonical_edge_address or step.address)
            referenced_result_identifier = source.referenced_result_identifier
        except KeyError:
            pass

    return SemanticSupportAtom(
        address=address,
        kind=kind,
        step_address=step.address,
        proposition_address=proposition_address,
        expression_ref=expression_ref,
        name=name,
        referenced_result_identifier=referenced_result_identifier,
        dependency_path=_dependency_path(
            resolved.result_identifier,
            referenced_result_identifier,
            graph,
        ),
        status=step.status,
        source_addresses=_dedupe(source_addresses),
    )


def _operation_status(
    *,
    reference_status: InferenceStatus,
    matched: bool,
    bindings: tuple[SemanticParameterBinding, ...] = (),
    obligations: tuple[SemanticApplicationObligation, ...] = (),
) -> InferenceStatus:
    if not matched or reference_status == InferenceStatus.UNRESOLVED:
        return InferenceStatus.UNRESOLVED
    if any(item.status == InferenceStatus.UNRESOLVED for item in bindings):
        return InferenceStatus.UNRESOLVED
    if any(item.status == ObligationStatus.UNRESOLVED for item in obligations):
        return InferenceStatus.UNRESOLVED
    if reference_status == InferenceStatus.AMBIGUOUS:
        return InferenceStatus.AMBIGUOUS
    if any(item.status == InferenceStatus.AMBIGUOUS for item in bindings):
        return InferenceStatus.AMBIGUOUS
    return InferenceStatus.CONFIDENT


def _result_applications(
    resolved: SymbolResolutionIR,
    *,
    transform_start: int,
    atom_start: int,
    obligation_start: int,
    graph: DependencyGraph | None,
) -> tuple[
    list[SemanticTransformation],
    list[SemanticSupportAtom],
    list[SemanticApplicationObligation],
]:
    propositions = _propositions(resolved)
    transformations: list[SemanticTransformation] = []
    atoms: list[SemanticSupportAtom] = []
    obligations: list[SemanticApplicationObligation] = []

    for step in resolved.proof.steps:
        if step.rule != ProofRuleKind.APPLY_RESULT:
            continue
        target = propositions.get(step.conclusion)
        target_expression = _expression(target)
        if target is None:
            continue

        results = [
            propositions[address]
            for address in step.premises
            if address in propositions
            and propositions[address].role == PropositionRole.IMPORTED_RESULT
        ]
        for result in results:
            transformation_address = f"M{transform_start + len(transformations)}"
            atom = _atom(
                resolved,
                step,
                result,
                address=f"K{atom_start + len(atoms)}",
                kind=SemanticSupportKind.RESULT,
                graph=graph,
            )
            atoms.append(atom)

            matched = False
            kind = SemanticTransformationKind.RESULT_APPLICATION
            bindings_out: tuple[SemanticParameterBinding, ...] = ()
            operation_obligations: tuple[SemanticApplicationObligation, ...] = ()
            input_refs: tuple[ExpressionRef, ...] = ()
            source_expression = _expression(result)

            if source_expression is not None and target_expression is not None:
                parameters, body, body_path = _unwrap_universals(source_expression)
                parameter_names = {name for name, _path in parameters}
                direct_matches = _match_template(
                    body,
                    target_expression,
                    parameter_names=parameter_names,
                )
                antecedent: MathExpr | None = None
                antecedent_path: tuple[str, ...] | None = None
                matches = direct_matches

                if direct_matches is not None:
                    if parameters:
                        kind = SemanticTransformationKind.RESULT_SPECIALIZATION
                elif (
                    isinstance(body, LogicalExpr)
                    and body.operator == LogicalOperator.IMPLIES
                    and len(body.arguments) == 2
                ):
                    antecedent, conclusion_template = body.arguments
                    antecedent_path = (*body_path, "arguments", "0")
                    matches = _match_template(
                        conclusion_template,
                        target_expression,
                        parameter_names=parameter_names,
                    )

                if matches is not None:
                    matched = True
                    bindings_out = tuple(
                        SemanticParameterBinding(
                            parameter_ref=ExpressionRef(
                                owner_address=result.address,
                                path=parameter_path,
                            ),
                            argument_ref=(
                                ExpressionRef(
                                    owner_address=target.address,
                                    path=matches[name].argument_path,
                                )
                                if name in matches
                                else None
                            ),
                            status=(
                                InferenceStatus.CONFIDENT
                                if name in matches
                                else InferenceStatus.UNRESOLVED
                            ),
                        )
                        for name, parameter_path in parameters
                    )

                    if antecedent is not None:
                        expected = _instantiate(antecedent, matches)
                        local_context = _context(resolved, target.address)
                        satisfied_by = (
                            _context_matches(
                                resolved,
                                expected,
                                local_context,
                                exclude=(result.address,),
                            )
                            if expected is not None
                            else ()
                        )
                        obligation = SemanticApplicationObligation(
                            address=f"A{obligation_start + len(obligations)}",
                            transformation_address=transformation_address,
                            template_ref=(
                                ExpressionRef(
                                    owner_address=result.address,
                                    path=antecedent_path,
                                )
                                if antecedent_path is not None
                                else None
                            ),
                            expected=expected,
                            local_context=local_context,
                            satisfied_by=satisfied_by,
                            status=(
                                ObligationStatus.DISCHARGED
                                if expected is not None and satisfied_by
                                else ObligationStatus.UNRESOLVED
                            ),
                            source_addresses=_dedupe(
                                [
                                    result.source_address,
                                    target.source_address,
                                    *[
                                        propositions[address].source_address
                                        for address in satisfied_by
                                    ],
                                ]
                            ),
                        )
                        obligations.append(obligation)
                        operation_obligations = (obligation,)
                        input_refs = tuple(
                            ExpressionRef(owner_address=address)
                            for address in satisfied_by
                        )

            status = _operation_status(
                reference_status=step.status,
                matched=matched,
                bindings=bindings_out,
                obligations=operation_obligations,
            )
            source_addresses = _dedupe(
                [
                    *atom.source_addresses,
                    target.source_address,
                    *[
                        propositions[ref.owner_address].source_address
                        for ref in input_refs
                    ],
                ]
            )
            transformations.append(
                SemanticTransformation(
                    address=transformation_address,
                    kind=kind,
                    step_addresses=(step.address,),
                    support_atom_addresses=(atom.address,),
                    input_refs=input_refs,
                    target_ref=ExpressionRef(owner_address=target.address),
                    parameter_bindings=bindings_out,
                    obligation_addresses=tuple(
                        item.address for item in operation_obligations
                    ),
                    status=status,
                    source_addresses=source_addresses,
                    opaque_source_addresses=(
                        source_addresses
                        if status != InferenceStatus.CONFIDENT
                        else ()
                    ),
                )
            )

    return transformations, atoms, obligations


def _rewrites(
    resolved: SymbolResolutionIR,
    *,
    transform_start: int,
    atom_start: int,
) -> tuple[list[SemanticTransformation], list[SemanticSupportAtom]]:
    transformations: list[SemanticTransformation] = []
    atoms: list[SemanticSupportAtom] = []
    steps = _steps(resolved)
    propositions = _propositions(resolved)

    for operation in resolved.substitutions:
        step = steps.get(operation.step_address)
        if step is None:
            continue
        equality = (
            propositions.get(operation.equality_ref.owner_address)
            if operation.equality_ref is not None
            else None
        )
        atom = _atom(
            resolved,
            step,
            equality,
            address=f"K{atom_start + len(atoms)}",
            kind=SemanticSupportKind.EQUALITY,
        )
        atoms.append(atom)
        source_addresses = _dedupe(
            [
                *atom.source_addresses,
                *[
                    item.source_address
                    for item in operation.provenance
                    if item.source_address is not None
                ],
            ]
        )
        transformations.append(
            SemanticTransformation(
                address=f"M{transform_start + len(transformations)}",
                kind=SemanticTransformationKind.EQUALITY_REWRITE,
                step_addresses=(step.address,),
                support_atom_addresses=(atom.address,),
                input_refs=(
                    (operation.input_ref,)
                    if operation.input_ref is not None
                    else ()
                ),
                target_ref=operation.output_ref,
                rewrite_from_ref=operation.from_ref,
                rewrite_to_ref=operation.to_ref,
                replacement_sites=operation.replacement_sites,
                lower_operation_address=operation.address,
                status=operation.status,
                source_addresses=source_addresses,
                opaque_source_addresses=(
                    source_addresses
                    if operation.status != InferenceStatus.CONFIDENT
                    else ()
                ),
            )
        )

    return transformations, atoms


def _definitions(
    resolved: SymbolResolutionIR,
    *,
    transform_start: int,
    atom_start: int,
) -> tuple[list[SemanticTransformation], list[SemanticSupportAtom]]:
    propositions = _propositions(resolved)
    transformations: list[SemanticTransformation] = []
    atoms: list[SemanticSupportAtom] = []

    for step in resolved.proof.steps:
        if step.rule != ProofRuleKind.DEFINITION_USE:
            continue
        target = propositions.get(step.conclusion)
        target_expression = _expression(target)
        if target is None:
            continue

        definitions = [
            propositions[address]
            for address in step.premises
            if address in propositions
            and propositions[address].role == PropositionRole.DEFINITION
        ]
        for definition in definitions:
            atom = _atom(
                resolved,
                step,
                definition,
                address=f"K{atom_start + len(atoms)}",
                kind=SemanticSupportKind.DEFINITION,
            )
            atoms.append(atom)
            transformation_address = f"M{transform_start + len(transformations)}"
            definition_expression = _expression(definition)
            matches: list[tuple[ProofProposition, bool, _ReplacementMatch]] = []

            if (
                target_expression is not None
                and isinstance(definition_expression, RelationExpr)
                and definition_expression.operator == RelationOperator.EQUAL
            ):
                for address in _context(resolved, target.address):
                    if address == definition.address:
                        continue
                    candidate = propositions.get(address)
                    candidate_expression = _expression(candidate)
                    if candidate is None or candidate_expression is None:
                        continue
                    for reverse in (False, True):
                        old = (
                            definition_expression.right
                            if reverse
                            else definition_expression.left
                        )
                        new = (
                            definition_expression.left
                            if reverse
                            else definition_expression.right
                        )
                        replacement = _replacement(
                            candidate_expression,
                            target_expression,
                            old=old,
                            new=new,
                        )
                        if replacement is not None:
                            matches.append((candidate, reverse, replacement))

            if len(matches) == 1:
                candidate, reverse, replacement = matches[0]
                status = (
                    step.status
                    if step.status == InferenceStatus.CONFIDENT
                    else InferenceStatus.UNRESOLVED
                )
                source_addresses = _dedupe(
                    [
                        *atom.source_addresses,
                        candidate.source_address,
                        target.source_address,
                    ]
                )
                transformations.append(
                    SemanticTransformation(
                        address=transformation_address,
                        kind=SemanticTransformationKind.DEFINITION_UNFOLD,
                        step_addresses=(step.address,),
                        support_atom_addresses=(atom.address,),
                        input_refs=(ExpressionRef(owner_address=candidate.address),),
                        target_ref=ExpressionRef(owner_address=target.address),
                        rewrite_from_ref=ExpressionRef(
                            owner_address=definition.address,
                            path=("right",) if reverse else ("left",),
                        ),
                        rewrite_to_ref=ExpressionRef(
                            owner_address=definition.address,
                            path=("left",) if reverse else ("right",),
                        ),
                        replacement_sites=tuple(
                            ExpressionRef(owner_address=target.address, path=path)
                            for path in replacement.sites
                        ),
                        status=status,
                        source_addresses=source_addresses,
                        opaque_source_addresses=(
                            source_addresses
                            if status != InferenceStatus.CONFIDENT
                            else ()
                        ),
                    )
                )
                continue

            status = (
                InferenceStatus.AMBIGUOUS
                if len(matches) > 1
                else InferenceStatus.UNRESOLVED
            )
            source_addresses = _dedupe(
                [*atom.source_addresses, target.source_address]
            )
            transformations.append(
                SemanticTransformation(
                    address=transformation_address,
                    kind=SemanticTransformationKind.DEFINITION_USE,
                    step_addresses=(step.address,),
                    support_atom_addresses=(atom.address,),
                    target_ref=ExpressionRef(owner_address=target.address),
                    status=status,
                    source_addresses=source_addresses,
                    opaque_source_addresses=source_addresses,
                )
            )

    return transformations, atoms


def _properties(
    resolved: SymbolResolutionIR,
    *,
    transform_start: int,
    atom_start: int,
) -> tuple[list[SemanticTransformation], list[SemanticSupportAtom]]:
    propositions = _propositions(resolved)
    transformations: list[SemanticTransformation] = []
    atoms: list[SemanticSupportAtom] = []

    for step in resolved.proof.steps:
        if step.rule != ProofRuleKind.NAMED_PROPERTY_APPLICATION:
            continue
        target = propositions.get(step.conclusion)
        if target is None:
            continue
        premise = next(
            (
                propositions[address]
                for address in step.premises
                if address in propositions
            ),
            None,
        )
        source_text = ""
        for address in step.source_addresses:
            try:
                text = resolved.proof.source(address).text.strip()
            except KeyError:
                continue
            if text:
                source_text = text
                break

        atom = _atom(
            resolved,
            step,
            premise,
            address=f"K{atom_start + len(atoms)}",
            kind=SemanticSupportKind.NAMED_PROPERTY,
            name=source_text or None,
        )
        atoms.append(atom)
        source_addresses = _dedupe(
            [*atom.source_addresses, target.source_address]
        )
        transformations.append(
            SemanticTransformation(
                address=f"M{transform_start + len(transformations)}",
                kind=SemanticTransformationKind.NAMED_PROPERTY_APPLICATION,
                step_addresses=(step.address,),
                support_atom_addresses=(atom.address,),
                input_refs=(
                    (ExpressionRef(owner_address=premise.address),)
                    if premise is not None and premise.expression is not None
                    else ()
                ),
                target_ref=ExpressionRef(owner_address=target.address),
                status=InferenceStatus.UNRESOLVED,
                source_addresses=source_addresses,
                opaque_source_addresses=source_addresses,
            )
        )

    return transformations, atoms


def elaborate_semantic_transformations(
    higher: HigherProofIR,
    *,
    dependency_graph: DependencyGraph | None = None,
) -> SemanticTransformationIR:
    """Recover common semantic transformations while preserving uncertainty."""

    resolved = higher.resolved
    transformations: list[SemanticTransformation] = []
    atoms: list[SemanticSupportAtom] = []
    obligations: list[SemanticApplicationObligation] = []

    result_items, result_atoms, result_obligations = _result_applications(
        resolved,
        transform_start=1,
        atom_start=1,
        obligation_start=1,
        graph=dependency_graph,
    )
    transformations.extend(result_items)
    atoms.extend(result_atoms)
    obligations.extend(result_obligations)

    rewrite_items, rewrite_atoms = _rewrites(
        resolved,
        transform_start=len(transformations) + 1,
        atom_start=len(atoms) + 1,
    )
    transformations.extend(rewrite_items)
    atoms.extend(rewrite_atoms)

    definition_items, definition_atoms = _definitions(
        resolved,
        transform_start=len(transformations) + 1,
        atom_start=len(atoms) + 1,
    )
    transformations.extend(definition_items)
    atoms.extend(definition_atoms)

    property_items, property_atoms = _properties(
        resolved,
        transform_start=len(transformations) + 1,
        atom_start=len(atoms) + 1,
    )
    transformations.extend(property_items)
    atoms.extend(property_atoms)

    return SemanticTransformationIR(
        result_identifier=higher.result_identifier,
        higher=higher.model_copy(deep=True),
        support_atoms=atoms,
        transformations=transformations,
        obligations=obligations,
    )


def build_semantic_transformation_ir(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
    *,
    symbol_table: SymbolTable | None = None,
    dependency_graph: DependencyGraph | None = None,
) -> SemanticTransformationIR:
    """Build issue-64 transformations from the established issue-63 path."""

    higher = build_higher_proof_ir(
        unit,
        request,
        symbol_table=symbol_table,
    )
    return elaborate_semantic_transformations(
        higher,
        dependency_graph=dependency_graph,
    )
