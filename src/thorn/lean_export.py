from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from thorn.evidence import InferenceStatus
from thorn.formula_ir import (
    ApplyExpr,
    BuiltinDomain,
    BuiltinDomainExpr,
    IdentifierExpr,
    LiteralExpr,
    LogicalExpr,
    LogicalOperator,
    MathExpr,
    QuantifiedExpr,
    Quantifier,
)
from thorn.proof_obligations import ObligationStatus, ProofRuleKind, PropositionRole
from thorn.semantic_transformations import (
    SemanticApplicationObligation,
    SemanticSupportKind,
    SemanticTransformation,
    SemanticTransformationIR,
    SemanticTransformationKind,
)


class LeanExportStatus(StrEnum):
    """How much of a Lean handoff is mechanically justified by canonical Proof IR."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class LeanFormalizationObligation(BaseModel):
    """One explicit Lean hole tied back to canonical Proof IR/source addresses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    reason: str
    expected: MathExpr | None = None
    lean_type: str | None = None
    semantic_obligation_address: str | None = None
    source_addresses: tuple[str, ...] = ()


class LeanExport(BaseModel):
    """Deterministic Lean projection over the mechanically recovered Proof IR subset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_identifier: str
    status: LeanExportStatus
    source: str
    obligations: tuple[LeanFormalizationObligation, ...] = ()

    @property
    def is_mechanically_checkable(self) -> bool:
        """True only when no formalisation hole or unsupported structure remains."""

        return self.status == LeanExportStatus.COMPLETE and not self.obligations


class _LeanUnsupported(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        expected: MathExpr | None = None,
        source_addresses: tuple[str, ...] = (),
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.expected = expected
        self.source_addresses = source_addresses


_LEAN_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_LEAN_RESERVED = {
    "abbrev",
    "axiom",
    "by",
    "class",
    "def",
    "deriving",
    "do",
    "else",
    "end",
    "example",
    "export",
    "false",
    "forall",
    "fun",
    "if",
    "import",
    "in",
    "inductive",
    "instance",
    "let",
    "match",
    "namespace",
    "opaque",
    "open",
    "partial",
    "section",
    "structure",
    "then",
    "theorem",
    "true",
    "where",
    "with",
}


def _lean_identifier(name: str) -> str:
    if _LEAN_IDENTIFIER_RE.fullmatch(name) is None or name.lower() in _LEAN_RESERVED:
        raise _LeanUnsupported(f"unsupported Lean identifier {name!r}")
    return name


def _local_name(address: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", address).lower()
    if not value or not value[0].isalpha():
        value = f"p_{value}"
    return value


def _theorem_name(result_identifier: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]", "_", result_identifier).strip("_").lower()
    if not value:
        value = "result"
    if not value[0].isalpha():
        value = f"result_{value}"
    return f"thorn_{value}"


def _render_nat_term(expression: MathExpr, *, bound: frozenset[str] = frozenset()) -> str:
    """Render a term only after its surrounding proposition established a Nat type."""

    if isinstance(expression, LiteralExpr) and expression.value.isdigit():
        return expression.value
    if isinstance(expression, IdentifierExpr) and expression.name in bound:
        return _lean_identifier(expression.name)
    raise _LeanUnsupported(
        "the initial Lean subset supports only natural-number literals and bound Nat variables",
        expected=expression,
    )


def _collect_nat_predicates(
    expression: MathExpr,
    *,
    bound_nat: frozenset[str] = frozenset(),
) -> set[str]:
    """Find predicate signatures established by canonical quantification over built-in ℕ."""

    result: set[str] = set()
    if isinstance(expression, ApplyExpr):
        if (
            isinstance(expression.function, IdentifierExpr)
            and len(expression.arguments) == 1
            and isinstance(expression.arguments[0], IdentifierExpr)
            and expression.arguments[0].name in bound_nat
        ):
            result.add(expression.function.name)
        return result
    if isinstance(expression, LogicalExpr):
        for argument in expression.arguments:
            result.update(_collect_nat_predicates(argument, bound_nat=bound_nat))
        return result
    if isinstance(expression, QuantifiedExpr):
        next_bound = bound_nat
        if (
            expression.quantifier == Quantifier.FOR_ALL
            and isinstance(expression.binder.domain, BuiltinDomainExpr)
            and expression.binder.domain.domain == BuiltinDomain.NATURALS
        ):
            next_bound = bound_nat | {expression.binder.name.name}
        result.update(_collect_nat_predicates(expression.body, bound_nat=next_bound))
    return result


def _render_proposition(
    expression: MathExpr,
    *,
    bound: frozenset[str] = frozenset(),
    nat_predicates: frozenset[str] = frozenset(),
    predicates: set[str] | None = None,
    precedence: int = 0,
) -> str:
    """Render the first bounded proposition subset without consulting source prose.

    A unary application becomes `Nat → Prop` only when a canonical quantified
    proposition has already established that predicate on the built-in naturals.
    Numeral spelling alone is never used to invent a Nat type.
    """

    if isinstance(expression, ApplyExpr):
        if not isinstance(expression.function, IdentifierExpr) or len(expression.arguments) != 1:
            raise _LeanUnsupported(
                "only unary identifier-headed proposition predicates are supported",
                expected=expression,
            )
        name = _lean_identifier(expression.function.name)
        if name not in nat_predicates:
            raise _LeanUnsupported(
                "predicate Nat domain is not mechanically established by canonical Proof IR",
                expected=expression,
            )
        argument = _render_nat_term(expression.arguments[0], bound=bound)
        if predicates is not None:
            predicates.add(name)
        return f"{name} {argument}"

    if isinstance(expression, LogicalExpr):
        if expression.operator != LogicalOperator.IMPLIES or len(expression.arguments) != 2:
            raise _LeanUnsupported(
                "only implication is supported in the initial Lean logical subset",
                expected=expression,
            )
        left = _render_proposition(
            expression.arguments[0],
            bound=bound,
            nat_predicates=nat_predicates,
            predicates=predicates,
            precedence=2,
        )
        right = _render_proposition(
            expression.arguments[1],
            bound=bound,
            nat_predicates=nat_predicates,
            predicates=predicates,
            precedence=1,
        )
        rendered = f"{left} → {right}"
        return f"({rendered})" if precedence > 1 else rendered

    if isinstance(expression, QuantifiedExpr):
        if expression.quantifier != Quantifier.FOR_ALL:
            raise _LeanUnsupported(
                "only universal quantification is supported in the initial Lean subset",
                expected=expression,
            )
        if (
            not isinstance(expression.binder.domain, BuiltinDomainExpr)
            or expression.binder.domain.domain != BuiltinDomain.NATURALS
        ):
            raise _LeanUnsupported(
                "the initial Lean subset requires a mechanically recovered built-in natural-number domain",
                expected=expression,
            )
        binder = _lean_identifier(expression.binder.name.name)
        body = _render_proposition(
            expression.body,
            bound=bound | {expression.binder.name.name},
            nat_predicates=nat_predicates,
            predicates=predicates,
        )
        rendered = f"∀ {binder} : Nat, {body}"
        return f"({rendered})" if precedence > 0 else rendered

    raise _LeanUnsupported(
        "expression is outside the initial proposition-valued predicate/forall/implication subset",
        expected=expression,
    )


def _dedupe(items: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _result_support(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
) -> str:
    result_atoms = [
        ir.support_atom(address)
        for address in transformation.support_atom_addresses
        if ir.support_atom(address).kind == SemanticSupportKind.RESULT
    ]
    if len(result_atoms) != 1:
        raise _LeanUnsupported(
            "a Lean theorem application requires exactly one recovered result support atom",
            source_addresses=transformation.source_addresses,
        )
    atom = result_atoms[0]
    if atom.status != InferenceStatus.CONFIDENT or atom.proposition_address is None:
        raise _LeanUnsupported(
            "the referenced result is not confidently source-linked",
            source_addresses=atom.source_addresses,
        )
    return atom.proposition_address


def _new_obligation(
    obligations: list[LeanFormalizationObligation],
    *,
    reason: str,
    expected: MathExpr | None,
    lean_type: str | None,
    semantic_obligation_address: str | None = None,
    source_addresses: tuple[str, ...] = (),
) -> LeanFormalizationObligation:
    item = LeanFormalizationObligation(
        address=f"LH{len(obligations) + 1}",
        reason=reason,
        expected=expected,
        lean_type=lean_type,
        semantic_obligation_address=semantic_obligation_address,
        source_addresses=_dedupe(source_addresses),
    )
    obligations.append(item)
    return item


def _obligation_argument(
    obligation: SemanticApplicationObligation,
    *,
    local_names: dict[str, str],
    nat_predicates: frozenset[str],
    obligations: list[LeanFormalizationObligation],
) -> tuple[str, list[str]]:
    if obligation.status == ObligationStatus.DISCHARGED:
        for address in obligation.satisfied_by:
            if address in local_names:
                return local_names[address], []
        raise _LeanUnsupported(
            "a discharged application premise is not available in the emitted local context",
            expected=obligation.expected,
            source_addresses=obligation.source_addresses,
        )

    if obligation.expected is None:
        raise _LeanUnsupported(
            "the missing result precondition has no canonical expected proposition",
            source_addresses=obligation.source_addresses,
        )
    lean_type = _render_proposition(
        obligation.expected,
        nat_predicates=nat_predicates,
    )
    item = _new_obligation(
        obligations,
        reason="missing_result_precondition",
        expected=obligation.expected,
        lean_type=lean_type,
        semantic_obligation_address=obligation.address,
        source_addresses=obligation.source_addresses,
    )
    hole_name = f"thorn_obligation_{item.address.lower()}"
    sources = ",".join(item.source_addresses) or "-"
    lines = [
        (
            f"  -- THORN_FORMALIZATION_OBLIGATION {item.address} "
            f"semantic={obligation.address} sources={sources}"
        ),
        f"  have {hole_name} : {lean_type} := by",
        "    sorry",
    ]
    return hole_name, lines


def _result_application_term(
    ir: SemanticTransformationIR,
    transformation: SemanticTransformation,
    *,
    local_names: dict[str, str],
    nat_predicates: frozenset[str],
    obligations: list[LeanFormalizationObligation],
) -> tuple[str, list[str]]:
    if transformation.kind not in {
        SemanticTransformationKind.RESULT_APPLICATION,
        SemanticTransformationKind.RESULT_SPECIALIZATION,
    }:
        raise _LeanUnsupported(
            (
                f"semantic transformation {transformation.kind.value!r} "
                "is outside the initial Lean subset"
            ),
            source_addresses=transformation.source_addresses,
        )
    if transformation.status == InferenceStatus.AMBIGUOUS:
        raise _LeanUnsupported(
            "ambiguous semantic transformations are never selected for Lean proof terms",
            source_addresses=transformation.source_addresses,
        )
    if any(
        binding.status != InferenceStatus.CONFIDENT
        for binding in transformation.parameter_bindings
    ):
        raise _LeanUnsupported(
            "unresolved result instantiation cannot become a Lean proof term",
            source_addresses=transformation.source_addresses,
        )

    result_address = _result_support(ir, transformation)
    if result_address not in local_names:
        raise _LeanUnsupported(
            "the recovered result support is not present in the emitted Lean context",
            source_addresses=transformation.source_addresses,
        )

    pieces = [local_names[result_address]]
    for binding in transformation.parameter_bindings:
        if binding.argument_ref is None:
            raise _LeanUnsupported(
                "result parameter has no mechanically recovered argument",
                source_addresses=transformation.source_addresses,
            )
        binding_argument = ir.higher.resolved.expression(binding.argument_ref)
        pieces.append(_render_nat_term(binding_argument))

    hole_lines: list[str] = []
    unresolved_application_obligations = 0
    for address in transformation.obligation_addresses:
        semantic_obligation = ir.obligation(address)
        if semantic_obligation.status == ObligationStatus.UNRESOLVED:
            unresolved_application_obligations += 1
        obligation_argument, lines = _obligation_argument(
            semantic_obligation,
            local_names=local_names,
            nat_predicates=nat_predicates,
            obligations=obligations,
        )
        pieces.append(obligation_argument)
        hole_lines.extend(lines)

    if (
        transformation.status == InferenceStatus.UNRESOLVED
        and unresolved_application_obligations == 0
    ):
        raise _LeanUnsupported(
            (
                "an unresolved result application without an explicit missing precondition "
                "is not exportable"
            ),
            source_addresses=transformation.opaque_source_addresses
            or transformation.source_addresses,
        )
    if transformation.status == InferenceStatus.CONFIDENT and unresolved_application_obligations:
        raise _LeanUnsupported(
            "confidence invariant violation: confident application carries an unresolved premise",
            source_addresses=transformation.source_addresses,
        )

    return " ".join(pieces), hole_lines


def _unsupported_export(
    ir: SemanticTransformationIR,
    *,
    reason: str,
    expected: MathExpr | None = None,
    source_addresses: tuple[str, ...] = (),
) -> LeanExport:
    obligation = LeanFormalizationObligation(
        address="LH1",
        reason=reason,
        expected=expected,
        source_addresses=_dedupe(source_addresses),
    )
    sources = ",".join(obligation.source_addresses) or "-"
    source = (
        "-- Generated by Thorn from canonical Proof IR.\n"
        "-- Thorn Lean export status: unsupported\n"
        f"-- THORN_FORMALIZATION_OBLIGATION LH1 reason={reason} sources={sources}\n"
    )
    return LeanExport(
        result_identifier=ir.result_identifier,
        status=LeanExportStatus.UNSUPPORTED,
        source=source,
        obligations=(obligation,),
    )


def project_lean(ir: SemanticTransformationIR) -> LeanExport:
    """Project canonical Proof IR semantics to a deliberately tiny Lean 4 subset.

    This function never reads source text. Exact source addresses are carried only as
    provenance for holes. A result application may be rendered while partial only when
    its canonical semantic transformation already matched and its uncertainty consists
    of explicit application-precondition obligations; those obligations become `sorry`
    holes instead of being invented or repaired.
    """

    proof = ir.higher.resolved.proof
    goals = [item for item in proof.propositions if item.role == PropositionRole.GOAL]
    if len(goals) != 1 or goals[0].expression is None:
        return _unsupported_export(
            ir,
            reason="Lean export requires exactly one canonical proposition goal",
            source_addresses=tuple(item.source_address for item in goals),
        )
    goal = goals[0]
    assert goal.expression is not None

    used_results = {
        atom.proposition_address
        for atom in ir.support_atoms
        if atom.kind == SemanticSupportKind.RESULT and atom.proposition_address is not None
    }
    context = [
        item
        for item in proof.propositions
        if (
            item.role == PropositionRole.ASSUMPTION
            or (item.role == PropositionRole.IMPORTED_RESULT and item.address in used_results)
        )
    ]
    derived = [
        item
        for item in proof.propositions
        if item.role in {PropositionRole.DERIVED, PropositionRole.UNRESOLVED}
    ]

    nat_predicate_names: set[str] = set()
    for proposition in [goal, *context, *derived]:
        if proposition.expression is not None:
            nat_predicate_names.update(_collect_nat_predicates(proposition.expression))
    nat_predicates = frozenset(nat_predicate_names)

    predicates: set[str] = set()
    try:
        goal_type = _render_proposition(
            goal.expression,
            nat_predicates=nat_predicates,
            predicates=predicates,
        )
        context_types: dict[str, str] = {}
        for proposition in context:
            if proposition.expression is None:
                raise _LeanUnsupported(
                    "used Lean context proposition has no canonical expression",
                    source_addresses=(proposition.source_address,),
                )
            context_types[proposition.address] = _render_proposition(
                proposition.expression,
                nat_predicates=nat_predicates,
                predicates=predicates,
            )
        derived_types: dict[str, str] = {}
        for proposition in derived:
            if proposition.expression is None:
                raise _LeanUnsupported(
                    "proof proposition has no canonical expression",
                    source_addresses=(proposition.source_address,),
                )
            derived_types[proposition.address] = _render_proposition(
                proposition.expression,
                nat_predicates=nat_predicates,
                predicates=predicates,
            )
    except _LeanUnsupported as exc:
        return _unsupported_export(
            ir,
            reason=exc.reason,
            expected=exc.expected,
            source_addresses=exc.source_addresses or (goal.source_address,),
        )

    local_names = {item.address: _local_name(item.address) for item in context}
    transformations_by_target: dict[str, list[SemanticTransformation]] = {}
    for transformation in ir.transformations:
        transformations_by_target.setdefault(
            transformation.target_ref.owner_address,
            [],
        ).append(transformation)

    obligations: list[LeanFormalizationObligation] = []
    body: list[str] = []
    try:
        for proposition in derived:
            local_name = _local_name(proposition.address)
            candidates = transformations_by_target.get(proposition.address, [])
            if len(candidates) == 1:
                term, hole_lines = _result_application_term(
                    ir,
                    candidates[0],
                    local_names=local_names,
                    nat_predicates=nat_predicates,
                    obligations=obligations,
                )
                body.extend(hole_lines)
                body.append(f"  have {local_name} : {derived_types[proposition.address]} := {term}")
            else:
                item = _new_obligation(
                    obligations,
                    reason=(
                        "missing_mechanical_derivation"
                        if not candidates
                        else "multiple_mechanical_derivations"
                    ),
                    expected=proposition.expression,
                    lean_type=derived_types[proposition.address],
                    source_addresses=(proposition.source_address,),
                )
                sources = ",".join(item.source_addresses) or "-"
                body.extend(
                    [
                        (
                            f"  -- THORN_FORMALIZATION_OBLIGATION {item.address} "
                            f"semantic=- sources={sources}"
                        ),
                        f"  have {local_name} : {derived_types[proposition.address]} := by",
                        "    sorry",
                    ]
                )
            local_names[proposition.address] = local_name

        terminal_steps = [
            step
            for step in proof.steps
            if step.conclusion == goal.address
            and step.rule == ProofRuleKind.EXACT
            and step.status == InferenceStatus.CONFIDENT
        ]
        if len(terminal_steps) != 1 or len(terminal_steps[0].premises) != 1:
            raise _LeanUnsupported(
                "the terminal theorem conclusion is not a unique recovered exact step",
                expected=goal.expression,
                source_addresses=(goal.source_address,),
            )
        final_address = terminal_steps[0].premises[0]
        if final_address not in local_names:
            raise _LeanUnsupported(
                "the terminal exact premise is not available in the emitted Lean context",
                expected=goal.expression,
                source_addresses=terminal_steps[0].source_addresses,
            )
        body.append(f"  exact {local_names[final_address]}")
    except _LeanUnsupported as exc:
        return _unsupported_export(
            ir,
            reason=exc.reason,
            expected=exc.expected,
            source_addresses=exc.source_addresses or (goal.source_address,),
        )

    predicate_params = ""
    if predicates:
        predicate_params = f" ({' '.join(sorted(predicates))} : Nat → Prop)"
    context_params = "".join(
        f" ({local_names[item.address]} : {context_types[item.address]})" for item in context
    )
    theorem = (
        f"theorem {_theorem_name(ir.result_identifier)}{predicate_params}{context_params} "
        f": {goal_type} := by\n"
        + "\n".join(body)
        + "\n"
    )
    status = LeanExportStatus.PARTIAL if obligations else LeanExportStatus.COMPLETE
    source = (
        "-- Generated by Thorn from canonical Proof IR.\n"
        f"-- Thorn Lean export status: {status.value}\n"
        + theorem
    )
    return LeanExport(
        result_identifier=ir.result_identifier,
        status=status,
        source=source,
        obligations=tuple(obligations),
    )