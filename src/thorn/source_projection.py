from __future__ import annotations

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


class LinguisticSpanTokenKind(StrEnum):
    MATH = "math"
    RESULT_REFERENCE = "result_reference"
    EQUATION_REFERENCE = "equation_reference"
    GENERIC_REFERENCE = "generic_reference"


@dataclass(frozen=True)
class ProjectionToken:
    kind: ProjectionTokenKind
    source: SourceSpan
    value: str | None = None
    macro_name: str | None = None


@dataclass(frozen=True)
class LinguisticSpanPlaceholder:
    token: str
    kind: LinguisticSpanTokenKind
    source: SourceSpan
    raw: str
    projected_start: int
    projected_end: int
    label: str | None = None


@dataclass(frozen=True)
class LinguisticSpanProjection:
    """One NLP-safe slice derived from the canonical reversible file projection."""

    text: str
    placeholders: tuple[LinguisticSpanPlaceholder, ...]

    def placeholder(self, token: str) -> LinguisticSpanPlaceholder:
        for item in self.placeholders:
            if item.token == token:
                return item
        raise KeyError(token)


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
        """Return whether normalized source-role facts permit semantic use of ``source``.

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

    def eligible_segments(self, source: SourceSpan) -> tuple[SourceSpan, ...]:
        """Return contiguous source-role-eligible pieces of ``source``.

        Excluded parser-owned regions are boundaries, not whitespace to bridge across.
        This lets semantic consumers segment eligible prose without ever reconstructing
        comments/verbatim rules from raw TeX. Partial region coverage yields no semantic
        source at all.
        """

        if not self.complete or source.file != self.file.path:
            return ()
        if source.start_offset < 0 or source.end_offset > len(self.file.raw):
            return ()

        excluded = sorted(
            (
                max(source.start_offset, region.span.start_offset),
                min(source.end_offset, region.span.end_offset),
            )
            for region in self.file.regions
            if region.kind in _INELIGIBLE_KINDS
            and region.span.start_offset < source.end_offset
            and source.start_offset < region.span.end_offset
        )
        merged: list[tuple[int, int]] = []
        for start, end in excluded:
            if not merged or merged[-1][1] < start:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))

        segments: list[SourceSpan] = []
        cursor = source.start_offset
        for start, end in merged:
            if cursor < start:
                segments.append(self.source_span(cursor, start))
            cursor = max(cursor, end)
        if cursor < source.end_offset:
            segments.append(self.source_span(cursor, source.end_offset))
        return tuple(segments)

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

    def project_span(
        self,
        source: SourceSpan,
        *,
        result_identifiers: set[str] | None = None,
    ) -> LinguisticSpanProjection:
        """Build an NLP-safe reversible slice from this normalized projection.

        This is the single production source-to-linguistic path. Math/reference syntax
        becomes stable ASCII placeholder tokens for local NLP while each placeholder
        retains exact original source provenance. Ineligible or partial source fails
        closed rather than being copied into the linguistic view.
        """

        if not self.source_span_eligible(source):
            raise ValueError("linguistic span projection requires eligible complete source")

        result_identifiers = result_identifiers or set()
        contained = [
            token
            for token in self.tokens
            if source.start_offset <= token.source.start_offset
            and token.source.end_offset <= source.end_offset
        ]
        contained.sort(
            key=lambda token: (
                token.source.start_offset,
                -(token.source.end_offset - token.source.start_offset),
                token.kind.value,
            )
        )
        filtered: list[ProjectionToken] = []
        cursor = source.start_offset
        for token in contained:
            if token.source.start_offset < cursor:
                continue
            filtered.append(token)
            cursor = token.source.end_offset

        counters: dict[LinguisticSpanTokenKind, int] = {}
        prefixes = {
            LinguisticSpanTokenKind.MATH: "THORNMATH",
            LinguisticSpanTokenKind.RESULT_REFERENCE: "THORNRESULT",
            LinguisticSpanTokenKind.EQUATION_REFERENCE: "THORNEQUATION",
            LinguisticSpanTokenKind.GENERIC_REFERENCE: "THORNREFERENCE",
        }
        pieces: list[str] = []
        placeholders: list[LinguisticSpanPlaceholder] = []
        source_cursor = source.start_offset
        projected_cursor = 0

        for item in filtered:
            literal = self.text[source_cursor : item.source.start_offset]
            pieces.append(literal)
            projected_cursor += len(literal)

            if item.kind == ProjectionTokenKind.MATH:
                kind = LinguisticSpanTokenKind.MATH
            elif item.macro_name == "eqref":
                kind = LinguisticSpanTokenKind.EQUATION_REFERENCE
            elif item.value is not None and item.value in result_identifiers:
                kind = LinguisticSpanTokenKind.RESULT_REFERENCE
            else:
                kind = LinguisticSpanTokenKind.GENERIC_REFERENCE

            number = counters.get(kind, 0) + 1
            counters[kind] = number
            placeholder_token = f"{prefixes[kind]}{number}"
            projected_start = projected_cursor
            projected_end = projected_start + len(placeholder_token)
            pieces.append(placeholder_token)
            placeholders.append(
                LinguisticSpanPlaceholder(
                    token=placeholder_token,
                    kind=kind,
                    source=item.source,
                    raw=item.source.text(self.file.raw),
                    projected_start=projected_start,
                    projected_end=projected_end,
                    label=item.value,
                )
            )
            projected_cursor = projected_end
            source_cursor = item.source.end_offset

        pieces.append(self.text[source_cursor : source.end_offset])
        return LinguisticSpanProjection(
            text="".join(pieces),
            placeholders=tuple(placeholders),
        )


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
                macro_name=macro.name,
            )
        )

    tokens.sort(key=lambda token: (token.source.start_offset, token.kind.value))
    return LinguisticProjection(
        file=file,
        text="".join(characters),
        tokens=tuple(tokens),
        status=ProjectionStatus.COMPLETE,
    )
