from __future__ import annotations

from pathlib import Path

import pytest

from thorn.frontends.tree_sitter import TreeSitterLatexFrontend
from thorn.latex import extract_project
from thorn.linguistic_statements import StatementScopeKind
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
    masked = {syntax.span.text(raw) for syntax in file.syntax}
    assert r"\arbitrarywrapper" in masked
    assert "{" in masked
    assert "}" in masked
    assert any(text.startswith(r"\section") for text in masked)
    assert any(text.startswith(r"\label") for text in masked)
    assert not any(text == "regular" for text in masked)


def test_tree_sitter_terminal_math_punctuation_uses_content_tail(
    tmp_path: Path,
) -> None:
    source = tmp_path / "math.tex"
    source.write_text(
        r"""\documentclass{article}
\begin{document}
The first quantity is
\[
  |a_n(x)|<\varepsilon \qquad n\geq N.
\]
The second quantity is
\[
  x. y
\]
and this sentence continues.
\end{document}
""",
        encoding="utf-8",
    )
    parsed = TreeSitterLatexFrontend().parse_project(source)
    file = parsed.file(source)
    displayed = [math for math in file.math if math.delimiter == r"\[\]"]

    assert len(displayed) == 2
    assert displayed[0].terminal_punctuation is not None
    assert displayed[0].terminal_punctuation.text(file.raw) == "."
    assert displayed[1].terminal_punctuation is None


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
    assert "The domain is\n\\[\n D=\\{x:0<x<1\\}.\n\\]" in exact_texts
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


def test_display_math_sentence_does_not_absorb_following_paragraph(tmp_path: Path) -> None:
    source = Path("eval/robustness/issue_101/clean_control.tex")
    if not source.exists():
        pytest.skip("repository robustness fixture unavailable")
    project = extract_project(
        source,
        frontend=TreeSitterLatexFrontend(),
        linguistic_frontend=_local_spacy_or_skip(),
    )
    inventory = project.linguistic_statements
    assert inventory is not None and inventory.complete

    definition = next(
        statement
        for statement in inventory.statements
        if statement.text.startswith("We say that the profiles are uniformly attenuating")
    )
    assert definition.text.endswith("\\]")
    assert "The next elementary observation" not in definition.text
    assert any(
        statement.text.startswith("The next elementary observation records the decay")
        for statement in inventory.statements
    )


def test_factorial_at_end_of_math_is_not_a_hard_sentence_boundary(tmp_path: Path) -> None:
    source = tmp_path / "factorial.tex"
    source.write_text(
        r"""\documentclass{article}
\begin{document}
There are $n!$ permutations. Another sentence follows.
\end{document}
""",
        encoding="utf-8",
    )
    project = extract_project(
        source,
        frontend=TreeSitterLatexFrontend(),
        linguistic_frontend=_local_spacy_or_skip(),
    )
    inventory = project.linguistic_statements
    assert inventory is not None and inventory.complete

    texts = [statement.text for statement in inventory.statements]
    assert r"There are $n!$ permutations." in texts
    assert "Another sentence follows." in texts


def test_multiple_sentences_inside_generic_macro_remain_distinct(tmp_path: Path) -> None:
    source = tmp_path / "wrapped.tex"
    source.write_text(
        r"""\documentclass{article}
\begin{document}
\emph{First sentence. Second sentence.}
\end{document}
""",
        encoding="utf-8",
    )
    project = extract_project(
        source,
        frontend=TreeSitterLatexFrontend(),
        linguistic_frontend=_local_spacy_or_skip(),
    )
    inventory = project.linguistic_statements
    assert inventory is not None and inventory.complete

    wrapped = [
        statement
        for statement in inventory.statements
        if statement.text in {"First sentence.", "Second sentence."}
    ]
    assert [statement.text for statement in wrapped] == [
        "First sentence.",
        "Second sentence.",
    ]
    assert len({statement.identifier for statement in wrapped}) == 2
    assert len({(statement.source.start_offset, statement.source.end_offset) for statement in wrapped}) == 2


def test_result_and_proof_extents_are_hard_linguistic_boundaries(tmp_path: Path) -> None:
    source = tmp_path / "scopes.tex"
    source.write_text(
        r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:main}
A conclusion holds
\end{theorem}
\begin{proof}
A proof begins here
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )
    project = extract_project(
        source,
        frontend=TreeSitterLatexFrontend(),
        linguistic_frontend=_local_spacy_or_skip(),
    )
    inventory = project.linguistic_statements
    assert inventory is not None and inventory.complete

    result = [
        statement
        for statement in inventory.statements
        if statement.result_identifier == "thm:main"
    ]
    assert any(
        statement.scope_kind == StatementScopeKind.RESULT_STATEMENT
        and "A conclusion holds" in statement.text
        for statement in result
    )
    assert any(
        statement.scope_kind == StatementScopeKind.RESULT_PROOF
        and "A proof begins here" in statement.text
        for statement in result
    )
    assert not any(
        "A conclusion holds" in statement.text and "A proof begins here" in statement.text
        for statement in inventory.statements
    )
