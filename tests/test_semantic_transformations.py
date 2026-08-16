from __future__ import annotations

from thorn.canonical_proof_ir import CanonicalNodeKind, CanonicalProofSource
from thorn.evidence import InferenceStatus
from thorn.formula_ir import (
    ApplyExpr,
    Binder,
    ExprLoweringStatus,
    IdentifierExpr,
    LogicalExpr,
    LogicalOperator,
    QuantifiedExpr,
    Quantifier,
    RelationExpr,
    RelationOperator,
)
from thorn.higher_proof_structure import elaborate_higher_proof_structure
from thorn.proof_obligations import (
    ObligationStatus,
    ProofObligation,
    ProofObligationIR,
    ProofProposition,
    ProofRuleKind,
    ProofStepEdge,
    PropositionRole,
)
from thorn.semantic_transformations import (
    SemanticSupportKind,
    SemanticTransformationKind,
    elaborate_semantic_transformations,
)
from thorn.symbol_resolution_ir import ExpressionRef, elaborate_symbol_resolution


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


def _proposition(
    address: str,
    expression,
    *,
    role: PropositionRole,
) -> ProofProposition:
    kind = {
        PropositionRole.ASSUMPTION: CanonicalNodeKind.HYPOTHESIS,
        PropositionRole.GOAL: CanonicalNodeKind.RESULT,
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
    contexts: dict[str, tuple[str, ...]] | None = None,
    source_text: dict[str, str] | None = None,
    referenced_results: dict[str, str] | None = None,
) -> ProofObligationIR:
    steps = steps or []
    contexts = contexts or {}
    source_text = source_text or {}
    referenced_results = referenced_results or {}

    addresses = [item.source_address for item in propositions]
    for step in steps:
        addresses.extend(
            address
            for address in step.source_addresses
            if address not in addresses
        )
    sources = [
        CanonicalProofSource(
            address=address,
            ir_identifier=f"ir:{address}",
            text=source_text.get(address, address),
            referenced_result_identifier=referenced_results.get(address),
        )
        for address in addresses
    ]
    obligations = [
        ProofObligation(
            address=f"O{index}",
            proposition_address=proposition_address,
            expected=next(
                item.expression
                for item in propositions
                if item.address == proposition_address
            ),
            expected_status=ExprLoweringStatus.FULL,
            local_context=context,
            source_address=proposition_address,
        )
        for index, (proposition_address, context) in enumerate(
            contexts.items(),
            start=1,
        )
    ]
    return ProofObligationIR(
        result_identifier="thm:current",
        propositions=propositions,
        obligations=obligations,
        steps=steps,
        sources=sources,
    )


def _semantic(proof: ProofObligationIR):
    resolved = elaborate_symbol_resolution(proof)
    higher = elaborate_higher_proof_structure(resolved)
    return resolved, higher, elaborate_semantic_transformations(higher)


def test_universal_result_application_records_binding_and_precondition() -> None:
    x = IdentifierExpr(name="x")
    a = IdentifierExpr(name="a")
    p_x = _app("P", x)
    q_x = _app("Q", x)
    p_a = _app("P", a)
    q_a = _app("Q", a)
    result = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x),
        body=_implies(p_x, q_x),
    )
    proof = _proof(
        [
            _proposition(
                "R1",
                result,
                role=PropositionRole.IMPORTED_RESULT,
            ),
            _proposition(
                "H1",
                p_a,
                role=PropositionRole.ASSUMPTION,
            ),
            _proposition(
                "C1",
                q_a,
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("R1",),
                conclusion="C1",
                rule=ProofRuleKind.APPLY_RESULT,
                status=InferenceStatus.CONFIDENT,
                canonical_edge_address="E1",
                source_addresses=("E1",),
            )
        ],
        contexts={"C1": ("R1", "H1")},
        source_text={"E1": "By Lemma 4."},
        referenced_results={
            "R1": "thm:lemma-4",
            "E1": "thm:lemma-4",
        },
    )

    _resolved, _higher, semantic = _semantic(proof)
    transformation = semantic.transformations[0]
    support = semantic.support_atom(transformation.support_atom_addresses[0])
    obligation = semantic.obligation(transformation.obligation_addresses[0])

    assert transformation.kind == SemanticTransformationKind.RESULT_APPLICATION
    assert transformation.status == InferenceStatus.CONFIDENT
    assert transformation.input_refs == (ExpressionRef(owner_address="H1"),)
    assert len(transformation.parameter_bindings) == 1
    assert transformation.parameter_bindings[0].parameter_ref == ExpressionRef(
        owner_address="R1",
        path=("binder", "name"),
    )
    assert transformation.parameter_bindings[0].argument_ref == ExpressionRef(
        owner_address="C1",
        path=("arguments", "0"),
    )
    assert obligation.expected == p_a
    assert obligation.status == ObligationStatus.DISCHARGED
    assert obligation.satisfied_by == ("H1",)
    assert support.kind == SemanticSupportKind.RESULT
    assert support.referenced_result_identifier == "thm:lemma-4"
    assert support.dependency_path == ("thm:current", "thm:lemma-4")


def test_missing_result_precondition_is_an_explicit_unresolved_obligation() -> None:
    x = IdentifierExpr(name="x")
    a = IdentifierExpr(name="a")
    result = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x),
        body=_implies(_app("P", x), _app("Q", x)),
    )
    proof = _proof(
        [
            _proposition(
                "R1",
                result,
                role=PropositionRole.IMPORTED_RESULT,
            ),
            _proposition(
                "C1",
                _app("Q", a),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("R1",),
                conclusion="C1",
                rule=ProofRuleKind.APPLY_RESULT,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        contexts={"C1": ("R1",)},
        source_text={"E1": "By Lemma 4."},
    )

    _resolved, _higher, semantic = _semantic(proof)
    transformation = semantic.transformations[0]
    obligation = semantic.obligation(transformation.obligation_addresses[0])

    assert obligation.expected == _app("P", a)
    assert obligation.satisfied_by == ()
    assert obligation.status == ObligationStatus.UNRESOLVED
    assert transformation.status == InferenceStatus.UNRESOLVED
    assert transformation.opaque_source_addresses


def test_universal_result_can_be_specialized_without_an_implication_precondition() -> None:
    x = IdentifierExpr(name="x")
    a = IdentifierExpr(name="a")
    proof = _proof(
        [
            _proposition(
                "R1",
                QuantifiedExpr(
                    quantifier=Quantifier.FOR_ALL,
                    binder=Binder(name=x),
                    body=_app("Q", x),
                ),
                role=PropositionRole.IMPORTED_RESULT,
            ),
            _proposition(
                "C1",
                _app("Q", a),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("R1",),
                conclusion="C1",
                rule=ProofRuleKind.APPLY_RESULT,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        contexts={"C1": ("R1",)},
    )

    _resolved, _higher, semantic = _semantic(proof)
    transformation = semantic.transformations[0]

    assert transformation.kind == SemanticTransformationKind.RESULT_SPECIALIZATION
    assert transformation.status == InferenceStatus.CONFIDENT
    assert transformation.obligation_addresses == ()
    assert transformation.parameter_bindings[0].argument_ref == ExpressionRef(
        owner_address="C1",
        path=("arguments", "0"),
    )


def test_result_reference_does_not_validate_a_mismatched_application() -> None:
    proof = _proof(
        [
            _proposition(
                "R1",
                _implies(
                    IdentifierExpr(name="P"),
                    IdentifierExpr(name="Q"),
                ),
                role=PropositionRole.IMPORTED_RESULT,
            ),
            _proposition(
                "C1",
                IdentifierExpr(name="R"),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("R1",),
                conclusion="C1",
                rule=ProofRuleKind.APPLY_RESULT,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        contexts={"C1": ("R1",)},
        source_text={"E1": "By Lemma 4, the claim follows."},
    )

    _resolved, _higher, semantic = _semantic(proof)
    transformation = semantic.transformations[0]

    assert transformation.kind == SemanticTransformationKind.RESULT_APPLICATION
    assert transformation.status == InferenceStatus.UNRESOLVED
    assert transformation.parameter_bindings == ()
    assert transformation.obligation_addresses == ()


def test_exact_equality_rewrite_reuses_issue_62_substitution_semantics() -> None:
    x = IdentifierExpr(name="x")
    y = IdentifierExpr(name="y")
    proof = _proof(
        [
            _proposition(
                "H1",
                RelationExpr(
                    operator=RelationOperator.EQUAL,
                    left=x,
                    right=y,
                ),
                role=PropositionRole.ASSUMPTION,
            ),
            _proposition(
                "C1",
                _app("P", x),
                role=PropositionRole.DERIVED,
            ),
            _proposition(
                "C2",
                _app("P", y),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("H1", "C1"),
                conclusion="C2",
                rule=ProofRuleKind.REWRITE_SUBSTITUTION,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        source_text={"E1": "Rewrite using H1."},
    )

    resolved, _higher, semantic = _semantic(proof)
    assert len(resolved.substitutions) == 1
    transformation = next(
        item
        for item in semantic.transformations
        if item.kind == SemanticTransformationKind.EQUALITY_REWRITE
    )
    support = semantic.support_atom(transformation.support_atom_addresses[0])

    assert transformation.status == InferenceStatus.CONFIDENT
    assert transformation.lower_operation_address == resolved.substitutions[0].address
    assert transformation.input_refs == (ExpressionRef(owner_address="C1"),)
    assert transformation.rewrite_from_ref == ExpressionRef(
        owner_address="H1",
        path=("left",),
    )
    assert transformation.rewrite_to_ref == ExpressionRef(
        owner_address="H1",
        path=("right",),
    )
    assert transformation.replacement_sites == (
        ExpressionRef(owner_address="C2", path=("arguments", "0")),
    )
    assert support.kind == SemanticSupportKind.EQUALITY
    assert support.proposition_address == "H1"


def test_rewrite_wording_without_exact_equality_transform_remains_unresolved() -> None:
    proof = _proof(
        [
            _proposition(
                "C1",
                IdentifierExpr(name="P"),
                role=PropositionRole.DERIVED,
            ),
            _proposition(
                "C2",
                IdentifierExpr(name="Q"),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("C1",),
                conclusion="C2",
                rule=ProofRuleKind.REWRITE_SUBSTITUTION,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        source_text={"E1": "Rewriting gives Q."},
    )

    resolved, _higher, semantic = _semantic(proof)
    assert resolved.substitutions[0].status == InferenceStatus.UNRESOLVED
    transformation = semantic.transformations[0]

    assert transformation.kind == SemanticTransformationKind.EQUALITY_REWRITE
    assert transformation.status == InferenceStatus.UNRESOLVED
    assert transformation.rewrite_from_ref is None
    assert transformation.rewrite_to_ref is None
    assert transformation.opaque_source_addresses


def test_definition_unfolding_requires_an_exact_context_replacement() -> None:
    f = IdentifierExpr(name="f")
    a = IdentifierExpr(name="a")
    proof = _proof(
        [
            _proposition(
                "D1",
                RelationExpr(
                    operator=RelationOperator.EQUAL,
                    left=f,
                    right=a,
                ),
                role=PropositionRole.DEFINITION,
            ),
            _proposition(
                "C1",
                _app("P", f),
                role=PropositionRole.DERIVED,
            ),
            _proposition(
                "C2",
                _app("P", a),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("D1",),
                conclusion="C2",
                rule=ProofRuleKind.DEFINITION_USE,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        contexts={"C2": ("D1", "C1")},
        source_text={"E1": "By the definition of f."},
    )

    _resolved, _higher, semantic = _semantic(proof)
    transformation = semantic.transformations[0]
    support = semantic.support_atom(transformation.support_atom_addresses[0])

    assert transformation.kind == SemanticTransformationKind.DEFINITION_UNFOLD
    assert transformation.status == InferenceStatus.CONFIDENT
    assert transformation.input_refs == (ExpressionRef(owner_address="C1"),)
    assert transformation.rewrite_from_ref == ExpressionRef(
        owner_address="D1",
        path=("left",),
    )
    assert transformation.rewrite_to_ref == ExpressionRef(
        owner_address="D1",
        path=("right",),
    )
    assert transformation.replacement_sites == (
        ExpressionRef(owner_address="C2", path=("arguments", "0")),
    )
    assert support.kind == SemanticSupportKind.DEFINITION
    assert support.proposition_address == "D1"


def test_definition_reference_without_exact_unfolding_is_only_a_use() -> None:
    proof = _proof(
        [
            _proposition(
                "D1",
                RelationExpr(
                    operator=RelationOperator.EQUAL,
                    left=IdentifierExpr(name="f"),
                    right=IdentifierExpr(name="a"),
                ),
                role=PropositionRole.DEFINITION,
            ),
            _proposition(
                "C1",
                IdentifierExpr(name="R"),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("D1",),
                conclusion="C1",
                rule=ProofRuleKind.DEFINITION_USE,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        contexts={"C1": ("D1",)},
    )

    _resolved, _higher, semantic = _semantic(proof)
    transformation = semantic.transformations[0]

    assert transformation.kind == SemanticTransformationKind.DEFINITION_USE
    assert transformation.status == InferenceStatus.UNRESOLVED
    assert transformation.opaque_source_addresses


def test_named_property_is_typed_support_but_not_a_validated_transformation() -> None:
    proof = _proof(
        [
            _proposition(
                "H1",
                IdentifierExpr(name="continuous_f"),
                role=PropositionRole.ASSUMPTION,
            ),
            _proposition(
                "C1",
                IdentifierExpr(name="Q"),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("H1",),
                conclusion="C1",
                rule=ProofRuleKind.NAMED_PROPERTY_APPLICATION,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        source_text={"E1": "By continuity of f, Q follows."},
    )

    _resolved, _higher, semantic = _semantic(proof)
    transformation = semantic.transformations[0]
    support = semantic.support_atom(transformation.support_atom_addresses[0])

    assert support.kind == SemanticSupportKind.NAMED_PROPERTY
    assert support.name == "By continuity of f, Q follows."
    assert support.status == InferenceStatus.CONFIDENT
    assert transformation.kind == SemanticTransformationKind.NAMED_PROPERTY_APPLICATION
    assert transformation.status == InferenceStatus.UNRESOLVED
    assert transformation.opaque_source_addresses


def test_elaboration_does_not_mutate_the_higher_or_resolution_layers() -> None:
    proof = _proof(
        [
            _proposition(
                "R1",
                IdentifierExpr(name="Q"),
                role=PropositionRole.IMPORTED_RESULT,
            ),
            _proposition(
                "C1",
                IdentifierExpr(name="Q"),
                role=PropositionRole.DERIVED,
            ),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("R1",),
                conclusion="C1",
                rule=ProofRuleKind.APPLY_RESULT,
                status=InferenceStatus.CONFIDENT,
                source_addresses=("E1",),
            )
        ],
        contexts={"C1": ("R1",)},
    )
    resolved = elaborate_symbol_resolution(proof)
    higher = elaborate_higher_proof_structure(resolved)
    before = higher.model_dump(mode="json")

    semantic = elaborate_semantic_transformations(higher)

    assert higher.model_dump(mode="json") == before
    assert semantic.higher.model_dump(mode="json") == before
    assert semantic.transformations[0].status == InferenceStatus.CONFIDENT
