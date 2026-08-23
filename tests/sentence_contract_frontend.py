from __future__ import annotations

import re

from thorn.linguistic import LinguisticDocument, LinguisticToken

_TOKEN_RE = re.compile(r"\S+")


class SentenceContractFrontend:
    """Deterministic test double for generic token/sentence observations only.

    It deliberately knows nothing about mathematical words, declaration cues, roles,
    or relevance. Production uses the configured LinguisticFrontend; this fixture only
    supplies stable sentence indices and exact token offsets to backend-independent
    tests that must not depend on a downloaded NLP model.
    """

    name = "contract-generic-sentences"

    def parse(self, text: str) -> LinguisticDocument:
        tokens: list[LinguisticToken] = []
        sentence_index = 0
        sentence_root: int | None = None
        for match in _TOKEN_RE.finditer(text):
            index = len(tokens)
            if sentence_root is None:
                sentence_root = index
            token_text = match.group(0)
            tokens.append(
                LinguisticToken(
                    index=index,
                    text=token_text,
                    lemma=token_text.casefold(),
                    pos="X",
                    dependency="ROOT" if index == sentence_root else "dep",
                    head_index=sentence_root,
                    sentence_index=sentence_index,
                    start=match.start(),
                    end=match.end(),
                )
            )
            if token_text.rstrip().endswith((".", "!", "?")):
                sentence_index += 1
                sentence_root = None
        return LinguisticDocument(text=text, tokens=tokens)
