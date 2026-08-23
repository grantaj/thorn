from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from thorn.models import SourceRange


class FrontendDiagnosticKind(StrEnum):
    PARSE_ERROR = "parse_error"
    MISSING_FILE = "missing_file"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"
    PROJECT_PARTIALITY = "project_partiality"


class FrontendRegionKind(StrEnum):
    """Parser-neutral source-region facts relevant to prose eligibility.

    These are syntactic/source roles, not mathematical authority decisions.
    """

    PREAMBLE = "preamble"
    NON_DOCUMENT = "non_document"
    DOCUMENT_TEXT = "document_text"
    COMMENT = "comment"
    VERBATIM = "verbatim"
    LISTING = "listing"
    MINTED = "minted"
    OPAQUE = "opaque"
    MATH = "math"


class FrontendSyntaxKind(StrEnum):
    """Parser-owned syntax that is not a linguistic word.

    This classification says nothing about the semantic meaning of the construct.
    It only identifies source syntax that a linguistic segmentation view may mask
    while retaining exact source provenance separately.
    """

    CONTROL = "control"


class SourceSpan(BaseModel):
    """Exact source provenance for a normalized frontend fact.

    Offsets are zero-based Python-string offsets and end-exclusive. Lines and
    columns are one-based. Backends whose native coordinates use bytes (notably
    Tree-sitter) must normalize before constructing this model.
    """

    file: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    start_line: int = Field(ge=1)
    start_column: int = Field(ge=1)
    end_line: int = Field(ge=1)
    end_column: int = Field(ge=1)

    def source_range(self) -> SourceRange:
        return SourceRange(
            file=self.file,
            start_line=self.start_line,
            end_line=self.end_line,
        )

    def text(self, source: str) -> str:
        return source[self.start_offset : self.end_offset]


class FrontendArgument(BaseModel):
    raw: str
    value: str
    span: SourceSpan
    optional: bool = False


class FrontendMacro(BaseModel):
    name: str
    raw: str
    span: SourceSpan
    arguments: list[FrontendArgument] = Field(default_factory=list)
    starred: bool = False


class FrontendEnvironment(BaseModel):
    name: str
    raw: str
    span: SourceSpan
    body_span: SourceSpan
    arguments: list[FrontendArgument] = Field(default_factory=list)

    def body(self, source: str) -> str:
        return self.body_span.text(source)


class FrontendMath(BaseModel):
    delimiter: str
    raw: str
    span: SourceSpan
    terminal_punctuation: SourceSpan | None = None


class FrontendRegion(BaseModel):
    kind: FrontendRegionKind
    span: SourceSpan

    @property
    def eligible_document_text(self) -> bool:
        return self.kind == FrontendRegionKind.DOCUMENT_TEXT


class FrontendSyntax(BaseModel):
    kind: FrontendSyntaxKind
    span: SourceSpan


class FrontendFile(BaseModel):
    path: str
    raw: str
    macros: list[FrontendMacro] = Field(default_factory=list)
    environments: list[FrontendEnvironment] = Field(default_factory=list)
    math: list[FrontendMath] = Field(default_factory=list)
    regions: list[FrontendRegion] = Field(default_factory=list)
    regions_complete: bool = False
    syntax: list[FrontendSyntax] = Field(default_factory=list)
    syntax_complete: bool = False

    def span(self, start: int, end: int) -> SourceSpan:
        """Construct an exact span without duplicating line/column arithmetic."""

        if start < 0 or end < start or end > len(self.raw):
            raise ValueError(f"invalid source span [{start}, {end}) for {self.path!r}")
        start_line = self.raw.count("\n", 0, start) + 1
        start_newline = self.raw.rfind("\n", 0, start)
        start_column = start + 1 if start_newline < 0 else start - start_newline
        end_line = self.raw.count("\n", 0, end) + 1
        end_newline = self.raw.rfind("\n", 0, end)
        end_column = end + 1 if end_newline < 0 else end - end_newline
        return SourceSpan(
            file=self.path,
            start_offset=start,
            end_offset=end,
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column,
        )


class FrontendDiagnostic(BaseModel):
    kind: FrontendDiagnosticKind
    message: str
    source: SourceSpan | None = None


class ParsedProject(BaseModel):
    main_file: str
    files: list[FrontendFile] = Field(default_factory=list)
    diagnostics: list[FrontendDiagnostic] = Field(default_factory=list)

    def file(self, path: str | Path) -> FrontendFile:
        target = str(Path(path).resolve())
        for item in self.files:
            if item.path == target:
                return item
        raise KeyError(f"unknown parsed file {target!r}")


class LatexFrontend(Protocol):
    """Parser-neutral, source-preserving LaTeX frontend contract.

    Implementations expose document syntax and provenance only. Mathematical
    interpretation belongs in Thorn analysis layers above this protocol.
    """

    name: str

    def parse_project(self, main_file: str | Path) -> ParsedProject: ...
