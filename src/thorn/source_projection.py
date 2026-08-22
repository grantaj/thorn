from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from thorn.frontend import FrontendFile, FrontendMacro, FrontendRegionKind, SourceSpan

_REFERENCE_MACROS = {"Cref", "autoref", "cref", "eqref", "ref"}
_INELIGIBLE_KINDS = {
    FrontendRegionKind.PREAMBLE,
    FrontendRegionKind.NON_DOCUMENT,
    FrontendRegionKind.COMMENT,
    FrontendRegionKind.VERBATIM,
    FrontendRegionKind.LISTING,
    FrontendRegionKind.MINTED,
    FrontendRegionKind.OPAQUE,
}


class ProjectionStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class ProjectionTokenKind(StrEnum):
    MATH = "math"
    REFERENCE = "reference"


@dataclass(frozen=True)
class ProjectionToken:
    kind: ProjectionTokenKind
    source: SourceSpan
    value: str | None = None


@dataclass(frozen=True)
class LinguisticProjection:
    """A reversible, source-offset-preserving linguistic view of one file."""

    file: FrontendFile
    text: str
    tokens: tuple[ProjectionToken, ...]
    status: ProjectionStatus
    partial_reason: str | None = None

    @property
    def complete(self) -> bool:
        return self.status == ProjectionStatus.COMPLETE

    def source_span(self, start: int, end: int) -> SourceSpan:
        return self.file.span(start, end)

    def source_span_eligible(self, source: SourceSpan) -> bool:
        """Return whether normalized source-role facts permit authority at ``source``.

        This is deliberately a source-role decision only. It does not interpret
        declaration grammar or mathematical meaning. A span touching any parser-owned
        excluded region is ineligible, and partial region coverage fails closed.
        """

        if not self.complete or source.file != self.file.path:
            return False
        if source.start_offset < 0 or source.end_offset > len(self.file.raw):
            return False
        return not any(
            region.kind in _INELIGIBLE_KINDS
            and region.span.start_offset < source.end_offset
            and source.start_offset < region.span.end_offset
            for region in self.file.regions
        )

    def token_containing(
        self,
        offset: int,
        *,
        kind: ProjectionTokenKind | None = None,
    ) -> ProjectionToken | None:
        for token in self.tokens:
            if kind is not None and token.kind != kind:
                continue
            if token.source.start_offset <= offset < token.source.end_offset:
                return token
        return None

    def _body_bounds(self, cue_offset: int) -> tuple[int, int]:
        floor = 0
        ceiling = len(self.text)
        for region in self.file.regions:
            if (
                region.kind == FrontendRegionKind.PREAMBLE
                and region.span.end_offset <= cue_offset
            ):
                floor = max(floor, region.span.end_offset)
            elif (
                region.kind == FrontendRegionKind.NON_DOCUMENT
                and cue_offset <= region.span.start_offset
            ):
                ceiling = min(ceiling, region.span.start_offset)
        return floor, ceiling

    @staticmethod
    def _math_ends_sentence(raw: str) -> bool:
        return (
            re.search(r"[.!?]\s*(?:\\\]|\\\)|\$\$|\$)\s*\Z", raw, re.DOTALL)
            is not None
        )

    def sentence_span(self, cue_offset: int) -> SourceSpan:
        """Return the exact source sentence containing a projection/source offset."""

        if not self.complete:
            raise ValueError("sentence provenance is unavailable for a partial projection")
        if cue_offset < 0 or cue_offset > len(self.text):
            raise ValueError("cue offset is outside the projection")

        floor, ceiling = self._body_bounds(cue_offset)
        paragraph_marker = self.text.rfind("\n\n", floor, cue_offset)
        paragraph_start = paragraph_marker + 2 if paragraph_marker >= floor else floor
        paragraph_end = self.text.find("\n\n", cue_offset, ceiling)
        if paragraph_end < 0:
            paragraph_end = ceiling

        start = cue_offset
        cursor = cue_offset - 1
        while cursor >= paragraph_start:
            token = self.token_containing(cursor)
            if token is not None:
                if token.kind == ProjectionTokenKind.MATH and self._math_ends_sentence(
                    token.source.text(self.file.raw)
                ):
                    start = token.source.end_offset
                    break
                cursor = token.source.start_offset - 1
                continue
            if self.text[cursor] in ".!?":
                start = cursor + 1
                break
            cursor -= 1
        else:
            start = paragraph_start
        while start < cue_offset and self.text[start].isspace():
            start += 1

        cursor = cue_offset
        end = paragraph_end
        while cursor < paragraph_end:
            token = self.token_containing(cursor)
            if token is not None:
                cursor = token.source.end_offset
                if token.kind == ProjectionTokenKind.MATH and self._math_ends_sentence(
                    token.source.text(self.file.raw)
                ):
                    end = cursor
                    break
                continue
            if self.text[cursor] in ".!?":
                end = cursor + 1
                break
            cursor += 1
        while end > start and self.file.raw[end - 1].isspace():
            end -= 1
        return self.source_span(start, end)


def _mask(characters: list[str], start: int, end: int) -> None:
    for index in range(max(0, start), min(len(characters), end)):
        if characters[index] != "\n":
            characters[index] = " "


def _placeholder(characters: list[str], start: int, end: int, marker: str) -> None:
    _mask(characters, start, end)
    for index in range(max(0, start), min(len(characters), end)):
        if characters[index] != "\n":
            characters[index] = marker
            break


def _first_required_argument_value(macro: FrontendMacro) -> str | None:
    for argument in macro.arguments:
        if not argument.optional:
            return argument.value.strip() or None
    return None


def _inside_ineligible_region(file: FrontendFile, start: int, end: int) -> bool:
    return any(
        region.kind in _INELIGIBLE_KINDS
        and region.span.start_offset <= start
        and end <= region.span.end_offset
        for region in file.regions
    )


def build_linguistic_projection(file: FrontendFile) -> LinguisticProjection:
    """Project normalized source facts into exact, reversible linguistic text.

    Projection offsets remain identical to source offsets. Parser-owned ineligible
    regions are masked, while math and references become typed placeholders carrying
    exact source spans. No source role is rediscovered by rescanning raw TeX.
    """

    characters = list(file.raw)
    if not file.regions_complete:
        _mask(characters, 0, len(characters))
        return LinguisticProjection(
            file=file,
            text="".join(characters),
            tokens=(),
            status=ProjectionStatus.PARTIAL,
            partial_reason="frontend did not establish complete source-region eligibility",
        )

    tokens: list[ProjectionToken] = []
    for region in file.regions:
        if region.kind in _INELIGIBLE_KINDS:
            _mask(characters, region.span.start_offset, region.span.end_offset)
        elif region.kind == FrontendRegionKind.MATH and not _inside_ineligible_region(
            file, region.span.start_offset, region.span.end_offset
        ):
            _placeholder(characters, region.span.start_offset, region.span.end_offset, "∎")
            tokens.append(ProjectionToken(kind=ProjectionTokenKind.MATH, source=region.span))

    for macro in file.macros:
        if macro.name not in _REFERENCE_MACROS:
            continue
        if _inside_ineligible_region(file, macro.span.start_offset, macro.span.end_offset):
            continue
        _placeholder(characters, macro.span.start_offset, macro.span.end_offset, "↗")
        tokens.append(
            ProjectionToken(
                kind=ProjectionTokenKind.REFERENCE,
                source=macro.span,
                value=_first_required_argument_value(macro),
            )
        )

    tokens.sort(key=lambda token: (token.source.start_offset, token.kind.value))
    return LinguisticProjection(
        file=file,
        text="".join(characters),
        tokens=tuple(tokens),
        status=ProjectionStatus.COMPLETE,
    )
