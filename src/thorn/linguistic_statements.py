from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.frontend import FrontendFile, ParsedProject, SourceSpan
from thorn.linguistic import LinguisticDocument, LinguisticFrontend, LinguisticToken
from thorn.source_projection import ProjectionTokenKind, build_linguistic_projection
from thorn.symbols import ResultRegion

_CONTENT_POS = {"ADJ", "NOUN", "PROPN"}
_MATH_MARKER = "∎"


class StatementScopeKind(StrEnum):
    PROJECT = "project"
    RESULT_STATEMENT = "result_statement"
    RESULT_PROOF = "result_proof"


class LinguisticStatement(BaseModel):
    """One NLP-delimited statement with exact authoritative source provenance."""

    identifier: str
    text: str
    source: SourceSpan
    content_terms: tuple[str, ...] = ()
    scope_kind: StatementScopeKind = StatementScopeKind.PROJECT
    result_identifier: str | None = None


class LinguisticStatementInventory(BaseModel):
    """Parser/NLP-neutral statement boundary facts available to later review policy."""

    complete: bool
    frontend: str | None = None
    statements: list[LinguisticStatement] = Field(default_factory=list)
    partial_reason: str | None = None


def _mask(characters: list[str], source: SourceSpan) -> None:
    for index in range(source.start_offset, source.end_offset):
        if characters[index] != "\n":
            characters[index] = " "


def _segmentation_view(file: FrontendFile) -> tuple[str, object] | None:
    """Return a syntax-clean, offset-preserving view used only for NLP segmentation."""

    projection = build_linguistic_projection(file)
    if not projection.complete or not file.syntax_complete:
        return None

    characters = list(projection.text)
    for syntax in file.syntax:
        _mask(characters, syntax.span)

    # The normal projection deliberately hides mathematical internals. Preserve only
    # parser-owned terminal punctuation so spaCy can end a prose sentence after a
    # display formula without learning TeX delimiters or mathematical notation.
    for math in file.math:
        punctuation = math.terminal_punctuation
        if punctuation is None:
            continue
        raw = punctuation.text(file.raw)
        if len(raw) == 1:
            characters[punctuation.start_offset] = raw

    return "".join(characters), projection


def _overlaps(left: SourceSpan, right: SourceSpan) -> bool:
    return (
        left.file == right.file
        and left.start_offset < right.end_offset
        and right.start_offset < left.end_offset
    )


def _scope_for(source: SourceSpan, regions: list[ResultRegion]) -> tuple[StatementScopeKind, str | None]:
    for region in regions:
        if region.file != source.file:
            continue
        if _overlaps(source, region.statement_span):
            return StatementScopeKind.RESULT_STATEMENT, region.identifier
        if region.proof_span is not None and _overlaps(source, region.proof_span):
            return StatementScopeKind.RESULT_PROOF, region.identifier
    return StatementScopeKind.PROJECT, None


def _content_terms(tokens: list[LinguisticToken], projection: object) -> tuple[str, ...]:
    terms: dict[str, None] = {}
    for token in tokens:
        if token.pos not in _CONTENT_POS:
            continue
        if token.text == _MATH_MARKER:
            continue
        # ``LinguisticProjection`` is deliberately accessed through its normalized
        # token lookup rather than by inspecting LaTeX syntax here.
        containing = projection.token_containing(token.start, kind=ProjectionTokenKind.MATH)
        if containing is not None:
            continue
        lemma = token.lemma.strip().casefold()
        if lemma:
            terms.setdefault(lemma, None)
    return tuple(terms)


def _source_span_for_sentence(
    file: FrontendFile,
    tokens: list[LinguisticToken],
    projection: object,
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


def _statements_for_file(
    file: FrontendFile,
    regions: list[ResultRegion],
    frontend: LinguisticFrontend,
) -> list[LinguisticStatement] | None:
    built = _segmentation_view(file)
    if built is None:
        return None
    text, projection = built
    document: LinguisticDocument = frontend.parse(text)
    sentence_indexes = sorted({token.sentence_index for token in document.tokens})
    statements: list[LinguisticStatement] = []
    for sentence_index in sentence_indexes:
        tokens = [
            token
            for token in document.tokens
            if token.sentence_index == sentence_index and token.text.strip()
        ]
        if not tokens:
            continue
        source = _source_span_for_sentence(file, tokens, projection)
        if not projection.source_span_eligible(source):
            continue
        scope_kind, result_identifier = _scope_for(source, regions)
        statements.append(
            LinguisticStatement(
                identifier=f"statement:{file.path}:{source.start_offset}",
                text=source.text(file.raw),
                source=source,
                content_terms=_content_terms(tokens, projection),
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

    No mathematical role is assigned here: there is no definition/assumption cue
    vocabulary and no command-name vocabulary. Exact source remains authoritative.
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
                    f"parser-owned syntax facts unavailable for linguistic segmentation: {file.path}"
                ),
            )
        statements.extend(converted)

    return LinguisticStatementInventory(
        complete=True,
        frontend=frontend.name,
        statements=statements,
    )
