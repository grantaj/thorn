from __future__ import annotations

from thorn.canonical_proof_ir import CanonicalNodeKind, CanonicalProofSource
from thorn.evidence import InferenceStatus
from thorn.formula_ir import (
    ApplyExpr,
    Binder,
    ExprLoweringStatus,
    IdentifierExpr,
    LiteralExpr,
    LogicalExpr,
    LogicalOperator,
    NotExpr,
    OperatorExpr,
    QuantifiedExpr,
    Quantifier,
)
from thorn.higher_proof_structure import (
    ProofBranchKind,
    ProofStructureKind,
    elaborate_higher_proof_structure,
)
from thorn.proof_obligations import (
    ProofObligationIR,
    ProofProposition,
    ProofRuleKind,
    ProofStepEdge,
    PropositionRole,
)
from thorn.symbol_resolution_ir import ExpressionRef, elaborate_symbol_resolution


def _prop(
    address: str,
    expression,
    *,
    role: PropositionRole = PropositionRole.DERIVED,
) -> ProofProposition:
    kind = {
        PropositionRole.GOAL: CanonicalNodeKind.RESULT,
        PropositionRole.ASSUMPTION: CanonicalNodeKind.HYPOTHESIS,
        PropositionRole.DERIVED: CanonicalNodeKind.CLAIM,
        PropositionRole.IMPORTED_RESULT: CanonicalNodeKind.DEPENDENCY,
        PropositionRole.DEFINITION: CanonicalNodeKind.DEFINITION,
        PropositionRole.UNRESOLVED: CanonicalNodeKind.UNRESOLVED_MATH,
    }[role]
    return ProofProposition(
        address=address,
        role=role,
        node_kind=kind,
        expression=expression,
        expression_status=ExprLoweringStatus.FULL,
        source_address=address,
    )


def _proof(
    propositions: list[ProofProposition],
    *,
    steps: list[ProofStepEdge] | None = None,
    source_text: dict[str, str] | None = None,
) -> ProofObligationIR:
    steps = steps or []
    source_text = source_text or {}
    addresses = [item.source_address for item in propositions]
    addresses.extend(
        address
        for step in steps
        for address in step.source_addresses
        if address not in addresses
    )
    return ProofObligationIR(
        result_identifier="thm:test",
        propositions=propositions,
        steps=steps,
        sources=[
            CanonicalProofSource(
                address=address,
                ir_identifier=f"ir:{address}",
                text=source_text.get(address, address),
            )
            for address in addresses
        ],
    )


def _higher(proof: ProofObligationIR):
    resolved = elaborate_symbol_resolution(proof)
    return resolved, elaborate_higher_proof_structure(resolved)


def _imp(left, right) -> LogicalExpr:
    return LogicalExpr(operator=LogicalOperator.IMPLIES, arguments=(left, right))


def test_exact_case_split_has_explicit_branches_and_discharged_case_assumptions() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    r = IdentifierExpr(name="R")
    disjunction = LogicalExpr(operator=LogicalOperator.OR, arguments=(p, q))
    proof = _proof(
        [
            _prop("T0", r, role=PropositionRole.GOAL),
            _prop("H1", disjunction, role=PropositionRole.ASSUMPTION),
            _prop("C1", _imp(p, r)),
            _prop("C2", _imp(q, r)),
            _prop("C3", r),
        ],
        source_text={
            "C1": "Case 1: assume P and derive R.",
            "C2": "Case 2: assume Q and derive R.",
        },
    )

    _resolved, higher = _higher(proof)
    structure = next(item for item in higher.structures if item.kind == ProofStructureKind.CASE_SPLIT)

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.CONFIDENT
    assert structure.premise_addresses == ("H1",)
    assert len(structure.branch_addresses) == 2

    first = higher.branch(structure.branch_addresses[0])
    second = higher.branch(structure.branch_addresses[1])
    assert first.kind == ProofBranchKind.CASE
    assert second.kind == ProofBranchKind.CASE
    assert first.discharged_assumption_refs == (
        ExpressionRef(owner_address="C1", path=("arguments", "0")),
    )
    assert second.discharged_assumption_refs == (
        ExpressionRef(owner_address="C2", path=("arguments", "0")),
    )
    assert first.status == InferenceStatus.CONFIDENT
    assert higher.source(first.source_addresses[0]).text.startswith("Case 1")


def test_case_wording_without_exhaustive_structural_shape_fails_closed() -> None:
    proof = _proof(
        [
            _prop("T0", IdentifierExpr(name="R"), role=PropositionRole.GOAL),
            _prop("C1", IdentifierExpr(name="P")),
        ],
        source_text={"C1": "We split into cases."},
    )

    _resolved, higher = _higher(proof)
    structure = next(item for item in higher.structures if item.kind == ProofStructureKind.CASE_SPLIT)

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.UNRESOLVED
    assert structure.branch_addresses == ()
    assert structure.opaque_source_addresses == ("C1",)


def test_structural_case_shape_can_be_recovered_without_claiming_it_was_asserted() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    r = IdentifierExpr(name="R")
    proof = _proof(
        [
            _prop("T0", r, role=PropositionRole.GOAL),
            _prop(
                "H1",
                LogicalExpr(operator=LogicalOperator.OR, arguments=(p, q)),
                role=PropositionRole.ASSUMPTION,
            ),
            _prop("C1", _imp(p, r)),
            _prop("C2", _imp(q, r)),
        ]
    )

    _resolved, higher = _higher(proof)
    structure = next(item for item in higher.structures if item.kind == ProofStructureKind.CASE_SPLIT)

    assert structure.assertion_status == InferenceStatus.UNRESOLVED
    assert structure.support_status == InferenceStatus.CONFIDENT


def test_contradiction_records_local_assumption_and_discharge_separately() -> None:
    q = IdentifierExpr(name="Q")
    proof = _proof(
        [
            _prop("T0", q, role=PropositionRole.GOAL),
            _prop("H1", NotExpr(operand=q), role=PropositionRole.ASSUMPTION),
            _prop("C1", IdentifierExpr(name="False")),
            _prop("C2", q),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("C1",),
                conclusion="C2",
                rule=ProofRuleKind.CONTRADICTION,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        source_text={"E1": "The claim follows by contradiction."},
    )

    _resolved, higher = _higher(proof)
    structure = next(
        item for item in higher.structures if item.kind == ProofStructureKind.CONTRADICTION
    )

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.CONFIDENT
    assert structure.local_assumptions == ("H1",)
    assert structure.discharged_assumptions == ("H1",)
    branch = higher.branch(structure.branch_addresses[0])
    assert branch.kind == ProofBranchKind.CONTRADICTION_BODY
    assert branch.local_assumptions == ("H1",)
    assert branch.conclusion_address == "C1"


def test_contradiction_cue_alone_is_not_mechanical_support() -> None:
    proof = _proof(
        [
            _prop("T0", IdentifierExpr(name="Q"), role=PropositionRole.GOAL),
            _prop("C1", IdentifierExpr(name="P")),
        ],
        source_text={"C1": "We proceed by contradiction."},
    )

    _resolved, higher = _higher(proof)
    structure = next(
        item for item in higher.structures if item.kind == ProofStructureKind.CONTRADICTION
    )

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.UNRESOLVED
    assert structure.opaque_source_addresses == ("C1",)


def test_contraposition_shape_is_explicit_but_not_certified_without_logic_assumptions() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    goal = _imp(p, q)
    contrapositive = _imp(NotExpr(operand=q), NotExpr(operand=p))
    proof = _proof(
        [
            _prop("T0", goal, role=PropositionRole.GOAL),
            _prop("C1", contrapositive),
        ],
        source_text={"C1": "We prove the contrapositive."},
    )

    _resolved, higher = _higher(proof)
    structure = next(
        item for item in higher.structures if item.kind == ProofStructureKind.CONTRAPOSITION
    )

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.AMBIGUOUS
    assert structure.transformed_goal_ref == ExpressionRef(owner_address="C1")
    branch = higher.branch(structure.branch_addresses[0])
    assert branch.assumption_refs == (
        ExpressionRef(owner_address="C1", path=("arguments", "0")),
    )
    assert branch.discharged_assumption_refs == branch.assumption_refs


def test_induction_recovers_base_step_parameter_and_induction_hypothesis() -> None:
    n = IdentifierExpr(name="n")
    k = IdentifierExpr(name="k")
    p_n = ApplyExpr(function=IdentifierExpr(name="P"), arguments=(n,))
    goal = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=n, domain=IdentifierExpr(name="N")),
        body=p_n,
    )
    base = ApplyExpr(
        function=IdentifierExpr(name="P"),
        arguments=(LiteralExpr(value="0"),),
    )
    p_k = ApplyExpr(function=IdentifierExpr(name="P"), arguments=(k,))
    p_k_next = ApplyExpr(
        function=IdentifierExpr(name="P"),
        arguments=(
            OperatorExpr(
                operator="+",
                arguments=(k, LiteralExpr(value="1")),
            ),
        ),
    )
    step = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=k, domain=IdentifierExpr(name="N")),
        body=_imp(p_k, p_k_next),
    )
    proof = _proof(
        [
            _prop("T0", goal, role=PropositionRole.GOAL),
            _prop("C1", base),
            _prop("C2", step),
        ],
        source_text={
            "C1": "Base case.",
            "C2": "For the inductive step, assume the induction hypothesis.",
        },
    )

    resolved, higher = _higher(proof)
    structure = next(item for item in higher.structures if item.kind == ProofStructureKind.INDUCTION)

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.CONFIDENT
    assert structure.premise_addresses == ("C1", "C2")
    assert structure.subject_ref == ExpressionRef(
        owner_address="T0",
        path=("binder", "name"),
    )
    assert resolved.expression(structure.subject_ref) == n

    base_branch = higher.branch(structure.branch_addresses[0])
    step_branch = higher.branch(structure.branch_addresses[1])
    assert base_branch.kind == ProofBranchKind.BASE_CASE
    assert step_branch.kind == ProofBranchKind.INDUCTIVE_STEP
    expected_ih = ExpressionRef(owner_address="C2", path=("body", "arguments", "0"))
    assert step_branch.assumption_refs == (expected_ih,)
    assert step_branch.discharged_assumption_refs == (expected_ih,)
    assert resolved.expression(expected_ih) == p_k


def test_induction_wording_with_missing_step_remains_opaque_and_unresolved() -> None:
    n = IdentifierExpr(name="n")
    goal = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=n),
        body=ApplyExpr(function=IdentifierExpr(name="P"), arguments=(n,)),
    )
    proof = _proof(
        [
            _prop("T0", goal, role=PropositionRole.GOAL),
            _prop(
                "C1",
                ApplyExpr(
                    function=IdentifierExpr(name="P"),
                    arguments=(LiteralExpr(value="0"),),
                ),
            ),
        ],
        source_text={"C1": "Proof by induction; this is the base case."},
    )

    _resolved, higher = _higher(proof)
    structure = next(item for item in higher.structures if item.kind == ProofStructureKind.INDUCTION)

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.UNRESOLVED
    assert structure.opaque_source_addresses == ("C1",)


def test_wlog_is_asserted_but_not_validated_from_lexical_cue() -> None:
    proof = _proof(
        [
            _prop("T0", IdentifierExpr(name="R"), role=PropositionRole.GOAL),
            _prop("C1", IdentifierExpr(name="P")),
        ],
        source_text={"C1": "Without loss of generality, assume x <= y."},
    )

    _resolved, higher = _higher(proof)
    structure = next(item for item in higher.structures if item.kind == ProofStructureKind.WLOG)

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.UNRESOLVED
    assert structure.opaque_source_addresses == ("C1",)


def test_local_subproof_exposes_assumption_and_discharge_without_inventing_derivation() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    proof = _proof(
        [
            _prop("T0", _imp(p, q), role=PropositionRole.GOAL),
            _prop("C1", _imp(p, q)),
        ],
        source_text={"C1": "Assume P. Therefore Q."},
    )

    _resolved, higher = _higher(proof)
    structure = next(item for item in higher.structures if item.kind == ProofStructureKind.SUBPROOF)

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.AMBIGUOUS
    branch = higher.branch(structure.branch_addresses[0])
    assumption = ExpressionRef(owner_address="C1", path=("arguments", "0"))
    assert branch.assumption_refs == (assumption,)
    assert branch.discharged_assumption_refs == (assumption,)
    assert branch.status == InferenceStatus.AMBIGUOUS
    assert structure.opaque_source_addresses == ("C1",)


def test_structurally_recovered_witness_becomes_explicit_witness_branch() -> None:
    x = IdentifierExpr(name="x")
    evidence = ApplyExpr(
        function=IdentifierExpr(name="P"),
        arguments=(IdentifierExpr(name="a"),),
    )
    existential = QuantifiedExpr(
        quantifier=Quantifier.EXISTS,
        binder=Binder(name=x),
        body=ApplyExpr(function=IdentifierExpr(name="P"), arguments=(x,)),
    )
    proof = _proof(
        [
            _prop("T0", existential, role=PropositionRole.GOAL),
            _prop("C1", evidence),
            _prop("C2", existential),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("C1",),
                conclusion="C2",
                rule=ProofRuleKind.WITNESS_INTRODUCTION,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        source_text={"E1": "Take a as the witness."},
    )

    resolved, higher = _higher(proof)
    assert len(resolved.witnesses) == 1
    operation = resolved.witnesses[0]
    structure = next(
        item for item in higher.structures if item.kind == ProofStructureKind.WITNESS_BRANCH
    )

    assert structure.assertion_status == InferenceStatus.CONFIDENT
    assert structure.support_status == InferenceStatus.CONFIDENT
    assert structure.operation_addresses == (operation.address,)
    assert structure.witness_ref == ExpressionRef(
        owner_address="C1",
        path=("arguments", "0"),
    )
    branch = higher.branch(structure.branch_addresses[0])
    assert branch.kind == ProofBranchKind.WITNESS
    assert branch.witness_ref == structure.witness_ref
    assert branch.evidence_ref == ExpressionRef(owner_address="C1")


def test_higher_elaboration_does_not_mutate_symbol_resolution_ir() -> None:
    p = IdentifierExpr(name="P")
    q = IdentifierExpr(name="Q")
    proof = _proof(
        [
            _prop("T0", q, role=PropositionRole.GOAL),
            _prop("C1", _imp(p, q)),
        ],
        source_text={"C1": "Assume P. Therefore Q."},
    )
    resolved = elaborate_symbol_resolution(proof)
    before = resolved.model_dump(mode="json")

    higher = elaborate_higher_proof_structure(resolved)

    assert resolved.model_dump(mode="json") == before
    assert higher.resolved.model_dump(mode="json") == before
    assert higher.resolved is not resolved


def test_non_strategy_prose_does_not_create_control_structure() -> None:
    proof = _proof(
        [
            _prop("T0", IdentifierExpr(name="Q"), role=PropositionRole.GOAL),
            _prop("C1", IdentifierExpr(name="Q")),
        ],
        source_text={"C1": "The preceding estimate gives Q."},
    )

    _resolved, higher = _higher(proof)

    assert higher.structures == []
    assert higher.branches == []
