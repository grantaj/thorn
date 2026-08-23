from __future__ import annotations

from pathlib import Path

import pytest

from thorn.eval_review import build_result_review_context
from thorn.frontends.tree_sitter import TreeSitterLatexFrontend
from thorn.latex import extract_project
from thorn.linguistic_statements import StatementScopeKind
from thorn.review_workflow import prepare_proof_review
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend


def _write_project(tmp_path: Path) -> Path:
    source = tmp_path / "paper.tex"
    source.write_text(
        r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\section{Setup}\label{sec:setup}
A historical aside discusses an unrelated example.

The domain is
\[
 D=\{x:0<x<1\}.
\]
An object is \arbitrarywrapper{regular} when it belongs to the domain.

\begin{theorem}\label{thm:main}
Every regular object in the domain has the stated property.
\end{theorem}
\begin{proof}
Take a regular object in the domain. The property follows.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )
    return source


def _local_spacy_or_skip() -> SpacyLinguisticFrontend:
    frontend = SpacyLinguisticFrontend()
    try:
        frontend.parse("A sentence.")
    except LinguisticFrontendUnavailable as exc:
        pytest.skip(str(exc))
    return frontend


def test_tree_sitter_exports_control_syntax_without_semantic_macro_roles(
    tmp_path: Path,
) -> None:
    source = _write_project(tmp_path)
    parsed = TreeSitterLatexFrontend().parse_project(source)
    file = parsed.file(source)
    raw = file.raw

    assert file.syntax_complete
    masked = {
        syntax.span.text(raw)
        for syntax in file.syntax
    }
    assert r"\arbitrarywrapper" in masked
    assert "{" in masked
    assert "}" in masked
    assert any(text.startswith(r"\section") for text in masked)
    assert any(text.startswith(r"\label") for text in masked)
    assert not any(text == "regular" for text in masked)


def test_spacy_statements_map_clean_segmentation_back_to_exact_source(
    tmp_path: Path,
) -> None:
    source = _write_project(tmp_path)
    project = extract_project(
        source,
        frontend=TreeSitterLatexFrontend(),
        linguistic_frontend=_local_spacy_or_skip(),
    )

    inventory = project.linguistic_statements
    assert inventory is not None
    assert inventory.complete

    exact_texts = {statement.text for statement in inventory.statements}
    assert (
        "The domain is\n"
        "\\[\n"
        " D=\\{x:0<x<1\\}.\n"
        "\\]"
    ) in exact_texts
    assert (
        r"An object is \arbitrarywrapper{regular} when it belongs to the domain."
        in exact_texts
    )
    assert "A historical aside discusses an unrelated example." in exact_texts

    assert all(r"\section" not in statement.text for statement in inventory.statements)
    assert all(r"\label" not in statement.text for statement in inventory.statements)
    result_statements = [
        statement
        for statement in inventory.statements
        if statement.result_identifier == "thm:main"
    ]
    assert {statement.scope_kind for statement in result_statements} == {
        StatementScopeKind.RESULT_STATEMENT,
        StatementScopeKind.RESULT_PROOF,
    }


def test_review_reachability_uses_generic_statement_relevance_and_bounded_sources(
    tmp_path: Path,
) -> None:
    source = _write_project(tmp_path)
    project = extract_project(
        source,
        frontend=TreeSitterLatexFrontend(),
        linguistic_frontend=_local_spacy_or_skip(),
    )

    context = build_result_review_context(project, "thm:main")
    assert len(context.items) == 1
    nearby = {item.text for item in context.items[0].nearby_context}
    domain_statement = "The domain is\n\\[\n D=\\{x:0<x<1\\}.\n\\]"
    wrapper_statement = (
        r"An object is \arbitrarywrapper{regular} when it belongs to the domain."
    )
    assert domain_statement in nearby
    assert wrapper_statement in nearby
    assert "A historical aside discusses an unrelated example." not in nearby

    prepared = prepare_proof_review(project, project.unit("thm:main"))
    statement_sources = [
        item
        for item in prepared.document.sources
        if item.ir_identifier.startswith("statement-context:")
    ]
    source_texts = {item.text for item in statement_sources}
    assert domain_statement in source_texts
    assert wrapper_statement in source_texts
    assert "A historical aside discusses an unrelated example." not in source_texts

    initial = prepared.document.render_initial()
    assert "CONTEXT @SCTX" in initial
    assert wrapper_statement not in initial
    assert domain_statement not in initial
