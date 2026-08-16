from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from thorn.canonical_proof_ir import (
    CanonicalEdgeKind,
    CanonicalNodeKind,
    CanonicalProofSource,
)
from thorn.canonical_typed_proof_ir import (
    CanonicalTypedProofEdge,
    CanonicalTypedProofIR,
    CanonicalTypedProofNode,
    build_canonical_typed_proof_ir,
)
from thorn.evidence import InferenceStatus
from thorn.formula_ir import ExprLoweringStatus, LogicalExpr, LogicalOperator, MathExpr
from thorn.models import TheoremUnit
from thorn.semantic_review_render import SemanticReviewRequest


class PropositionRole(StrEnum):
    """Semantic role of a proposition-like item in a local proof state."""

    ASSUMPTION = "assumption"
    GOAL = "goal"
    DERIVED = "derived"
    IMPORTED_RESULT = "imported_result"
    DEFINITION = "definition"
    UNRESOLVED = "unresolved"


class ObligationStatus(StrEnum):
    """Whether the manuscript structurally presents a discharge for an obligation.

    ``DISCHARGED`` is deliberately not a proof-validity judgement. It means that
    Thorn recovered a confident structural derivation candidate for understood
    mathematical content. Semantic validation remains downstream work.
    """

    DISCHARGED = "discharged"
    UNRESOLVED = "unresolved"


class ProofRuleKind(StrEnum):
    """Small rule vocabulary justified by source or exact expression structure."""

    UNKNOWN = "unknown"
    EXACT = "exact"
    APPLY_RESULT = "apply_result"
    IMPLICATION_ELIMINATION = "implication_elimination"
    DEFINITION_USE = "definition_use"
    REWRITE_SUBSTITUTION = "rewrite_substitution"
    INSTANTIATE = "instantiate"
    WITNESS_INTRODUCTION = "witness_introduction"
    CONTRADICTION = "contradiction"
    NAMED_PROPERTY_APPLICATION = "named_property_application"


class ProofProposition(BaseModel):
    """One source-addressable proposition available to proof-state consumers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    role: PropositionRole
    node_kind: CanonicalNodeKind
    expression: MathExpr | None = None
    expression_status: ExprLoweringStatus | None = None
    source_address: str


class ProofStepEdge(BaseModel):
    """A typed structural derivation candidate.

    The edge records what the manuscript structurally presents, not that the rule
    application is mathematically valid. ``UNKNOWN`` is a normal rule value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    premises: tuple[str, ...] = ()
    conclusion: str
    rule: ProofRuleKind = ProofRuleKind.UNKNOWN
    status: InferenceStatus = InferenceStatus.UNRESOLVED
    canonical_edge_address: str | None = None
    source_addresses: tuple[str, ...] = ()


class ProofObligation(BaseModel):
    """Expected proposition plus the local context visible at that proof point."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    address: str
    proposition_address: str
    expected: MathExpr | None = None
    expected_status: ExprLoweringStatus | None = None
    local_context: tuple[str, ...] = ()
    support_context: tuple[str, ...] = ()
    status: ObligationStatus = ObligationStatus.UNRESOLVED
    discharging_steps: tuple[str, ...] = ()
    source_address: str
    terminal: bool = False


class ProofObligationIR(BaseModel):
    """Explicit local proof states derived conservatively from canonical typed IR."""

    result_identifier: str
    propositions: list[ProofProposition] = Field(default_factory=list)
    obligations: list[ProofObligation] = Field(default_factory=list)
    steps: list[ProofStepEdge] = Field(default_factory=list)
    sources: list[CanonicalProofSource] = Field(default_factory=list)
    pruned_claims: int = 0
    unresolved_math_claims: int = 0

    def source(self, address: str) -> CanonicalProofSource:
        for item in self.sources:
            if item.address == address:
                return item
        raise KeyError(f"unknown proof-obligation source address {address!r}")

    def proposition(self, address: str) -> ProofProposition:
        for item in self.propositions:
            if item.address == address:
                return item
        raise KeyError(f"unknown proposition address {address!r}")

    def obligation(self, address: str) -> ProofObligation:
        for item in self.obligations:
            if item.address == address:
                return item
        raise KeyError(f"unknown obligation address {address!r}")

    @property
    def terminal_obligation(self) -> ProofObligation:
        terminal = [item for item in self.obligations if item.terminal]
        if len(terminal) != 1:
            raise ValueError(
                f"expected exactly one terminal obligation, found {len(terminal)}"
            )
        return terminal[0]

    @property
    def unresolved_obligations(self) -> list[ProofObligation]:
        return [
            item
            for item in self.obligations
            if item.status == ObligationStatus.UNRESOLVED
        ]


_ROLE_BY_NODE_KIND: dict[CanonicalNodeKind, PropositionRole] = {
    CanonicalNodeKind.RESULT: PropositionRole.GOAL,
    CanonicalNodeKind.HYPOTHESIS: PropositionRole.ASSUMPTION,
    CanonicalNodeKind.LOCAL_CONSTRAINT: PropositionRole.ASSUMPTION,
    CanonicalNodeKind.DEFINITION: PropositionRole.DEFINITION,
    CanonicalNodeKind.DEPENDENCY: PropositionRole.IMPORTED_RESULT,
    CanonicalNodeKind.CLAIM: PropositionRole.DERIVED,
    CanonicalNodeKind.UNRESOLVED_MATH: PropositionRole.UNRESOLVED,
    CanonicalNodeKind.OPAQUE_PROSE: PropositionRole.UNRESOLVED,
}

_GLOBAL_CONTEXT_KINDS = {
    CanonicalNodeKind.HYPOTHESIS,
    CanonicalNodeKind.LOCAL_CONSTRAINT,
    CanonicalNodeKind.DEFINITION,
    CanonicalNodeKind.DEPENDENCY,
}
_PROOF_NODE_KINDS = {
    CanonicalNodeKind.CLAIM,
    CanonicalNodeKind.UNRESOLVED_MATH,
    CanonicalNodeKind.OPAQUE_PROSE,
}
_NON_INFERENCE_EDGE_KINDS = {
    CanonicalEdgeKind.QUANTIFIER,
    CanonicalEdgeKind.QUALIFIER,
}

_REWRITE_RE = re.compile(
    r"\b(?:rewrit(?:e|ing)|substitut(?:e|ing|ion))\b", re.IGNORECASE
)
_INSTANTIATE_RE = re.compile(
    r"\b(?:instantiat(?:e|ing|ion)|speciali[sz](?:e|ing|ation))\b",
    re.IGNORECASE,
)
_WITNESS_RE = re.compile(r"\bwitness\b", re.IGNORECASE)
_CONTRADICTION_RE = re.compile(r"\bcontradiction\b", re.IGNORECASE)


def _proposition(node: CanonicalTypedProofNode) -> ProofProposition:
    return ProofProposition(
        address=node.address,
        role=_ROLE_BY_NODE_KIND[node.kind],
        node_kind=node.kind,
        expression=node.expression,
        expression_status=node.expression_status,
        source_address=node.address,
    )


def _expression_by_address(ir: CanonicalTypedProofIR) -> dict[str, MathExpr | None]:
    return {node.address: node.expression for node in ir.nodes}


def _rule_from_edge_kind(edge: CanonicalTypedProofEdge) -> ProofRuleKind:
    if edge.kind == CanonicalEdgeKind.RESULT_REFERENCE:
        return ProofRuleKind.APPLY_RESULT
    if edge.kind == CanonicalEdgeKind.DEFINITION:
        return ProofRuleKind.DEFINITION_USE
    if edge.kind == CanonicalEdgeKind.NAMED_PROPERTY:
        return ProofRuleKind.NAMED_PROPERTY_APPLICATION
    return ProofRuleKind.UNKNOWN


def _rule_from_source_text(text: str) -> ProofRuleKind:
    if _CONTRADICTION_RE.search(text):
        return ProofRuleKind.CONTRADICTION
    if _REWRITE_RE.search(text):
        return ProofRuleKind.REWRITE_SUBSTITUTION
    if _WITNESS_RE.search(text):
        return ProofRuleKind.WITNESS_INTRODUCTION
    if _INSTANTIATE_RE.search(text):
        return ProofRuleKind.INSTANTIATE
    return ProofRuleKind.UNKNOWN


def _implication_elimination_premises(
    *,
    edge: CanonicalTypedProofEdge,
    expressions: dict[str, MathExpr | None],
    local_context: tuple[str, ...],
) -> tuple[str, ...] | None:
    if edge.source is None:
        return None
    source_expression = expressions.get(edge.source)
    target_expression = expressions.get(edge.target)
    if not isinstance(source_expression, LogicalExpr):
        return None
    if source_expression.operator != LogicalOperator.IMPLIES:
        return None
    if len(source_expression.arguments) != 2:
        return None
    antecedent, consequent = source_expression.arguments
    if target_expression != consequent:
        return None
    for address in local_context:
        if address == edge.source:
            continue
        if expressions.get(address) == antecedent:
            return (edge.source, address)
    return None


def _typed_step(
    *,
    edge: CanonicalTypedProofEdge,
    ir: CanonicalTypedProofIR,
    expressions: dict[str, MathExpr | None],
    local_context: tuple[str, ...],
) -> ProofStepEdge:
    source_text = ir.source(edge.address).text
    premises: tuple[str, ...] = (edge.source,) if edge.source is not None else ()
    rule = _rule_from_edge_kind(edge)

    if rule == ProofRuleKind.UNKNOWN:
        implication_premises = _implication_elimination_premises(
            edge=edge,
            expressions=expressions,
            local_context=local_context,
        )
        if implication_premises is not None:
            rule = ProofRuleKind.IMPLICATION_ELIMINATION
            premises = implication_premises
        else:
            rule = _rule_from_source_text(source_text)

    status = edge.status
    if any(
        premise.startswith("@") or premise not in expressions for premise in premises
    ):
        status = InferenceStatus.UNRESOLVED

    return ProofStepEdge(
        address=edge.address,
        premises=premises,
        conclusion=edge.target,
        rule=rule,
        status=status,
        canonical_edge_address=edge.address,
        source_addresses=(edge.address,),
    )


def _is_understood(proposition: ProofProposition) -> bool:
    return (
        proposition.expression is not None
        and proposition.expression_status is not None
        and proposition.expression_status != ExprLoweringStatus.OPAQUE
        and proposition.role != PropositionRole.UNRESOLVED
    )


def _obligation_status(
    proposition: ProofProposition,
    steps: list[ProofStepEdge],
) -> ObligationStatus:
    if not _is_understood(proposition):
        return ObligationStatus.UNRESOLVED
    if any(step.status == InferenceStatus.CONFIDENT for step in steps):
        return ObligationStatus.DISCHARGED
    return ObligationStatus.UNRESOLVED


def _terminal_step(
    *,
    goal: ProofProposition,
    proof_nodes: list[ProofProposition],
) -> ProofStepEdge | None:
    if not proof_nodes:
        return None
    final = proof_nodes[-1]
    exact = (
        _is_understood(goal)
        and _is_understood(final)
        and goal.expression == final.expression
    )
    return ProofStepEdge(
        address="X0",
        premises=(final.address,),
        conclusion=goal.address,
        rule=ProofRuleKind.EXACT if exact else ProofRuleKind.UNKNOWN,
        status=InferenceStatus.CONFIDENT if exact else InferenceStatus.UNRESOLVED,
        source_addresses=(final.source_address, goal.source_address),
    )


def elaborate_proof_obligations(ir: CanonicalTypedProofIR) -> ProofObligationIR:
    """Create explicit proof states without changing the issue-57 graph slice.

    The canonical graph determines topology and source addresses. Issue #60 expressions
    determine understood proposition content. This layer only adds proof-state roles,
    conservative rule labels, and explicit unresolved obligations.
    """

    propositions = [_proposition(node) for node in ir.nodes]
    proposition_by_address = {item.address: item for item in propositions}
    expressions = _expression_by_address(ir)
    global_context = tuple(
        item.address for item in propositions if item.node_kind in _GLOBAL_CONTEXT_KINDS
    )
    proof_nodes = [
        item for item in propositions if item.node_kind in _PROOF_NODE_KINDS
    ]

    context_by_target: dict[str, tuple[str, ...]] = {}
    prior: list[str] = []
    for proposition in proof_nodes:
        context_by_target[proposition.address] = (*global_context, *prior)
        prior.append(proposition.address)

    steps: list[ProofStepEdge] = []
    for edge in ir.edges:
        if edge.kind in _NON_INFERENCE_EDGE_KINDS:
            continue
        if edge.target not in proposition_by_address:
            continue
        steps.append(
            _typed_step(
                edge=edge,
                ir=ir,
                expressions=expressions,
                local_context=context_by_target.get(edge.target, global_context),
            )
        )

    incoming: dict[str, list[ProofStepEdge]] = {}
    for step in steps:
        incoming.setdefault(step.conclusion, []).append(step)

    obligations: list[ProofObligation] = []
    obligation_index = 0
    for proposition in proof_nodes:
        obligation_index += 1
        candidate_steps = incoming.get(proposition.address, [])
        context = context_by_target[proposition.address]
        support_context = tuple(
            dict.fromkeys(
                premise
                for step in candidate_steps
                for premise in step.premises
                if premise in proposition_by_address
            )
        )
        obligations.append(
            ProofObligation(
                address=f"O{obligation_index}",
                proposition_address=proposition.address,
                expected=proposition.expression,
                expected_status=proposition.expression_status,
                local_context=context,
                support_context=support_context,
                status=_obligation_status(proposition, candidate_steps),
                discharging_steps=tuple(
                    step.address
                    for step in candidate_steps
                    if step.status == InferenceStatus.CONFIDENT
                ),
                source_address=proposition.source_address,
            )
        )

    goals = [item for item in propositions if item.role == PropositionRole.GOAL]
    if len(goals) != 1:
        raise ValueError(f"expected exactly one theorem goal, found {len(goals)}")
    goal = goals[0]
    terminal_step = _terminal_step(goal=goal, proof_nodes=proof_nodes)
    if terminal_step is not None:
        steps.append(terminal_step)
    final_obligation_status = obligations[-1].status if obligations else None
    terminal_status = (
        ObligationStatus.DISCHARGED
        if (
            terminal_step is not None
            and terminal_step.status == InferenceStatus.CONFIDENT
            and final_obligation_status == ObligationStatus.DISCHARGED
        )
        else ObligationStatus.UNRESOLVED
    )
    terminal_support = terminal_step.premises if terminal_step is not None else ()
    terminal_discharging = (
        (terminal_step.address,)
        if terminal_status == ObligationStatus.DISCHARGED
        else ()
    )
    obligations.append(
        ProofObligation(
            address="G0",
            proposition_address=goal.address,
            expected=goal.expression,
            expected_status=goal.expression_status,
            local_context=(*global_context, *(item.address for item in proof_nodes)),
            support_context=terminal_support,
            status=terminal_status,
            discharging_steps=terminal_discharging,
            source_address=goal.source_address,
            terminal=True,
        )
    )

    return ProofObligationIR(
        result_identifier=ir.result_identifier,
        propositions=propositions,
        obligations=obligations,
        steps=steps,
        sources=ir.sources,
        pruned_claims=ir.pruned_claims,
        unresolved_math_claims=ir.unresolved_math_claims,
    )


def build_proof_obligation_ir(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
) -> ProofObligationIR:
    """Build typed canonical IR and expose explicit local proof obligations."""

    typed_ir = build_canonical_typed_proof_ir(unit, request)
    return elaborate_proof_obligations(typed_ir)
