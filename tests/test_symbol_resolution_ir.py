from __future__ import annotations

from thorn.canonical_proof_ir import CanonicalNodeKind, CanonicalProofSource
from thorn.dependencies import DependencyNode
from thorn.evidence import InferenceStatus
from thorn.formula_ir import (
    ApplyExpr,
    Binder,
    ExprLoweringStatus,
    IdentifierExpr,
    LogicalExpr,
    LogicalOperator,
    OperatorExpr,
    QuantifiedExpr,
    Quantifier,
    RelationExpr,
    RelationOperator,
    TupleExpr,
)
from thorn.frontend import SourceSpan
from thorn.models import SourceRange, TheoremUnit
from thorn.proof_obligations import (
    ProofObligationIR,
    ProofProposition,
    ProofRuleKind,
    ProofStepEdge,
    PropositionRole,
)
from thorn.semantic_review import ReviewTargetKind, SemanticReviewItem
from thorn.semantic_review_render import SemanticReviewRequest
from thorn.symbol_resolution_ir import (
    DeclarationKind,
    ExpressionRef,
    ResolutionStatus,
    ScopeOrigin,
    alpha_equivalent,
    alpha_normalize_math_expr,
    build_symbol_resolution_ir,
    elaborate_symbol_resolution,
)
from thorn.symbols import (
    IntroductionKind,
    Scope,
    ScopeKind,
    Symbol,
    SymbolRole,
    SymbolUse,
)


def _span(start: int, end: int) -> SourceSpan:
    return SourceSpan(
        file="paper.tex",
        start_offset=start,
        end_offset=end,
        start_line=1,
        start_column=start + 1,
        end_line=1,
        end_column=end + 1,
    )


def _proposition(
    address: str,
    expression,
    *,
    role: PropositionRole = PropositionRole.DERIVED,
    kind: CanonicalNodeKind = CanonicalNodeKind.CLAIM,
) -> ProofProposition:
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
) -> ProofObligationIR:
    sources = [
        CanonicalProofSource(
            address=item.address,
            ir_identifier=f"ir:{item.address}",
            text=item.address,
            source_span=_span(index * 20, index * 20 + 15),
        )
        for index, item in enumerate(propositions)
    ]
    return ProofObligationIR(
        result_identifier="thm:test",
        propositions=propositions,
        steps=steps or [],
        sources=sources,
    )


def test_quantifier_binder_has_identity_scope_domain_and_bound_reference() -> None:
    x = IdentifierExpr(name="x")
    expression = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x, domain=IdentifierExpr(name="R")),
        body=ApplyExpr(function=IdentifierExpr(name="P"), arguments=(x,)),
    )
    proof = _proof([_proposition("C1", expression)])

    resolved = elaborate_symbol_resolution(proof)

    binder = next(item for item in resolved.declarations if item.kind == DeclarationKind.BINDER)
    assert binder.name == "x"
    assert binder.domain_ref == ExpressionRef(
        owner_address="C1",
        path=("binder", "domain"),
    )
    assert resolved.expression(binder.domain_ref) == IdentifierExpr(name="R")

    bound = resolved.reference(ExpressionRef(owner_address="C1", path=("body", "arguments", "0")))
    assert bound.status == ResolutionStatus.BOUND
    assert bound.declaration_addresses == (binder.address,)
    binder_scope = next(item for item in resolved.scopes if item.address == binder.scope_address)
    assert binder_scope.origin == ScopeOrigin.BINDER
    assert binder_scope.parent_status == InferenceStatus.CONFIDENT

    assert (
        resolved.reference(ExpressionRef(owner_address="C1", path=("binder", "domain"))).status
        == ResolutionStatus.UNRESOLVED
    )
    assert (
        resolved.reference(ExpressionRef(owner_address="C1", path=("body", "function"))).status
        == ResolutionStatus.UNRESOLVED
    )


def test_nested_shadowing_resolves_to_nearest_binder_not_same_spelling() -> None:
    expression = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=IdentifierExpr(name="x")),
        body=TupleExpr(
            items=(
                IdentifierExpr(name="x"),
                QuantifiedExpr(
                    quantifier=Quantifier.EXISTS,
                    binder=Binder(name=IdentifierExpr(name="x")),
                    body=IdentifierExpr(name="x"),
                ),
            )
        ),
    )
    resolved = elaborate_symbol_resolution(_proof([_proposition("C1", expression)]))
    binders = [item for item in resolved.declarations if item.kind == DeclarationKind.BINDER]
    assert len(binders) == 2

    outer_ref = resolved.reference(ExpressionRef(owner_address="C1", path=("body", "items", "0")))
    inner_ref = resolved.reference(
        ExpressionRef(
            owner_address="C1",
            path=("body", "items", "1", "body"),
        )
    )
    assert outer_ref.declaration_addresses != inner_ref.declaration_addresses
    assert resolved.declaration(outer_ref.declaration_addresses[0]).name == "x"
    assert resolved.declaration(inner_ref.declaration_addresses[0]).name == "x"


def test_same_spelling_source_declarations_remain_ambiguous_without_use_evidence() -> None:
    proof = _proof([_proposition("C1", IdentifierExpr(name="x"))])
    symbols = [
        Symbol(
            identifier="symbol:x:outer",
            name="x",
            role=SymbolRole.SCALAR,
            introduction_kind=IntroductionKind.LET,
            scope_identifier="scope:outer",
            result_identifier="thm:test",
            source=_span(100, 101),
            introduction_source=_span(90, 101),
            raw_introduction="let x",
        ),
        Symbol(
            identifier="symbol:x:inner",
            name="x",
            role=SymbolRole.SCALAR,
            introduction_kind=IntroductionKind.LET,
            scope_identifier="scope:inner",
            result_identifier="thm:test",
            source=_span(120, 121),
            introduction_source=_span(110, 121),
            raw_introduction="let x",
        ),
    ]

    resolved = elaborate_symbol_resolution(proof, symbols=symbols)
    reference = resolved.reference(ExpressionRef(owner_address="C1"))

    assert reference.status == ResolutionStatus.AMBIGUOUS
    assert len(reference.declaration_addresses) == 2
    assert {
        resolved.declaration(address).source_symbol_identifier
        for address in reference.declaration_addresses
    } == {
        "symbol:x:outer",
        "symbol:x:inner",
    }


def test_exact_source_use_resolves_identity_and_preserves_type_and_scope() -> None:
    proof = _proof([_proposition("C1", IdentifierExpr(name="x"))])
    symbol = Symbol(
        identifier="symbol:x",
        name="x",
        role=SymbolRole.SCALAR,
        domain_latex=r"\mathbb{R}",
        introduction_kind=IntroductionKind.LET,
        scope_identifier="scope:proof",
        result_identifier="thm:test",
        source=_span(1, 2),
        introduction_source=_span(0, 2),
        raw_introduction="let x be real",
    )
    use = SymbolUse(
        name="x",
        scope_identifier="scope:proof",
        source=_span(1, 2),
        raw="x",
        resolved_symbol_identifier="symbol:x",
    )
    scopes = [
        Scope(
            identifier="scope:result",
            kind=ScopeKind.RESULT,
            result_identifier="thm:test",
            source=_span(0, 15),
        ),
        Scope(
            identifier="scope:proof",
            kind=ScopeKind.PROOF,
            parent_identifier="scope:result",
            result_identifier="thm:test",
            source=_span(0, 15),
        ),
    ]

    resolved = elaborate_symbol_resolution(
        proof,
        symbols=[symbol],
        symbol_uses=[use],
        scopes=scopes,
    )
    reference = resolved.reference(ExpressionRef(owner_address="C1"))

    assert reference.status == ResolutionStatus.RESOLVED
    declaration = resolved.declaration(reference.declaration_addresses[0])
    assert declaration.source_symbol_identifier == "symbol:x"
    assert declaration.role == SymbolRole.SCALAR
    assert declaration.domain_latex == r"\mathbb{R}"
    proof_scope = next(
        item for item in resolved.scopes if item.source_scope_identifier == "scope:proof"
    )
    result_scope = next(
        item for item in resolved.scopes if item.source_scope_identifier == "scope:result"
    )
    assert proof_scope.parent_address == result_scope.address
    assert proof_scope.parent_status == InferenceStatus.CONFIDENT
    assert resolved.source_scope_complete is True


def test_unresolved_source_use_does_not_fall_back_to_lexical_guess() -> None:
    proof = _proof([_proposition("C1", IdentifierExpr(name="x"))])
    symbol = Symbol(
        identifier="symbol:x",
        name="x",
        introduction_kind=IntroductionKind.LET,
        scope_identifier="scope:proof",
        result_identifier="thm:test",
        source=_span(1, 2),
        introduction_source=_span(0, 2),
        raw_introduction="let x",
    )
    use = SymbolUse(
        name="x",
        scope_identifier="scope:proof",
        source=_span(1, 2),
        raw="x",
        resolved_symbol_identifier=None,
    )

    resolved = elaborate_symbol_resolution(proof, symbols=[symbol], symbol_uses=[use])

    assert (
        resolved.reference(ExpressionRef(owner_address="C1")).status == ResolutionStatus.UNRESOLVED
    )


def test_alpha_normalization_is_invariant_to_bound_renaming_but_not_free_renaming() -> None:
    left = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=IdentifierExpr(name="x"), domain=IdentifierExpr(name="R")),
        body=ApplyExpr(
            function=IdentifierExpr(name="P"),
            arguments=(IdentifierExpr(name="x"), IdentifierExpr(name="z")),
        ),
    )
    renamed = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=IdentifierExpr(name="y"), domain=IdentifierExpr(name="R")),
        body=ApplyExpr(
            function=IdentifierExpr(name="P"),
            arguments=(IdentifierExpr(name="y"), IdentifierExpr(name="z")),
        ),
    )
    free_renamed = renamed.model_copy(
        update={
            "body": ApplyExpr(
                function=IdentifierExpr(name="P"),
                arguments=(IdentifierExpr(name="y"), IdentifierExpr(name="w")),
            )
        }
    )

    assert alpha_equivalent(left, renamed)
    assert not alpha_equivalent(left, free_renamed)
    assert alpha_normalize_math_expr(left) == alpha_normalize_math_expr(renamed)


def test_alpha_normalization_handles_shadowing_structurally() -> None:
    left = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=IdentifierExpr(name="x")),
        body=QuantifiedExpr(
            quantifier=Quantifier.EXISTS,
            binder=Binder(name=IdentifierExpr(name="x")),
            body=ApplyExpr(
                function=IdentifierExpr(name="P"),
                arguments=(IdentifierExpr(name="x"),),
            ),
        ),
    )
    right = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=IdentifierExpr(name="y")),
        body=QuantifiedExpr(
            quantifier=Quantifier.EXISTS,
            binder=Binder(name=IdentifierExpr(name="z")),
            body=ApplyExpr(
                function=IdentifierExpr(name="P"),
                arguments=(IdentifierExpr(name="z"),),
            ),
        ),
    )

    assert alpha_equivalent(left, right)


def test_universal_instantiation_references_parameter_argument_and_conclusion_ast() -> None:
    x = IdentifierExpr(name="x")
    theorem = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=x),
        body=ApplyExpr(function=IdentifierExpr(name="P"), arguments=(x,)),
    )
    conclusion = ApplyExpr(
        function=IdentifierExpr(name="P"),
        arguments=(IdentifierExpr(name="a"),),
    )
    proof = _proof(
        [
            _proposition(
                "R1",
                theorem,
                role=PropositionRole.IMPORTED_RESULT,
                kind=CanonicalNodeKind.DEPENDENCY,
            ),
            _proposition("C1", conclusion),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("R1",),
                conclusion="C1",
                rule=ProofRuleKind.APPLY_RESULT,
                status=InferenceStatus.CONFIDENT,
            )
        ],
    )

    resolved = elaborate_symbol_resolution(proof)

    assert len(resolved.instantiations) == 1
    operation = resolved.instantiations[0]
    assert operation.status == InferenceStatus.CONFIDENT
    assert operation.quantified_ref == ExpressionRef(owner_address="R1")
    assert operation.parameter_ref == ExpressionRef(owner_address="R1", path=("binder", "name"))
    assert operation.argument_ref == ExpressionRef(owner_address="C1", path=("arguments", "0"))
    assert resolved.expression(operation.argument_ref) == IdentifierExpr(name="a")


def test_explicit_instantiation_remains_unresolved_when_structure_does_not_match() -> None:
    theorem = QuantifiedExpr(
        quantifier=Quantifier.FOR_ALL,
        binder=Binder(name=IdentifierExpr(name="x")),
        body=IdentifierExpr(name="P"),
    )
    proof = _proof(
        [_proposition("C1", theorem), _proposition("C2", IdentifierExpr(name="Q"))],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("C1",),
                conclusion="C2",
                rule=ProofRuleKind.INSTANTIATE,
                status=InferenceStatus.CONFIDENT,
            )
        ],
    )

    resolved = elaborate_symbol_resolution(proof)

    assert len(resolved.instantiations) == 1
    assert resolved.instantiations[0].status == InferenceStatus.UNRESOLVED
    assert resolved.instantiations[0].argument_ref is None


def test_existential_witness_is_recovered_from_exact_instance() -> None:
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
        [_proposition("C1", evidence), _proposition("C2", existential)],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("C1",),
                conclusion="C2",
                rule=ProofRuleKind.UNKNOWN,
                status=InferenceStatus.CONFIDENT,
            )
        ],
    )

    resolved = elaborate_symbol_resolution(proof)

    assert len(resolved.witnesses) == 1
    witness = resolved.witnesses[0]
    assert witness.status == InferenceStatus.CONFIDENT
    assert witness.witness_ref == ExpressionRef(owner_address="C1", path=("arguments", "0"))
    assert resolved.expression(witness.witness_ref) == IdentifierExpr(name="a")


def test_rewrite_substitution_requires_exact_equality_and_two_premises() -> None:
    equality = RelationExpr(
        operator=RelationOperator.EQUAL,
        left=IdentifierExpr(name="x"),
        right=IdentifierExpr(name="a"),
    )
    input_expression = ApplyExpr(
        function=IdentifierExpr(name="P"),
        arguments=(IdentifierExpr(name="x"),),
    )
    output_expression = ApplyExpr(
        function=IdentifierExpr(name="P"),
        arguments=(IdentifierExpr(name="a"),),
    )
    proof = _proof(
        [
            _proposition(
                "H1",
                equality,
                role=PropositionRole.ASSUMPTION,
                kind=CanonicalNodeKind.HYPOTHESIS,
            ),
            _proposition("C1", input_expression),
            _proposition("C2", output_expression),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("H1", "C1"),
                conclusion="C2",
                rule=ProofRuleKind.REWRITE_SUBSTITUTION,
                status=InferenceStatus.CONFIDENT,
            )
        ],
    )

    resolved = elaborate_symbol_resolution(proof)

    assert len(resolved.substitutions) == 1
    operation = resolved.substitutions[0]
    assert operation.status == InferenceStatus.CONFIDENT
    assert operation.equality_ref == ExpressionRef(owner_address="H1")
    assert operation.from_ref == ExpressionRef(owner_address="H1", path=("left",))
    assert operation.to_ref == ExpressionRef(owner_address="H1", path=("right",))
    assert operation.input_ref == ExpressionRef(owner_address="C1")
    assert operation.output_ref == ExpressionRef(owner_address="C2")
    assert operation.replacement_sites == (
        ExpressionRef(owner_address="C2", path=("arguments", "0")),
    )


def test_rewrite_wording_without_structural_premises_stays_unresolved() -> None:
    proof = _proof(
        [
            _proposition("C1", IdentifierExpr(name="P")),
            _proposition("C2", IdentifierExpr(name="Q")),
        ],
        steps=[
            ProofStepEdge(
                address="E1",
                premises=("C1",),
                conclusion="C2",
                rule=ProofRuleKind.REWRITE_SUBSTITUTION,
                status=InferenceStatus.CONFIDENT,
            )
        ],
    )

    operation = elaborate_symbol_resolution(proof).substitutions[0]

    assert operation.status == InferenceStatus.UNRESOLVED
    assert operation.equality_ref is None
    assert operation.from_ref is None
    assert operation.to_ref is None


def test_resolution_layer_does_not_mutate_proof_ir() -> None:
    expression = LogicalExpr(
        operator=LogicalOperator.IMPLIES,
        arguments=(IdentifierExpr(name="P"), IdentifierExpr(name="Q")),
    )
    proof = _proof([_proposition("C1", expression)])
    before = proof.model_dump(mode="json")

    resolved = elaborate_symbol_resolution(proof)

    assert proof.model_dump(mode="json") == before
    assert resolved.proof.model_dump(mode="json") == before
    assert resolved.proof is not proof


def test_build_path_consumes_existing_typed_obligation_pipeline() -> None:
    unit = TheoremUnit(
        identifier="thm:test",
        environment="theorem",
        statement=r"For all x in \mathbb{R}, P(x).",
        proof=None,
        statement_range=SourceRange(file="paper.tex", start_line=1, end_line=1),
    )
    item = SemanticReviewItem(
        identifier="review:test",
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=DependencyNode.from_unit(unit),
    )
    request = SemanticReviewRequest(item=item)

    resolved = build_symbol_resolution_ir(unit, request)

    goal = resolved.proof.proposition("T0")
    assert isinstance(goal.expression, QuantifiedExpr)
    binder = next(
        item
        for item in resolved.declarations
        if item.kind == DeclarationKind.BINDER and item.provenance.source_address == "T0"
    )
    body_x = resolved.reference(ExpressionRef(owner_address="T0", path=("body", "arguments", "0")))
    assert body_x.status == ResolutionStatus.BOUND
    assert body_x.declaration_addresses == (binder.address,)


def test_expression_refs_are_structural_not_rendered_strings() -> None:
    expression = OperatorExpr(
        operator="+",
        arguments=(IdentifierExpr(name="x"), IdentifierExpr(name="y")),
    )
    resolved = elaborate_symbol_resolution(_proof([_proposition("C1", expression)]))

    left = ExpressionRef(owner_address="C1", path=("arguments", "0"))
    right = ExpressionRef(owner_address="C1", path=("arguments", "1"))
    assert resolved.expression(left) == IdentifierExpr(name="x")
    assert resolved.expression(right) == IdentifierExpr(name="y")
