from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from thorn.canonical_proof_ir import CanonicalProofSource
from thorn.evidence import InferenceStatus
from thorn.formula_ir import (
    ApplyExpr,
    IdentifierExpr,
    LiteralExpr,
    LogicalExpr,
    LogicalOperator,
    MathExpr,
    NotExpr,
    OperatorExpr,
    QuantifiedExpr,
    Quantifier,
    RelationExpr,
    SetExpr,
    TupleExpr,
)
from thorn.models import TheoremUnit
from thorn.proof_obligations import (
    ProofObligationIR,
    ProofProposition,
    ProofRuleKind,
    PropositionRole,
)
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.symbol_resolution_ir import (
    ExpressionRef,
    SymbolResolutionIR,
    alpha_equivalent,
    build_symbol_resolution_ir,
)
from thorn.symbols import SymbolTable


class ProofStructureKind(StrEnum):
    """Higher-level proof-control structures exposed to downstream consumers."""

    CASE_SPLIT = "case_split"
    CONTRADICTION = "contradiction"
    CONTRAPOSITION = "contraposition"
    INDUCTION = "induction"
    WLOG = "wlog"
    SUBPROOF = "subproof"
    WITNESS_BRANCH = "witness_branch"


class ProofBranchKind(StrEnum):
    CASE = "case"
    CONTRADICTION_BODY = "contradiction_body"
    BASE_CASE = "base_case"
    INDUCTIVE_STEP = "inductive_step"
    LOCAL_SUBPROOF = "local_subproof"
    WITNESS = "witness"


class ProofBranch(BaseModel):
    """One source-addressable control-flow branch.

    ``status`` describes how well Thorn recovered the branch *shape*. It does not
    assert that the mathematical reasoning inside the branch is valid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    kind: ProofBranchKind
    parent_structure_address: str
    label: str | None = None
    proposition_addresses: tuple[str, ...] = ()
    local_assumptions: tuple[str, ...] = ()
    assumption_refs: tuple[ExpressionRef, ...] = ()
    conclusion_address: str | None = None
    conclusion_ref: ExpressionRef | None = None
    discharged_assumptions: tuple[str, ...] = ()
    discharged_assumption_refs: tuple[ExpressionRef, ...] = ()
    witness_ref: ExpressionRef | None = None
    evidence_ref: ExpressionRef | None = None
    status: InferenceStatus = InferenceStatus.UNRESOLVED
    source_addresses: tuple[str, ...] = ()


class ProofControlStructure(BaseModel):
    """A higher-level proof strategy with assertion and support kept separate.

    ``assertion_status`` answers whether the manuscript explicitly presents the
    strategy. ``support_status`` answers whether Thorn recovered enough exact
    structure to support the control-flow shape. Neither field is a proof-validity
    judgement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    kind: ProofStructureKind
    assertion_status: InferenceStatus = InferenceStatus.UNRESOLVED
    support_status: InferenceStatus = InferenceStatus.UNRESOLVED
    branch_addresses: tuple[str, ...] = ()
    premise_addresses: tuple[str, ...] = ()
    conclusion_address: str | None = None
    local_assumptions: tuple[str, ...] = ()
    discharged_assumptions: tuple[str, ...] = ()
    subject_ref: ExpressionRef | None = None
    transformed_goal_ref: ExpressionRef | None = None
    witness_ref: ExpressionRef | None = None
    operation_addresses: tuple[str, ...] = ()
    parent_structure_address: str | None = None
    source_addresses: tuple[str, ...] = ()
    opaque_source_addresses: tuple[str, ...] = ()


class HigherProofIR(BaseModel):
    """Issue-63 control-flow elaboration over the issue-62 resolution layer."""

    result_identifier: str
    resolved: SymbolResolutionIR
    structures: list[ProofControlStructure] = Field(default_factory=list)
    branches: list[ProofBranch] = Field(default_factory=list)

    def structure(self, address: str) -> ProofControlStructure:
        for item in self.structures:
            if item.address == address:
                return item
        raise KeyError(f"unknown proof structure address {address!r}")

    def branch(self, address: str) -> ProofBranch:
        for item in self.branches:
            if item.address == address:
                return item
        raise KeyError(f"unknown proof branch address {address!r}")

    def source(self, address: str) -> CanonicalProofSource:
        return self.resolved.proof.source(address)


_CASE_ASSERT_RE = re.compile(
    r"\b(?:split(?:ting)?\s+into\s+cases|proof\s+by\s+cases|consider\s+the\s+cases)\b",
    re.IGNORECASE,
)
_CASE_LABEL_RE = re.compile(r"^\s*case\b", re.IGNORECASE)
_CONTRADICTION_RE = re.compile(
    r"\b(?:proof\s+by\s+contradiction|by\s+contradiction|assume\s+the\s+contrary)\b",
    re.IGNORECASE,
)
_CONTRAPOSITION_RE = re.compile(
    r"\b(?:contrapositive|contraposition)\b",
    re.IGNORECASE,
)
_INDUCTION_RE = re.compile(
    r"\b(?:proof\s+by\s+induction|by\s+induction|inductive\s+step|induction\s+hypothesis)\b",
    re.IGNORECASE,
)
_WLOG_RE = re.compile(
    r"\b(?:without\s+loss\s+of\s+generality|w\.?\s*l\.?\s*o\.?\s*g\.?|by\s+symmetry)\b",
    re.IGNORECASE,
)
_SUBPROOF_RE = re.compile(
    r"^\s*(?:assume|suppose)\b",
    re.IGNORECASE,
)
_FALSE_NAMES = {"false", "⊥", "contradiction"}


def _proof_source_text(proof: ProofObligationIR, address: str) -> str:
    try:
        return proof.source(address).text
    except KeyError:
        return ""


def _explicit_cues(
    proof: ProofObligationIR,
    pattern: re.Pattern[str],
) -> tuple[str, ...]:
    addresses: list[str] = []
    seen: set[str] = set()
    for source in proof.sources:
        if source.address in seen:
            continue
        if pattern.search(source.text):
            addresses.append(source.address)
            seen.add(source.address)
    return tuple(addresses)


def _proposition_map(proof: ProofObligationIR) -> dict[str, ProofProposition]:
    return {item.address: item for item in proof.propositions}


def _understood_expression(proposition: ProofProposition) -> MathExpr | None:
    if proposition.expression is None:
        return None
    if proposition.role == PropositionRole.UNRESOLVED:
        return None
    return proposition.expression


def _is_false_expression(expression: MathExpr | None) -> bool:
    return isinstance(expression, IdentifierExpr) and expression.name.casefold() in _FALSE_NAMES


def _not(expression: MathExpr) -> NotExpr:
    return NotExpr(operand=expression)


def _alpha_equal(left: MathExpr | None, right: MathExpr | None) -> bool:
    return left is not None and right is not None and alpha_equivalent(left, right)


def _replace_free_name(
    expression: MathExpr,
    *,
    name: str,
    replacement: MathExpr,
) -> MathExpr:
    """Replace occurrences of one binder name while respecting nested shadowing."""

    if isinstance(expression, IdentifierExpr):
        return replacement if expression.name == name else expression
    if isinstance(expression, LiteralExpr):
        return expression
    if isinstance(expression, ApplyExpr):
        return ApplyExpr(
            function=_replace_free_name(expression.function, name=name, replacement=replacement),
            arguments=tuple(
                _replace_free_name(item, name=name, replacement=replacement)
                for item in expression.arguments
            ),
        )
    if isinstance(expression, OperatorExpr):
        return OperatorExpr(
            operator=expression.operator,
            arguments=tuple(
                _replace_free_name(item, name=name, replacement=replacement)
                for item in expression.arguments
            ),
        )
    if isinstance(expression, RelationExpr):
        return RelationExpr(
            operator=expression.operator,
            left=_replace_free_name(expression.left, name=name, replacement=replacement),
            right=_replace_free_name(expression.right, name=name, replacement=replacement),
        )
    if isinstance(expression, LogicalExpr):
        return LogicalExpr(
            operator=expression.operator,
            arguments=tuple(
                _replace_free_name(item, name=name, replacement=replacement)
                for item in expression.arguments
            ),
        )
    if isinstance(expression, NotExpr):
        return NotExpr(
            operand=_replace_free_name(expression.operand, name=name, replacement=replacement)
        )
    if isinstance(expression, TupleExpr):
        return TupleExpr(
            items=tuple(
                _replace_free_name(item, name=name, replacement=replacement)
                for item in expression.items
            )
        )
    if isinstance(expression, SetExpr):
        return SetExpr(
            items=tuple(
                _replace_free_name(item, name=name, replacement=replacement)
                for item in expression.items
            )
        )
    if isinstance(expression, QuantifiedExpr):
        domain = (
            _replace_free_name(expression.binder.domain, name=name, replacement=replacement)
            if expression.binder.domain is not None
            else None
        )
        if expression.binder.name.name == name:
            return expression.model_copy(
                update={"binder": expression.binder.model_copy(update={"domain": domain})}
            )
        return expression.model_copy(
            update={
                "binder": expression.binder.model_copy(update={"domain": domain}),
                "body": _replace_free_name(expression.body, name=name, replacement=replacement),
            }
        )
    return expression


def _next_expression(binder_name: str) -> OperatorExpr:
    return OperatorExpr(
        operator="+",
        arguments=(IdentifierExpr(name=binder_name), LiteralExpr(value="1")),
    )


def _case_split_structure(
    resolved: SymbolResolutionIR,
    *,
    index: int,
) -> tuple[ProofControlStructure | None, list[ProofBranch]]:
    proof = resolved.proof
    propositions = proof.propositions
    cue_addresses = _explicit_cues(proof, _CASE_ASSERT_RE)
    label_addresses = tuple(
        item.address
        for item in propositions
        if _CASE_LABEL_RE.search(_proof_source_text(proof, item.source_address))
    )
    assertion_addresses = tuple(dict.fromkeys((*cue_addresses, *label_addresses)))
    assertion_status = (
        InferenceStatus.CONFIDENT if assertion_addresses else InferenceStatus.UNRESOLVED
    )

    for disjunction in propositions:
        expression = _understood_expression(disjunction)
        if not isinstance(expression, LogicalExpr) or expression.operator != LogicalOperator.OR:
            continue
        if len(expression.arguments) < 2:
            continue

        branch_candidates: list[tuple[ProofProposition, MathExpr, MathExpr]] = []
        for case_expression in expression.arguments:
            candidate: tuple[ProofProposition, MathExpr, MathExpr] | None = None
            for proposition in propositions:
                prop_expression = _understood_expression(proposition)
                if not isinstance(prop_expression, LogicalExpr):
                    continue
                if prop_expression.operator != LogicalOperator.IMPLIES:
                    continue
                if len(prop_expression.arguments) != 2:
                    continue
                antecedent, consequent = prop_expression.arguments
                if _alpha_equal(antecedent, case_expression):
                    candidate = (proposition, antecedent, consequent)
                    break
            if candidate is None:
                branch_candidates = []
                break
            branch_candidates.append(candidate)

        if len(branch_candidates) != len(expression.arguments):
            continue
        common_conclusion = branch_candidates[0][2]
        if not all(_alpha_equal(item[2], common_conclusion) for item in branch_candidates[1:]):
            continue

        conclusion_address = next(
            (
                proposition.address
                for proposition in propositions
                if _alpha_equal(_understood_expression(proposition), common_conclusion)
            ),
            None,
        )
        structure_address = f"S{index}:cases"
        branches: list[ProofBranch] = []
        for branch_index, (proposition, _antecedent, _consequent) in enumerate(
            branch_candidates,
            start=1,
        ):
            assumption_ref = ExpressionRef(
                owner_address=proposition.address,
                path=("arguments", "0"),
            )
            conclusion_ref = ExpressionRef(
                owner_address=proposition.address,
                path=("arguments", "1"),
            )
            branches.append(
                ProofBranch(
                    address=f"{structure_address}:B{branch_index}",
                    kind=ProofBranchKind.CASE,
                    parent_structure_address=structure_address,
                    label=f"case {branch_index}",
                    proposition_addresses=(proposition.address,),
                    assumption_refs=(assumption_ref,),
                    conclusion_address=proposition.address,
                    conclusion_ref=conclusion_ref,
                    discharged_assumption_refs=(assumption_ref,),
                    status=InferenceStatus.CONFIDENT,
                    source_addresses=(proposition.source_address,),
                )
            )
        source_addresses = tuple(
            dict.fromkeys(
                (
                    disjunction.source_address,
                    *(item[0].source_address for item in branch_candidates),
                    *assertion_addresses,
                )
            )
        )
        structure = ProofControlStructure(
            address=structure_address,
            kind=ProofStructureKind.CASE_SPLIT,
            assertion_status=assertion_status,
            support_status=InferenceStatus.CONFIDENT,
            branch_addresses=tuple(item.address for item in branches),
            premise_addresses=(disjunction.address,),
            conclusion_address=conclusion_address,
            source_addresses=source_addresses,
        )
        return structure, branches

    if assertion_addresses:
        structure = ProofControlStructure(
            address=f"S{index}:cases",
            kind=ProofStructureKind.CASE_SPLIT,
            assertion_status=InferenceStatus.CONFIDENT,
            support_status=InferenceStatus.UNRESOLVED,
            source_addresses=assertion_addresses,
            opaque_source_addresses=assertion_addresses,
        )
        return structure, []
    return None, []


def _contradiction_structures(
    resolved: SymbolResolutionIR,
    *,
    start_index: int,
) -> tuple[list[ProofControlStructure], list[ProofBranch]]:
    proof = resolved.proof
    propositions = _proposition_map(proof)
    structures: list[ProofControlStructure] = []
    branches: list[ProofBranch] = []
    index = start_index

    for step in proof.steps:
        if step.rule != ProofRuleKind.CONTRADICTION:
            continue
        conclusion = propositions.get(step.conclusion)
        if conclusion is None:
            continue
        conclusion_expression = _understood_expression(conclusion)
        source_addresses = tuple(dict.fromkeys((*step.source_addresses, conclusion.source_address)))
        assertion_status = (
            InferenceStatus.CONFIDENT
            if any(
                _CONTRADICTION_RE.search(_proof_source_text(proof, address))
                for address in source_addresses
            )
            else InferenceStatus.AMBIGUOUS
        )

        negated_address = (
            next(
                (
                    item.address
                    for item in proof.propositions
                    if _alpha_equal(_understood_expression(item), _not(conclusion_expression))
                ),
                None,
            )
            if conclusion_expression is not None
            else None
        )
        false_address = next(
            (
                item.address
                for item in proof.propositions
                if _is_false_expression(_understood_expression(item))
            ),
            None,
        )
        support_status = (
            InferenceStatus.CONFIDENT
            if negated_address is not None and false_address is not None
            else InferenceStatus.UNRESOLVED
        )
        structure_address = f"S{index}:contradiction"
        branch_addresses: tuple[str, ...] = ()
        local_assumptions: tuple[str, ...] = ()
        discharged_assumptions: tuple[str, ...] = ()
        if negated_address is not None:
            branch_address = f"{structure_address}:B1"
            local_assumptions = (negated_address,)
            discharged_assumptions = (negated_address,)
            body_addresses = tuple(
                address for address in (negated_address, false_address) if address is not None
            )
            branches.append(
                ProofBranch(
                    address=branch_address,
                    kind=ProofBranchKind.CONTRADICTION_BODY,
                    parent_structure_address=structure_address,
                    label="contradiction body",
                    proposition_addresses=body_addresses,
                    local_assumptions=local_assumptions,
                    conclusion_address=false_address,
                    discharged_assumptions=discharged_assumptions,
                    status=support_status,
                    source_addresses=tuple(
                        propositions[address].source_address
                        for address in body_addresses
                        if address in propositions
                    ),
                )
            )
            branch_addresses = (branch_address,)

        opaque = source_addresses if support_status != InferenceStatus.CONFIDENT else ()
        structures.append(
            ProofControlStructure(
                address=structure_address,
                kind=ProofStructureKind.CONTRADICTION,
                assertion_status=assertion_status,
                support_status=support_status,
                branch_addresses=branch_addresses,
                premise_addresses=tuple(
                    address for address in (negated_address, false_address) if address is not None
                ),
                conclusion_address=conclusion.address,
                local_assumptions=local_assumptions,
                discharged_assumptions=discharged_assumptions,
                source_addresses=source_addresses,
                opaque_source_addresses=opaque,
            )
        )
        index += 1

    if structures:
        return structures, branches

    cue_addresses = _explicit_cues(proof, _CONTRADICTION_RE)
    if cue_addresses:
        structures.append(
            ProofControlStructure(
                address=f"S{index}:contradiction",
                kind=ProofStructureKind.CONTRADICTION,
                assertion_status=InferenceStatus.CONFIDENT,
                support_status=InferenceStatus.UNRESOLVED,
                source_addresses=cue_addresses,
                opaque_source_addresses=cue_addresses,
            )
        )
    return structures, branches


def _contraposition_structure(
    resolved: SymbolResolutionIR,
    *,
    index: int,
) -> tuple[ProofControlStructure | None, list[ProofBranch]]:
    proof = resolved.proof
    cues = _explicit_cues(proof, _CONTRAPOSITION_RE)
    goal = next(
        (item for item in proof.propositions if item.role == PropositionRole.GOAL),
        None,
    )
    if goal is None:
        return None, []
    goal_expression = _understood_expression(goal)
    if (
        isinstance(goal_expression, LogicalExpr)
        and goal_expression.operator == LogicalOperator.IMPLIES
        and len(goal_expression.arguments) == 2
    ):
        antecedent, consequent = goal_expression.arguments
        expected = LogicalExpr(
            operator=LogicalOperator.IMPLIES,
            arguments=(_not(consequent), _not(antecedent)),
        )
        candidate = next(
            (
                item
                for item in proof.propositions
                if item.address != goal.address
                and _alpha_equal(_understood_expression(item), expected)
            ),
            None,
        )
        if candidate is not None:
            structure_address = f"S{index}:contraposition"
            assumption_ref = ExpressionRef(
                owner_address=candidate.address,
                path=("arguments", "0"),
            )
            conclusion_ref = ExpressionRef(
                owner_address=candidate.address,
                path=("arguments", "1"),
            )
            branch = ProofBranch(
                address=f"{structure_address}:B1",
                kind=ProofBranchKind.LOCAL_SUBPROOF,
                parent_structure_address=structure_address,
                label="contrapositive",
                proposition_addresses=(candidate.address,),
                assumption_refs=(assumption_ref,),
                conclusion_address=candidate.address,
                conclusion_ref=conclusion_ref,
                discharged_assumption_refs=(assumption_ref,),
                status=InferenceStatus.AMBIGUOUS,
                source_addresses=(candidate.source_address,),
            )
            source_addresses = tuple(
                dict.fromkeys((goal.source_address, candidate.source_address, *cues))
            )
            structure = ProofControlStructure(
                address=structure_address,
                kind=ProofStructureKind.CONTRAPOSITION,
                assertion_status=(
                    InferenceStatus.CONFIDENT if cues else InferenceStatus.UNRESOLVED
                ),
                support_status=InferenceStatus.AMBIGUOUS,
                branch_addresses=(branch.address,),
                premise_addresses=(candidate.address,),
                conclusion_address=goal.address,
                transformed_goal_ref=ExpressionRef(owner_address=candidate.address),
                source_addresses=source_addresses,
                opaque_source_addresses=() if cues else source_addresses,
            )
            return structure, [branch]
    if cues:
        return (
            ProofControlStructure(
                address=f"S{index}:contraposition",
                kind=ProofStructureKind.CONTRAPOSITION,
                assertion_status=InferenceStatus.CONFIDENT,
                support_status=InferenceStatus.UNRESOLVED,
                conclusion_address=goal.address,
                source_addresses=tuple(dict.fromkeys((goal.source_address, *cues))),
                opaque_source_addresses=cues,
            ),
            [],
        )
    return None, []


def _induction_structure(
    resolved: SymbolResolutionIR,
    *,
    index: int,
) -> tuple[ProofControlStructure | None, list[ProofBranch]]:
    proof = resolved.proof
    cues = _explicit_cues(proof, _INDUCTION_RE)
    goal = next(
        (item for item in proof.propositions if item.role == PropositionRole.GOAL),
        None,
    )
    if goal is None:
        return None, []
    expression = _understood_expression(goal)
    if not isinstance(expression, QuantifiedExpr) or expression.quantifier != Quantifier.FOR_ALL:
        if cues:
            return (
                ProofControlStructure(
                    address=f"S{index}:induction",
                    kind=ProofStructureKind.INDUCTION,
                    assertion_status=InferenceStatus.CONFIDENT,
                    support_status=InferenceStatus.UNRESOLVED,
                    conclusion_address=goal.address,
                    source_addresses=tuple(dict.fromkeys((goal.source_address, *cues))),
                    opaque_source_addresses=cues,
                ),
                [],
            )
        return None, []

    binder_name = expression.binder.name.name
    base_expected = _replace_free_name(
        expression.body,
        name=binder_name,
        replacement=LiteralExpr(value="0"),
    )
    base = next(
        (
            item
            for item in proof.propositions
            if item.address != goal.address
            and _alpha_equal(_understood_expression(item), base_expected)
        ),
        None,
    )

    step: ProofProposition | None = None
    step_assumption_ref: ExpressionRef | None = None
    step_conclusion_ref: ExpressionRef | None = None
    for item in proof.propositions:
        if item.address == goal.address:
            continue
        candidate = _understood_expression(item)
        step_binder_name = binder_name
        step_body = candidate
        prefix: tuple[str, ...] = ()
        if isinstance(candidate, QuantifiedExpr) and candidate.quantifier == Quantifier.FOR_ALL:
            step_binder_name = candidate.binder.name.name
            step_body = candidate.body
            prefix = ("body",)
        if not isinstance(step_body, LogicalExpr):
            continue
        if step_body.operator != LogicalOperator.IMPLIES or len(step_body.arguments) != 2:
            continue
        expected_current = _replace_free_name(
            expression.body,
            name=binder_name,
            replacement=IdentifierExpr(name=step_binder_name),
        )
        expected_next = _replace_free_name(
            expression.body,
            name=binder_name,
            replacement=_next_expression(step_binder_name),
        )
        if not _alpha_equal(step_body.arguments[0], expected_current):
            continue
        if not _alpha_equal(step_body.arguments[1], expected_next):
            continue
        step = item
        step_assumption_ref = ExpressionRef(
            owner_address=item.address,
            path=(*prefix, "arguments", "0"),
        )
        step_conclusion_ref = ExpressionRef(
            owner_address=item.address,
            path=(*prefix, "arguments", "1"),
        )
        break

    if base is not None and step is not None and step_assumption_ref is not None:
        structure_address = f"S{index}:induction"
        base_branch = ProofBranch(
            address=f"{structure_address}:B1",
            kind=ProofBranchKind.BASE_CASE,
            parent_structure_address=structure_address,
            label="base case",
            proposition_addresses=(base.address,),
            conclusion_address=base.address,
            conclusion_ref=ExpressionRef(owner_address=base.address),
            status=InferenceStatus.CONFIDENT,
            source_addresses=(base.source_address,),
        )
        step_branch = ProofBranch(
            address=f"{structure_address}:B2",
            kind=ProofBranchKind.INDUCTIVE_STEP,
            parent_structure_address=structure_address,
            label="inductive step",
            proposition_addresses=(step.address,),
            assumption_refs=(step_assumption_ref,),
            conclusion_address=step.address,
            conclusion_ref=step_conclusion_ref,
            discharged_assumption_refs=(step_assumption_ref,),
            status=InferenceStatus.CONFIDENT,
            source_addresses=(step.source_address,),
        )
        source_addresses = tuple(
            dict.fromkeys((goal.source_address, base.source_address, step.source_address, *cues))
        )
        structure = ProofControlStructure(
            address=structure_address,
            kind=ProofStructureKind.INDUCTION,
            assertion_status=InferenceStatus.CONFIDENT if cues else InferenceStatus.UNRESOLVED,
            support_status=InferenceStatus.CONFIDENT,
            branch_addresses=(base_branch.address, step_branch.address),
            premise_addresses=(base.address, step.address),
            conclusion_address=goal.address,
            subject_ref=ExpressionRef(
                owner_address=goal.address,
                path=("binder", "name"),
            ),
            source_addresses=source_addresses,
        )
        return structure, [base_branch, step_branch]

    if cues:
        return (
            ProofControlStructure(
                address=f"S{index}:induction",
                kind=ProofStructureKind.INDUCTION,
                assertion_status=InferenceStatus.CONFIDENT,
                support_status=InferenceStatus.UNRESOLVED,
                conclusion_address=goal.address,
                subject_ref=ExpressionRef(
                    owner_address=goal.address,
                    path=("binder", "name"),
                ),
                source_addresses=tuple(dict.fromkeys((goal.source_address, *cues))),
                opaque_source_addresses=cues,
            ),
            [],
        )
    return None, []


def _wlog_structures(
    resolved: SymbolResolutionIR,
    *,
    start_index: int,
) -> list[ProofControlStructure]:
    proof = resolved.proof
    cues = _explicit_cues(proof, _WLOG_RE)
    structures: list[ProofControlStructure] = []
    for offset, address in enumerate(cues):
        related_steps = [
            step
            for step in proof.steps
            if address in step.source_addresses
            and step.rule == ProofRuleKind.NAMED_PROPERTY_APPLICATION
        ]
        structures.append(
            ProofControlStructure(
                address=f"S{start_index + offset}:wlog",
                kind=ProofStructureKind.WLOG,
                assertion_status=InferenceStatus.CONFIDENT,
                support_status=(
                    InferenceStatus.AMBIGUOUS if related_steps else InferenceStatus.UNRESOLVED
                ),
                premise_addresses=tuple(
                    premise for step in related_steps for premise in step.premises
                ),
                conclusion_address=(related_steps[-1].conclusion if related_steps else None),
                source_addresses=(address,),
                opaque_source_addresses=(address,),
            )
        )
    return structures


def _subproof_structures(
    resolved: SymbolResolutionIR,
    *,
    start_index: int,
) -> tuple[list[ProofControlStructure], list[ProofBranch]]:
    proof = resolved.proof
    structures: list[ProofControlStructure] = []
    branches: list[ProofBranch] = []
    index = start_index
    for proposition in proof.propositions:
        text = _proof_source_text(proof, proposition.source_address)
        if not _SUBPROOF_RE.search(text):
            continue
        expression = _understood_expression(proposition)
        if not isinstance(expression, LogicalExpr):
            continue
        if expression.operator != LogicalOperator.IMPLIES or len(expression.arguments) != 2:
            continue
        structure_address = f"S{index}:subproof"
        assumption_ref = ExpressionRef(
            owner_address=proposition.address,
            path=("arguments", "0"),
        )
        conclusion_ref = ExpressionRef(
            owner_address=proposition.address,
            path=("arguments", "1"),
        )
        branch = ProofBranch(
            address=f"{structure_address}:B1",
            kind=ProofBranchKind.LOCAL_SUBPROOF,
            parent_structure_address=structure_address,
            label="local subproof",
            proposition_addresses=(proposition.address,),
            assumption_refs=(assumption_ref,),
            conclusion_address=proposition.address,
            conclusion_ref=conclusion_ref,
            discharged_assumption_refs=(assumption_ref,),
            status=InferenceStatus.AMBIGUOUS,
            source_addresses=(proposition.source_address,),
        )
        structures.append(
            ProofControlStructure(
                address=structure_address,
                kind=ProofStructureKind.SUBPROOF,
                assertion_status=InferenceStatus.CONFIDENT,
                support_status=InferenceStatus.AMBIGUOUS,
                branch_addresses=(branch.address,),
                conclusion_address=proposition.address,
                source_addresses=(proposition.source_address,),
                opaque_source_addresses=(proposition.source_address,),
            )
        )
        branches.append(branch)
        index += 1
    return structures, branches


def _witness_structures(
    resolved: SymbolResolutionIR,
    *,
    start_index: int,
) -> tuple[list[ProofControlStructure], list[ProofBranch]]:
    proof = resolved.proof
    step_by_address = {step.address: step for step in proof.steps}
    structures: list[ProofControlStructure] = []
    branches: list[ProofBranch] = []
    for offset, operation in enumerate(resolved.witnesses):
        structure_address = f"S{start_index + offset}:witness"
        step = step_by_address.get(operation.step_address)
        assertion_status = (
            InferenceStatus.CONFIDENT
            if step is not None and step.rule == ProofRuleKind.WITNESS_INTRODUCTION
            else InferenceStatus.UNRESOLVED
        )
        source_addresses = tuple(
            dict.fromkeys(
                provenance.source_address
                for provenance in operation.provenance
                if provenance.source_address is not None
            )
        )
        if not source_addresses and step is not None:
            source_addresses = step.source_addresses
        branch = ProofBranch(
            address=f"{structure_address}:B1",
            kind=ProofBranchKind.WITNESS,
            parent_structure_address=structure_address,
            label="witness",
            proposition_addresses=tuple(
                dict.fromkeys(
                    ref.owner_address
                    for ref in (operation.evidence_ref, operation.existential_ref)
                    if ref is not None
                )
            ),
            conclusion_address=operation.existential_ref.owner_address,
            conclusion_ref=operation.existential_ref,
            witness_ref=operation.witness_ref,
            evidence_ref=operation.evidence_ref,
            status=operation.status,
            source_addresses=source_addresses,
        )
        structures.append(
            ProofControlStructure(
                address=structure_address,
                kind=ProofStructureKind.WITNESS_BRANCH,
                assertion_status=assertion_status,
                support_status=operation.status,
                branch_addresses=(branch.address,),
                conclusion_address=operation.existential_ref.owner_address,
                witness_ref=operation.witness_ref,
                operation_addresses=(operation.address,),
                source_addresses=source_addresses,
                opaque_source_addresses=(
                    source_addresses if operation.status != InferenceStatus.CONFIDENT else ()
                ),
            )
        )
        branches.append(branch)
    return structures, branches


def elaborate_higher_proof_structure(resolved: SymbolResolutionIR) -> HigherProofIR:
    """Expose higher proof-control shape without changing lower semantic layers."""

    structures: list[ProofControlStructure] = []
    branches: list[ProofBranch] = []
    index = 1

    case_structure, case_branches = _case_split_structure(resolved, index=index)
    if case_structure is not None:
        structures.append(case_structure)
        branches.extend(case_branches)
        index += 1

    contradiction_structures, contradiction_branches = _contradiction_structures(
        resolved,
        start_index=index,
    )
    structures.extend(contradiction_structures)
    branches.extend(contradiction_branches)
    index += len(contradiction_structures)

    contraposition_structure, contraposition_branches = _contraposition_structure(
        resolved,
        index=index,
    )
    if contraposition_structure is not None:
        structures.append(contraposition_structure)
        branches.extend(contraposition_branches)
        index += 1

    induction_structure, induction_branches = _induction_structure(
        resolved,
        index=index,
    )
    if induction_structure is not None:
        structures.append(induction_structure)
        branches.extend(induction_branches)
        index += 1

    wlog_structures = _wlog_structures(resolved, start_index=index)
    structures.extend(wlog_structures)
    index += len(wlog_structures)

    subproof_structures, subproof_branches = _subproof_structures(
        resolved,
        start_index=index,
    )
    structures.extend(subproof_structures)
    branches.extend(subproof_branches)
    index += len(subproof_structures)

    witness_structures, witness_branches = _witness_structures(
        resolved,
        start_index=index,
    )
    structures.extend(witness_structures)
    branches.extend(witness_branches)

    return HigherProofIR(
        result_identifier=resolved.result_identifier,
        resolved=resolved.model_copy(deep=True),
        structures=structures,
        branches=branches,
    )


def build_higher_proof_ir(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
    *,
    symbol_table: SymbolTable | None = None,
) -> HigherProofIR:
    """Build issue-63 control-flow IR from the established issue-62 path."""

    resolved = build_symbol_resolution_ir(
        unit,
        request,
        symbol_table=symbol_table,
    )
    return elaborate_higher_proof_structure(resolved)
