from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/thorn/symbol_extract.py",
    '''_SIMPLE_SYMBOL = r"(?:\\\\[A-Za-z]+|[A-Za-z])(?:_(?:\\{[^{}]+\\}|[A-Za-z0-9]+))?"
''',
    '''_SIMPLE_SYMBOL = (
    r"(?:\\\\[A-Za-z]+|[A-Za-z])"
    r"(?:_(?:\\{[^{}]+\\}|\\\\[A-Za-z]+|[A-Za-z0-9]+))?"
)
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''_SIMPLE_DEF_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*(?P<operator>:=|=|\\\\coloneqq)\\s*"
    r"(?P<rhs>.+?)\\s*$"
)
_RELATION_RE = re.compile(
''',
    '''_SIMPLE_DEF_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*(?P<operator>:=|=|\\\\coloneqq)\\s*"
    r"(?P<rhs>.+?)\\s*$"
)
_PROJECT_EXPLICIT_DEF_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*"
    r"(?:"
    r":=|\\\\coloneqq|"
    r"\\\\(?:stackrel|overset)\\s*\\{\\s*"
    r"(?:(?:def|definition)|\\\\(?:text|mathrm)\\s*\\{\\s*(?:def|definition)\\s*\\})"
    r"\\s*\\}\\s*\\{=\\}"
    r")\\s*(?P<rhs>.+?)\\s*$",
    re.IGNORECASE | re.DOTALL,
)
_RELATION_RE = re.compile(
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''    result_identifier: str,
    introduction_start: int,
''',
    '''    result_identifier: str | None,
    introduction_start: int,
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''def _masked_content(content: str) -> str:
''',
    '''def _inside_result_region(math: FrontendMath, regions: list[ResultRegion]) -> bool:
    for region in regions:
        for span in (region.statement_span, region.proof_span):
            if span is None or span.file != math.span.file:
                continue
            if (
                span.start_offset <= math.span.start_offset
                and math.span.end_offset <= span.end_offset
            ):
                return True
    return False


def _add_project_definitions(
    *,
    table: SymbolTable,
    file: FrontendFile,
    regions: list[ResultRegion],
) -> None:
    """Recover only mechanically explicit definitions outside result regions.

    Project scope is deliberately conservative: ordinary equalities are not
    definitions here.  We accept only explicit definitional operators so a
    later target can resolve a used symbol without importing unrelated section
    prose or promoting an arbitrary displayed equality into semantic context.
    """

    for math in file.math:
        if _inside_result_region(math, regions):
            continue
        content, content_start = _math_inner(math)
        match = _PROJECT_EXPLICIT_DEF_RE.match(content)
        if match is None:
            continue
        candidate = _Candidate(
            name=match.group("name"),
            name_start=match.start("name"),
            name_end=match.end("name"),
            definition_operator=":=",
            definition_rhs=match.group("rhs").strip(),
        )
        _append_candidate(
            table=table,
            file=file,
            content_start=content_start,
            candidate=candidate,
            kind=IntroductionKind.DEFINE,
            scope_identifier="project",
            result_identifier=None,
            introduction_start=math.span.start_offset,
            introduction_end=math.span.end_offset,
        )


def _masked_content(content: str) -> str:
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''        scope_rows.append((region, file, result_scope, statement_scope, proof_scope))

    # Statement introductions are result-scoped so theorem hypotheses are visible
''',
    '''        scope_rows.append((region, file, result_scope, statement_scope, proof_scope))

    # Ordinary manuscript prose can define notation before the theorem-like
    # environment that later uses it. Populate the existing project scope only
    # from explicit definitional operators; target selection downstream remains
    # use-driven, so this does not dump all project definitions into review.
    regions_by_file: dict[str, list[ResultRegion]] = {}
    for region in regions:
        regions_by_file.setdefault(region.file, []).append(region)
    for file in project.files:
        _add_project_definitions(
            table=table,
            file=file,
            regions=regions_by_file.get(file.path, []),
        )

    # Statement introductions are result-scoped so theorem hypotheses are visible
''',
)

# Add an end-to-end regression beside the existing issue-75 definition case.
test_path = Path("tests/test_proof_ir_context_fidelity.py")
test = test_path.read_text(encoding="utf-8")
anchor = '''def _write_precondition_case(path: Path, available: str) -> None:\n'''
if test.count(anchor) != 1:
    raise SystemExit("unexpected issue75 test layout")
new_test = r'''def _write_project_definition_case(path: Path, definition: str) -> None:
    path.write_text(
        rf"""\documentclass{{article}}
\usepackage{{amsthm}}
\newtheorem{{proposition}}{{Proposition}}
\begin{{document}}
The thresholded object is defined by
\[
A_\tau \stackrel{{\mathrm{{def}}}}{{=}} {definition}.
\]
\begin{{proposition}}\label{{prop:main}}
$A_\tau$ has property $Q$.
\end{{proposition}}
\begin{{proof}}
\[
Q(A_\tau)
\]
\end{{proof}}
\end{{document}}
""",
        encoding="utf-8",
    )


def test_explicit_project_definition_is_selected_only_when_target_uses_it(
    tmp_path: Path,
) -> None:
    good = tmp_path / "project-definition-good.tex"
    bad = tmp_path / "project-definition-bad.tex"
    _write_project_definition_case(good, r"F(\tau^2)")
    _write_project_definition_case(bad, r"F(\tau)")

    good_project, _good_ir, good_doc = _build(good, "prop:main")
    _bad_project, _bad_ir, bad_doc = _build(bad, "prop:main")

    project_symbol = next(
        symbol
        for symbol in good_project.symbol_table.symbols
        if symbol.name == r"A_\tau" and symbol.result_identifier is None
    )
    project_definition = next(
        definition
        for definition in good_project.symbol_table.definitions
        if definition.symbol_identifier == project_symbol.identifier
    )
    assert project_definition.expression_latex == r"F(\tau^2)."

    good_definition = next(source for source in good_doc.sources if source.address == "D1")
    bad_definition = next(source for source in bad_doc.sources if source.address == "D1")
    assert r"\tau^2" in good_definition.text
    assert r"\tau^2" not in bad_definition.text
    assert good_doc.render_initial() != bad_doc.render_initial()

    rescue = render_source_rescue(
        good_doc,
        parse_source_rescue_request(good_doc, "NEED_SOURCE D1"),
    )
    assert r"A_\tau" in rescue.text
    assert r"\tau^2" in rescue.text


'''
test_path.write_text(test.replace(anchor, new_test + anchor), encoding="utf-8")
