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
    '''_PROJECT_EXPLICIT_DEF_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*"
    r"(?:"
    r":=|\\\\coloneqq|"
    r"\\\\(?:stackrel|overset)\\s*\\{\\s*"
    r"(?:(?:def|definition)|\\\\(?:text|mathrm)\\s*\\{\\s*(?:def|definition)\\s*\\})"
    r"\\s*\\}\\s*\\{=\\}"
    r")\\s*(?P<rhs>.+?)\\s*$",
    re.IGNORECASE | re.DOTALL,
)
''',
    '''_PROJECT_COLON_DEF_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*(?::=|\\\\coloneqq)\\s*"
    r"(?P<rhs>.+?)\\s*$",
    re.DOTALL,
)
_PROJECT_STACKED_DEF_PREFIX_RE = re.compile(
    rf"^\\s*(?P<name>{_SIMPLE_SYMBOL})\\s*\\\\(?:stackrel|overset)",
    re.IGNORECASE,
)
_DEF_ANNOTATION_RE = re.compile(
    r"(?<![A-Za-z])def(?:inition)?(?![A-Za-z])",
    re.IGNORECASE,
)
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''def _inside_result_region(math: FrontendMath, regions: list[ResultRegion]) -> bool:
''',
    '''def _take_braced_group(text: str, start: int) -> tuple[str, int] | None:
    """Return one balanced braced group and the offset immediately after it."""

    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text) or text[index] != "{":
        return None

    depth = 0
    content_start = index + 1
    for cursor in range(index, len(text)):
        char = text[cursor]
        if char == "{" and (cursor == 0 or text[cursor - 1] != "\\\\"):
            depth += 1
        elif char == "}" and (cursor == 0 or text[cursor - 1] != "\\\\"):
            depth -= 1
            if depth == 0:
                return text[content_start:cursor], cursor + 1
    return None


def _project_definition_candidate(content: str) -> _Candidate | None:
    colon_match = _PROJECT_COLON_DEF_RE.match(content)
    if colon_match is not None:
        return _Candidate(
            name=colon_match.group("name"),
            name_start=colon_match.start("name"),
            name_end=colon_match.end("name"),
            definition_operator=":=",
            definition_rhs=colon_match.group("rhs").strip(),
        )

    stacked_match = _PROJECT_STACKED_DEF_PREFIX_RE.match(content)
    if stacked_match is None:
        return None
    annotation_group = _take_braced_group(content, stacked_match.end())
    if annotation_group is None:
        return None
    annotation, offset = annotation_group
    equals_group = _take_braced_group(content, offset)
    if equals_group is None:
        return None
    equals, offset = equals_group

    # Presentation wrappers such as ``\\scriptstyle\\text{\\tiny def}`` are
    # irrelevant, but the semantic marker itself must be literal and the second
    # argument must still be exactly an equals sign modulo braces/whitespace.
    if _DEF_ANNOTATION_RE.search(annotation) is None:
        return None
    if re.sub(r"[{}\\s]", "", equals) != "=":
        return None
    rhs = content[offset:].strip()
    if not rhs:
        return None
    return _Candidate(
        name=stacked_match.group("name"),
        name_start=stacked_match.start("name"),
        name_end=stacked_match.end("name"),
        definition_operator=":=",
        definition_rhs=rhs,
    )


def _inside_result_region(math: FrontendMath, regions: list[ResultRegion]) -> bool:
''',
)

replace_once(
    "src/thorn/symbol_extract.py",
    '''        content, content_start = _math_inner(math)
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
''',
    '''        content, content_start = _math_inner(math)
        candidate = _project_definition_candidate(content)
        if candidate is None:
            continue
        _append_candidate(
''',
)

replace_once(
    "tests/test_proof_ir_context_fidelity.py",
    r'''A_\tau \stackrel{{\mathrm{{def}}}}{{=}} {definition}.
''',
    r'''A_\tau \stackrel{{{{\scriptstyle\text{{\tiny def}}}}}}{{{{=}}}} {definition}.
''',
)
