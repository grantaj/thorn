from __future__ import annotations

import re
from pathlib import Path

from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.support import ClaimForm, QualifierKind

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


def test_noncanonical_trailing_binder_is_preserved_as_ambiguous_candidate(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "binder.tex"
    tex.write_text(
        r"""\documentclass{article}
\newtheorem{theorem}{Theorem}
\begin{document}
\begin{theorem}\label{thm:main}
A conclusion.
\end{theorem}
\begin{proof}
\[
a_n = 0.
\]
where $n\ge 1$ throughout the argument.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    core = extract_project(tex)
    core_claims = core.proof_support_graph.claims_for_result("thm:main")
    assert len(core_claims) == 2
    assert core_claims[0].form == ClaimForm.DISPLAY
    assert core_claims[0].qualifiers == []

    project = extract_project(tex, linguistic_frontend=StaticDependencyFrontend())
    claims = project.proof_support_graph.claims_for_result("thm:main")

    assert len(claims) == 2
    assert claims[0].form == ClaimForm.DISPLAY
    assert len(claims[0].qualifiers) == 1
    qualifier = claims[0].qualifiers[0]
    assert qualifier.kind == QualifierKind.TRAILING_BINDER
    assert qualifier.status == InferenceStatus.AMBIGUOUS
    assert qualifier.bound_names[0].name == "n"
    assert qualifier.evidence[0].context.endswith("where $n\\ge 1$ throughout the argument.")
    assert qualifier.evidence[0].dependency_path == ["PROPN:obl", "VERB:ROOT"]

    # Because the parse is not semantically decisive, the prose remains a claim
    # rather than being swallowed as though the binder interpretation were certain.
    assert claims[1].form == ClaimForm.PROSE
    assert claims[1].raw == r"where $n\ge 1$ throughout the argument."
