from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from thorn.analysis import analyze_project
from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import SourceSpan
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.spacy_linguistic import SpacyLinguisticFrontend
from thorn.support import Claim, ClaimForm, ProofSupportGraph, SupportEdge, SupportKind

_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


class StaticDependencyFrontend:
    name = "static-dependencies"

    def parse(self, text: str) -> LinguisticDocument:
        tokens = [
            LinguisticToken(
                index=0,
                text="predicate",
                lemma="predicate",
                pos="VERB",
                dependency="ROOT",
                head_index=0,
                sentence_index=0,
                start=0,
                end=0,
            )
        ]
        for match in _PLACEHOLDER_RE.finditer(text):
            tokens.append(
                LinguisticToken(
                    index=len(tokens),
                    text=match.group(0),
                    lemma=match.group(0),
                    pos="PROPN",
                    dependency="obl",
                    head_index=0,
                    sentence_index=0,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return LinguisticDocument(text=text, tokens=tokens)


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


def test_dependency_signature_is_structural_not_lexical() -> None:
    first = LinguisticDocument(
        text="THORNRESULT1 yields THORNCLAIM1",
        tokens=[
            LinguisticToken(
                index=0,
                text="THORNRESULT1",
                lemma="THORNRESULT1",
                pos="PROPN",
                dependency="nsubj",
                head_index=1,
                sentence_index=0,
                start=0,
                end=12,
            ),
            LinguisticToken(
                index=1,
                text="yields",
                lemma="yield",
                pos="VERB",
                dependency="ROOT",
                head_index=1,
                sentence_index=0,
                start=13,
                end=19,
            ),
        ],
    )
    second = LinguisticDocument(
        text="THORNRESULT1 proves THORNCLAIM1",
        tokens=[
            LinguisticToken(
                index=0,
                text="THORNRESULT1",
                lemma="THORNRESULT1",
                pos="PROPN",
                dependency="nsubj",
                head_index=1,
                sentence_index=0,
                start=0,
                end=12,
            ),
            LinguisticToken(
                index=1,
                text="proves",
                lemma="prove",
                pos="VERB",
                dependency="ROOT",
                head_index=1,
                sentence_index=0,
                start=13,
                end=19,
            ),
        ],
    )

    assert first.root_path_signature(0) == second.root_path_signature(0)
    assert first.root_path_signature(0) == ["PROPN:nsubj", "VERB:ROOT"]
    assert "yield" not in " ".join(first.root_path_signature(0))
    assert "prove" not in " ".join(second.root_path_signature(0))


def test_spacy_adapter_immediately_normalizes_parser_objects() -> None:
    class FakeToken:
        def __init__(
            self,
            i: int,
            text: str,
            lemma: str,
            pos: str,
            dep: str,
            idx: int,
        ) -> None:
            self.i = i
            self.text = text
            self.lemma_ = lemma
            self.pos_ = pos
            self.dep_ = dep
            self.idx = idx
            self.head: FakeToken = self

    root = FakeToken(0, "follows", "follow", "VERB", "ROOT", 0)
    ref = FakeToken(1, "THORNRESULT1", "THORNRESULT1", "PROPN", "obl", 8)
    ref.head = root

    class FakeSentence:
        def __iter__(self) -> Any:
            return iter((root, ref))

    class FakeDoc:
        def __iter__(self) -> Any:
            return iter((root, ref))

        @property
        def sents(self) -> tuple[FakeSentence, ...]:
            return (FakeSentence(),)

    loaded: list[str] = []

    def loader(model_name: str) -> Any:
        loaded.append(model_name)
        return lambda _text: FakeDoc()

    frontend = SpacyLinguisticFrontend(model_name="fake-en", loader=loader)
    document = frontend.parse("follows THORNRESULT1")

    assert loaded == ["fake-en"]
    assert document.tokens[1].head_index == 0
    assert document.tokens[1].dependency == "obl"
    assert document.model_dump() == {
        "text": "follows THORNRESULT1",
        "tokens": [
            {
                "index": 0,
                "text": "follows",
                "lemma": "follow",
                "pos": "VERB",
                "dependency": "ROOT",
                "head_index": 0,
                "sentence_index": 0,
                "start": 0,
                "end": 7,
            },
            {
                "index": 1,
                "text": "THORNRESULT1",
                "lemma": "THORNRESULT1",
                "pos": "PROPN",
                "dependency": "obl",
                "head_index": 0,
                "sentence_index": 0,
                "start": 8,
                "end": 20,
            },
        ],
    }


def test_ambiguous_support_edge_is_ir_not_deterministic_support() -> None:
    source_claim = Claim(
        identifier="claim:source",
        result_identifier="thm:test",
        form=ClaimForm.PROSE,
        raw="A fact.",
        source=_span(0, 7),
    )
    target_claim = Claim(
        identifier="claim:target",
        result_identifier="thm:test",
        form=ClaimForm.PROSE,
        raw="A conclusion.",
        source=_span(8, 21),
    )
    edge = SupportEdge(
        identifier="edge:1",
        target_claim_identifier=target_claim.identifier,
        source_claim_identifier=source_claim.identifier,
        kind=SupportKind.PRIOR_CLAIM,
        source=_span(8, 21),
        raw_justification="A conclusion.",
        status=InferenceStatus.AMBIGUOUS,
        evidence=[
            StructuralEvidence(
                reason="dependency attachment permits a support reading",
                source=_span(8, 21),
                target=target_claim.source,
                context="A fact. A conclusion.",
                dependency_path=["PROPN:obl", "VERB:ROOT"],
                frontend="static-dependencies",
            )
        ],
    )
    graph = ProofSupportGraph(claims=[source_claim, target_claim], edges=[edge])

    assert graph.incoming_edges(target_claim.identifier) == [edge]
    assert graph.confident_incoming_edges(target_claim.identifier) == []
    assert graph.downstream_claim_ids(source_claim.identifier) == []
    assert graph.load_bearing_claim_ids() == []


def test_local_linguistic_frontend_adds_ambiguous_reference_candidate_only(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "linguistic.tex"
    tex.write_text(
        r"""\documentclass{article}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:base}
A base fact.
\end{lemma}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
Via Lemma~\ref{lem:base}, the conclusion follows.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    core_project = extract_project(tex)
    core_claim = core_project.proof_support_graph.claims_for_result("thm:main")[0]
    assert core_project.proof_support_graph.incoming_edges(core_claim.identifier) == []

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    claim = project.proof_support_graph.claims_for_result("thm:main")[0]
    candidates = project.proof_support_graph.incoming_edges(claim.identifier)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.kind == SupportKind.RESULT_REFERENCE
    assert candidate.target_label == "lem:base"
    assert candidate.status == InferenceStatus.AMBIGUOUS
    assert candidate.source.text(tex.read_text(encoding="utf-8")) == r"\ref{lem:base}"
    assert len(candidate.evidence) == 1
    assert candidate.evidence[0].target == claim.source
    assert candidate.evidence[0].context == claim.raw
    assert candidate.evidence[0].dependency_path == ["PROPN:obl", "VERB:ROOT"]
    assert candidate.evidence[0].frontend == "static-dependencies"
    assert project.proof_support_graph.confident_incoming_edges(claim.identifier) == []
    assert analyze_project(project) == []


def test_expository_reference_never_becomes_confident_from_parser_alone(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "exposition.tex"
    tex.write_text(
        r"""\documentclass{article}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{lemma}\label{lem:base}
A base fact.
\end{lemma}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
See Lemma~\ref{lem:base} for background; the conclusion is our goal.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    claim = project.proof_support_graph.claims_for_result("thm:main")[0]
    candidates = project.proof_support_graph.incoming_edges(claim.identifier)

    assert len(candidates) == 1
    assert candidates[0].status == InferenceStatus.AMBIGUOUS
    assert project.proof_support_graph.confident_incoming_edges(claim.identifier) == []
    assert analyze_project(project) == []
