from __future__ import annotations

from pathlib import Path

from thorn.evidence import InferenceStatus
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.llm_proof_language import (
    parse_source_rescue_request,
    project_llm_proof_language,
    render_source_rescue,
)
from thorn.proof_obligations import ObligationStatus
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import (
    SemanticTransformationKind,
    build_semantic_transformation_ir,
)
from thorn.support import SupportKind


def _build(path: Path, target: str):
    project = extract_project(path)
    unit = project.unit(target)
    context = build_result_review_context(project, target)
    request = build_semantic_review_request(context.items[0])
    semantic = build_semantic_transformation_ir(
        unit,
        request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    return project, semantic, project_llm_proof_language(semantic)


def _write_definition_case(path: Path, definition: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{assumption}}{{Assumption}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{assumption}}\label{{ass:scale}}
Let $S={definition}$.
\end{{assumption}}
\begin{{theorem}}\label{{thm:main}}
Under Assumption~\ref{{ass:scale}}, $Q(S)$.
\end{{theorem}}
\begin{{proof}}
\[
Q(S)
\]
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def test_statement_dependency_survives_and_is_source_rescuable(tmp_path: Path) -> None:
    good = tmp_path / "definition-good.tex"
    bad = tmp_path / "definition-bad.tex"
    _write_definition_case(good, r"f(\tau^2)")
    _write_definition_case(bad, r"f(\tau)")

    _good_project, _good_ir, good_doc = _build(good, "thm:main")
    _bad_project, _bad_ir, bad_doc = _build(bad, "thm:main")

    good_handle = next(
        source
        for source in good_doc.sources
        if source.referenced_result_identifier == "ass:scale"
    )
    bad_handle = next(
        source
        for source in bad_doc.sources
        if source.referenced_result_identifier == "ass:scale"
    )
    assert r"\tau^2" in good_handle.text
    assert r"\tau^2" not in bad_handle.text
    assert good_doc.render_initial() != bad_doc.render_initial()

    rescue = render_source_rescue(
        good_doc,
        parse_source_rescue_request(good_doc, f"NEED_SOURCE {good_handle.address}"),
    )
    assert r"\tau^2" in rescue.text


def _write_precondition_case(path: Path, available: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{lemma}}{{Lemma}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{lemma}}\label{{lem:transfer}}
If $H_B$, then $C$.
\end{{lemma}}
\begin{{proof}}
\[
H_B \Rightarrow C
\]
\end{{proof}}
\begin{{theorem}}\label{{thm:main}}
$C$.
\end{{theorem}}
\begin{{proof}}
We have ${available}$.
By Lemma~\ref{{lem:transfer}}, $C$.
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def test_result_application_keeps_unmet_precondition_distinct_from_control(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "precondition-bad.tex"
    good = tmp_path / "precondition-good.tex"
    _write_precondition_case(bad, "H_A")
    _write_precondition_case(good, "H_B")

    _bad_project, bad_ir, bad_doc = _build(bad, "thm:main")
    _good_project, good_ir, good_doc = _build(good, "thm:main")

    bad_app = next(
        item
        for item in bad_ir.transformations
        if item.kind == SemanticTransformationKind.RESULT_APPLICATION
    )
    good_app = next(
        item
        for item in good_ir.transformations
        if item.kind == SemanticTransformationKind.RESULT_APPLICATION
    )
    bad_obligation = bad_ir.obligation(bad_app.obligation_addresses[0])
    good_obligation = good_ir.obligation(good_app.obligation_addresses[0])

    assert bad_obligation.status == ObligationStatus.UNRESOLVED
    assert good_obligation.status == ObligationStatus.DISCHARGED
    assert bad_app.status == InferenceStatus.UNRESOLVED
    assert good_app.status == InferenceStatus.CONFIDENT
    assert "NEED " in bad_doc.render_initial()
    assert "NEED " not in good_doc.render_initial()


def test_generic_asserted_support_is_preserved_without_confidence_promotion(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "asserted-property.tex"
    tex.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:main}
$B$.
\end{theorem}
\begin{proof}
We have $A$.
Using the asserted implication from $A$ to smoothness, $B$.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    project, semantic, document = _build(tex, "thm:main")
    claims = project.proof_support_graph.claims_for_result("thm:main")
    relation = next(
        edge
        for edge in project.proof_support_graph.incoming_edges(claims[-1].identifier)
        if edge.kind == SupportKind.NAMED_PROPERTY
    )
    assert relation.status == InferenceStatus.UNRESOLVED
    assert relation.confidence is None
    assert relation.named_property is not None
    assert "asserted implication" in relation.named_property

    transformation = next(
        item
        for item in semantic.transformations
        if item.kind == SemanticTransformationKind.NAMED_PROPERTY_APPLICATION
    )
    assert transformation.status == InferenceStatus.UNRESOLVED
    assert transformation.opaque_source_addresses
    assert "asserted implication" in document.render_initial()

    address = transformation.opaque_source_addresses[0]
    rescue = render_source_rescue(
        document,
        parse_source_rescue_request(document, f"NEED_SOURCE {address}"),
    )
    assert "asserted implication" in rescue.text
