from __future__ import annotations

import re
from pathlib import Path

from thorn.canonical_proof_ir import CanonicalNodeKind, build_canonical_proof_ir
from thorn.dependencies import DependencyResolution
from thorn.eval_review import build_result_review_context
from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.semantic_review_render import build_semantic_review_request
from thorn.support import SupportKind
from thorn.workspace import WorkspaceResolution

_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


class StaticDependencyFrontend:
    """Parser-neutral NLP stand-in that attaches typed reference placeholders."""

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


def test_partial_workspace_cannot_prove_reference_uniqueness(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        "\\begin{lemma}\\label{lem:unique}\n"
        "For every natural $x$, if $P(x)$, then $Q(x)$.\n"
        "\\end{lemma}\n"
        "\\begin{proof}Immediate.\\end{proof}\n"
        "\\input{child}\n"
        "\\begin{theorem}\\label{thm:main}\n"
        "$Q(2)$.\n"
        "\\end{theorem}\n"
        "\\begin{proof}\n"
        "By Lemma~\\ref{lem:unique}, $Q(2)$.\n"
        "\\end{proof}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    child.write_text("\\input{main}\n", encoding="utf-8")

    project = extract_project(main, linguistic_frontend=StaticDependencyFrontend())

    assert project.workspace is not None
    assert project.workspace.resolution == WorkspaceResolution.PARTIAL

    dependency = next(
        edge
        for edge in project.dependency_graph.edges
        if edge.source_identifier == "thm:main" and edge.target_label == "lem:unique"
    )
    assert dependency.resolution == DependencyResolution.AMBIGUOUS
    assert dependency.target_identifier is None
    assert dependency.source_occurrence_ids
    assert dependency.target_occurrence_ids
    assert project.dependency_graph.direct_dependency_ids("thm:main") == []

    support_edges = [
        edge
        for edge in project.proof_support_graph.edges
        if edge.kind == SupportKind.RESULT_REFERENCE and edge.target_label == "lem:unique"
    ]
    assert support_edges
    assert all(edge.status != InferenceStatus.CONFIDENT for edge in support_edges)
    assert all(edge.confidence is None for edge in support_edges)

    review_item = build_result_review_context(project, "thm:main").items[0]
    assert review_item.dependencies == []
    request = build_semantic_review_request(review_item)
    proof_ir = build_canonical_proof_ir(project.unit("thm:main"), request)
    assert not any(node.kind == CanonicalNodeKind.DEPENDENCY for node in proof_ir.nodes)
