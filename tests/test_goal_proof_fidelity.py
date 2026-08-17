from __future__ import annotations

from pathlib import Path

import pytest

from thorn.canonical_proof_ir import (
    CanonicalEdgeKind,
    CanonicalNodeKind,
    CanonicalProofIR,
    build_canonical_proof_ir,
)
from thorn.canonical_typed_proof_ir import (
    CanonicalTypedProofIR,
    build_canonical_typed_proof_ir,
)
from thorn.eval_review import build_result_review_context
from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.llm_proof_language import (
    LLMProofLanguage,
    parse_source_rescue_request,
    project_llm_proof_language,
    render_source_rescue,
)
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    advertised_source_addresses,
    build_proof_review_turn,
)
from thorn.proof_obligations import (
    ObligationStatus,
    ProofObligationIR,
    ProofRuleKind,
    elaborate_proof_obligations,
)
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import (
    SemanticTransformationIR,
    build_semantic_transformation_ir,
)


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


def _write_support_case(path: Path, *, established: str, goal: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{lemma}}{{Lemma}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{lemma}}\label{{lem:support}}
{established}.
\end{{lemma}}
\begin{{proof}}
{established}.
\end{{proof}}
\begin{{theorem}}\label{{thm:main}}
{goal}.
\end{{theorem}}
\begin{{proof}}
By Lemma~\ref{{lem:support}}, {established}.
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def _node(ir: CanonicalProofIR, address: str):
    return next(item for item in ir.nodes if item.address == address)


def _typed_node(ir: CanonicalTypedProofIR, address: str):
    return next(item for item in ir.nodes if item.address == address)


def _terminal_step(proof: ProofObligationIR):
    return next(item for item in proof.steps if item.address == "X0")


_MISMATCH_CASES = [
    pytest.param(r"$x\le y$", r"$x=y$", id="inequality-versus-equality"),
    pytest.param(
        r"there exists $x$ such that $P(x)$",
        r"there exists a unique $x$ such that $P(x)$",
        id="existence-versus-uniqueness",
    ),
    pytest.param(
        r"the function $f$ is injective",
        r"the function $f$ is bijective",
        id="injectivity-versus-bijectivity",
    ),
    pytest.param(
        r"the sequence $f_n$ converges pointwise to $f$",
        r"the sequence $f_n$ converges uniformly to $f$",
        id="pointwise-versus-uniform",
    ),
    pytest.param(
        r"the property $P$ holds in a neighbourhood of $x$",
        r"the property $P$ holds on $X$",
        id="local-versus-global",
    ),
    pytest.param(
        r"$\forall x\,\exists y\,P(x,y)$",
        r"$\exists y\,\forall x\,P(x,y)$",
        id="quantifier-order",
    ),
    pytest.param(
        r"$P\Rightarrow Q$",
        r"$P\Leftrightarrow Q$",
        id="implication-versus-equivalence",
    ),
]


@pytest.mark.parametrize(("established", "goal"), _MISMATCH_CASES)
def test_held_out_strength_mismatches_preserve_goal_support_boundary(
    tmp_path: Path,
    established: str,
    goal: str,
) -> None:
    tex = tmp_path / "mismatch.tex"
    _write_support_case(tex, established=established, goal=goal)

    canonical, typed, proof, semantic, document = _trace(tex, "thm:main")
    terminal = proof.terminal_obligation
    assert terminal.support_context
    final_address = terminal.support_context[0]

    # Source/extraction and canonical recovery keep the theorem goal and the
    # proof's final recovered claim as distinct stable objects. No vocabulary
    # about the mathematical strength relation is needed for this assertion.
    assert final_address != "T0"
    assert goal in canonical.source("T0").text
    assert established in canonical.source(final_address).text
    assert _node(canonical, "T0").atom != _node(canonical, final_address).atom
    assert typed.source("T0").text == canonical.source("T0").text
    assert typed.source(final_address).text == canonical.source(final_address).text
    assert _typed_node(typed, "T0").address == "T0"
    assert _typed_node(typed, final_address).address == final_address

    # The existing proof-obligation relation, not a parallel theorem/proof
    # graph, identifies the candidate final discharge and refuses to promote a
    # non-exact or opaque match to a proof-success claim.
    step = _terminal_step(proof)
    assert step.premises == (final_address,)
    assert step.conclusion == "T0"
    assert step.rule == ProofRuleKind.UNKNOWN
    assert step.status == InferenceStatus.UNRESOLVED
    assert terminal.status == ObligationStatus.UNRESOLVED
    assert terminal.discharging_steps == ()

    semantic_proof = semantic.higher.resolved.proof
    semantic_step = _terminal_step(semantic_proof)
    assert semantic_step.premises == (final_address,)
    assert semantic_step.conclusion == "T0"
    assert semantic_step.status == InferenceStatus.UNRESOLVED

    # thorn-proof/1 exposes the attempted final discharge structurally and
    # advertises exact source for both sides of that unresolved bridge.
    goal_line = next(line for line in document.lines if line.startswith("T0 "))
    assert f"<- {final_address}" in goal_line
    goal_obligation_line = next(
        line for line in document.lines if line.startswith("GOAL G0 T0:")
    )
    assert "| open" in goal_obligation_line
    advertised = set(advertised_source_addresses(document))
    assert {"T0", final_address} <= advertised

    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=document))
    assert {"T0", final_address} <= set(turn.allowed_source_addresses)
    rescue = render_source_rescue(
        document,
        parse_source_rescue_request(
            document,
            f"NEED_SOURCE {final_address},T0",
        ),
    )
    assert established in rescue.text
    assert goal in rescue.text


def test_clean_exact_neighbour_uses_same_terminal_mechanism(tmp_path: Path) -> None:
    tex = tmp_path / "exact.tex"
    statement = r"$x\le y$"
    _write_support_case(tex, established=statement, goal=statement)

    canonical, _typed, proof, semantic, document = _trace(tex, "thm:main")
    terminal = proof.terminal_obligation
    final_address = terminal.support_context[0]
    step = _terminal_step(proof)

    assert final_address != "T0"
    assert canonical.source("T0").text != canonical.source(final_address).text
    assert step.premises == (final_address,)
    assert step.conclusion == "T0"
    assert step.rule == ProofRuleKind.EXACT
    assert step.status == InferenceStatus.CONFIDENT
    final_obligation = next(
        item for item in proof.obligations if item.proposition_address == final_address
    )
    assert final_obligation.status == ObligationStatus.DISCHARGED
    assert terminal.status == ObligationStatus.DISCHARGED
    assert terminal.discharging_steps == ("X0",)

    semantic_step = _terminal_step(semantic.higher.resolved.proof)
    assert semantic_step.rule == ProofRuleKind.EXACT
    assert semantic_step.status == InferenceStatus.CONFIDENT
    goal_line = next(line for line in document.lines if line.startswith("T0 "))
    assert f"<- {final_address}" in goal_line
    goal_obligation_line = next(
        line for line in document.lines if line.startswith("GOAL G0 T0:")
    )
    assert "| structural" in goal_obligation_line


def test_extrema_fixture_traces_bounded_claim_to_open_attainment_goal() -> None:
    fixture = Path(
        "eval/cases/ladder/04_proof_sufficiency/proves_only_weaker_statement.tex"
    )

    canonical, typed, proof, semantic, document = _trace(
        fixture,
        "thm:extreme-value-gap",
    )

    goal = _node(canonical, "T0")
    assert goal.kind == CanonicalNodeKind.RESULT
    assert "attains both a maximum" in goal.atom
    assert "attains both a maximum" in canonical.source("T0").text

    bounded_prose = next(
        node for node in canonical.nodes if "bounded" in canonical.source(node.address).text
    )
    bound_display = next(
        node
        for node in canonical.nodes
        if r"m\le f(x)\le M" in canonical.source(node.address).text
    )
    final_claim = next(
        node
        for node in canonical.nodes
        if "attains its minimum and maximum" in canonical.source(node.address).text
    )
    assert len({goal.address, bounded_prose.address, bound_display.address, final_claim.address}) == 4
    assert bound_display.kind == CanonicalNodeKind.CLAIM
    assert final_claim.kind == CanonicalNodeKind.OPAQUE_PROSE

    bridge = next(
        edge for edge in canonical.edges if edge.target == final_claim.address
    )
    assert bridge.kind == CanonicalEdgeKind.PRIOR_CLAIM
    assert bridge.source == bound_display.address
    assert bridge.status == InferenceStatus.CONFIDENT

    # Typed/canonical payloads remain distinct. The prose conclusion stays
    # deliberately opaque rather than being coerced into attainment semantics.
    assert _typed_node(typed, bound_display.address).expression is not None
    assert _typed_node(typed, final_claim.address).expression is None

    terminal_step = _terminal_step(proof)
    assert terminal_step.premises == (final_claim.address,)
    assert terminal_step.conclusion == "T0"
    assert terminal_step.rule == ProofRuleKind.UNKNOWN
    assert terminal_step.status == InferenceStatus.UNRESOLVED
    assert proof.terminal_obligation.support_context == (final_claim.address,)
    assert proof.terminal_obligation.status == ObligationStatus.UNRESOLVED
    assert proof.terminal_obligation.discharging_steps == ()

    semantic_step = _terminal_step(semantic.higher.resolved.proof)
    assert semantic_step.status == InferenceStatus.UNRESOLVED
    rendered = document.render_initial()
    assert "attains both a maximum" in rendered
    goal_line = next(line for line in document.lines if line.startswith("T0 "))
    assert f"<- {final_claim.address}" in goal_line
    assert any(
        line.startswith(f"{bound_display.address} ") for line in document.lines
    )
    assert any(line.startswith(f"{final_claim.address} ") for line in document.lines)

    # All opaque/unresolved material needed to inspect the asserted bridge is
    # mechanically reachable through the existing #87/#88 source-handle path.
    advertised = set(advertised_source_addresses(document))
    assert {
        "T0",
        bounded_prose.address,
        final_claim.address,
    } <= advertised
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=document))
    assert advertised == set(turn.allowed_source_addresses)
    rescue = render_source_rescue(
        document,
        parse_source_rescue_request(
            document,
            f"NEED_SOURCE {bounded_prose.address},{final_claim.address},T0",
        ),
    )
    assert "is bounded" in rescue.text
    assert "attains its minimum and maximum" in rescue.text
    assert "attains both a maximum" in rescue.text
