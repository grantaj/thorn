from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import ParsedProject, SourceSpan
from thorn.workspace import (
    ProjectPosition,
    ProjectPositionLookup,
    ProjectWorkspaceFacts,
    WorkspaceResolution,
)

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
        """Return lexically visible symbols without guessing project occurrence order.

        Project symbols are returned for scope introspection when no source position is
        requested. Source-sensitive project visibility belongs to ``resolve`` because it
        requires ``ProjectWorkspaceFacts`` rather than physical file offsets.
        """

        chain = self.scope_chain(scope_identifier)
        rank = {scope_id: index for index, scope_id in enumerate(chain)}
        visible: list[Symbol] = []
        for symbol in self.symbols:
            if symbol.scope_identifier not in rank:
                continue
            if source is not None and symbol.scope_identifier == "project":
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

    def _resolve_project_symbol(
        self,
        canonical_name: str,
        scope_identifier: str,
        source: SourceSpan,
        workspace: ProjectWorkspaceFacts | None,
    ) -> Symbol | None:
        if (
            workspace is None
            or workspace.resolution != WorkspaceResolution.RESOLVED
            or "project" not in self.scope_chain(scope_identifier)
        ):
            return None

        lookup = ProjectPositionLookup(workspace)
        use_positions = lookup.positions(source.file, source.start_offset)
        if not use_positions:
            return None
        candidates = [
            symbol
            for symbol in self.symbols
            if symbol.scope_identifier == "project"
            and canonical_symbol_name(symbol.name) == canonical_name
        ]
        if not candidates:
            return None

        occurrence_targets: set[str | None] = set()
        for use_position in use_positions:
            best_position: ProjectPosition | None = None
            best_identifiers: set[str] = set()
            for symbol in candidates:
                declaration = symbol.introduction_source
                for position in lookup.positions(
                    declaration.file,
                    declaration.end_offset,
                ):
                    if position >= use_position:
                        continue
                    if best_position is None or best_position < position:
                        best_position = position
                        best_identifiers = {symbol.identifier}
                    elif position == best_position:
                        best_identifiers.add(symbol.identifier)
            occurrence_targets.add(
                next(iter(best_identifiers)) if len(best_identifiers) == 1 else None
            )

        if len(occurrence_targets) != 1:
            return None
        target_identifier = next(iter(occurrence_targets))
        if target_identifier is None:
            return None
        return self.symbol(target_identifier)

    def resolve(
        self,
        name: str,
        scope_identifier: str,
        source: SourceSpan,
        *,
        workspace: ProjectWorkspaceFacts | None = None,
    ) -> Symbol | None:
        canonical_name = canonical_symbol_name(name)
        for symbol in self.visible_symbols(scope_identifier, source):
            if canonical_symbol_name(symbol.name) == canonical_name:
                return symbol
        return self._resolve_project_symbol(
            canonical_name,
            scope_identifier,
            source,
            workspace,
        )


def extract_symbol_table(
    project: ParsedProject,
    regions: list[ResultRegion],
    *,
    workspace: ProjectWorkspaceFacts | None = None,
) -> SymbolTable:
    """Build Thorn-owned deterministic symbol evidence."""

    from thorn.symbol_extract import extract_symbol_table as run_extractor

    table = run_extractor(project, regions)

    from thorn.structured_authority import enforce_structured_authority_boundary

    enforce_structured_authority_boundary(project, table, workspace=workspace)

    # Explicit mathematical project declarations remain Thorn-owned authority. Their
    # source span is the exact structural introduction recovered by this extractor;
    # broader prose belongs to the separate generic statement/context substrate.
    from thorn.project_context import add_project_authoritative_context
    from thorn.project_context_source import add_project_mapping_constraints

    add_project_authoritative_context(
        project,
        regions,
        table,
        workspace=workspace,
    )
    add_project_mapping_constraints(project, table)
    enforce_structured_authority_boundary(project, table, workspace=workspace)
    return table
