from __future__ import annotations

from thorn.dependencies import DependencyNode
from thorn.evidence import InferenceStatus
from thorn.frontend import SourceSpan
from thorn.models import SourceRange
from thorn.providers.request_envelope import semantic_request_envelope
from thorn.semantic_review import ReviewSourceContext, ReviewTargetKind, SemanticReviewItem
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import build_semantic_review_request
from thorn.support import Claim, ClaimForm, SupportEdge, SupportKind
from thorn.symbols import Constraint, Definition, SymbolCandidateKind, SymbolIntroductionCandidate


def _span(start: int, end: int, line: int) -> SourceSpan:
    return SourceSpan(
        file="paper.tex",
        start_offset=start,
        end_offset=end,
        start_line=line,
        start_column=1,
        end_line=line,
        end_column=end - start + 1,
    )


def _request():
    result_id = "thm:test"
    first = Claim(
        identifier="long-internal-claim-a",
        result_identifier=result_id,
        form=ClaimForm.PROSE,
        raw="Assume x > 0.",
        source=_span(100, 113, 10),
    )
    second = Claim(
        identifier="long-internal-claim-b",
        result_identifier=result_id,
        form=ClaimForm.PROSE,
        raw="Therefore x^2 > 0.",
        source=_span(120, 138, 11),
    )
    relation = SupportEdge(
        identifier="long-internal-relation",
        source_claim_identifier=first.identifier,
        target_claim_identifier=second.identifier,
        kind=SupportKind.PRIOR_CLAIM,
        source=_span(120, 138, 11),
        raw_justification="therefore",
        status=InferenceStatus.AMBIGUOUS,
    )
    item = SemanticReviewItem(
        identifier="semantic-review:test-with-long-machine-id",
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=DependencyNode(
            identifier=result_id,
            label=result_id,
            environment="theorem",
            statement="For x > 0, x^2 > 0.",
            source=SourceRange(file="paper.tex", start_line=2, end_line=4),
        ),
        claims=[second, first],
        trigger_relation_identifiers=[relation.identifier],
        support_relations=[relation],
        hypotheses=[
            Constraint(
                identifier="machine-hypothesis-id",
                symbol_identifier="machine-symbol-id",
                relation=">",
                expression_latex="0",
                source=_span(20, 25, 2),
                raw="x > 0",
            )
        ],
        definitions=[
            Definition(
                identifier="machine-definition-id",
                symbol_identifier="machine-symbol-id",
                operator="iff",
                expression_latex="x^2>0",
                source=_span(40, 58, 3),
                raw="P(x) iff x^2 > 0",
            )
        ],
        symbol_candidates=[
            SymbolIntroductionCandidate(
                identifier="machine-candidate-id",
                name="z",
                kind=SymbolCandidateKind.INTRODUCTION,
                scope_identifier="machine-scope-id",
                result_identifier=result_id,
                source=_span(130, 131, 11),
                math_source=_span(130, 134, 11),
                raw_context="possibly introduce z",
                status=InferenceStatus.AMBIGUOUS,
            )
        ],
        dependencies=[
            DependencyNode(
                identifier="lem:needed:machine-id",
                label="lem:needed",
                environment="lemma",
                statement="If x > 0 then x^2 > 0.",
                source=SourceRange(file="paper.tex", start_line=50, end_line=52),
            )
        ],
        nearby_context=[
            ReviewSourceContext(
                text="frontend retained duplicate wording",
                source=_span(120, 138, 11),
            )
        ],
    )
    return build_semantic_review_request(item)


def test_compact_renderer_keeps_mathematics_and_drops_machine_provenance() -> None:
    rendered = render_compact_semantic_review_request(_request())

    assert "For x > 0, x^2 > 0." in rendered
    assert "C1: Assume x > 0." in rendered
    assert "C2: Therefore x^2 > 0." in rendered
    assert "R1: C1 -> C2; kind=prior_claim; wording=therefore" in rendered
    assert "# Explicit hypotheses\n- x > 0" in rendered
    assert "# Definitions\n- P(x) iff x^2 > 0" in rendered
    assert "lem:needed: If x > 0 then x^2 > 0." in rendered

    assert "paper.tex" not in rendered
    assert "offsets" not in rendered
    assert "long-internal" not in rendered
    assert "machine-" not in rendered
    assert "possibly introduce z" not in rendered
    assert "frontend retained duplicate wording" not in rendered
    assert "AMBIGUOUS" not in rendered


def test_compact_renderer_is_deterministic() -> None:
    first = render_compact_semantic_review_request(_request())
    second = render_compact_semantic_review_request(_request())
    assert first == second


def test_semantic_envelope_uses_compact_renderer_only_when_explicitly_selected(
    monkeypatch,
) -> None:
    request = _request()

    monkeypatch.delenv("THORN_SEMANTIC_RENDERING", raising=False)
    full = semantic_request_envelope(request, "fixture-model")
    assert "Review item: semantic-review:test-with-long-machine-id" in full.user_content

    monkeypatch.setenv("THORN_SEMANTIC_RENDERING", "compact")
    compact = semantic_request_envelope(request, "fixture-model")
    assert compact.user_content == render_compact_semantic_review_request(request)
    assert compact.fingerprint() != full.fingerprint()
