from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.frontend import FrontendFile, FrontendMacro, SourceSpan


class SemanticPlaceholderKind(StrEnum):
    MATH = "math"
    RESULT_REFERENCE = "result_reference"
    EQUATION_REFERENCE = "equation_reference"
    GENERIC_REFERENCE = "generic_reference"


class SemanticPlaceholder(BaseModel):
    token: str
    kind: SemanticPlaceholderKind
    source: SourceSpan
    raw: str
    projected_start: int = Field(ge=0)
    projected_end: int = Field(ge=0)
    label: str | None = None


class SemanticProjection(BaseModel):
    text: str
    placeholders: list[SemanticPlaceholder] = Field(default_factory=list)

    def placeholder(self, token: str) -> SemanticPlaceholder:
        for item in self.placeholders:
            if item.token == token:
                return item
        raise KeyError(token)


class _Replacement(BaseModel):
    start: int
    end: int
    kind: SemanticPlaceholderKind
    source: SourceSpan
    raw: str
    label: str | None = None


def _first_required_argument(macro: FrontendMacro) -> str | None:
    for argument in macro.arguments:
        if not argument.optional:
            value = argument.value.strip()
            return value or None
    return None


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < other_end and end > other_start for other_start, other_end in spans)


def project_semantic_span(
    file: FrontendFile,
    span: SourceSpan,
    *,
    result_identifiers: set[str] | None = None,
) -> SemanticProjection:
    """Replace known mathematical syntax with typed NLP-safe placeholders.

    The linguistic parser sees ordinary prose plus atomic Thorn tokens. Every
    token retains an exact reverse mapping to the original source span. This
    layer performs no linguistic or mathematical inference.
    """

    result_identifiers = result_identifiers or set()
    replacements: list[_Replacement] = []

    math_spans: list[tuple[int, int]] = []
    for math in file.math:
        if math.span.start_offset < span.start_offset or math.span.end_offset > span.end_offset:
            continue
        math_spans.append((math.span.start_offset, math.span.end_offset))
        replacements.append(
            _Replacement(
                start=math.span.start_offset,
                end=math.span.end_offset,
                kind=SemanticPlaceholderKind.MATH,
                source=math.span,
                raw=math.raw,
            )
        )

    for macro in file.macros:
        if macro.name not in {"ref", "eqref", "autoref", "cref", "Cref"}:
            continue
        if macro.span.start_offset < span.start_offset or macro.span.end_offset > span.end_offset:
            continue
        if _overlaps(macro.span.start_offset, macro.span.end_offset, math_spans):
            continue
        label = _first_required_argument(macro)
        if macro.name == "eqref":
            kind = SemanticPlaceholderKind.EQUATION_REFERENCE
        elif label is not None and label in result_identifiers:
            kind = SemanticPlaceholderKind.RESULT_REFERENCE
        else:
            kind = SemanticPlaceholderKind.GENERIC_REFERENCE
        replacements.append(
            _Replacement(
                start=macro.span.start_offset,
                end=macro.span.end_offset,
                kind=kind,
                source=macro.span,
                raw=macro.raw,
                label=label,
            )
        )

    replacements.sort(key=lambda item: (item.start, -(item.end - item.start)))
    filtered: list[_Replacement] = []
    cursor = span.start_offset
    for replacement in replacements:
        if replacement.start < cursor:
            continue
        filtered.append(replacement)
        cursor = replacement.end

    counters: dict[SemanticPlaceholderKind, int] = {}
    pieces: list[str] = []
    placeholders: list[SemanticPlaceholder] = []
    source_cursor = span.start_offset
    projected_cursor = 0
    prefixes = {
        SemanticPlaceholderKind.MATH: "THORNMATH",
        SemanticPlaceholderKind.RESULT_REFERENCE: "THORNRESULT",
        SemanticPlaceholderKind.EQUATION_REFERENCE: "THORNEQUATION",
        SemanticPlaceholderKind.GENERIC_REFERENCE: "THORNREFERENCE",
    }

    for replacement in filtered:
        literal = file.raw[source_cursor : replacement.start]
        pieces.append(literal)
        projected_cursor += len(literal)

        number = counters.get(replacement.kind, 0) + 1
        counters[replacement.kind] = number
        token = f"{prefixes[replacement.kind]}{number}"
        start = projected_cursor
        end = start + len(token)
        pieces.append(token)
        placeholders.append(
            SemanticPlaceholder(
                token=token,
                kind=replacement.kind,
                source=replacement.source,
                raw=replacement.raw,
                projected_start=start,
                projected_end=end,
                label=replacement.label,
            )
        )
        projected_cursor = end
        source_cursor = replacement.end

    pieces.append(file.raw[source_cursor : span.end_offset])
    return SemanticProjection(text="".join(pieces), placeholders=placeholders)
