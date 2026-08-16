from __future__ import annotations

import pytest

from thorn.canonical_proof_ir import (
    CanonicalEdgeKind,
    CanonicalNodeKind,
    CanonicalProofSource,
)
from thorn.canonical_typed_proof_ir import (
    CanonicalTypedProofEdge,
    CanonicalTypedProofIR,
    CanonicalTypedProofNode,
)
from thorn.evidence import InferenceStatus
from thorn.formula_ir import (
    ExprLoweringStatus,
    IdentifierExpr,
    LogicalExpr,
    LogicalOperator,
    OpaqueExpr,
)
from thorn.proof_obligations import (
    ObligationStatus,
    ProofRuleKind,
    PropositionRole,
    elaborate_proof_obligations,
)


def _source(address: str, text: str | None = None) -> CanonicalProofSource:
    return CanonicalProofSource(
        address=address,
        ir_identifier=f"ir:{address}",
        text=text if text is not None else address,
    )


def _node(
    address: str,
    kind: CanonicalNodeKind,
    expression=None,
    *,
    status: ExprLoweringStatus | None = ExprLoweringStatus.FULL,
    opaque: bool = False,
) -> CanonicalTypedProofNode:
    return CanonicalTypedProofNode(
        address=address,
        kind=kind,
        atom=address,
        opaque=opaque,
        expression=expression,
        expression_status=status if expression is not None else None,
    )


def _ir(
    *,
    nodes: list[CanonicalTypedProofNode],
    edges: list[CanonicalTypedProofEdge] | None = None,
    source_text: dict[str, str] | None = None,
) -> CanonicalTypedProofIR:
    edges = edges or []
    source_text = source_text or {}
    addresses = [node.address for node in nodes] + [edge.address for edge in edges]
    return CanonicalTypedProofIR(
        result_identifier="thm:test",
        nodes=nodes,
        edges=edges,
        sources=[_source(address, source_text.get(address)) for address in addresses],
    )


def test_roles_context_and_terminal_goal_are_explicit() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    implication = LogicalExpr(operator=LogicalOperator.IMPLIES, arguments=(p, q))
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node("H1", CanonicalNodeKind.HYPOTHESIS, p),
            _node("D1", CanonicalNodeKind.DEFINITION, IdentifierExpr(name="D")),
            _node("R1", CanonicalNodeKind.DEPENDENCY, implication),
            _node("C1", CanonicalNodeKind.CLAIM, q),
        ],
        edges=[
            CanonicalTypedProofEdge(
                address="E1",
                kind=CanonicalEdgeKind.RESULT_REFERENCE,
                source="R1",
                target="C1",
                status=InferenceStatus.CONFIDENT,
            )
        ],
    )

    proof = elaborate_proof_obligations(graph)

    assert proof.proposition("T0").role == PropositionRole.GOAL
    assert proof.proposition("H1").role == PropositionRole.ASSUMPTION
    assert proof.proposition("D1").role == PropositionRole.DEFINITION
    assert proof.proposition("R1").role == PropositionRole.IMPORTED_RESULT
    assert proof.proposition("C1").role == PropositionRole.DERIVED

    claim_obligation = next(
        item for item in proof.obligations if item.proposition_address == "C1"
    )
    assert claim_obligation.local_context == ("H1", "D1", "R1")
    assert claim_obligation.support_context == ("R1",)
    assert claim_obligation.status == ObligationStatus.DISCHARGED
    assert claim_obligation.discharging_steps == ("E1",)

    support_step = next(item for item in proof.steps if item.address == "E1")
    assert support_step.rule == ProofRuleKind.APPLY_RESULT
    assert support_step.premises == ("R1",)
    assert support_step.status == InferenceStatus.CONFIDENT

    terminal = proof.terminal_obligation
    assert terminal.address == "G0"
    assert terminal.proposition_address == "T0"
    assert terminal.expected == q
    assert terminal.local_context == ("H1", "D1", "R1", "C1")
    assert terminal.status == ObligationStatus.DISCHARGED
    assert terminal.support_context == ("C1",)
    terminal_step = next(item for item in proof.steps if item.address == "X0")
    assert terminal_step.rule == ProofRuleKind.EXACT
    assert terminal_step.conclusion == "T0"


def test_exact_implication_elimination_is_detected_from_typed_structure() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    implication = LogicalExpr(operator=LogicalOperator.IMPLIES, arguments=(p, q))
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node("H1", CanonicalNodeKind.HYPOTHESIS, p),
            _node("C1", CanonicalNodeKind.CLAIM, implication),
            _node("C2", CanonicalNodeKind.CLAIM, q),
        ],
        edges=[
            CanonicalTypedProofEdge(
                address="E1",
                kind=CanonicalEdgeKind.PRIOR_CLAIM,
                source="C1",
                target="C2",
                status=InferenceStatus.CONFIDENT,
            )
        ],
    )

    proof = elaborate_proof_obligations(graph)
    step = next(item for item in proof.steps if item.address == "E1")

    assert step.rule == ProofRuleKind.IMPLICATION_ELIMINATION
    assert step.premises == ("C1", "H1")
    obligation = next(
        item for item in proof.obligations if item.proposition_address == "C2"
    )
    assert obligation.status == ObligationStatus.DISCHARGED
    assert obligation.support_context == ("C1", "H1")


def test_ambiguous_unknown_rule_remains_first_class_and_does_not_discharge() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node("C1", CanonicalNodeKind.CLAIM, p),
            _node("C2", CanonicalNodeKind.CLAIM, q),
        ],
        edges=[
            CanonicalTypedProofEdge(
                address="E1",
                kind=CanonicalEdgeKind.PRIOR_CLAIM,
                source="C1",
                target="C2",
                status=InferenceStatus.AMBIGUOUS,
            )
        ],
    )

    proof = elaborate_proof_obligations(graph)
    step = next(item for item in proof.steps if item.address == "E1")
    obligation = next(
        item for item in proof.obligations if item.proposition_address == "C2"
    )

    assert step.rule == ProofRuleKind.UNKNOWN
    assert step.status == InferenceStatus.AMBIGUOUS
    assert obligation.status == ObligationStatus.UNRESOLVED
    assert obligation.discharging_steps == ()
    assert proof.terminal_obligation.status == ObligationStatus.UNRESOLVED
    terminal_step = next(item for item in proof.steps if item.address == "X0")
    assert terminal_step.rule == ProofRuleKind.EXACT
    assert terminal_step.status == InferenceStatus.CONFIDENT


@pytest.mark.parametrize(
    ("text", "expected_rule"),
    [
        (
            "Rewriting with the displayed equation gives the claim.",
            ProofRuleKind.REWRITE_SUBSTITUTION,
        ),
        ("Instantiate the preceding statement at x.", ProofRuleKind.INSTANTIATE),
        ("Choose y as a witness.", ProofRuleKind.WITNESS_INTRODUCTION),
        ("This follows by contradiction.", ProofRuleKind.CONTRADICTION),
    ],
)
def test_rule_names_require_bounded_source_evidence(
    text: str,
    expected_rule: ProofRuleKind,
) -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node("C1", CanonicalNodeKind.CLAIM, p),
            _node("C2", CanonicalNodeKind.CLAIM, q),
        ],
        edges=[
            CanonicalTypedProofEdge(
                address="E1",
                kind=CanonicalEdgeKind.EXPLICIT_REASON,
                source="C1",
                target="C2",
                status=InferenceStatus.CONFIDENT,
            )
        ],
        source_text={"E1": text},
    )

    proof = elaborate_proof_obligations(graph)

    step = next(item for item in proof.steps if item.address == "E1")
    assert step.rule == expected_rule


def test_named_property_and_definition_edges_have_safe_rule_kinds() -> None:
    q = IdentifierExpr(name="Q")
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node("D1", CanonicalNodeKind.DEFINITION, IdentifierExpr(name="D")),
            _node("C1", CanonicalNodeKind.CLAIM, IdentifierExpr(name="P")),
            _node("C2", CanonicalNodeKind.CLAIM, q),
        ],
        edges=[
            CanonicalTypedProofEdge(
                address="E1",
                kind=CanonicalEdgeKind.DEFINITION,
                source="D1",
                target="C1",
            ),
            CanonicalTypedProofEdge(
                address="E2",
                kind=CanonicalEdgeKind.NAMED_PROPERTY,
                source="C1",
                target="C2",
            ),
        ],
    )

    proof = elaborate_proof_obligations(graph)
    rules = {step.address: step.rule for step in proof.steps}

    assert rules["E1"] == ProofRuleKind.DEFINITION_USE
    assert rules["E2"] == ProofRuleKind.NAMED_PROPERTY_APPLICATION


def test_opaque_content_stays_as_explicit_unresolved_obligation() -> None:
    q = IdentifierExpr(name="Q")
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node(
                "U1",
                CanonicalNodeKind.UNRESOLVED_MATH,
                OpaqueExpr(text=r"\sum_i a_i"),
                status=ExprLoweringStatus.OPAQUE,
            ),
            _node("P1", CanonicalNodeKind.OPAQUE_PROSE, None, opaque=True),
        ]
    )

    proof = elaborate_proof_obligations(graph)
    unresolved = {
        item.proposition_address: item for item in proof.unresolved_obligations
    }

    assert proof.proposition("U1").role == PropositionRole.UNRESOLVED
    assert proof.proposition("P1").role == PropositionRole.UNRESOLVED
    assert unresolved["U1"].expected == OpaqueExpr(text=r"\sum_i a_i")
    assert unresolved["U1"].local_context == ()
    assert unresolved["P1"].expected is None
    assert unresolved["P1"].local_context == ("U1",)
    assert proof.terminal_obligation.status == ObligationStatus.UNRESOLVED


def test_terminal_mismatch_is_connected_but_not_claimed_as_proved() -> None:
    q = IdentifierExpr(name="Q")
    r = IdentifierExpr(name="R")
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node("C1", CanonicalNodeKind.CLAIM, r),
        ]
    )

    proof = elaborate_proof_obligations(graph)
    terminal = proof.terminal_obligation
    terminal_step = next(item for item in proof.steps if item.address == "X0")

    assert terminal.support_context == ("C1",)
    assert terminal.status == ObligationStatus.UNRESOLVED
    assert terminal.discharging_steps == ()
    assert terminal_step.rule == ProofRuleKind.UNKNOWN
    assert terminal_step.status == InferenceStatus.UNRESOLVED


def test_source_addresses_are_recoverable_and_input_ir_is_not_mutated() -> None:
    q = IdentifierExpr(name="Q")
    graph = _ir(
        nodes=[
            _node("T0", CanonicalNodeKind.RESULT, q),
            _node("C1", CanonicalNodeKind.CLAIM, q),
        ]
    )
    before = graph.model_dump(mode="json")

    proof = elaborate_proof_obligations(graph)

    assert graph.model_dump(mode="json") == before
    for proposition in proof.propositions:
        assert proof.source(proposition.source_address).address == proposition.address
    for obligation in proof.obligations:
        source = proof.source(obligation.source_address)
        assert source.address == obligation.proposition_address
    for step in proof.steps:
        for address in step.source_addresses:
            assert proof.source(address).address == address
