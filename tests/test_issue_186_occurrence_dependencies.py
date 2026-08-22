from __future__ import annotations

import re
from pathlib import Path

from thorn.canonical_proof_ir import CanonicalNodeKind, build_canonical_proof_ir
from thorn.dependencies import DependencyResolution
from thorn.eval_review import build_result_review_context
from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.report import build_report
from thorn.semantic_review_render import build_semantic_review_request
from thorn.support import SupportKind

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


def _write_main(path: Path, body: str) -> None:
    path.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body.strip()}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )


def _result_reference_edges(project, result_identifier: str):
    claim_ids = {
        claim.identifier
        for claim in project.proof_support_graph.claims_for_result(result_identifier)
    }
    return [
        edge
        for edge in project.proof_support_graph.edges
        if edge.target_claim_identifier in claim_ids
        and edge.kind == SupportKind.RESULT_REFERENCE
    ]


def test_repeated_target_occurrence_fails_closed_across_consumers(tmp_path: Path) -> None:
    main = tmp_path / "main.tex"
    shared = tmp_path / "shared.tex"
    _write_main(
        main,
        r"""
\input{shared}
\input{shared}
\begin{theorem}\label{thm:main}
$Q(2)$.
\end{theorem}
\begin{proof}
By Lemma~\ref{lem:shared}, $Q(2)$.
\end{proof}
""",
    )
    shared.write_text(
        r"""\begin{lemma}\label{lem:shared}
For every natural $x$, if $P(x)$, then $Q(x)$.
\end{lemma}
\begin{proof}Immediate.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main, linguistic_frontend=StaticDependencyFrontend())
    dependency = next(
        edge
        for edge in project.dependency_graph.edges
        if edge.source_identifier == "thm:main" and edge.target_label == "lem:shared"
    )

    assert dependency.resolution == DependencyResolution.AMBIGUOUS
    assert dependency.target_identifier is None
    assert len(dependency.target_occurrence_ids) == 2
    assert len(set(dependency.target_occurrence_ids)) == 2
    assert project.dependency_graph.direct_dependency_ids("thm:main") == []
    assert project.dependency_graph.transitive_dependency_ids("thm:main") == []

    support_edges = _result_reference_edges(project, "thm:main")
    assert len(support_edges) == 1
    assert support_edges[0].status != InferenceStatus.CONFIDENT
    assert support_edges[0].confidence is None

    review_item = build_result_review_context(project, "thm:main").items[0]
    assert review_item.dependencies == []

    request = build_semantic_review_request(review_item)
    proof_ir = build_canonical_proof_ir(project.unit("thm:main"), request)
    assert not any(node.kind == CanonicalNodeKind.DEPENDENCY for node in proof_ir.nodes)

    report = build_report(project)
    report_result = next(item for item in report.results if item.identifier == "thm:main")
    assert report_result.dependencies == ()


def test_repeated_reference_to_unique_target_collapses_with_provenance(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    repeated = tmp_path / "repeated.tex"
    _write_main(
        main,
        r"""
\begin{lemma}\label{lem:unique}
The unique fact holds.
\end{lemma}
\begin{proof}Immediate.\end{proof}
\input{repeated}
\input{repeated}
""",
    )
    repeated.write_text(
        r"""\begin{theorem}\label{thm:repeated}
The conclusion follows from Lemma~\ref{lem:unique}.
\end{theorem}
\begin{proof}Apply Lemma~\ref{lem:unique}.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main)
    dependencies = [
        edge
        for edge in project.dependency_graph.edges
        if edge.source_identifier == "thm:repeated" and edge.target_label == "lem:unique"
    ]

    assert len(dependencies) == 2
    for dependency in dependencies:
        assert dependency.resolution == DependencyResolution.RESOLVED
        assert dependency.target_identifier == "lem:unique"
        assert len(dependency.source_occurrence_ids) == 2
        assert len(set(dependency.source_occurrence_ids)) == 2
        assert len(dependency.target_occurrence_ids) == 1

    assert project.workspace is not None
    expected_source_occurrences = [
        fact.occurrence_id
        for fact in project.workspace.references
        if fact.name == "lem:unique"
    ]
    assert dependencies[0].source_occurrence_ids == expected_source_occurrences
    assert dependencies[1].source_occurrence_ids == expected_source_occurrences
    assert project.dependency_graph.direct_dependency_ids("thm:repeated") == ["lem:unique"]


def test_same_physical_target_repeated_through_nested_include_is_ambiguous(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    wrapper = tmp_path / "wrapper.tex"
    shared = tmp_path / "shared.tex"
    _write_main(
        main,
        r"""
\input{wrapper}
\input{wrapper}
\begin{theorem}\label{thm:main}
See Lemma~\ref{lem:shared}.
\end{theorem}
\begin{proof}By Lemma~\ref{lem:shared}, the claim follows.\end{proof}
""",
    )
    wrapper.write_text("\\input{shared}\n", encoding="utf-8")
    shared.write_text(
        r"""\begin{lemma}\label{lem:shared}
The nested shared fact holds.
\end{lemma}
\begin{proof}Immediate.\end{proof}
""",
        encoding="utf-8",
    )

    project = extract_project(main)
    edges = [
        edge
        for edge in project.dependency_graph.edges
        if edge.source_identifier == "thm:main" and edge.target_label == "lem:shared"
    ]

    assert len(edges) == 2
    assert all(edge.resolution == DependencyResolution.AMBIGUOUS for edge in edges)
    assert all(len(edge.target_occurrence_ids) == 2 for edge in edges)
    assert project.dependency_graph.direct_dependency_ids("thm:main") == []


def test_physical_duplicate_labels_in_separate_files_remain_ambiguous(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main.tex"
    first = tmp_path / "first.tex"
    second = tmp_path / "second.tex"
    _write_main(
        main,
        r"""
\input{first}
\input{second}
\begin{theorem}\label{thm:main}
See Lemma~\ref{lem:duplicate}.
\end{theorem}
\begin{proof}Immediate.\end{proof}
""",
    )
    first.write_text(
        "\\begin{lemma}\\label{lem:duplicate}First.\\end{lemma}\n",
        encoding="utf-8",
    )
    second.write_text(
        "\\begin{lemma}\\label{lem:duplicate}Second.\\end{lemma}\n",
        encoding="utf-8",
    )

    project = extract_project(main)
    edge = next(
        edge
        for edge in project.dependency_graph.edges
        if edge.source_identifier == "thm:main" and edge.target_label == "lem:duplicate"
    )

    assert edge.resolution == DependencyResolution.AMBIGUOUS
    assert edge.target_identifier is None
    assert len(edge.target_occurrence_ids) == 2
