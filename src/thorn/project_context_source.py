from __future__ import annotations

from thorn.frontend import ParsedProject
from thorn.symbols import Constraint, ScopeKind, SymbolRole, SymbolTable


def add_project_mapping_constraints(
    project: ParsedProject,
    table: SymbolTable,
) -> None:
    """Represent explicit project map declarations in canonical constraint IR.

    Source ownership stays with the exact structural introduction span recovered by
    project symbol extraction. Broader sentence/prose context is supplied separately
    by the generic source-mapped statement path; this layer does not reconstruct
    sentence boundaries or enlarge source spans.
    """

    del project
    constrained = {constraint.symbol_identifier for constraint in table.constraints}
    for symbol in table.symbols:
        if table.scope(symbol.scope_identifier).kind != ScopeKind.PROJECT:
            continue
        if symbol.role != SymbolRole.MAP or symbol.identifier in constrained:
            continue
        if symbol.domain_latex is None or symbol.codomain_latex is None:
            continue
        table.constraints.append(
            Constraint(
                identifier=f"constraint:{symbol.identifier}:mapping",
                symbol_identifier=symbol.identifier,
                relation=":",
                expression_latex=f"{symbol.domain_latex}\\to {symbol.codomain_latex}",
                source=symbol.introduction_source,
                raw=symbol.raw_introduction,
            )
        )

    table.constraints.sort(key=lambda item: (item.source.file, item.source.start_offset))
