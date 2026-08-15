from __future__ import annotations

from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.dependencies import DependencyNode, DependencyResolution, ExtractedProject
from thorn.models import Severity, SourceRange
from thorn.symbols import Symbol, SymbolRole


class CheckCategory(StrEnum):
    DUPLICATE_LABEL = "duplicate_label"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    MISSING_REFERENCE = "missing_reference"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    ROLE_CONFLICT = "role_conflict"


class CheckFinding(BaseModel):
    rule: str
    category: CheckCategory
    severity: Severity
    title: str
    explanation: str
    source: SourceRange
    unit_id: str | None = None
    evidence: list[str] = Field(default_factory=list)


_CHECK_RULES: dict[CheckCategory, str] = {
    CheckCategory.DUPLICATE_LABEL: "TH101",
    CheckCategory.AMBIGUOUS_REFERENCE: "TH102",
    CheckCategory.MISSING_REFERENCE: "TH103",
    CheckCategory.CIRCULAR_DEPENDENCY: "TH104",
    CheckCategory.ROLE_CONFLICT: "TH113",
}


def _finding(
    category: CheckCategory,
    severity: Severity,
    title: str,
    explanation: str,
    source: SourceRange,
    *,
    unit_id: str | None = None,
    evidence: list[str] | None = None,
) -> CheckFinding:
    return CheckFinding(
        rule=_CHECK_RULES[category],
        category=category,
        severity=severity,
        title=title,
        explanation=explanation,
        source=source,
        unit_id=unit_id,
        evidence=evidence or [],
    )


def _check_dependencies(project: ExtractedProject) -> list[CheckFinding]:
    graph = project.dependency_graph
    findings: list[CheckFinding] = []

    by_label: dict[str, list[DependencyNode]] = defaultdict(list)
    for node in graph.nodes:
        if node.label is not None:
            by_label[node.label].append(node)

    for label, nodes in by_label.items():
        if len(nodes) < 2:
            continue
        locations = [
            f"{node.source.file}:{node.source.start_line}-{node.source.end_line}"
            for node in nodes
        ]
        duplicate = nodes[1]
        findings.append(
            _finding(
                CheckCategory.DUPLICATE_LABEL,
                Severity.ERROR,
                "Duplicate theorem/result label",
                f"The label {label!r} is attached to multiple theorem-like results.",
                duplicate.source,
                unit_id=duplicate.identifier,
                evidence=[f"label {label!r} occurs at {location}" for location in locations],
            )
        )

    for edge in graph.edges:
        if edge.resolution == DependencyResolution.AMBIGUOUS:
            findings.append(
                _finding(
                    CheckCategory.AMBIGUOUS_REFERENCE,
                    Severity.ERROR,
                    "Ambiguous theorem/result reference",
                    (
                        f"Reference {edge.target_label!r} resolves to more than one "
                        "theorem-like result."
                    ),
                    edge.source,
                    unit_id=edge.source_identifier,
                    evidence=[f"target label: {edge.target_label}"],
                )
            )
        elif edge.resolution == DependencyResolution.MISSING:
            findings.append(
                _finding(
                    CheckCategory.MISSING_REFERENCE,
                    Severity.ERROR,
                    "Missing internal reference",
                    (
                        f"Reference {edge.target_label!r} has no matching label in the "
                        "parsed LaTeX project."
                    ),
                    edge.source,
                    unit_id=edge.source_identifier,
                    evidence=[f"target label: {edge.target_label}"],
                )
            )

    for component in graph.cycles():
        first = graph.node(component[0])
        cycle_text = " -> ".join([*component, component[0]])
        findings.append(
            _finding(
                CheckCategory.CIRCULAR_DEPENDENCY,
                Severity.ERROR,
                "Circular theorem/result dependency",
                "These theorem-like results form a dependency cycle.",
                first.source,
                unit_id=first.identifier,
                evidence=[cycle_text],
            )
        )

    return findings


def _role_family(role: SymbolRole) -> str | None:
    if role == SymbolRole.UNKNOWN:
        return None
    if role in {SymbolRole.MAP, SymbolRole.FUNCTION}:
        return "callable"
    return role.value


def _check_symbols(project: ExtractedProject) -> list[CheckFinding]:
    """Emit only symbol diagnostics justified by explicit same-scope evidence.

    The symbol IR also records unresolved uses and lexical-scope candidates, but
    those facts are intentionally not diagnostics yet. Mathematical prose permits
    trailing binders (for example, a displayed inequality followed by "for every
    x") and repeated/local re-binding. The full synthetic-matrix audit for #18
    showed that source order or same-name scope facts alone are not sufficient
    evidence for a user-facing warning.
    """

    table = project.symbol_table
    findings: list[CheckFinding] = []
    grouped: dict[tuple[str, str], list[Symbol]] = defaultdict(list)
    for symbol in table.symbols:
        grouped[(symbol.scope_identifier, symbol.name)].append(symbol)

    for (_scope_identifier, name), symbols in grouped.items():
        role_families = {
            family
            for symbol in symbols
            if (family := _role_family(symbol.role)) is not None
        }
        if len(role_families) < 2:
            continue
        ordered = sorted(symbols, key=lambda symbol: symbol.source.start_offset)
        source_symbol = ordered[-1]
        findings.append(
            _finding(
                CheckCategory.ROLE_CONFLICT,
                Severity.WARNING,
                "Conflicting explicit symbol roles",
                (
                    f"{name!r} is explicitly introduced with incompatible roles in "
                    "the same lexical scope."
                ),
                source_symbol.source.source_range(),
                unit_id=source_symbol.result_identifier,
                evidence=[
                    f"{symbol.role.value}: {symbol.raw_introduction}"
                    for symbol in ordered
                    if _role_family(symbol.role) is not None
                ],
            )
        )

    return findings


def check_project(project: ExtractedProject) -> list[CheckFinding]:
    """Run deterministic, zero-inference structural analyses over Thorn IR."""

    findings = [*_check_dependencies(project), *_check_symbols(project)]
    return sorted(
        findings,
        key=lambda item: (
            item.source.file,
            item.source.start_line,
            item.rule,
            item.title,
        ),
    )
