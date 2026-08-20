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


class SourceSpan(BaseModel):
    """Exact source provenance for a normalized frontend fact.

    Offsets are zero-based and end-exclusive. Lines and columns are one-based.
    The existing Thorn diagnostic layer can deliberately collapse this to a
    line-oriented :class:`SourceRange` without losing the original offsets.
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


class FrontendFile(BaseModel):
    path: str
    raw: str
    macros: list[FrontendMacro] = Field(default_factory=list)
    environments: list[FrontendEnvironment] = Field(default_factory=list)
    math: list[FrontendMath] = Field(default_factory=list)


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
