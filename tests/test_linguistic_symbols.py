from __future__ import annotations

import re
from pathlib import Path

from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken


class StaticDependencyFrontend:
    name = "static-dependencies"

    def parse(self, text: str) -> LinguisticDocument:
        matches = list(re.finditer(r"\S+", text))
        tokens = [
            LinguisticToken(
                index=index,
                text=match.group(0),
                lemma=match.group(0),
                pos="VERB" if index == 0 else "X",
                dependency="ROOT" if index == 0 else "dep",
                head_index=0,
                sentence_index=0,
                start=match.start(),
                end=match.end(),
            )
            for index, match in enumerate(matches)
        ]
        return LinguisticDocument(text=text, tokens=tokens)


def test_linguistic_symbol_ablation_preserves_source_without_candidates(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "introductions.tex"
    tex.write_text(
        r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
Fix $x\in X$ for the argument. Put $c:=a+b$ for later use.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    core = extract_project(tex)
    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())

    # Generic NLP must not invent additional symbol semantics. The deterministic
    # symbol table is identical whether or not a linguistic frontend is present.
    assert project.symbol_table == core.symbol_table
    assert project.symbol_table.candidates == []
    assert all(symbol.name not in {"x", "c"} for symbol in project.symbol_table.symbols)

    # The ablation removes interpretation, not evidence: exact source-mapped
    # statements remain available independently to advisory context/review.
    inventory = project.linguistic_statements
    assert inventory is not None
    assert inventory.complete
    assert any(r"$x\in X$" in statement.text for statement in inventory.statements)
    assert any(r"$c:=a+b$" in statement.text for statement in inventory.statements)
