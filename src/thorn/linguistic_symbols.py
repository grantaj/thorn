from __future__ import annotations

from thorn.frontend import ParsedProject
from thorn.linguistic import LinguisticFrontend
from thorn.symbols import ResultRegion, SymbolTable


def add_linguistic_symbol_candidates(
    project: ParsedProject,
    regions: list[ResultRegion],
    table: SymbolTable,
    frontend: LinguisticFrontend,
) -> None:
    """Do not derive mathematical symbol candidates from generic linguistic parsing.

    Issue #203 is testing whether this convenience interpretation supplies any
    independently useful Thorn-owned capability. Exact source-mapped linguistic
    statements remain available through the statement/advisory-context substrate;
    this bounded ablation deliberately adds no symbol candidates and does not mutate
    deterministic symbol authority, scope, provenance, or resolution.
    """

    del project, regions, table, frontend
