from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import ParsedProject, SourceSpan
from thorn.linguistic import LinguisticFrontend
from thorn.workspace import ProjectWorkspaceFacts

if TYPE_CHECKING:
    from thorn.linguistic_declarations import ProseDeclarationInventory

_ATOMIC_BRACED_SUBSCRIPT_RE = re.compile(
    r"^(?P<base>(?:\\[A-Za-z]+|[A-Za-z]))_\{(?P<sub>\\[A-Za-z]+|[A-Za-z0-9]+)\}$"
)


def canonical_symbol_name(name: str) -> str:
    """Canonicalize only mechanically equivalent simple LaTeX symbol spellings."""

    match = _ATOMIC_BRACED_SUBSCRIPT_RE.match(name)
    if match is None:
        return name
    return f"{match.group('base')}_{match.group('sub')}"


class ScopeKind(StrEnum):
    PROJECT = "project"
    RESULT = "result"
    STATEMENT = "statement"
    PROOF = "proof"
    LOCAL = "local"


class SymbolRole(StrEnum):
    UNKNOWN = "unknown"
    SCALAR = "scalar"
    MAP = "map"
    FUNCTION = "function"
    SET = "set"
    SEQUENCE = "sequence"
    INDEX = "index"


class IntroductionKind(StrEnum):
    LET = "let"
    FOR = "for"
    DEFINE = "define"
    SET = "set"
    QUANTIFIER = "quantifier"


class SymbolCandidateKind(StrEnum):
    INTRODUCTION = "introduction"
    DEFINITION = "definition"


class Scope(BaseModel):
    identifier: str
    kind: ScopeKind
    parent_identifier: str | None = None
    result_identifier: str | None = None
    source: SourceSpan | None = None


class Symbol(BaseModel):
    identifier: str
    name: str
    role: SymbolRole = SymbolRole.UNKNOWN
    arity: int | None = None
    domain_latex: str | None = None
    codomain_latex: str | None = None
    introduction_kind: IntroductionKind
    scope_identifier: str
    result_identifier: str | None = None
    source: SourceSpan
    introduction_source: SourceSpan
    raw_introduction: str


class SymbolIntroductionCandidate(BaseModel):
    """A declaration-shaped entity retained without entering deterministic scope."""

    identifier: str
    name: str
    kind: SymbolCandidateKind
    role: SymbolRole = SymbolRole.UNKNOWN
    scope_identifier: str
    result_identifier: str
    source: SourceSpan
    math_source: SourceSpan
    raw_context: str
    definition_operator: str | None = None
    expression_latex: str | None = None
    status: InferenceStatus = InferenceStatus.AMBIGUOUS
    evidence: list[StructuralEvidence] = Field(default_factory=list)


class Definition(BaseModel):
    identifier: str
    symbol_identifier: str
    operator: str
    expression_latex: str
    source: SourceSpan
    raw: str


class Constraint(BaseModel):
    identifier: str
    symbol_identifier: str
    relation: str
    expression_latex: str
    source: SourceSpan
    raw: str


class SymbolUse(BaseModel):
    name: str
    scope_identifier: str
    source: SourceSpan
    raw: str
    resolved_symbol_identifier: str | None = None


class ResultRegion(BaseModel):
    """Source regions needed by symbol extraction, independent of parser backend."""

    identifier: str
    file: str
    statement_span: SourceSpan
    proof_span: SourceSpan | None = None


class SymbolTable(BaseModel):
    scopes: list[Scope] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    candidates: list[SymbolIntroductionCandidate] = Field(default_factory=list)
    definitions: list[Definition] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    uses: list[SymbolUse] = Field(default_factory=list)

    def scope(self, identifier: str) -> Scope:
        for scope in self.scopes:
            if scope.identifier == identifier:
                return scope
        raise KeyError(f"unknown scope {identifier!r}")

    def symbol(self, identifier: str) -> Symbol:
        for symbol in self.symbols:
            if symbol.identifier == identifier:
                return symbol
        raise KeyError(f"unknown symbol {identifier!r}")

    def scope_chain(self, identifier: str) -> list[str]:
        chain: list[str] = []
        current: str | None = identifier
        while current is not None:
            if current in chain:
                raise ValueError(f"scope cycle at {current!r}")
            chain.append(current)
            current = self.scope(current).parent_identifier
        return chain

    def visible_symbols(
        self,
        scope_identifier: str,
        source: SourceSpan | None = None,
    ) -> list[Symbol]:
        chain = self.scope_chain(scope_identifier)
        rank = {scope_id: index for index, scope_id in enumerate(chain)}
        visible: list[Symbol] = []
        for symbol in self.symbols:
            if symbol.scope_identifier not in rank:
                continue
            if (
                source is not None
                and symbol.source.file == source.file
                and symbol.source.start_offset > source.start_offset
            ):
                continue
            visible.append(symbol)
        return sorted(
            visible,
            key=lambda symbol: (rank[symbol.scope_identifier], -symbol.source.start_offset),
        )

    def resolve(
        self,
        name: str,
        scope_identifier: str,
        source: SourceSpan,
    ) -> Symbol | None:
        canonical_name = canonical_symbol_name(name)
        for symbol in self.visible_symbols(scope_identifier, source):
            if canonical_symbol_name(symbol.name) == canonical_name:
                return symbol
        return None


def extract_symbol_table(
    project: ParsedProject,
    regions: list[ResultRegion],
    *,
    workspace: ProjectWorkspaceFacts | None = None,
    prose_declarations: ProseDeclarationInventory | None = None,
    linguistic_frontend: LinguisticFrontend | None = None,
) -> SymbolTable:
    """Build deterministic symbols plus optional ambiguity-aware candidates."""

    from thorn.symbol_extract import extract_symbol_table as run_extractor

    table = run_extractor(project, regions)

    # Mathematical project declarations remain Thorn-owned authority. Prose
    # authority is a separate policy layer consuming the normalized candidate and
    # workspace boundaries established by #161; it never reparses declaration grammar.
    from thorn.project_context import add_project_authoritative_context
    from thorn.project_context_source import preserve_project_authoritative_source

    add_project_authoritative_context(project, regions, table)
    preserve_project_authoritative_source(project, table)

    if workspace is not None and prose_declarations is not None:
        from thorn.project_semantic_context import add_project_semantic_context

        add_project_semantic_context(
            project,
            regions,
            table,
            workspace=workspace,
            prose_declarations=prose_declarations,
        )

    if linguistic_frontend is not None:
        from thorn.linguistic_symbols import add_linguistic_symbol_candidates

        add_linguistic_symbol_candidates(
            project,
            regions,
            table,
            linguistic_frontend,
        )
    return table
