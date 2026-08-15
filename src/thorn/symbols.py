from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.frontend import SourceSpan


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
            if source is not None and symbol.source.file == source.file:
                if symbol.source.start_offset > source.start_offset:
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
        for symbol in self.visible_symbols(scope_identifier, source):
            if symbol.name == name:
                return symbol
        return None
