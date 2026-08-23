from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.frontend import FrontendFile, ParsedProject, SourceSpan
from thorn.linguistic import LinguisticFrontend, LinguisticToken
from thorn.source_projection import LinguisticProjection, build_linguistic_projection
from thorn.symbols import ResultRegion


class StatementScopeKind(StrEnum):
    PROJECT = "project"
    RESULT_STATEMENT = "result_statement"
    RESULT_PROOF = "result_proof"


class LinguisticStatement(BaseModel):
    """One NLP-delimited statement with exact authoritative source provenance."""

    identifier: str
    text: str
    source: SourceSpan
    scope_kind: StatementScopeKind = StatementScopeKind.PROJECT
    result_identifier: str | None = None


class LinguisticStatementInventory(BaseModel):
    """Parser/NLP-neutral statement boundary facts available to later policy."""

    complete: bool
    frontend: str | None = None
    statements: list[LinguisticStatement] = Field(default_factory=list)
    partial_reason: str | None = None


def _mask(characters: list[str], source: SourceSpan) -> None:
    for index in range(source.start_offset, source.end_offset):
        if characters[index] != "\n":
            characters[index] = " "


def _segmentation_view(file: FrontendFile) -> tuple[str, LinguisticProjection] | None:
    """Return a syntax-clean, offset-preserving view used only for NLP segmentation."""

    projection = build_linguistic_projection(file)
    if not projection.complete or not file.syntax_complete:
        return None

    characters = list(projection.text)
    for syntax in file.syntax:
        _mask(characters, syntax.span)
    return "".join(characters), projection


def _overlaps(left: SourceSpan, right: SourceSpan) -> bool:
    return (
        left.file == right.file
        and left.start_offset < right.end_offset
        and right.start_offset < left.end_offset
    )


def _scope_for(
    source: SourceSpan,
    regions: list[ResultRegion],
) -> tuple[StatementScopeKind, str | None]:
    for region in regions:
        if region.file != source.file:
            continue
        if _overlaps(source, region.statement_span):
            return StatementScopeKind.RESULT_STATEMENT, region.identifier
        if region.proof_span is not None and _overlaps(source, region.proof_span):
            return StatementScopeKind.RESULT_PROOF, region.identifier
    return StatementScopeKind.PROJECT, None


def _source_span_for_sentence(
    file: FrontendFile,
    tokens: list[LinguisticToken],
    projection: LinguisticProjection,
) -> SourceSpan:
    start = min(token.start for token in tokens)
    end = max(token.end for token in tokens)

    # Expand NLP placeholders back to the complete exact source construct. A display
    # formula therefore retains its delimiters and a generic inline wrapper retains
    # its original command when one of its argument tokens lies inside the sentence.
    for item in projection.tokens:
        if item.source.start_offset < end and start < item.source.end_offset:
            start = min(start, item.source.start_offset)
            end = max(end, item.source.end_offset)
    changed = True
    while changed:
        changed = False
        for macro in file.macros:
            if macro.span.start_offset < end and start < macro.span.end_offset:
                new_start = min(start, macro.span.start_offset)
                new_end = max(end, macro.span.end_offset)
                if (new_start, new_end) != (start, end):
                    start, end = new_start, new_end
                    changed = True
    return file.span(start, end)


def _hard_statement_boundaries(file: FrontendFile) -> list[int]:
    """Return parser-owned math boundaries that explicitly terminate a sentence."""

    return sorted(
        {
            math.span.end_offset
            for math in file.math
            if math.terminal_punctuation is not None
        }
    )


def _sentence_tokens(
    text: str,
    frontend: LinguisticFrontend,
    hard_boundaries: list[int],
) -> list[list[LinguisticToken]]:
    """Segment with NLP while respecting parser-owned hard sentence boundaries."""

    sentences: list[list[LinguisticToken]] = []
    cursor = 0
    for boundary in [*hard_boundaries, len(text)]:
        if boundary <= cursor:
            continue
        document = frontend.parse(text[cursor:boundary])
        for sentence_index in sorted({token.sentence_index for token in document.tokens}):
            tokens = [
                token.model_copy(
                    update={
                        "start": token.start + cursor,
                        "end": token.end + cursor,
                    }
                )
                for token in document.tokens
                if token.sentence_index == sentence_index and token.text.strip()
            ]
            if tokens:
                sentences.append(tokens)
        cursor = boundary
    return sentences


def _statements_for_file(
    file: FrontendFile,
    regions: list[ResultRegion],
    frontend: LinguisticFrontend,
) -> list[LinguisticStatement] | None:
    built = _segmentation_view(file)
    if built is None:
        return None
    text, projection = built
    statements: list[LinguisticStatement] = []
    for tokens in _sentence_tokens(text, frontend, _hard_statement_boundaries(file)):
        source = _source_span_for_sentence(file, tokens, projection)
        if not projection.source_span_eligible(source):
            continue
        scope_kind, result_identifier = _scope_for(source, regions)
        statements.append(
            LinguisticStatement(
                identifier=f"statement:{file.path}:{source.start_offset}",
                text=source.text(file.raw),
                source=source,
                scope_kind=scope_kind,
                result_identifier=result_identifier,
            )
        )
    return statements


def collect_project_linguistic_statements(
    project: ParsedProject,
    regions: list[ResultRegion],
    frontend: LinguisticFrontend | None,
) -> LinguisticStatementInventory:
    """Let local NLP delimit statements over parser-owned syntax-clean source facts.

    This layer assigns no mathematical role or relevance. Exact source remains
    authoritative, and parser-owned terminal math punctuation is a hard statement
    boundary rather than an English or TeX-macro heuristic.
    """

    if frontend is None:
        return LinguisticStatementInventory(
            complete=False,
            partial_reason="no linguistic frontend configured",
        )

    statements: list[LinguisticStatement] = []
    for file in project.files:
        converted = _statements_for_file(file, regions, frontend)
        if converted is None:
            return LinguisticStatementInventory(
                complete=False,
                frontend=frontend.name,
                partial_reason=(
                    "parser-owned syntax facts unavailable for linguistic "
                    f"segmentation: {file.path}"
                ),
            )
        statements.extend(converted)

    return LinguisticStatementInventory(
        complete=True,
        frontend=frontend.name,
        statements=statements,
    )
