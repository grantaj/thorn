from __future__ import annotations

from pathlib import Path

from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.linguistic_declarations import ProseDeclarationCapability, ProseDeclarationRole


class _DeclarationFrontend:
    name = "fixture-declarations"

    def parse(self, text: str) -> LinguisticDocument:
        sentence = "We call a map admissible if it is continuous."
        base = text.find(sentence)
        if base < 0:
            return LinguisticDocument(text=text)

        words = [
            ("We", "we", "PRON", "nsubj", 1),
            ("call", "call", "VERB", "ROOT", 1),
            ("a", "a", "DET", "det", 3),
            ("map", "map", "NOUN", "dobj", 1),
            ("admissible", "admissible", "ADJ", "oprd", 1),
            ("if", "if", "SCONJ", "mark", 8),
            ("it", "it", "PRON", "nsubj", 8),
            ("is", "be", "AUX", "cop", 8),
            ("continuous", "continuous", "ADJ", "advcl", 1),
        ]
        cursor = base
        tokens: list[LinguisticToken] = []
        for index, (surface, lemma, pos, dependency, head_index) in enumerate(words):
            start = text.find(surface, cursor)
            assert start >= 0
            end = start + len(surface)
            tokens.append(
                LinguisticToken(
                    index=index,
                    text=surface,
                    lemma=lemma,
                    pos=pos,
                    dependency=dependency,
                    head_index=head_index,
                    sentence_index=0,
                    start=start,
                    end=end,
                )
            )
            cursor = end
        return LinguisticDocument(text=text, tokens=tokens)


def _write_project(tmp_path: Path) -> Path:
    source = tmp_path / "paper.tex"
    source.write_text(
        r"""\documentclass{article}
\begin{document}
We call a map admissible if it is continuous.
\begin{theorem}\label{thm:main}
A conclusion holds.
\end{theorem}
\end{document}
""",
        encoding="utf-8",
    )
    return source


def test_project_candidate_has_exact_provenance_without_becoming_authority(
    tmp_path: Path,
) -> None:
    source = _write_project(tmp_path)
    raw = source.read_text(encoding="utf-8")
    project = extract_project(source, linguistic_frontend=_DeclarationFrontend())

    inventory = project.prose_declarations
    assert inventory is not None
    assert inventory.capability == ProseDeclarationCapability.COMPLETE
    assert inventory.frontend == "fixture-declarations"
    assert len(inventory.candidates) == 1

    candidate = inventory.candidates[0]
    assert candidate.role == ProseDeclarationRole.DEFINITION
    assert candidate.term == "admissible"
    assert candidate.status == InferenceStatus.AMBIGUOUS
    assert candidate.term_source.text(raw) == "admissible"
    assert candidate.source.text(raw) == "We call a map admissible if it is continuous."
    assert len(candidate.evidence) == 1
    assert candidate.evidence[0].source.text(raw) == "call"
    assert candidate.evidence[0].target == candidate.term_source
    assert candidate.evidence[0].frontend == "fixture-declarations"
    assert candidate.evidence[0].dependency_path == ["ADJ:oprd", "VERB:ROOT"]

    # The parser proposal is deliberately not fed into deterministic Symbol IR in Slice C.
    assert all(symbol.name != "admissible" for symbol in project.symbol_table.symbols)
    assert "prose_declarations" not in project.model_dump(mode="json")


def test_structural_only_extraction_advertises_reduced_prose_capability(
    tmp_path: Path,
) -> None:
    project = extract_project(_write_project(tmp_path))

    inventory = project.prose_declarations
    assert inventory is not None
    assert inventory.capability == ProseDeclarationCapability.REDUCED
    assert inventory.frontend is None
    assert inventory.candidates == []
    assert inventory.reasons
