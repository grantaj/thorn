from __future__ import annotations

from types import SimpleNamespace

import pytest

from thorn.audit import audit_unit
from thorn.dependencies import DependencyGraph, DependencyNode, ExtractedProject
from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import SourceSpan
from thorn.models import AttackReport, DefenseReport, SourceRange, TheoremUnit
from thorn.providers import openai as openai_provider
from thorn.semantic_audit import review_semantic_context
from thorn.semantic_review import (
    ReviewContext,
    ReviewSourceContext,
    ReviewTargetKind,
    SemanticReviewItem,
    build_review_context,
)
from thorn.semantic_review_render import (
    SemanticReviewRequest,
    build_semantic_review_request,
    render_semantic_review_request,
)
from thorn.support import Claim, ClaimForm, ProofSupportGraph, SupportEdge, SupportKind
from thorn.symbols import (
    Constraint,
    Definition,
    IntroductionKind,
    Symbol,
    SymbolCandidateKind,
    SymbolIntroductionCandidate,
    SymbolTable,
)


def _span(start: int, end: int, line: int, *, file: str = "paper.tex") -> SourceSpan:
    return SourceSpan(
        file=file,
        start_offset=start,
        end_offset=end,
        start_line=line,
        start_column=1,
        end_line=line,
        end_column=end - start + 1,
    )


def _review_item(
    marker: str = "main",
    *,
    line_shift: int = 0,
    offset_shift: int = 0,
    statement: str = "For x > 0, P(x) holds.",
) -> SemanticReviewItem:
    result_id = f"thm:{marker}"
    claim0 = Claim(
        identifier=f"{marker}:c0",
        result_identifier=result_id,
        form=ClaimForm.PROSE,
        raw="Assume x > 0.",
        source=_span(100 + offset_shift, 113 + offset_shift, 10 + line_shift),
    )
    claim1 = Claim(
        identifier=f"{marker}:c1",
        result_identifier=result_id,
        form=ClaimForm.PROSE,
        raw="Therefore x^2 > 0.",
        source=_span(120 + offset_shift, 138 + offset_shift, 11 + line_shift),
    )
    claim2 = Claim(
        identifier=f"{marker}:c2",
        result_identifier=result_id,
        form=ClaimForm.PROSE,
        raw="Hence P(x).",
        source=_span(140 + offset_shift, 151 + offset_shift, 12 + line_shift),
    )

    ambiguous = SupportEdge(
        identifier=f"{marker}:e-ambiguous",
        source_claim_identifier=claim0.identifier,
        target_claim_identifier=claim1.identifier,
        kind=SupportKind.PRIOR_CLAIM,
        source=_span(120 + offset_shift, 138 + offset_shift, 11 + line_shift),
        raw_justification="therefore",
        status=InferenceStatus.AMBIGUOUS,
        confidence=None,
        evidence=[
            StructuralEvidence(
                reason="candidate antecedent attachment",
                source=_span(120 + offset_shift, 138 + offset_shift, 11 + line_shift),
                target=_span(100 + offset_shift, 113 + offset_shift, 10 + line_shift),
                context="Assume x > 0. Therefore x^2 > 0.",
                dependency_path=["SCONJ:mark", "VERB:advcl"],
                frontend="synthetic",
            )
        ],
    )
    unresolved = SupportEdge(
        identifier=f"{marker}:e-unresolved",
        target_claim_identifier=claim2.identifier,
        kind=SupportKind.RESULT_REFERENCE,
        source=_span(140 + offset_shift, 151 + offset_shift, 12 + line_shift),
        raw_justification=r"Lemma~\ref{lem:needed}",
        target_label="lem:needed",
        status=InferenceStatus.UNRESOLVED,
        confidence=None,
        evidence=[
            StructuralEvidence(
                reason="reference support role is unresolved",
                source=_span(140 + offset_shift, 151 + offset_shift, 12 + line_shift),
                context=r"Hence P(x) by Lemma~\ref{lem:needed}.",
            )
        ],
    )
    confident = SupportEdge(
        identifier=f"{marker}:e-confident",
        source_claim_identifier=claim1.identifier,
        target_claim_identifier=claim2.identifier,
        kind=SupportKind.PRIOR_CLAIM,
        source=_span(140 + offset_shift, 151 + offset_shift, 12 + line_shift),
        raw_justification="hence",
        status=InferenceStatus.CONFIDENT,
        confidence=1.0,
    )

    symbol_x = Symbol(
        identifier=f"{marker}:sym:x",
        name="x",
        introduction_kind=IntroductionKind.FOR,
        scope_identifier=f"{marker}:scope:result",
        result_identifier=result_id,
        source=_span(20 + offset_shift, 21 + offset_shift, 2 + line_shift),
        introduction_source=_span(15 + offset_shift, 30 + offset_shift, 2 + line_shift),
        raw_introduction="For x > 0",
    )
    definition_p = Definition(
        identifier=f"{marker}:def:P",
        symbol_identifier=symbol_x.identifier,
        operator="iff",
        expression_latex="x^2>0",
        source=_span(40 + offset_shift, 58 + offset_shift, 3 + line_shift),
        raw="P(x) iff x^2 > 0",
    )
    hypothesis = Constraint(
        identifier=f"{marker}:hyp:x",
        symbol_identifier=symbol_x.identifier,
        relation=">",
        expression_latex="0",
        source=_span(20 + offset_shift, 25 + offset_shift, 2 + line_shift),
        raw="x > 0",
    )
    local_constraint = Constraint(
        identifier=f"{marker}:local:x",
        symbol_identifier=symbol_x.identifier,
        relation="!=",
        expression_latex="1",
        source=_span(114 + offset_shift, 119 + offset_shift, 10 + line_shift),
        raw="x != 1",
    )
    candidate = SymbolIntroductionCandidate(
        identifier=f"{marker}:cand:z",
        name="z",
        kind=SymbolCandidateKind.INTRODUCTION,
        scope_identifier=f"{marker}:scope:proof",
        result_identifier=result_id,
        source=_span(130 + offset_shift, 131 + offset_shift, 11 + line_shift),
        math_source=_span(130 + offset_shift, 134 + offset_shift, 11 + line_shift),
        raw_context="possibly introduce z",
        status=InferenceStatus.AMBIGUOUS,
    )

    dependency = DependencyNode(
        identifier=f"{marker}:lem:needed",
        label="lem:needed",
        environment="lemma",
        statement="If x > 0 then x^2 > 0.",
        source=SourceRange(
            file="paper.tex",
            start_line=50 + line_shift,
            end_line=52 + line_shift,
        ),
    )
    result = DependencyNode(
        identifier=result_id,
        label=result_id,
        environment="theorem",
        statement=statement,
        source=SourceRange(
            file="paper.tex",
            start_line=2 + line_shift,
            end_line=4 + line_shift,
        ),
    )

    return SemanticReviewItem(
        identifier=f"semantic-review:{marker}",
        target_kind=ReviewTargetKind.SUPPORT_RELATION,
        result=result,
        claims=[claim2, claim0, claim1],
        trigger_relation_identifiers=[unresolved.identifier, ambiguous.identifier],
        support_relations=[confident, unresolved, ambiguous],
        hypotheses=[hypothesis],
        local_constraints=[local_constraint],
        symbols=[symbol_x],
        definitions=[definition_p],
        symbol_candidates=[candidate],
        dependencies=[dependency],
        nearby_context=[
            ReviewSourceContext(
                text="Assume x > 0. Therefore x^2 > 0.",
                source=ambiguous.source,
            )
        ],
    )


class FakeSemanticProvider:
    model = "fake-semantic"

    def __init__(self) -> None:
        self.requests: list[SemanticReviewRequest] = []

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        self.requests.append(request)
        return AttackReport(findings=[])


class FakeRawProvider:
    model = "fake-raw"

    def __init__(self) -> None:
        self.attacked: list[str] = []

    def attack(self, unit: TheoremUnit) -> AttackReport:
        self.attacked.append(unit.identifier)
        return AttackReport(findings=[])

    def defend(self, unit: TheoremUnit, findings: list[object]) -> DefenseReport:
        raise AssertionError("empty attack should not invoke defender")


class FakeResponses:
    def __init__(self, outputs: list[object | None]) -> None:
        self.outputs = iter(outputs)
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=next(self.outputs),
            usage=SimpleNamespace(input_tokens=12, output_tokens=3, total_tokens=15),
        )


class FakeClient:
    def __init__(self, outputs: list[object | None]) -> None:
        self.responses = FakeResponses(outputs)


def test_semantic_request_rendering_is_deterministic_and_preserves_identity() -> None:
    item = _review_item()
    first = render_semantic_review_request(build_semantic_review_request(item))
    second = render_semantic_review_request(build_semantic_review_request(_review_item()))

    assert first.encode() == second.encode()
    assert "Review item: semantic-review:main" in first
    assert "Target kind: support_relation" in first
    assert "Result ID: thm:main" in first
    assert "Claim ID: main:c1" in first
    assert "Relation ID: main:e-ambiguous" in first
    assert "paper.tex:11:1-11:19 [offsets 120:138]" in first
    assert "Dependency ID: main:lem:needed" in first
    assert "paper.tex:50-52" in first


def test_uncertainty_is_escalation_reason_not_asserted_defect() -> None:
    rendered = render_semantic_review_request(build_semantic_review_request(_review_item()))
    escalation = rendered.split("## Relations that caused semantic escalation", 1)[1].split(
        "## Confident support context", 1
    )[0]
    confident = rendered.split("## Confident support context", 1)[1].split(
        "## Explicit hypotheses", 1
    )[0]

    assert "Status: AMBIGUOUS" in escalation
    assert "Status: UNRESOLVED" in escalation
    assert "main:e-confident" not in escalation
    assert "main:e-confident" in confident
    assert "Status: CONFIDENT" in confident
    assert "AMBIGUOUS and UNRESOLVED are uncertainty states, not correctness defects" in rendered
    assert "CONFIDENT relations are interpretation context only" in rendered


def test_rendering_is_bounded_to_selected_review_item() -> None:
    selected = _review_item()
    unrelated = _review_item(
        "other",
        line_shift=100,
        offset_shift=1000,
        statement="UNRELATED THEOREM CONTENT MUST NOT LEAK",
    )
    context = ReviewContext(items=[selected, unrelated])

    rendered = render_semantic_review_request(build_semantic_review_request(context.items[0]))

    assert "x > 0" in rendered
    assert "P(x) iff x^2 > 0" in rendered
    assert "Symbol ID: main:sym:x" in rendered
    assert "If x > 0 then x^2 > 0." in rendered
    assert "UNRELATED THEOREM CONTENT MUST NOT LEAK" not in rendered
    assert "semantic-review:other" not in rendered


def test_request_boundary_is_provider_neutral() -> None:
    request = build_semantic_review_request(_review_item())

    assert set(SemanticReviewRequest.model_fields) == {"item"}
    assert "prompt" not in SemanticReviewItem.model_fields
    assert "messages" not in SemanticReviewItem.model_fields
    assert "openai" not in request.canonical_json().lower()
    assert "\"role\"" not in request.canonical_json().lower()


def test_raw_theorem_unit_path_still_coexists() -> None:
    unit = TheoremUnit(
        identifier="thm:raw",
        environment="theorem",
        statement="B holds.",
        proof="A, hence B.",
        statement_range=SourceRange(file="raw.tex", start_line=1, end_line=2),
    )
    provider = FakeRawProvider()

    result = audit_unit(unit, provider, cache=None)

    assert result.unit == unit
    assert result.findings == []
    assert provider.attacked == ["thm:raw"]


def test_fake_semantic_provider_receives_exact_bounded_request_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    item = _review_item()
    context = ReviewContext(items=[item])
    provider = FakeSemanticProvider()

    results = review_semantic_context(context, provider)

    assert len(provider.requests) == 1
    expected = build_semantic_review_request(item)
    assert provider.requests[0].canonical_json() == expected.canonical_json()
    assert len(results) == 1
    result = results[0]
    assert result.item_identifier == item.identifier
    assert result.result_identifier == item.result.identifier
    assert result.result_source == item.result.source
    assert result.trigger_relation_identifiers == sorted(item.trigger_relation_identifiers)
    assert result.report.findings == []


def test_multiple_items_stay_distinct_and_grouped_item_stays_one_request() -> None:
    grouped = _review_item()
    other = _review_item("other", line_shift=100, offset_shift=1000)
    provider = FakeSemanticProvider()

    results = review_semantic_context(ReviewContext(items=[grouped, other]), provider)

    assert len(provider.requests) == 2
    assert len(results) == 2
    assert [request.item.identifier for request in provider.requests] == [
        "semantic-review:main",
        "semantic-review:other",
    ]
    assert sorted(provider.requests[0].item.trigger_relation_identifiers) == [
        "main:e-ambiguous",
        "main:e-unresolved",
    ]


def test_ambiguous_symbol_candidate_alone_never_invokes_semantic_provider() -> None:
    unit = TheoremUnit(
        identifier="thm:candidate-only",
        environment="theorem",
        statement="A harmless statement.",
        proof="A harmless proof.",
        statement_range=SourceRange(file="paper.tex", start_line=1, end_line=2),
    )
    candidate = SymbolIntroductionCandidate(
        identifier="cand:only",
        name="z",
        kind=SymbolCandidateKind.INTRODUCTION,
        scope_identifier="scope:proof",
        result_identifier=unit.identifier,
        source=_span(10, 11, 3),
        math_source=_span(10, 14, 3),
        raw_context="possibly introduce z",
        status=InferenceStatus.AMBIGUOUS,
    )
    project = ExtractedProject(
        main_file="paper.tex",
        units=[unit],
        dependency_graph=DependencyGraph(nodes=[DependencyNode.from_unit(unit)]),
        symbol_table=SymbolTable(candidates=[candidate]),
        proof_support_graph=ProofSupportGraph(),
    )
    provider = FakeSemanticProvider()

    context = build_review_context(project)
    results = review_semantic_context(context, provider)

    assert context.items == []
    assert results == []
    assert provider.requests == []


def test_openai_semantic_adapter_is_keyless_with_fake_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    client = FakeClient([AttackReport(findings=[])])
    monkeypatch.setattr(openai_provider, "OpenAI", lambda: client)
    provider = openai_provider.OpenAIProvider(model="fake-model")
    request = build_semantic_review_request(_review_item())

    report = provider.review_semantic(request)

    assert report.findings == []
    assert provider.requests == 1
    assert provider.total_tokens == 15
    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == "fake-model"
    assert call["text_format"] is AttackReport
    payload = call["input"]
    assert isinstance(payload, list)
    assert "bounded mathematical neighbourhood" in payload[0]["content"]
    assert payload[1]["content"] == render_semantic_review_request(request)
