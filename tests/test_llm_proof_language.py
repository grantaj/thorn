from __future__ import annotations

import pytest

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
)
from thorn.frontend import SourceSpan
from thorn.higher_proof_structure import (
    HigherProofIR,
    ProofBranch,
    ProofBranchKind,
    ProofControlStructure,
    ProofStructureKind,
)
from thorn.llm_proof_language import (
    ProofLanguageStyle,
    parse_source_rescue_request,
    project_llm_proof_language,
    proof_language_inventory,
    render_llm_proof_language,
    render_source_rescue,
)
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
    SemanticApplicationObligation,
    SemanticParameterBinding,
    SemanticSupportAtom,
    SemanticSupportKind,
    SemanticTransformation,
    SemanticTransformationIR,
    SemanticTransformationKind,
)
from thorn.symbol_resolution_ir import ExpressionRef, SymbolResolutionIR


def _span(line: int) -> SourceSpan:
    return SourceSpan(
        file="paper.tex",
        start_offset=(line - 1) * 20,
        end_offset=(line - 1) * 20 + 10,
        start_line=line,
        start_column=1,
        end_line=line,
        end_column=11,
    )


def _source(address: str, text: str, line: int) -> CanonicalProofSource:
    return CanonicalProofSource(
        address=address,
        ir_identifier=f"ir:{address}",
        text=text,
        source_span=_span(line),
    )


def _proposition(
    address: str,
    role: PropositionRole,
    expression: object,
    node_kind: CanonicalNodeKind,
) -> ProofProposition:
    return ProofProposition(
        address=address,
        role=role,
        node_kind=node_kind,
        expression=expression,
        expression_status=ExprLoweringStatus.FULL,
        source_address=address,
    )


def _application_ir(*, unresolved: bool = False) -> SemanticTransformationIR:
    x = IdentifierExpr(name="x")
    a = IdentifierExpr(name="a")
    p_x = ApplyExpr(function=IdentifierExpr(name="P"), arguments=(x,))
    q_x = ApplyExpr(function=IdentifierExpr(name="Q"), arguments=(x,))
    p_a = ApplyExpr(function=IdentifierExpr(name="P"), arguments=(a,))
    q_a = ApplyExpr(function=IdentifierExpr(name="Q"), arguments=(a,))
    result = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x),
        body=LogicalExpr(
            operator=LogicalOperator.IMPLIES,
            arguments=(p_x, q_x),
        ),
    )

    propositions = [
        _proposition("T0", PropositionRole.GOAL, q_a, CanonicalNodeKind.RESULT),
        _proposition(
            "R1",
            PropositionRole.IMPORTED_RESULT,
            result,
            CanonicalNodeKind.DEPENDENCY,
        ),
        _proposition("H1", PropositionRole.ASSUMPTION, p_a, CanonicalNodeKind.HYPOTHESIS),
        _proposition("C1", PropositionRole.DERIVED, q_a, CanonicalNodeKind.CLAIM),
    ]
    steps = [
        ProofStepEdge(
            address="E1",
            premises=("R1",),
            conclusion="C1",
            rule=ProofRuleKind.APPLY_RESULT,
            status=(
                InferenceStatus.UNRESOLVED if unresolved else InferenceStatus.CONFIDENT
            ),
            source_addresses=("E1",),
        )
    ]
    obligations = [
        ProofObligation(
            address="G1",
            proposition_address="C1",
            expected=q_a,
            expected_status=ExprLoweringStatus.FULL,
            local_context=("R1", "H1"),
            status=(
                ObligationStatus.UNRESOLVED
                if unresolved
                else ObligationStatus.DISCHARGED
            ),
            discharging_steps=(() if unresolved else ("E1",)),
            source_address="C1",
        ),
        ProofObligation(
            address="G0",
            proposition_address="T0",
            expected=q_a,
            expected_status=ExprLoweringStatus.FULL,
            local_context=("C1",),
            status=ObligationStatus.UNRESOLVED,
            source_address="T0",
            terminal=True,
        ),
    ]
    proof = ProofObligationIR(
        result_identifier="thm:test",
        propositions=propositions,
        obligations=obligations,
        steps=steps,
        sources=[
            _source("T0", "The theorem claims Q(a).", 1),
            _source("R1", "Lemma 4: for all x, P(x) implies Q(x).", 2),
            _source("H1", "Assume P(a).", 3),
            _source("C1", "Therefore Q(a).", 4),
            _source("E1", "By Lemma 4, Q(a).", 5),
        ],
    )
    resolved = SymbolResolutionIR(result_identifier="thm:test", proof=proof)
    higher = HigherProofIR(result_identifier="thm:test", resolved=resolved)
    support = SemanticSupportAtom(
        address="K1",
        kind=SemanticSupportKind.RESULT,
        step_address="E1",
        proposition_address="R1",
        expression_ref=ExpressionRef(owner_address="R1"),
        referenced_result_identifier="thm:lemma",
        dependency_path=("thm:test", "thm:lemma"),
        status=InferenceStatus.CONFIDENT,
        source_addresses=("E1", "R1"),
    )
    precondition = SemanticApplicationObligation(
        address="O1",
        transformation_address="M1",
        template_ref=ExpressionRef(
            owner_address="R1",
            path=("body", "arguments", "0"),
        ),
        expected=p_a,
        local_context=("R1", "H1"),
        satisfied_by=(() if unresolved else ("H1",)),
        status=(
            ObligationStatus.UNRESOLVED
            if unresolved
            else ObligationStatus.DISCHARGED
        ),
        source_addresses=("E1",),
    )
    transformation = SemanticTransformation(
        address="M1",
        kind=SemanticTransformationKind.RESULT_APPLICATION,
        step_addresses=("E1",),
        support_atom_addresses=("K1",),
        input_refs=(() if unresolved else (ExpressionRef(owner_address="H1"),)),
        target_ref=ExpressionRef(owner_address="C1"),
        parameter_bindings=(
            SemanticParameterBinding(
                parameter_ref=ExpressionRef(
                    owner_address="R1",
                    path=("binder", "name"),
                ),
                argument_ref=ExpressionRef(
                    owner_address="C1",
                    path=("arguments", "0"),
                ),
                status=InferenceStatus.CONFIDENT,
            ),
        ),
        obligation_addresses=("O1",),
        status=(
            InferenceStatus.UNRESOLVED if unresolved else InferenceStatus.CONFIDENT
        ),
        source_addresses=("E1", "R1", "C1"),
        opaque_source_addresses=(("E1",) if unresolved else ()),
    )
    return SemanticTransformationIR(
        result_identifier="thm:test",
        higher=higher,
        support_atoms=[support],
        transformations=[transformation],
        obligations=[precondition],
    )


def test_compact_language_exposes_result_application_goal_and_dependency() -> None:
    ir = _application_ir()

    rendered = render_llm_proof_language(ir)

    assert rendered.startswith("THORN-PROOF 1\n")
    assert "R1 ∀x.(P(x)⇒Q(x))" in rendered
    assert "H1 P(a)" in rendered
    assert "C1 Q(a) <- R1[x:=a],H1" in rendered
    assert "DEP R1 thm:test>thm:lemma" in rendered
    assert "GOAL G0 T0: Q(a) | ctx C1 | open @T0" in rendered
    assert "By Lemma 4" not in rendered


def test_unresolved_application_is_a_hole_with_source_and_precondition() -> None:
    ir = _application_ir(unresolved=True)

    rendered = render_llm_proof_language(ir)

    assert "C1 Q(a) <- R1[x:=a],?O1:P(a) ? @E1" in rendered
    assert "HOLE G1 C1: Q(a) | ctx R1,H1 | open @C1" in rendered
    assert "NEED O1: P(a) | ctx R1,H1 @E1" in rendered


def test_source_rescue_is_batched_exact_and_bound_to_fingerprint() -> None:
    document = project_llm_proof_language(_application_ir(unresolved=True))

    request = parse_source_rescue_request(
        document,
        "NEED_SOURCE E1, R1, E1",
    )
    response = render_source_rescue(document, request)

    assert request.addresses == ("E1", "R1")
    assert request.document_fingerprint == document.fingerprint()
    assert response.addresses == ("E1", "R1")
    assert "SOURCE @E1\nBy Lemma 4, Q(a).\nEND_SOURCE @E1" in response.text
    assert "SOURCE @R1\nRESULT_ID thm:lemma" not in response.text
    assert "Lemma 4: for all x, P(x) implies Q(x)." in response.text


def test_source_rescue_rejects_unknown_unbounded_and_second_round() -> None:
    document = project_llm_proof_language(_application_ir(unresolved=True))

    with pytest.raises(KeyError):
        parse_source_rescue_request(document, "NEED_SOURCE Z99")
    with pytest.raises(ValueError, match="at most 1"):
        parse_source_rescue_request(document, "NEED_SOURCE E1,R1", max_addresses=1)
    with pytest.raises(ValueError, match="exactly one"):
        parse_source_rescue_request(document, "NEED_SOURCE E1", round_number=2)
    with pytest.raises(ValueError, match="expected NEED_SOURCE"):
        parse_source_rescue_request(document, "SOURCE E1")


def test_source_rescue_rejects_request_for_another_packet() -> None:
    document = project_llm_proof_language(_application_ir(unresolved=True))
    request = parse_source_rescue_request(document, "NEED_SOURCE E1")
    changed = document.model_copy(update={"lines": (*document.lines, "EXTRA")})

    with pytest.raises(ValueError, match="does not match"):
        render_source_rescue(changed, request)


def test_fingerprint_and_projection_are_deterministic() -> None:
    ir = _application_ir()

    first = project_llm_proof_language(ir)
    second = project_llm_proof_language(ir.model_copy(deep=True))

    assert first.render_initial() == second.render_initial()
    assert first.fingerprint() == second.fingerprint()
    assert first.canonical_json() == second.canonical_json()


def test_compact_and_explicit_candidates_share_semantic_inventory() -> None:
    ir = _application_ir(unresolved=True)

    compact = render_llm_proof_language(ir, style=ProofLanguageStyle.COMPACT)
    explicit = render_llm_proof_language(ir, style=ProofLanguageStyle.EXPLICIT)
    inventory = proof_language_inventory(ir)

    assert len(compact) < len(explicit)
    assert "C1" in compact and "C1" in explicit
    assert "O1" in compact and "O1" in explicit
    assert inventory["transformations"] == 1
    assert inventory["open_application_obligations"] == 1
    assert inventory["source_handles"] == 5


def test_control_structure_is_delaborated_without_source_prose() -> None:
    ir = _application_ir()
    branch = ProofBranch(
        address="S1:cases:B1",
        kind=ProofBranchKind.CASE,
        parent_structure_address="S1:cases",
        local_assumptions=("H1",),
        conclusion_address="C1",
        status=InferenceStatus.CONFIDENT,
        source_addresses=("C1",),
    )
    structure = ProofControlStructure(
        address="S1:cases",
        kind=ProofStructureKind.CASE_SPLIT,
        assertion_status=InferenceStatus.CONFIDENT,
        support_status=InferenceStatus.CONFIDENT,
        branch_addresses=(branch.address,),
        premise_addresses=("H1",),
        conclusion_address="C1",
        source_addresses=("E1",),
    )
    higher = ir.higher.model_copy(
        update={"structures": [structure], "branches": [branch]}
    )
    structured = ir.model_copy(update={"higher": higher})

    rendered = render_llm_proof_language(structured)

    assert "FLOW F1 CASES -> C1 from H1 {case[H1]=>C1}" in rendered
    assert "By Lemma 4" not in rendered


def test_lower_semantic_ir_is_not_mutated_by_projection() -> None:
    ir = _application_ir(unresolved=True)
    before = ir.model_dump(mode="json")

    project_llm_proof_language(ir)
    render_llm_proof_language(ir, style=ProofLanguageStyle.EXPLICIT)

    assert ir.model_dump(mode="json") == before
