import json

from thorn.dependencies import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyResolution,
    ExtractedProject,
    ReferenceContext,
)
from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import SourceSpan
from thorn.models import SourceRange, TheoremUnit
from thorn.semantic_review import build_review_context
from thorn.support import Claim, ClaimForm, ProofSupportGraph, SupportEdge, SupportKind
from thorn.symbols import (
    Constraint,
    Definition,
    IntroductionKind,
    Scope,
    ScopeKind,
    Symbol,
    SymbolCandidateKind,
    SymbolIntroductionCandidate,
    SymbolTable,
    SymbolUse,
)


def span(start: int, end: int, line: int, *, file: str = "paper.tex") -> SourceSpan:
    return SourceSpan(
        file=file,
        start_offset=start,
        end_offset=end,
        start_line=line,
        start_column=1,
        end_line=line,
        end_column=end - start + 1,
    )


def claim(identifier: str, start: int, line: int, raw: str | None = None) -> Claim:
    return Claim(
        identifier=identifier,
        result_identifier="thm:main",
        form=ClaimForm.PROSE,
        raw=raw or f"Claim {identifier}.",
        source=span(start, start + 20, line),
    )


def make_project(*, include_uncertain: bool = True) -> ExtractedProject:
    claims = [
        claim("c1", 100, 10, "Assume the local estimate holds."),
        claim("c2", 130, 11, "Therefore f(x) is positive."),
        claim("c3", 160, 12, "Apply the cited lemma to f(x)."),
        claim("filler1", 200, 20),
        claim("filler2", 230, 21),
        claim("c6", 300, 30, "A separate argument begins."),
        claim("c7", 330, 31, "Its separate conclusion follows."),
    ]

    local_evidence = StructuralEvidence(
        reason="candidate antecedent attachment",
        source=span(130, 151, 11),
        target=span(100, 120, 10),
        context="Since the local estimate holds, therefore f(x) is positive.",
        dependency_path=["SCONJ:mark", "VERB:advcl"],
        frontend="synthetic",
    )
    edges = [
        SupportEdge(
            identifier="e-confident",
            source_claim_identifier="c2",
            target_claim_identifier="c3",
            kind=SupportKind.PRIOR_CLAIM,
            source=span(160, 180, 12),
            raw_justification="from the preceding conclusion",
            status=InferenceStatus.CONFIDENT,
            confidence=1.0,
        ),
    ]
    if include_uncertain:
        edges.extend(
            [
                SupportEdge(
                    identifier="e-local-prior",
                    source_claim_identifier="c1",
                    target_claim_identifier="c2",
                    kind=SupportKind.PRIOR_CLAIM,
                    source=span(130, 151, 11),
                    raw_justification="therefore",
                    status=InferenceStatus.AMBIGUOUS,
                    confidence=None,
                    evidence=[local_evidence],
                ),
                SupportEdge(
                    identifier="e-local-result",
                    target_claim_identifier="c3",
                    kind=SupportKind.RESULT_REFERENCE,
                    source=span(160, 181, 12),
                    raw_justification=r"Lemma~\\ref{lem:needed}",
                    target_label="lem:needed",
                    status=InferenceStatus.UNRESOLVED,
                    confidence=None,
                    evidence=[
                        StructuralEvidence(
                            reason=(
                                "reference is structurally present but support role is unresolved"
                            ),
                            source=span(160, 181, 12),
                            context=r"Apply Lemma~\\ref{lem:needed} to f(x).",
                        )
                    ],
                ),
                SupportEdge(
                    identifier="e-far",
                    source_claim_identifier="c6",
                    target_claim_identifier="c7",
                    kind=SupportKind.PRIOR_CLAIM,
                    source=span(330, 350, 31),
                    raw_justification="hence",
                    status=InferenceStatus.AMBIGUOUS,
                    confidence=None,
                    evidence=[
                        StructuralEvidence(
                            reason="candidate antecedent attachment",
                            source=span(330, 350, 31),
                            target=span(300, 320, 30),
                            context="A separate argument, hence its conclusion.",
                        )
                    ],
                ),
            ]
        )

    result_scope = Scope(
        identifier="scope:result",
        kind=ScopeKind.RESULT,
        parent_identifier="project",
        result_identifier="thm:main",
        source=span(10, 80, 2),
    )
    proof_scope = Scope(
        identifier="scope:proof",
        kind=ScopeKind.PROOF,
        parent_identifier="scope:result",
        result_identifier="thm:main",
        source=span(90, 380, 9),
    )
    unrelated_scope = Scope(
        identifier="scope:other",
        kind=ScopeKind.PROOF,
        parent_identifier="scope:result",
        result_identifier="thm:main",
        source=span(390, 450, 40),
    )
    x = Symbol(
        identifier="sym:x",
        name="x",
        introduction_kind=IntroductionKind.FOR,
        scope_identifier="scope:result",
        result_identifier="thm:main",
        source=span(30, 31, 3),
        introduction_source=span(20, 40, 3),
        raw_introduction="For $x>0$",
    )
    f = Symbol(
        identifier="sym:f",
        name="f",
        introduction_kind=IntroductionKind.DEFINE,
        scope_identifier="scope:proof",
        result_identifier="thm:main",
        source=span(105, 106, 10),
        introduction_source=span(100, 120, 10),
        raw_introduction="Define $f(x)=x$.",
    )
    y = Symbol(
        identifier="sym:y",
        name="y",
        introduction_kind=IntroductionKind.LET,
        scope_identifier="scope:other",
        result_identifier="thm:main",
        source=span(400, 401, 40),
        introduction_source=span(390, 410, 40),
        raw_introduction="Let $y$ be real.",
    )
    symbol_table = SymbolTable(
        scopes=[
            Scope(identifier="project", kind=ScopeKind.PROJECT),
            result_scope,
            proof_scope,
            unrelated_scope,
        ],
        symbols=[y, f, x],
        candidates=[
            SymbolIntroductionCandidate(
                identifier="cand:z",
                name="z",
                kind=SymbolCandidateKind.INTRODUCTION,
                scope_identifier="scope:proof",
                result_identifier="thm:main",
                source=span(145, 146, 11),
                math_source=span(145, 150, 11),
                raw_context="possibly introduce z",
                status=InferenceStatus.AMBIGUOUS,
            )
        ],
        definitions=[
            Definition(
                identifier="def:f",
                symbol_identifier="sym:f",
                operator="=",
                expression_latex="x",
                source=span(100, 120, 10),
                raw="Define $f(x)=x$.",
            ),
            Definition(
                identifier="def:y",
                symbol_identifier="sym:y",
                operator="=",
                expression_latex="2",
                source=span(390, 410, 40),
                raw="Set $y=2$.",
            ),
        ],
        constraints=[
            Constraint(
                identifier="hyp:x",
                symbol_identifier="sym:x",
                relation=">",
                expression_latex="0",
                source=span(20, 40, 3),
                raw="$x>0$",
            ),
            Constraint(
                identifier="constraint:y",
                symbol_identifier="sym:y",
                relation=">",
                expression_latex="0",
                source=span(390, 410, 40),
                raw="$y>0$",
            ),
        ],
        uses=[
            SymbolUse(
                name="x",
                scope_identifier="scope:proof",
                source=span(140, 141, 11),
                raw="x",
                resolved_symbol_identifier="sym:x",
            ),
            SymbolUse(
                name="f",
                scope_identifier="scope:proof",
                source=span(135, 136, 11),
                raw="f",
                resolved_symbol_identifier="sym:f",
            ),
            SymbolUse(
                name="y",
                scope_identifier="scope:other",
                source=span(405, 406, 40),
                raw="y",
                resolved_symbol_identifier="sym:y",
            ),
        ],
    )

    unit = TheoremUnit(
        identifier="thm:main",
        environment="theorem",
        label="thm:main",
        statement="For x > 0, the main conclusion holds.",
        proof="Synthetic proof.",
        statement_range=SourceRange(file="paper.tex", start_line=2, end_line=4),
        proof_range=SourceRange(file="paper.tex", start_line=9, end_line=35),
    )
    needed = DependencyNode(
        identifier="lem:needed",
        label="lem:needed",
        environment="lemma",
        statement="The needed local estimate is valid.",
        source=SourceRange(file="paper.tex", start_line=50, end_line=52),
    )
    unrelated = DependencyNode(
        identifier="lem:unrelated",
        label="lem:unrelated",
        environment="lemma",
        statement="An unrelated fact.",
        source=SourceRange(file="paper.tex", start_line=60, end_line=62),
    )
    result_node = DependencyNode.from_unit(unit)
    dependencies = DependencyGraph(
        nodes=[unrelated, result_node, needed],
        edges=[
            DependencyEdge(
                source_identifier="thm:main",
                target_label="lem:unrelated",
                target_identifier="lem:unrelated",
                source=SourceRange(file="paper.tex", start_line=30, end_line=30),
                context=ReferenceContext.PROOF,
                resolution=DependencyResolution.RESOLVED,
            ),
            DependencyEdge(
                source_identifier="thm:main",
                target_label="lem:needed",
                target_identifier="lem:needed",
                source=SourceRange(file="paper.tex", start_line=12, end_line=12),
                context=ReferenceContext.PROOF,
                resolution=DependencyResolution.RESOLVED,
            ),
        ],
    )
    return ExtractedProject(
        main_file="paper.tex",
        units=[unit],
        dependency_graph=dependencies,
        symbol_table=symbol_table,
        proof_support_graph=ProofSupportGraph(claims=claims, edges=edges),
    )


def local_item(project: ExtractedProject):
    context = build_review_context(project)
    return next(
        item
        for item in context.items
        if "e-local-prior" in item.trigger_relation_identifiers
    )


def test_ambiguous_prior_claim_support_retains_claims_result_evidence_and_ranges() -> None:
    item = local_item(make_project())

    assert {claim.identifier for claim in item.claims} >= {"c1", "c2"}
    assert item.result.identifier == "thm:main"
    assert item.result.statement == "For x > 0, the main conclusion holds."
    assert item.result.source == SourceRange(file="paper.tex", start_line=2, end_line=4)
    edge = next(edge for edge in item.support_relations if edge.identifier == "e-local-prior")
    assert edge.status == InferenceStatus.AMBIGUOUS
    assert edge.evidence[0].reason == "candidate antecedent attachment"
    assert edge.source.start_offset == 130
    assert edge.evidence[0].target is not None
    assert edge.evidence[0].target.start_offset == 100


def test_grouped_local_ambiguity_is_bounded() -> None:
    context = build_review_context(make_project())

    assert len(context.items) == 2
    item = local_item(make_project())
    assert item.trigger_relation_identifiers == ["e-local-prior", "e-local-result"]
    assert {claim.identifier for claim in item.claims} == {"c1", "c2", "c3"}
    assert "e-far" not in {edge.identifier for edge in item.support_relations}
    assert {claim.identifier for claim in item.claims}.isdisjoint({"c6", "c7"})


def test_symbol_definition_and_hypothesis_selection_is_structural_and_scoped() -> None:
    item = local_item(make_project())

    assert {symbol.identifier for symbol in item.symbols} == {"sym:x", "sym:f"}
    assert [definition.identifier for definition in item.definitions] == ["def:f"]
    assert [hypothesis.identifier for hypothesis in item.hypotheses] == ["hyp:x"]
    assert [candidate.identifier for candidate in item.symbol_candidates] == ["cand:z"]
    assert "sym:y" not in {symbol.identifier for symbol in item.symbols}
    assert "def:y" not in {definition.identifier for definition in item.definitions}


def test_directly_relevant_result_dependency_is_included_only() -> None:
    item = local_item(make_project())

    assert [node.identifier for node in item.dependencies] == ["lem:needed"]
    assert "lem:unrelated" not in {node.identifier for node in item.dependencies}


def test_provenance_survives_canonical_serialization() -> None:
    item = local_item(make_project())
    payload = json.loads(item.canonical_json())

    assert payload["result"]["source"] == {
        "file": "paper.tex",
        "start_line": 2,
        "end_line": 4,
    }
    claim_payload = next(claim for claim in payload["claims"] if claim["identifier"] == "c2")
    assert claim_payload["source"]["start_offset"] == 130
    edge_payload = next(
        edge for edge in payload["support_relations"] if edge["identifier"] == "e-local-prior"
    )
    assert edge_payload["source"]["start_offset"] == 130
    assert edge_payload["evidence"][0]["source"]["start_offset"] == 130
    assert payload["dependencies"][0]["source"]["start_line"] == 50


def test_confident_structure_can_be_context_but_never_triggers() -> None:
    item = local_item(make_project())
    assert "e-confident" in {edge.identifier for edge in item.support_relations}
    assert "e-confident" not in item.trigger_relation_identifiers

    confident_only = build_review_context(make_project(include_uncertain=False))
    assert confident_only.items == []


def test_ambiguous_symbol_candidate_alone_does_not_create_review_item() -> None:
    project = make_project(include_uncertain=False)
    assert project.symbol_table.candidates[0].status == InferenceStatus.AMBIGUOUS
    assert build_review_context(project).items == []


def test_serialization_and_order_are_deterministic_and_backend_object_free() -> None:
    first = make_project()
    second = make_project()
    second.proof_support_graph.edges.reverse()
    second.proof_support_graph.claims.reverse()
    second.symbol_table.symbols.reverse()
    second.symbol_table.definitions.reverse()
    second.dependency_graph.nodes.reverse()
    second.dependency_graph.edges.reverse()

    first_json = build_review_context(first).canonical_json()
    second_json = build_review_context(second).canonical_json()
    assert first_json == second_json
    assert "spacy" not in first_json.lower()
    decoded = json.loads(first_json)
    assert isinstance(decoded, dict)
