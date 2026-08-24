from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from thorn.frontend import SourceSpan
from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.source_projection import (
    LinguisticSpanPlaceholder,
    LinguisticSpanProjection,
    LinguisticSpanTokenKind,
)

# Frozen before the first semantic measurement for #215. These are deliberately
# graph-semantic operator classes, not whole-sentence templates. Do not expand
# them after inspecting results from the frozen corpora.
INTRODUCE = frozenset({"assume", "suppose", "fix", "let", "define", "set"})
NAME = frozenset({"call", "term", "mean", "say"})
SUPPORT_VERBS = frozenset({"use", "apply", "invoke", "follow"})
SUPPORT_NOUNS = frozenset({"consequence"})
CONDITIONS = frozenset({"if", "when", "whenever", "provided"})
HYPOTHETICAL = frozenset({"would", "could", "might"})
PLACEHOLDER_RE = re.compile(r"\bTHORN(?:MATH|REF)\d+\b")


@dataclass(frozen=True)
class Segment:
    raw: str
    projected: str
    source_start: int
    projected_start: int


@dataclass(frozen=True)
class CaseText:
    source: str
    projected: str
    segments: tuple[Segment, ...]

    def source_span(self, start: int, end: int) -> tuple[int, int] | None:
        for segment in self.segments:
            projected_end = segment.projected_start + len(segment.projected)
            if not (segment.projected_start <= start and end <= projected_end):
                continue
            if start == segment.projected_start and end == projected_end:
                return segment.source_start, segment.source_start + len(segment.raw)
            if len(segment.raw) != len(segment.projected):
                return None
            delta = start - segment.projected_start
            source_start = segment.source_start + delta
            return source_start, source_start + (end - start)
        return None


@dataclass(frozen=True)
class AdaptedResultReference:
    """One production result-reference placeholder exposed to the frozen compiler."""

    token: str
    placeholder: LinguisticSpanPlaceholder


@dataclass(frozen=True)
class AdaptedCase:
    """Frozen research input plus lossless production source/reference identity."""

    case: CaseText
    source: SourceSpan
    result_references: tuple[AdaptedResultReference, ...] = ()

    def result_reference(self, token: str) -> LinguisticSpanPlaceholder:
        for item in self.result_references:
            if item.token == token:
                return item.placeholder
        raise KeyError(token)

    def absolute_source_span(self, item: Grounding) -> SourceSpan | None:
        """Map one exactly grounded frozen field back to its original source span."""

        if item.source is None:
            return None
        start, end = item.source
        if not (0 <= start <= end <= len(self.case.source)):
            return None

        def line_column(offset: int) -> tuple[int, int]:
            prefix = self.case.source[:offset]
            newline_count = prefix.count("\n")
            if newline_count == 0:
                return self.source.start_line, self.source.start_column + offset
            return self.source.start_line + newline_count, len(prefix.rsplit("\n", 1)[1]) + 1

        start_line, start_column = line_column(start)
        end_line, end_column = line_column(end)
        return SourceSpan(
            file=self.source.file,
            start_offset=self.source.start_offset + start,
            end_offset=self.source.start_offset + end,
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column,
        )


@dataclass(frozen=True)
class Grounding:
    text: str
    start: int
    end: int
    source: tuple[int, int] | None

    @property
    def exact(self) -> bool:
        return self.source is not None


@dataclass(frozen=True)
class Frame:
    operation: str
    rule: str
    sentence: int
    bind: Grounding | None = None
    payload: tuple[Grounding, ...] = ()
    prerequisites: tuple[Grounding, ...] = ()
    evidence: tuple[Grounding, ...] = ()

    @property
    def exact(self) -> bool:
        parts = [*self.payload, *self.prerequisites, *self.evidence]
        if self.bind is not None:
            parts.append(self.bind)
        return bool(parts) and all(part.exact for part in parts)


def build_case(raw_case: dict[str, Any]) -> CaseText:
    items = raw_case["segments"] if "segments" in raw_case else [raw_case["text"]]
    source_parts: list[str] = []
    projected_parts: list[str] = []
    segments: list[Segment] = []
    source_cursor = projected_cursor = 0
    for item in items:
        if isinstance(item, str):
            raw = projected = item
        else:
            raw = str(item["raw"])
            projected = str(item.get("projected", item.get("token", raw)))
        segments.append(Segment(raw, projected, source_cursor, projected_cursor))
        source_parts.append(raw)
        projected_parts.append(projected)
        source_cursor += len(raw)
        projected_cursor += len(projected)
    return CaseText("".join(source_parts), "".join(projected_parts), tuple(segments))


def adapt_linguistic_span_projection(
    projection: LinguisticSpanProjection,
    *,
    source: SourceSpan,
) -> AdaptedCase:
    """Losslessly adapt the production typed projection to the frozen #215 dialect.

    The semantic compiler remains unchanged: production ``THORNRESULTn`` placeholders
    are renamed deterministically to the already-frozen ``THORNREFn`` research input.
    The original production placeholder is retained alongside that token so callers can
    join a recognized support frame to independently established result resolution and
    exact ``SourceSpan`` provenance. Equation/generic references remain typed production
    placeholders and are deliberately invisible to the frozen result-support compiler.
    """

    source_parts: list[str] = []
    projected_parts: list[str] = []
    segments: list[Segment] = []
    references: list[AdaptedResultReference] = []
    source_cursor = projected_cursor = text_cursor = result_index = 0

    def append(raw: str, projected: str) -> None:
        nonlocal source_cursor, projected_cursor
        if not raw and not projected:
            return
        segments.append(Segment(raw, projected, source_cursor, projected_cursor))
        source_parts.append(raw)
        projected_parts.append(projected)
        source_cursor += len(raw)
        projected_cursor += len(projected)

    for placeholder in sorted(
        projection.placeholders,
        key=lambda item: item.projected_start,
    ):
        if placeholder.projected_start < text_cursor:
            raise ValueError("overlapping linguistic projection placeholders")
        if (
            placeholder.source.file != source.file
            or placeholder.source.start_offset < source.start_offset
            or source.end_offset < placeholder.source.end_offset
        ):
            raise ValueError("linguistic projection placeholder lies outside source span")
        placeholder_text = projection.text[
            placeholder.projected_start : placeholder.projected_end
        ]
        if placeholder_text != placeholder.token:
            raise ValueError("linguistic projection placeholder offsets do not match text")

        literal = projection.text[text_cursor : placeholder.projected_start]
        append(literal, literal)

        projected = placeholder.token
        if placeholder.kind == LinguisticSpanTokenKind.RESULT_REFERENCE:
            result_index += 1
            projected = f"THORNREF{result_index}"
            references.append(AdaptedResultReference(projected, placeholder))
        append(placeholder.raw, projected)
        text_cursor = placeholder.projected_end

    append(projection.text[text_cursor:], projection.text[text_cursor:])
    case = CaseText(
        source="".join(source_parts),
        projected="".join(projected_parts),
        segments=tuple(segments),
    )
    if len(case.source) != source.end_offset - source.start_offset:
        raise ValueError("linguistic projection source length does not match source span")
    return AdaptedCase(
        case=case,
        source=source,
        result_references=tuple(references),
    )


def sentence_groups(document: LinguisticDocument) -> list[list[LinguisticToken]]:
    grouped: dict[int, list[LinguisticToken]] = defaultdict(list)
    for token in document.tokens:
        grouped[token.sentence_index].append(token)
    return [grouped[index] for index in sorted(grouped)]


def grounding(case: CaseText, text: str, start: int, end: int) -> Grounding:
    return Grounding(text, start, end, case.source_span(start, end))


def placeholders(case: CaseText, tokens: list[LinguisticToken], prefix: str) -> list[Grounding]:
    start = min(token.start for token in tokens)
    end = max(token.end for token in tokens)
    return [
        grounding(case, match.group(), match.start(), match.end())
        for match in PLACEHOLDER_RE.finditer(case.projected, start, end)
        if match.group().startswith(prefix)
    ]


def children(tokens: list[LinguisticToken], index: int) -> list[LinguisticToken]:
    return [token for token in tokens if token.head_index == index and token.index != index]


def subjects(tokens: list[LinguisticToken], anchor: LinguisticToken) -> list[LinguisticToken]:
    return [
        token
        for token in children(tokens, anchor.index)
        if token.dependency in {"nsubj", "nsubjpass"}
    ]


def passive(tokens: list[LinguisticToken], anchor: LinguisticToken) -> bool:
    return any(token.dependency == "nsubjpass" for token in subjects(tokens, anchor)) or any(
        token.dependency == "auxpass" for token in children(tokens, anchor.index)
    )


def ancestors(tokens: list[LinguisticToken], token: LinguisticToken) -> list[LinguisticToken]:
    by_index = {item.index: item for item in tokens}
    result = [token]
    seen = {token.index}
    while token.head_index in by_index and token.head_index not in seen:
        token = by_index[token.head_index]
        result.append(token)
        seen.add(token.index)
    return result


def token_at(tokens: list[LinguisticToken], item: Grounding) -> LinguisticToken | None:
    return next(
        (token for token in tokens if token.start < item.end and item.start < token.end),
        None,
    )


def quote_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for left, right in (("“", "”"), ("‘", "’"), ('"', '"')):
        cursor = 0
        while (start := text.find(left, cursor)) >= 0:
            end = text.find(right, start + len(left))
            if end < 0:
                break
            ranges.append((start, end + len(right)))
            cursor = end + len(right)
    return ranges


def quoted(ranges: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(left <= start and end <= right for left, right in ranges)


def blocked(tokens: list[LinguisticToken]) -> bool:
    return any(
        token.dependency == "neg" or token.lemma.casefold() == "not" for token in tokens
    )


def authorial(tokens: list[LinguisticToken], anchor: LinguisticToken, *, naming: bool) -> bool:
    if passive(tokens, anchor):
        return True
    found = subjects(tokens, anchor)
    if naming and anchor.lemma.casefold() == "say":
        return False
    if not naming:
        return not found or all(token.lemma.casefold() == "we" for token in found)
    return bool(found) and all(token.lemma.casefold() == "we" for token in found)


def condition_after(
    tokens: list[LinguisticToken], anchor: LinguisticToken
) -> LinguisticToken | None:
    found = [
        token
        for token in tokens
        if token.start > anchor.end and token.text.casefold() in CONDITIONS
    ]
    return min(found, key=lambda token: token.start) if found else None


def naming_term(
    tokens: list[LinguisticToken], anchor: LinguisticToken, condition: LinguisticToken | None
) -> tuple[str, int, int] | None:
    if condition is None:
        candidates = [
            token
            for token in tokens
            if token.start < anchor.start and token.pos in {"NOUN", "PROPN"}
        ]
        if not candidates:
            return None
        head = candidates[-1]
        modifiers = [
            token
            for token in children(tokens, head.index)
            if token.dependency in {"amod", "compound"}
        ]
        parts = sorted([*modifiers, head], key=lambda token: token.start)
        return " ".join(token.text for token in parts), parts[0].start, parts[-1].end

    candidates = [
        token
        for token in tokens
        if anchor.end <= token.start < condition.start
        and token.pos in {"ADJ", "NOUN", "PROPN"}
        and token.dependency not in {"nsubj", "nsubjpass", "dobj", "pobj"}
    ]
    if not candidates:
        return None
    token = candidates[-1]
    return token.text, token.start, token.end


def declaration_frames(
    case: CaseText,
    tokens: list[LinguisticToken],
    quotes: list[tuple[int, int]],
) -> list[Frame]:
    if blocked(tokens):
        return []
    maths = placeholders(case, tokens, "THORNMATH")
    result: list[Frame] = []

    for anchor in tokens:
        lemma = anchor.lemma.casefold()
        if lemma not in INTRODUCE or quoted(quotes, anchor.start, anchor.end):
            continue
        if not authorial(tokens, anchor, naming=False) or not maths:
            continue
        bind = maths[0] if lemma in {"fix", "let", "define", "set"} else None
        intro_payload = tuple(maths[1:] if bind is not None and len(maths) > 1 else maths)
        if intro_payload:
            result.append(
                Frame(
                    "declare",
                    "introduction-operator",
                    anchor.sentence_index,
                    bind=bind,
                    payload=intro_payload,
                    evidence=(grounding(case, anchor.text, anchor.start, anchor.end),),
                )
            )

    for anchor in tokens:
        lemma = anchor.lemma.casefold()
        if lemma not in NAME or quoted(quotes, anchor.start, anchor.end):
            continue
        if not authorial(tokens, anchor, naming=True):
            continue
        naming_condition = None if lemma == "mean" else condition_after(tokens, anchor)
        if lemma != "mean" and naming_condition is None:
            continue
        naming = naming_term(tokens, anchor, naming_condition)
        naming_payload = [
            item
            for item in maths
            if item.start > (anchor.end if naming_condition is None else naming_condition.end)
        ]
        if naming is None or not naming_payload:
            continue
        term_text, term_start, term_end = naming
        evidence = [grounding(case, anchor.text, anchor.start, anchor.end)]
        if naming_condition is not None:
            evidence.append(
                grounding(
                    case,
                    naming_condition.text,
                    naming_condition.start,
                    naming_condition.end,
                )
            )
        result.append(
            Frame(
                "declare",
                "naming-operator",
                anchor.sentence_index,
                bind=grounding(case, term_text, term_start, term_end),
                payload=tuple(naming_payload),
                evidence=tuple(evidence),
            )
        )

    conditions = [token for token in tokens if token.text.casefold() in CONDITIONS]
    exacts = [token for token in tokens if token.lemma.casefold() == "exactly"]
    if conditions and exacts:
        exact_condition = conditions[0]
        candidates = [
            token
            for token in tokens
            if token.start < exact_condition.start
            and token.pos in {"ADJ", "NOUN", "PROPN"}
            and token.dependency not in {"nsubj", "nsubjpass", "dobj", "pobj"}
        ]
        exact_payload = [item for item in maths if item.start > exact_condition.end]
        if candidates and exact_payload:
            exact_term = candidates[-1]
            result.append(
                Frame(
                    "declare",
                    "exact-biconditional",
                    exact_condition.sentence_index,
                    bind=grounding(case, exact_term.text, exact_term.start, exact_term.end),
                    payload=tuple(exact_payload),
                    evidence=(
                        grounding(case, exacts[0].text, exacts[0].start, exacts[0].end),
                        grounding(
                            case,
                            exact_condition.text,
                            exact_condition.start,
                            exact_condition.end,
                        ),
                    ),
                )
            )
    return result


def requirement_frames(
    case: CaseText,
    tokens: list[LinguisticToken],
    quotes: list[tuple[int, int]],
) -> list[Frame]:
    refs = placeholders(case, tokens, "THORNREF")
    maths = placeholders(case, tokens, "THORNMATH")
    if not refs or blocked(tokens) or any(
        token.lemma.casefold() in HYPOTHETICAL for token in tokens
    ):
        return []

    grouped: dict[int, tuple[LinguisticToken, list[Grounding]]] = {}
    for ref in refs:
        if quoted(quotes, ref.start, ref.end):
            continue
        ref_token = token_at(tokens, ref)
        if ref_token is None:
            continue
        operator = next(
            (
                token
                for token in ancestors(tokens, ref_token)
                if token.lemma.casefold() in SUPPORT_VERBS | SUPPORT_NOUNS
            ),
            None,
        )
        if operator is None or quoted(quotes, operator.start, operator.end):
            continue
        lemma = operator.lemma.casefold()
        if not maths and lemma not in SUPPORT_NOUNS:
            continue
        if lemma not in {"follow"} | SUPPORT_NOUNS:
            found_subjects = subjects(tokens, operator)
            if found_subjects and not passive(tokens, operator) and any(
                token.lemma.casefold() != "we" for token in found_subjects
            ):
                continue
        grouped.setdefault(operator.index, (operator, []))[1].append(ref)

    return [
        Frame(
            "require",
            "support-operator",
            operator.sentence_index,
            prerequisites=tuple(sorted(items, key=lambda item: item.start)),
            evidence=(grounding(case, operator.text, operator.start, operator.end),),
        )
        for operator, items in grouped.values()
    ]


def compile_effects(case: CaseText, document: LinguisticDocument) -> list[Frame]:
    quotes = quote_ranges(case.projected)
    result: list[Frame] = []
    for tokens in sentence_groups(document):
        result.extend(declaration_frames(case, tokens, quotes))
        result.extend(requirement_frames(case, tokens, quotes))
    return result
