from __future__ import annotations

from pathlib import Path

from thorn.dependencies import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyResolution,
    ExtractedProject,
    ReferenceContext,
)
from thorn.frontend import (
    FrontendDiagnosticKind,
    FrontendEnvironment,
    FrontendFile,
    FrontendMacro,
    LatexFrontend,
    SourceSpan,
)
from thorn.frontend import ParsedProject as FrontendProject
from thorn.frontends import RegexLatexFrontend
from thorn.linguistic import LinguisticFrontend
from thorn.linguistic_declarations import collect_project_prose_declarations
from thorn.linguistic_support import apply_linguistic_uncertainty
from thorn.models import SourceRange, TheoremUnit
from thorn.project_partiality import normalize_project_structure
from thorn.support_corroboration import corroborate_explicit_result_support
from thorn.support_extract import extract_proof_support_graph
from thorn.symbols import ResultRegion, extract_symbol_table
from thorn.workspace import ProjectPositionLookup, build_project_workspace_facts

_DEFAULT_THEOREM_ENVS = {
    "theorem",
    "lemma",
    "proposition",
    "corollary",
    "claim",
}
_REF_MACROS = {"ref", "eqref", "autoref", "cref", "Cref"}
_DEFAULT_FRONTEND = RegexLatexFrontend()


def _theorem_envs(project: FrontendProject) -> set[str]:
    envs = set(_DEFAULT_THEOREM_ENVS)
    for file in project.files:
        for macro in file.macros:
            if macro.name != "newtheorem" or not macro.arguments:
                continue
            argument = macro.arguments[0]
            if not argument.optional and argument.value.strip():
                envs.add(argument.value.strip())
    return envs


def _local_context(text: str, start_line: int, lines: int = 120) -> str:
    source_lines = text.splitlines()
    first = max(0, start_line - lines - 1)
    last = max(0, start_line - 1)
    return "\n".join(source_lines[first:last]).strip()


def _macros_in_span(
    file: FrontendFile,
    span: SourceSpan,
    names: set[str] | None = None,
) -> list[FrontendMacro]:
    return [
        macro
        for macro in file.macros
        if macro.span.start_offset >= span.start_offset
        and macro.span.end_offset <= span.end_offset
        and (names is None or macro.name in names)
    ]


def _first_required_argument(macro: FrontendMacro) -> str | None:
    for argument in macro.arguments:
        if not argument.optional:
            return argument.value.strip()
    return None


def _environment_title(environment: FrontendEnvironment) -> str | None:
    for argument in environment.arguments:
        if argument.optional:
            return argument.value
    return None


def _find_proof_after(
    file: FrontendFile,
    theorem: FrontendEnvironment,
    next_theorem_start: int | None,
) -> FrontendEnvironment | None:
    upper = next_theorem_start if next_theorem_start is not None else len(file.raw)
    candidates = [
        environment
        for environment in file.environments
        if environment.name == "proof"
        and environment.span.start_offset >= theorem.span.end_offset
        and environment.span.start_offset < upper
        and environment.span.start_line - theorem.span.end_line <= 40
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item.span.start_offset)


def _block_references(
    file: FrontendFile,
    environment: FrontendEnvironment,
    source_identifier: str,
    context: ReferenceContext,
) -> list[tuple[str, SourceRange, ReferenceContext]]:
    references: list[tuple[str, SourceRange, ReferenceContext]] = []
    for macro in _macros_in_span(file, environment.body_span, _REF_MACROS):
        raw_labels = _first_required_argument(macro)
        if not raw_labels:
            continue
        for label in (item.strip() for item in raw_labels.split(",")):
            if label:
                references.append((label, macro.span.source_range(), context))
    return references


def _project_labels(project: FrontendProject) -> set[str]:
    labels: set[str] = set()
    for file in project.files:
        for macro in file.macros:
            if macro.name != "label":
                continue
            label = _first_required_argument(macro)
            if label:
                labels.add(label)
    return labels


def _raise_missing_file_diagnostic(project: FrontendProject) -> None:
    for diagnostic in project.diagnostics:
        if diagnostic.kind != FrontendDiagnosticKind.MISSING_FILE:
            continue
        prefix = "included LaTeX file not found: "
        if diagnostic.message.startswith(prefix):
            raise FileNotFoundError(diagnostic.message.removeprefix(prefix))
        raise FileNotFoundError(diagnostic.message)


def _raise_project_partiality_diagnostic(project: FrontendProject) -> None:
    for diagnostic in project.diagnostics:
        if diagnostic.kind == FrontendDiagnosticKind.PROJECT_PARTIALITY:
            raise ValueError(diagnostic.message)


def extract_project(
    main_file: str | Path,
    *,
    frontend: LatexFrontend | None = None,
    linguistic_frontend: LinguisticFrontend | None = None,
) -> ExtractedProject:
    """Extract theorem/result, dependency, symbol, and proof-support IR.

    LaTeX syntax is supplied by a parser-neutral frontend. Optional local NLP
    proposes structural candidates only; mathematical interpretation remains
    Thorn-owned above both parser boundaries.
    """

    parser = frontend or _DEFAULT_FRONTEND
    parsed = normalize_project_structure(parser.parse_project(main_file))
    _raise_project_partiality_diagnostic(parsed)
    _raise_missing_file_diagnostic(parsed)
    workspace = build_project_workspace_facts(parsed)
    project_positions = ProjectPositionLookup(workspace)
    envs = _theorem_envs(parsed)
    all_labels = _project_labels(parsed)
    units: list[TheoremUnit] = []
    regions: list[ResultRegion] = []
    references: list[tuple[str, str, SourceRange, ReferenceContext]] = []

    for file in parsed.files:
        blocks = sorted(
            (environment for environment in file.environments if environment.name in envs),
            key=lambda item: item.span.start_offset,
        )
        for index, block in enumerate(blocks):
            next_start = blocks[index + 1].span.start_offset if index + 1 < len(blocks) else None
            proof = _find_proof_after(file, block, next_start)
            label_macros = _macros_in_span(file, block.body_span, {"label"})
            label = _first_required_argument(label_macros[0]) if label_macros else None
            identifier = label or f"{Path(file.path).name}:{block.span.start_line}:{block.name}"
            unit = TheoremUnit(
                identifier=identifier,
                environment=block.name,
                title=_environment_title(block),
                label=label,
                statement=block.body(file.raw).strip(),
                proof=proof.body(file.raw).strip() if proof else None,
                statement_range=block.span.source_range(),
                proof_range=proof.span.source_range() if proof else None,
                local_context=_local_context(file.raw, block.span.start_line),
            )
            units.append(unit)
            regions.append(
                ResultRegion(
                    identifier=identifier,
                    file=file.path,
                    statement_span=block.span,
                    proof_span=proof.span if proof is not None else None,
                )
            )
            references.extend(
                (
                    identifier,
                    target_label,
                    source,
                    context,
                )
                for target_label, source, context in _block_references(
                    file,
                    block,
                    identifier,
                    ReferenceContext.STATEMENT,
                )
            )
            if proof is not None:
                references.extend(
                    (
                        identifier,
                        target_label,
                        source,
                        context,
                    )
                    for target_label, source, context in _block_references(
                        file,
                        proof,
                        identifier,
                        ReferenceContext.PROOF,
                    )
                )

    ordered_results = sorted(
        zip(units, regions, strict=True),
        key=lambda item: project_positions.sort_key(
            item[1].file,
            item[1].statement_span.start_offset,
        ),
    )
    units = [item[0] for item in ordered_results]
    regions = [item[1] for item in ordered_results]

    by_label: dict[str, list[TheoremUnit]] = {}
    for unit in units:
        if unit.label is not None:
            by_label.setdefault(unit.label, []).append(unit)

    edges: list[DependencyEdge] = []
    for source_identifier, target_label, source, context in references:
        candidates = by_label.get(target_label, [])
        if not candidates:
            if target_label not in all_labels:
                edges.append(
                    DependencyEdge(
                        source_identifier=source_identifier,
                        target_label=target_label,
                        source=source,
                        context=context,
                        resolution=DependencyResolution.MISSING,
                    )
                )
            continue
        if len(candidates) == 1:
            edges.append(
                DependencyEdge(
                    source_identifier=source_identifier,
                    target_label=target_label,
                    target_identifier=candidates[0].identifier,
                    source=source,
                    context=context,
                    resolution=DependencyResolution.RESOLVED,
                )
            )
        else:
            edges.append(
                DependencyEdge(
                    source_identifier=source_identifier,
                    target_label=target_label,
                    source=source,
                    context=context,
                    resolution=DependencyResolution.AMBIGUOUS,
                )
            )

    graph = DependencyGraph(
        nodes=[DependencyNode.from_unit(unit) for unit in units],
        edges=edges,
    )
    enriched = [
        unit.model_copy(
            update={"referenced_results": graph.render_dependency_context(unit.identifier)}
        )
        for unit in units
    ]
    support_graph = extract_proof_support_graph(
        parsed,
        regions,
        linguistic_frontend=linguistic_frontend,
    )
    if linguistic_frontend is not None:
        support_graph = apply_linguistic_uncertainty(
            parsed,
            regions,
            support_graph,
            linguistic_frontend,
        )
    support_graph = corroborate_explicit_result_support(
        support_graph,
        dependencies=graph,
        units=enriched,
    )
    prose_declarations = collect_project_prose_declarations(
        parsed,
        regions,
        linguistic_frontend,
    )

    return ExtractedProject(
        main_file=parsed.main_file,
        units=enriched,
        dependency_graph=graph,
        symbol_table=extract_symbol_table(
            parsed,
            regions,
            workspace=workspace,
            prose_declarations=prose_declarations,
            linguistic_frontend=linguistic_frontend,
        ),
        proof_support_graph=support_graph,
        workspace=workspace,
        prose_declarations=prose_declarations,
    )


def extract_units(
    main_file: str | Path,
    *,
    frontend: LatexFrontend | None = None,
    linguistic_frontend: LinguisticFrontend | None = None,
) -> list[TheoremUnit]:
    """Extract theorem-like result/proof units from a LaTeX project."""

    return extract_project(
        main_file,
        frontend=frontend,
        linguistic_frontend=linguistic_frontend,
    ).units
