from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/thorn/support_extract.py",
    '''_REFERENCE_SUPPORT_CUE_RE = re.compile(
    r"\\b(?:by|from|using|apply|applying|invoke|invoking)\\b",
    re.IGNORECASE,
)
_BOUND_NAME_RE = re.compile(
''',
    '''_REFERENCE_SUPPORT_CUE_RE = re.compile(
    r"\\b(?:by|from|using|apply|applying|invoke|invoking)\\b",
    re.IGNORECASE,
)
_ASSERTED_SUPPORT_RE = re.compile(
    r"^\\s*(?:by|using|from|applying|apply|invoking|invoke)\\s+(.+?),\\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_BOUND_NAME_RE = re.compile(
''',
)

replace_once(
    "src/thorn/support_extract.py",
    '''    for property_match in _NAMED_PROPERTY_RE.finditer(raw):
        start = claim.source.start_offset + property_match.start()
        end = claim.source.start_offset + property_match.end()
        _add_edge(
            edges,
            target=claim,
            kind=SupportKind.NAMED_PROPERTY,
            source=_span(file, start, end),
            raw=property_match.group(0),
            named_property=property_match.group(1).lower(),
        )

    since = _SINCE_RE.match(raw)
''',
    '''    for property_match in _NAMED_PROPERTY_RE.finditer(raw):
        start = claim.source.start_offset + property_match.start()
        end = claim.source.start_offset + property_match.end()
        _add_edge(
            edges,
            target=claim,
            kind=SupportKind.NAMED_PROPERTY,
            source=_span(file, start, end),
            raw=property_match.group(0),
            named_property=property_match.group(1).lower(),
        )

    # Real mathematical prose frequently names a support principle without a
    # theorem reference (for example, "using stability under ..."). Preserve
    # the asserted support phrase generically rather than growing a vocabulary
    # of property names. The phrase is deliberately UNRESOLVED: extracting a
    # support assertion is not evidence that its premises hold or that the
    # asserted mathematical transformation is valid.
    asserted = _ASSERTED_SUPPORT_RE.match(raw)
    has_structural_support = any(
        edge.target_claim_identifier == claim.identifier
        and edge.kind
        in {
            SupportKind.RESULT_REFERENCE,
            SupportKind.EQUATION_REFERENCE,
            SupportKind.DEFINITION,
            SupportKind.NAMED_PROPERTY,
        }
        for edge in edges
    )
    if asserted is not None and not has_structural_support:
        reason = asserted.group(1).strip()
        reason_start = raw.find(asserted.group(1))
        absolute_start = claim.source.start_offset + reason_start
        reason_source = _span(
            file,
            absolute_start,
            absolute_start + len(asserted.group(1)),
        )
        _add_edge(
            edges,
            target=claim,
            kind=SupportKind.NAMED_PROPERTY,
            source=reason_source,
            raw=reason,
            named_property=reason,
            confidence=None,
            status=InferenceStatus.UNRESOLVED,
            evidence=[
                StructuralEvidence(
                    reason=(
                        "source explicitly presents this phrase as mathematical "
                        "support; its identity, premises, and validity remain unresolved"
                    ),
                    source=reason_source,
                    target=claim.source,
                    context=claim.raw,
                )
            ],
        )

    since = _SINCE_RE.match(raw)
''',
)

replace_once(
    "src/thorn/canonical_proof_ir.py",
    '''    used_dependency_labels = {
        edge.target_label
        for edge in included_support
        if edge.kind == SupportKind.RESULT_REFERENCE and edge.target_label is not None
    }
    dependencies = [
        dependency
        for dependency in item.dependencies
        if dependency.label in used_dependency_labels
    ]
''',
    '''    # SemanticReviewItem has already bounded direct dependencies for this
    # review target. Preserve that dependency-driven closure here, including
    # assumptions/results referenced by the theorem statement itself. Filtering
    # again by proof-body support edges made load-bearing statement assumptions
    # disappear and, worse, removed their source-rescue addresses.
    dependencies = sorted(
        item.dependencies,
        key=lambda dependency: (
            dependency.source.file,
            dependency.source.start_line,
            dependency.source.end_line,
            dependency.identifier,
        ),
    )
''',
)

replace_once(
    "src/thorn/eval_review.py",
    '''def _result_symbol_context(
    project: ExtractedProject,
    result_identifier: str,
) -> tuple[
    list[Constraint],
    list[Constraint],
    list[Symbol],
    list[Definition],
    list[SymbolIntroductionCandidate],
]:
    table = project.symbol_table
    symbols = sorted(
        (symbol for symbol in table.symbols if symbol.result_identifier == result_identifier),
        key=_symbol_key,
    )
    symbol_ids = {symbol.identifier for symbol in symbols}
''',
    '''def _result_symbol_context(
    project: ExtractedProject,
    result_identifier: str,
    claims: list[Claim],
) -> tuple[
    list[Constraint],
    list[Constraint],
    list[Symbol],
    list[Definition],
    list[SymbolIntroductionCandidate],
]:
    table = project.symbol_table
    result = _result_node(project, result_identifier)

    def is_target_use(source: SourceSpan) -> bool:
        if (
            source.file == result.source.file
            and result.source.start_line <= source.start_line <= result.source.end_line
        ):
            return True
        return any(
            source.file == claim.source.file
            and claim.source.start_offset <= source.start_offset
            and source.end_offset <= claim.source.end_offset
            for claim in claims
        )

    # Keep result-owned symbols, then close selectively over actually resolved
    # symbol uses in the target statement/proof. This admits an outer/global
    # definition only when the target really uses that symbol; it is not a
    # whole-paper symbol-table dump.
    symbol_ids = {
        symbol.identifier
        for symbol in table.symbols
        if symbol.result_identifier == result_identifier
    }
    symbol_ids.update(
        use.resolved_symbol_identifier
        for use in table.uses
        if use.resolved_symbol_identifier is not None and is_target_use(use.source)
    )
    symbols = sorted(
        (symbol for symbol in table.symbols if symbol.identifier in symbol_ids),
        key=_symbol_key,
    )
''',
)

replace_once(
    "src/thorn/eval_review.py",
    '''    hypotheses, local_constraints, symbols, definitions, candidates = _result_symbol_context(
        project,
        result_identifier,
    )
''',
    '''    hypotheses, local_constraints, symbols, definitions, candidates = _result_symbol_context(
        project,
        result_identifier,
        claims,
    )
''',
)
