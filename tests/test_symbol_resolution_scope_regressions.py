from thorn.canonical_proof_ir import CanonicalNodeKind, CanonicalProofSource
from thorn.formula_ir import (
    Binder,
    ExprLoweringStatus,
    IdentifierExpr,
    QuantifiedExpr,
    Quantifier,
)
from thorn.frontend import SourceSpan
from thorn.proof_obligations import ProofObligationIR, ProofProposition, PropositionRole
from thorn.symbol_resolution_ir import (
    ExpressionRef,
    ResolutionStatus,
    elaborate_symbol_resolution,
)


def _source(address: str, start: int) -> CanonicalProofSource:
    return CanonicalProofSource(
        address=address,
        ir_identifier=f"ir:{address}",
        text=address,
        source_span=SourceSpan(
            file="paper.tex",
            start_offset=start,
            end_offset=start + 10,
            start_line=1,
            start_column=start + 1,
            end_line=1,
            end_column=start + 11,
        ),
    )


def test_binder_identity_does_not_leak_across_propositions() -> None:
    first = ProofProposition(
        address="C1",
        role=PropositionRole.DERIVED,
        node_kind=CanonicalNodeKind.CLAIM,
        expression=QuantifiedExpr(
            quantifier=Quantifier.FOR_ALL,
            binder=Binder(name=IdentifierExpr(name="x")),
            body=IdentifierExpr(name="x"),
        ),
        expression_status=ExprLoweringStatus.FULL,
        source_address="C1",
    )
    second = ProofProposition(
        address="C2",
        role=PropositionRole.DERIVED,
        node_kind=CanonicalNodeKind.CLAIM,
        expression=IdentifierExpr(name="x"),
        expression_status=ExprLoweringStatus.FULL,
        source_address="C2",
    )
    proof = ProofObligationIR(
        result_identifier="thm:test",
        propositions=[first, second],
        sources=[_source("C1", 0), _source("C2", 20)],
    )

    resolved = elaborate_symbol_resolution(proof)

    inner = resolved.reference(ExpressionRef(owner_address="C1", path=("body",)))
    free = resolved.reference(ExpressionRef(owner_address="C2"))
    assert inner.status == ResolutionStatus.BOUND
    assert free.status == ResolutionStatus.UNRESOLVED
    assert free.declaration_addresses == ()
