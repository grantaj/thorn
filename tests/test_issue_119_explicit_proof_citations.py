from __future__ import annotations

import re
from pathlib import Path

from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.lean_export import LeanExportStatus, project_lean
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.proof_obligations import ObligationStatus
from thorn.proof_visualizer import build_proof_visualizer_data
from thorn.review_workflow import prepare_proof_review
from thorn.semantic_review import build_review_context
from thorn.semantic_transformations import SemanticTransformationKind
from thorn.support import SupportKind

_ROOT = Path(__file__).resolve().parents[1]
_QUICKSTART = _ROOT / "examples" / "quickstart" / "clean" / "paper.tex"
_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


class StaticDependencyFrontend:
    """Parser-neutral local-NLP stand-in that attaches every typed placeholder."""

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


def _result_edges(project, result_identifier: str):
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


def _write_application_paper(
    path: Path,
    *,
    target: str,
    proof: str,
) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{lemma}}{{Lemma}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{lemma}}\label{{lem:transfer}}
For every natural $x$, if $P(x)$, then $Q(x)$.
\end{{lemma}}
\begin{{proof}}
Assume $P(x)$. Then $Q(x)$.
\end{{proof}}
\begin{{theorem}}\label{{thm:main}}
{target}
\end{{theorem}}
\begin{{proof}}
{proof}
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def test_normal_linguistic_quickstart_recovers_confident_explicit_applications() -> None:
    project = extract_project(
        _QUICKSTART,
        linguistic_frontend=StaticDependencyFrontend(),
    )
    edges = _result_edges(project, "thm:main")

    assert len(edges) == 2
    assert all(edge.explicit for edge in edges)
    assert all(edge.status == InferenceStatus.CONFIDENT for edge in edges)
    assert all(edge.confidence == 1.0 for edge in edges)
    assert all(edge.evidence[-1].frontend == "thorn-math" for edge in edges)
    assert all(
        "unique fully lowered target/application match" in edge.evidence[-1].reason
        for edge in edges
    )

    # The proof graph and targeted review selector consume the same recovered
    # support status; this is not a Lean-only promotion.
    visualizer = build_proof_visualizer_data(project)
    main_supports = [
        support
        for claim in visualizer["proofUnits"]["thm:main"]["claims"]
        for support in claim["supports"]
        if support["kind"] == SupportKind.RESULT_REFERENCE.value
    ]
    assert len(main_supports) == 2
    assert all(item["status"] == InferenceStatus.CONFIDENT.value for item in main_supports)
    assert not any(
        item.result.identifier == "thm:main" for item in build_review_context(project).items
    )

    prepared = prepare_proof_review(project, project.unit("thm:main"))
    applications = [
        item
        for item in prepared.state.transformations
        if item.kind
        in {
            SemanticTransformationKind.RESULT_APPLICATION,
            SemanticTransformationKind.RESULT_SPECIALIZATION,
        }
    ]
    assert len(applications) == 2
    assert all(item.status == InferenceStatus.CONFIDENT for item in applications)

    export = project_lean(prepared.state)
    assert export.status == LeanExportStatus.COMPLETE
    assert export.obligations == ()
    assert "sorry" not in export.source


def test_application_like_nonmatching_reference_remains_ambiguous(tmp_path: Path) -> None:
    tex = tmp_path / "nonmatching.tex"
    _write_application_paper(
        tex,
        target="$R(2)$.",
        proof=r"By Lemma~\ref{lem:transfer}, $R(2)$.",
    )

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    edges = _result_edges(project, "thm:main")

    assert len(edges) == 1
    assert edges[0].explicit is True
    assert edges[0].status == InferenceStatus.AMBIGUOUS
    assert edges[0].confidence is None
    assert all(item.frontend != "thorn-math" for item in edges[0].evidence)


def test_explicit_binding_that_disagrees_with_target_stays_ambiguous(tmp_path: Path) -> None:
    tex = tmp_path / "bad-binding.tex"
    _write_application_paper(
        tex,
        target="$Q(2)$.",
        proof=r"By Lemma~\ref{lem:transfer}, with $x=3$, we obtain $Q(2)$.",
    )

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    edges = _result_edges(project, "thm:main")

    assert len(edges) == 1
    assert edges[0].status == InferenceStatus.AMBIGUOUS
    assert edges[0].confidence is None
    assert all(item.frontend != "thorn-math" for item in edges[0].evidence)


def test_expository_result_reference_stays_ambiguous_even_with_matching_math(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "expository.tex"
    _write_application_paper(
        tex,
        target="$Q(2)$.",
        proof=(
            r"Using coordinates is convenient here; later see "
            r"Lemma~\ref{lem:transfer} for background; the related target is $Q(2)$."
        ),
    )

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    edges = _result_edges(project, "thm:main")

    # The legacy cue extractor sees the unrelated leading "Using" and the local
    # NLP layer therefore retains the reference as a candidate. Mathematical
    # target compatibility alone must not launder that expository role.
    assert len(edges) == 1
    assert edges[0].explicit is True
    assert edges[0].status == InferenceStatus.AMBIGUOUS
    assert edges[0].confidence is None
    assert all(item.frontend != "thorn-math" for item in edges[0].evidence)


def test_missing_precondition_keeps_application_identity_but_not_checkability(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "missing-precondition.tex"
    _write_application_paper(
        tex,
        target="$Q(2)$.",
        proof=r"From Lemma~\ref{lem:transfer}, $Q(2)$.",
    )

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    edges = _result_edges(project, "thm:main")
    assert len(edges) == 1
    assert edges[0].status == InferenceStatus.CONFIDENT
    assert "separate proof obligation" in edges[0].evidence[-1].reason

    prepared = prepare_proof_review(project, project.unit("thm:main"))
    applications = [
        item
        for item in prepared.state.transformations
        if item.kind == SemanticTransformationKind.RESULT_APPLICATION
    ]
    assert len(applications) == 1
    application = applications[0]
    assert application.status == InferenceStatus.UNRESOLVED
    assert len(application.obligation_addresses) == 1
    obligation = prepared.state.obligation(application.obligation_addresses[0])
    assert obligation.status == ObligationStatus.UNRESOLVED
    assert obligation.satisfied_by == ()

    export = project_lean(prepared.state)
    assert export.status == LeanExportStatus.PARTIAL
    assert export.obligations
    assert "sorry" in export.source
