from __future__ import annotations

from pathlib import Path

import pytest

from thorn.canonical_proof_ir import CanonicalProofIR, build_canonical_proof_ir
from thorn.canonical_typed_proof_ir import (
    CanonicalTypedProofIR,
    build_canonical_typed_proof_ir,
)
from thorn.eval import _load_cases
from thorn.eval_review import build_result_review_context
from thorn.formula_ir import IdentifierExpr, QuantifiedExpr, lower_math_expression
from thorn.latex import extract_project
from thorn.lean_export import LeanExportStatus, project_lean
from thorn.llm_proof_language import LLMProofLanguage, project_llm_proof_language
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    advertised_source_addresses,
    build_proof_review_turn,
)
from thorn.proof_obligations import ProofObligationIR, elaborate_proof_obligations
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import (
    SemanticTransformationIR,
    build_semantic_transformation_ir,
)

_CASE_DIR = Path("eval/cases/ladder/09_material_assumption_gaps")


def _trace(
    path: Path,
    target: str,
) -> tuple[
    CanonicalProofIR,
    CanonicalTypedProofIR,
    ProofObligationIR,
    SemanticTransformationIR,
    LLMProofLanguage,
]:
    project = extract_project(path)
    unit = project.unit(target)
    context = build_result_review_context(project, target)
    request = build_semantic_review_request(context.items[0])
    canonical = build_canonical_proof_ir(unit, request)
    typed = build_canonical_typed_proof_ir(unit, request)
    proof = elaborate_proof_obligations(typed)
    semantic = build_semantic_transformation_ir(
        unit,
        request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    document = project_llm_proof_language(semantic)
    return canonical, typed, proof, semantic, document


_CASES = [
    pytest.param(
        "euclidean_pythagoras_clean.tex",
        "thm:euclidean-pythagoras-clean",
        "Euclidean plane",
        "Pythagorean theorem",
        id="euclidean-clean",
    ),
    pytest.param(
        "euclidean_pythagoras_gap.tex",
        "thm:riemannian-pythagoras-gap",
        "Riemannian surface",
        "Pythagorean theorem",
        id="euclidean-gap",
    ),
    pytest.param(
        "real_square_roots_clean.tex",
        "thm:real-square-roots-clean",
        r"\mathbb R",
        "no zero divisors",
        id="domain-clean",
    ),
    pytest.param(
        "ring_square_roots_gap.tex",
        "thm:ring-square-roots-gap",
        "arbitrary ring",
        "one factor is zero",
        id="domain-gap",
    ),
    pytest.param(
        "integer_cancellation_clean.tex",
        "thm:integer-cancellation-clean",
        r"\mathbb Z",
        "Cancel the common factor",
        id="foundational-clean",
    ),
    pytest.param(
        "modular_integer_cancellation_gap.tex",
        "thm:modular-integer-cancellation-gap",
        r"\mathbb Z/4\mathbb Z",
        "Cancel the common factor",
        id="foundational-gap",
    ),
    pytest.param(
        "finite_dimensional_subsequence_clean.tex",
        "thm:finite-dimensional-subsequence-clean",
        "finite-dimensional",
        "ball is compact",
        id="dimension-clean",
    ),
    pytest.param(
        "arbitrary_dimensional_subsequence_gap.tex",
        "thm:arbitrary-dimensional-subsequence-gap",
        "normed real vector space",
        "ball is compact",
        id="dimension-gap",
    ),
]


@pytest.mark.parametrize(
    ("fixture", "target", "scope_fragment", "proof_fragment"),
    _CASES,
)
def test_material_assumption_cases_survive_to_review_boundary(
    fixture: str,
    target: str,
    scope_fragment: str,
    proof_fragment: str,
) -> None:
    path = _CASE_DIR / fixture
    project = extract_project(path)
    unit = project.unit(target)
    assert scope_fragment in unit.statement
    assert unit.proof is not None and proof_fragment in unit.proof

    canonical, typed, proof, semantic, document = _trace(path, target)

    # T0 remains the exact theorem-goal source across the canonical, typed,
    # obligation, semantic-transformation, and model-facing projections.
    assert typed.source("T0").text == canonical.source("T0").text
    assert proof.source("T0").text == canonical.source("T0").text
    assert document.source("T0").text == canonical.source("T0").text
    assert proof.terminal_obligation.proposition_address == "T0"
    assert semantic.higher.resolved.proof.terminal_obligation.proposition_address == "T0"

    # The proof sentence which consumes the potentially ambient premise must
    # survive as authoritative source whenever it participates in recovered
    # proof structure. This tests provenance, not deterministic theorem proving.
    proof_sources = [
        source for source in canonical.sources if proof_fragment in source.text
    ]
    assert proof_sources, f"{proof_fragment!r} was lost from canonical proof source"
    for source in proof_sources:
        assert typed.source(source.address).text == source.text
        assert document.source(source.address).text == source.text

    rendered = document.render_initial()
    advertised = set(advertised_source_addresses(document))
    assert scope_fragment in rendered or "T0" in advertised
    assert any(
        proof_fragment in rendered or source.address in advertised
        for source in proof_sources
    )

    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=document))
    assert advertised == set(turn.allowed_source_addresses)


_PAIRS = [
    pytest.param(
        "euclidean_pythagoras_clean.tex",
        "thm:euclidean-pythagoras-clean",
        "euclidean_pythagoras_gap.tex",
        "thm:riemannian-pythagoras-gap",
        "Euclidean",
        id="euclidean",
    ),
    pytest.param(
        "real_square_roots_clean.tex",
        "thm:real-square-roots-clean",
        "ring_square_roots_gap.tex",
        "thm:ring-square-roots-gap",
        r"\mathbb R",
        id="domain",
    ),
    pytest.param(
        "integer_cancellation_clean.tex",
        "thm:integer-cancellation-clean",
        "modular_integer_cancellation_gap.tex",
        "thm:modular-integer-cancellation-gap",
        "For integers",
        id="foundational",
    ),
    pytest.param(
        "finite_dimensional_subsequence_clean.tex",
        "thm:finite-dimensional-subsequence-clean",
        "arbitrary_dimensional_subsequence_gap.tex",
        "thm:arbitrary-dimensional-subsequence-gap",
        "finite-dimensional",
        id="dimension",
    ),
]


@pytest.mark.parametrize(
    ("clean_fixture", "clean_target", "gap_fixture", "gap_target", "clean_only_scope"),
    _PAIRS,
)
def test_defect_packet_does_not_silently_strength_to_clean_ambient_scope(
    clean_fixture: str,
    clean_target: str,
    gap_fixture: str,
    gap_target: str,
    clean_only_scope: str,
) -> None:
    clean = _trace(_CASE_DIR / clean_fixture, clean_target)[-1]
    gap = _trace(_CASE_DIR / gap_fixture, gap_target)[-1]

    assert clean_only_scope in clean.source("T0").text
    assert clean_only_scope not in gap.source("T0").text
    assert clean_only_scope not in gap.render_initial()
    assert all(clean_only_scope not in source.text for source in gap.sources)


def test_material_assumption_family_is_first_class_review_only_eval_family() -> None:
    loaded = _load_cases(_CASE_DIR)
    assert len(loaded) == 8
    assert {expectation.kind for _, expectation in loaded} == {"clean", "finding"}
    assert all(expectation.modes == ["review"] for _, expectation in loaded)
    assert {
        expectation.fault_class
        for _, expectation in loaded
        if expectation.kind == "finding"
    } == {
        "material_assumption_gap_euclidean",
        "material_assumption_gap_domain",
        "material_assumption_gap_foundational",
        "material_assumption_gap_dimension",
    }
    assert all(
        "counterfactual materiality" in expectation.detection_methods
        for _, expectation in loaded
    )
    assert all(
        expectation.notes is not None and "Load-bearing premise" in expectation.notes
        for _, expectation in loaded
    )


def test_nearby_named_domain_is_not_globally_promoted_to_reals() -> None:
    lowered = lower_math_expression("For every x in K, P(x)")
    assert isinstance(lowered.expression, QuantifiedExpr)
    assert lowered.expression.binder.domain == IdentifierExpr(name="K")


@pytest.mark.parametrize(
    ("fixture", "target"),
    [
        ("euclidean_pythagoras_clean.tex", "thm:euclidean-pythagoras-clean"),
        ("ring_square_roots_gap.tex", "thm:ring-square-roots-gap"),
    ],
)
def test_lean_handoff_stays_partial_without_ambient_strengthening(
    fixture: str,
    target: str,
) -> None:
    semantic = _trace(_CASE_DIR / fixture, target)[-2]
    export = project_lean(semantic)

    # These prose-heavy examples are outside the deliberately bounded Lean
    # subset. A formalisation limitation is not evidence of a paper defect
    # and is not a licence to pick a stronger ambient structure.
    assert export.status in {LeanExportStatus.PARTIAL, LeanExportStatus.UNSUPPORTED}
    assert not export.is_mechanically_checkable
    assert "LinearOrderedField" not in export.source
    assert "EuclideanSpace" not in export.source
