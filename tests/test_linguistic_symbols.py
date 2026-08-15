from __future__ import annotations

import re
from pathlib import Path

from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.symbols import SymbolCandidateKind

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


def test_linguistic_introductions_remain_candidates_not_declared_symbols(
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
    assert core.symbol_table.candidates == []
    assert all(symbol.name not in {"x", "c"} for symbol in core.symbol_table.symbols)

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    candidates = {candidate.name: candidate for candidate in project.symbol_table.candidates}

    assert set(candidates) == {"x", "c"}
    assert candidates["x"].kind == SymbolCandidateKind.INTRODUCTION
    assert candidates["c"].kind == SymbolCandidateKind.DEFINITION
    assert candidates["c"].definition_operator == ":="
    assert candidates["c"].expression_latex == "a+b"
    assert candidates["x"].status == InferenceStatus.AMBIGUOUS
    assert candidates["c"].status == InferenceStatus.AMBIGUOUS
    assert candidates["x"].source.text(tex.read_text(encoding="utf-8")) == "x"
    assert "Fix" in candidates["x"].raw_context
    assert candidates["x"].evidence[0].dependency_path == ["PROPN:obl", "VERB:ROOT"]
    assert all(symbol.name not in {"x", "c"} for symbol in project.symbol_table.symbols)
