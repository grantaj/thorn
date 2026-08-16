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
    '''_PROJECT_STACKED_DEF_PREFIX_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*\\\\(?:stackrel|overset)",
    re.IGNORECASE,
)
_DEF_ANNOTATION_RE = re.compile(
''',
    '''_PROJECT_STACKED_DEF_PREFIX_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*\\\\(?:stackrel|overset)",
    re.IGNORECASE,
)
_PROJECT_MACRO_DEF_PREFIX_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*(?P<operator>\\\\[A-Za-z@]+)",
)
_STACKED_OPERATOR_PREFIX_RE = re.compile(r"^\\\\(?:stackrel|overset)", re.IGNORECASE)
_DEF_ANNOTATION_RE = re.compile(
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''def _project_definition_candidate(content: str) -> _Candidate | None:
    colon_match = _PROJECT_COLON_DEF_RE.match(content)
''',
    '''def _is_explicit_definition_operator(operator: str) -> bool:
    stripped = operator.strip()
    if stripped in {":=", r"\\coloneqq"}:
        return True

    stacked = _STACKED_OPERATOR_PREFIX_RE.match(stripped)
    if stacked is None:
        return False
    annotation_group = _take_braced_group(stripped, stacked.end())
    if annotation_group is None:
        return False
    annotation, offset = annotation_group
    equals_group = _take_braced_group(stripped, offset)
    if equals_group is None:
        return False
    equals, offset = equals_group
    if stripped[offset:].strip():
        return False
    return (
        _DEF_ANNOTATION_RE.search(annotation) is not None
        and re.sub(r"[{}\\s]", "", equals) == "="
    )


def _definition_operator_macros(file: FrontendFile) -> set[str]:
    """Return zero-argument local macros that mechanically mean definition-equals."""

    operators: set[str] = set()
    for macro in file.macros:
        if macro.name not in {"newcommand", "renewcommand", "providecommand"}:
            continue
        required = [argument for argument in macro.arguments if not argument.optional]
        optional = [argument.value.strip() for argument in macro.arguments if argument.optional]
        if len(required) < 2 or any(value not in {"", "0"} for value in optional):
            continue
        name = required[0].value.strip()
        if re.fullmatch(r"\\\\[A-Za-z@]+", name) is None:
            continue
        replacement = required[-1].value.strip()
        if _is_explicit_definition_operator(replacement):
            operators.add(name)
    return operators


def _project_definition_candidate(
    content: str,
    definition_operator_macros: set[str],
) -> _Candidate | None:
    colon_match = _PROJECT_COLON_DEF_RE.match(content)
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''    stacked_match = _PROJECT_STACKED_DEF_PREFIX_RE.match(content)
    if stacked_match is None:
        return None
    annotation_group = _take_braced_group(content, stacked_match.end())
''',
    '''    macro_match = _PROJECT_MACRO_DEF_PREFIX_RE.match(content)
    if (
        macro_match is not None
        and macro_match.group("operator") in definition_operator_macros
    ):
        rhs = content[macro_match.end() :].strip()
        if rhs:
            return _Candidate(
                name=macro_match.group("name"),
                name_start=macro_match.start("name"),
                name_end=macro_match.end("name"),
                definition_operator=macro_match.group("operator"),
                definition_rhs=rhs,
            )

    stacked_match = _PROJECT_STACKED_DEF_PREFIX_RE.match(content)
    if stacked_match is None:
        return None
    annotation_group = _take_braced_group(content, stacked_match.end())
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
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
''',
    '''def _inside_result_region(source: SourceSpan, regions: list[ResultRegion]) -> bool:
    for region in regions:
        for span in (region.statement_span, region.proof_span):
            if span is None or span.file != source.file:
                continue
            if span.start_offset <= source.start_offset and source.end_offset <= span.end_offset:
                return True
    return False


def _project_definition_blocks(
    file: FrontendFile,
) -> list[tuple[str, int, int, int, SourceSpan]]:
    """Return display-math blocks eligible for project-level definitions."""

    blocks: list[tuple[str, int, int, int, SourceSpan]] = []
    covered: list[tuple[int, int]] = []
    for math in file.math:
        content, content_start = _math_inner(math)
        blocks.append(
            (
                content,
                content_start,
                math.span.start_offset,
                math.span.end_offset,
                math.span,
            )
        )
        covered.append((math.span.start_offset, math.span.end_offset))

    # The regex frontend deliberately exposes equation environments as
    # environments rather than FrontendMath.  Treat the common display-math
    # environments as equivalent blocks here so semantic extraction does not
    # depend on a parser-specific representation choice.
    for environment in file.environments:
        if environment.name not in {"equation", "equation*", "displaymath"}:
            continue
        if any(
            start <= environment.span.start_offset and environment.span.end_offset <= end
            for start, end in covered
        ):
            continue
        body = environment.body(file.raw)
        leading = len(body) - len(body.lstrip())
        content = body.strip()
        if not content:
            continue
        blocks.append(
            (
                content,
                environment.body_span.start_offset + leading,
                environment.span.start_offset,
                environment.span.end_offset,
                environment.span,
            )
        )
    blocks.sort(key=lambda item: item[2])
    return blocks
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''    for math in file.math:
        if _inside_result_region(math, regions):
            continue
        content, content_start = _math_inner(math)
        candidate = _project_definition_candidate(content)
        if candidate is None:
            continue
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
''',
    '''    definition_operator_macros = _definition_operator_macros(file)
    for content, content_start, introduction_start, introduction_end, source in (
        _project_definition_blocks(file)
    ):
        if _inside_result_region(source, regions):
            continue
        candidate = _project_definition_candidate(content, definition_operator_macros)
        if candidate is None:
            continue
        _append_candidate(
            table=table,
            file=file,
            content_start=content_start,
            candidate=candidate,
            kind=IntroductionKind.DEFINE,
            scope_identifier="project",
            result_identifier=None,
            introduction_start=introduction_start,
            introduction_end=introduction_end,
        )
''',
)

# Add a regression matching the real-paper shape without copying its mathematics:
# a locally named zero-argument macro expands to an explicit def-marked equals
# sign, and the definition lives in an equation environment.  A nearby arbitrary
# macro must not be promoted to a definition.
test_path = Path("tests/test_proof_ir_context_fidelity.py")
test = test_path.read_text(encoding="utf-8")
anchor = '''def _write_precondition_case(path: Path, available: str) -> None:\n'''
if test.count(anchor) != 1:
    raise SystemExit("unexpected issue75 test layout")
addition = r'''def test_local_definitional_operator_macro_is_resolved_conservatively(
    tmp_path: Path,
) -> None:
    tex = tmp_path / "macro-definition.tex"
    tex.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newcommand{\meaningop}{\stackrel{\text{\tiny def}}{=}}
\newcommand{\noteop}{\stackrel{\text{\tiny note}}{=}}
\newtheorem{proposition}{Proposition}
\begin{document}
\begin{equation}
A_{\tau} \meaningop F(\tau^2)
\end{equation}
\begin{equation}
B_{\tau} \noteop G(\tau^2)
\end{equation}
\begin{proposition}\label{prop:main}
$A_\tau$ has property $Q$.
\end{proposition}
\begin{proof}
\[
Q(A_\tau)
\]
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    project, _semantic, document = _build(tex, "prop:main")
    project_symbols = [
        symbol
        for symbol in project.symbol_table.symbols
        if symbol.result_identifier is None
    ]
    assert [symbol.name for symbol in project_symbols] == [r"A_\tau"]
    definition = next(
        item
        for item in project.symbol_table.definitions
        if item.symbol_identifier == project_symbols[0].identifier
    )
    assert definition.operator == r"\meaningop"
    assert definition.expression_latex == r"F(\tau^2)"

    definition_source = next(source for source in document.sources if source.address == "D1")
    assert r"A_{\tau} \meaningop F(\tau^2)" in definition_source.text
    assert r"B_{\tau}" not in definition_source.text
    rescue = render_source_rescue(
        document,
        parse_source_rescue_request(document, "NEED_SOURCE D1"),
    )
    assert r"\meaningop" in rescue.text
    assert r"\tau^2" in rescue.text


'''
test_path.write_text(test.replace(anchor, addition + anchor), encoding="utf-8")
