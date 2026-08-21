from __future__ import annotations

import re

from thorn.linguistic import LinguisticDocument, LinguisticToken

_STYLE_TERM = r"(?:\\[A-Za-z]+\{[^{}]+\}|[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3})"
_CONDITION = r"(?:when|if|whenever|provided\s+that)"
_CALLED = re.compile(
    rf"\b(?:is|are|will\s+be|shall\s+be)\s+(?P<cue>called|termed)\s+"
    rf"(?P<term>{_STYLE_TERM})\s+(?P<condition>{_CONDITION})\b",
    re.IGNORECASE,
)
_SAID = re.compile(
    rf"\b(?:is|are)\s+(?P<cue>said)\s+to\s+be\s+"
    rf"(?P<term>{_STYLE_TERM})\s+(?P<condition>{_CONDITION})\b",
    re.IGNORECASE,
)
_WE_SAY = re.compile(
    rf"\b(?P<we>we)\s+(?P<cue>say)\s+that\b[^.!?\n]{{1,160}}?"
    rf"\b(?:is|are)\s+(?P<term>{_STYLE_TERM})\s+"
    rf"(?P<condition>{_CONDITION})\b",
    re.IGNORECASE,
)
_BY_MEAN = re.compile(
    rf"\bby\s+(?:an?\s+)?(?P<term>{_STYLE_TERM})\s+"
    r"(?P<we>we)\s+(?P<cue>mean)\b",
    re.IGNORECASE,
)
_AMBIENT = re.compile(
    r"(?:^|(?<=[.!?])\s+|(?<=\n))"
    r"(?P<prefix>throughout|in\s+what\s+follows|henceforth|from\s+now\s+on|"
    r"unless\s+otherwise\s+stated|unless\s+specified\s+otherwise)\s*,?\s*"
    r"(?:(?:the|all|every|each)\s+)?"
    r"(?P<term>[A-Za-z][A-Za-z-]*(?:\s+[A-Za-z][A-Za-z-]*){0,5}?)\s+"
    r"(?P<copula>is|are)\b",
    re.IGNORECASE | re.MULTILINE,
)
_WRAPPER = re.compile(r"\\[A-Za-z]+\{(?P<inner>[^{}]+)\}\Z")


def _term_span(match: re.Match[str]) -> tuple[str, int, int]:
    raw = match.group("term")
    start = match.start("term")
    wrapper = _WRAPPER.fullmatch(raw.strip())
    if wrapper is None:
        leading = len(raw) - len(raw.lstrip())
        term = raw.strip()
        start += leading
        return term, start, start + len(term)
    inner_raw = wrapper.group("inner")
    term = inner_raw.strip()
    start += raw.find(inner_raw) + (len(inner_raw) - len(inner_raw.lstrip()))
    return term, start, start + len(term)


class DeclarationContractFrontend:
    """Deterministic test double exposing normalized grammatical facts only.

    Regexes live here solely to materialize stable LinguisticFrontend contract
    fixtures. Production authority never imports or uses this implementation.
    """

    name = "contract-declaration-fixture"

    def parse(self, text: str) -> LinguisticDocument:
        tokens: list[LinguisticToken] = []
        sentence_index = 0

        def add(
            token_text: str,
            *,
            start: int,
            end: int,
            lemma: str,
            pos: str,
            dependency: str,
            head_index: int | None = None,
        ) -> int:
            index = len(tokens)
            tokens.append(
                LinguisticToken(
                    index=index,
                    text=token_text,
                    lemma=lemma,
                    pos=pos,
                    dependency=dependency,
                    head_index=index if head_index is None else head_index,
                    sentence_index=sentence_index,
                    start=start,
                    end=end,
                )
            )
            return index

        for pattern, lemma in ((_CALLED, "call"), (_SAID, "say")):
            for match in pattern.finditer(text):
                cue_start, cue_end = match.span("cue")
                cue_index = add(
                    match.group("cue"),
                    start=cue_start,
                    end=cue_end,
                    lemma=lemma,
                    pos="VERB",
                    dependency="ROOT",
                )
                subject_start = max(0, match.start() - 1)
                add(
                    "subject",
                    start=subject_start,
                    end=subject_start,
                    lemma="subject",
                    pos="NOUN",
                    dependency="nsubjpass",
                    head_index=cue_index,
                )
                term, start, end = _term_span(match)
                add(
                    term,
                    start=start,
                    end=end,
                    lemma=term.casefold(),
                    pos="ADJ",
                    dependency="oprd",
                    head_index=cue_index,
                )
                condition_start, condition_end = match.span("condition")
                add(
                    match.group("condition"),
                    start=condition_start,
                    end=condition_end,
                    lemma=match.group("condition").casefold(),
                    pos="SCONJ",
                    dependency="mark",
                    head_index=cue_index,
                )
                sentence_index += 1

        for match in _WE_SAY.finditer(text):
            cue_start, cue_end = match.span("cue")
            cue_index = add(
                match.group("cue"),
                start=cue_start,
                end=cue_end,
                lemma="say",
                pos="VERB",
                dependency="ROOT",
            )
            we_start, we_end = match.span("we")
            add(
                match.group("we"),
                start=we_start,
                end=we_end,
                lemma="we",
                pos="PRON",
                dependency="nsubj",
                head_index=cue_index,
            )
            term, start, end = _term_span(match)
            add(
                term,
                start=start,
                end=end,
                lemma=term.casefold(),
                pos="ADJ",
                dependency="oprd",
                head_index=cue_index,
            )
            condition_start, condition_end = match.span("condition")
            add(
                match.group("condition"),
                start=condition_start,
                end=condition_end,
                lemma=match.group("condition").casefold(),
                pos="SCONJ",
                dependency="mark",
                head_index=cue_index,
            )
            sentence_index += 1

        for match in _BY_MEAN.finditer(text):
            term, start, end = _term_span(match)
            term_index = add(
                term,
                start=start,
                end=end,
                lemma=term.casefold(),
                pos="NOUN",
                dependency="pobj",
            )
            we_start, we_end = match.span("we")
            add(
                match.group("we"),
                start=we_start,
                end=we_end,
                lemma="we",
                pos="PRON",
                dependency="nsubj",
                head_index=term_index,
            )
            cue_start, cue_end = match.span("cue")
            cue_index = add(
                match.group("cue"),
                start=cue_start,
                end=cue_end,
                lemma="mean",
                pos="VERB",
                dependency="ROOT",
            )
            tokens[term_index] = tokens[term_index].model_copy(
                update={"head_index": cue_index}
            )
            sentence_index += 1

        for match in _AMBIENT.finditer(text):
            copula_start, copula_end = match.span("copula")
            copula_index = add(
                match.group("copula"),
                start=copula_start,
                end=copula_end,
                lemma="be",
                pos="AUX",
                dependency="ROOT",
            )
            term = match.group("term")
            term_start, term_end = match.span("term")
            add(
                term,
                start=term_start,
                end=term_end,
                lemma=term.casefold(),
                pos="NOUN",
                dependency="nsubj",
                head_index=copula_index,
            )
            prefix_start, prefix_end = match.span("prefix")
            add(
                match.group("prefix"),
                start=prefix_start,
                end=prefix_end,
                lemma=match.group("prefix").casefold(),
                pos="ADV",
                dependency="advmod",
                head_index=copula_index,
            )
            sentence_index += 1

        return LinguisticDocument(text=text, tokens=tokens)
