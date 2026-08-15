from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pylatexenc.latexwalker import (  # type: ignore[import-untyped]
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexMathNode,
    LatexWalker,
    LatexWalkerParseError,
    get_default_latex_context_db,
)
from pylatexenc.macrospec import EnvironmentSpec, MacroSpec  # type: ignore[import-untyped]

from thorn.frontend import (
    FrontendArgument,
    FrontendDiagnostic,
    FrontendDiagnosticKind,
    FrontendEnvironment,
    FrontendFile,
    FrontendMacro,
    FrontendMath,
    ParsedProject,
    SourceSpan,
)

_ONE_ARGUMENT_MACROS = {
    "Cref",
    "autoref",
    "cref",
    "eqref",
    "include",
    "input",
    "label",
    "ref",
}

_BEGIN_RE = re.compile(r"\\begin\s*\{([^{}]+)\}")
_UNKNOWN_OPTIONAL_MACRO_RE = re.compile(r"\\([A-Za-z@]+)\*?\s*\[")


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _span(path: Path, text: str, start: int, end: int) -> SourceSpan:
    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    start_line, start_column = _line_column(text, start)
    end_line, end_column = _line_column(text, end)
    return SourceSpan(
        file=str(path),
        start_offset=start,
        end_offset=end,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _raw_node_span(node: Any) -> tuple[int, int]:
    start = int(node.pos)
    return start, start + int(node.len)


def _argument_from_node(path: Path, text: str, node: Any) -> FrontendArgument | None:
    if node is None:
        return None
    start, end = _raw_node_span(node)
    raw = text[start:end]
    if not raw:
        return None

    optional = False
    value = raw
    if isinstance(node, LatexGroupNode):
        delimiters = getattr(node, "delimiters", None)
        if delimiters == ("[", "]"):
            optional = True
            value = raw[1:-1]
        elif delimiters == ("{", "}"):
            value = raw[1:-1]
    return FrontendArgument(
        raw=raw,
        value=value,
        span=_span(path, text, start, end),
        optional=optional,
    )


def _arguments(path: Path, text: str, node: Any) -> list[FrontendArgument]:
    nodeargd = getattr(node, "nodeargd", None)
    argnlist = getattr(nodeargd, "argnlist", None)
    if not argnlist:
        return []

    arguments: list[FrontendArgument] = []
    for arg in argnlist:
        converted = _argument_from_node(path, text, arg)
        if converted is None:
            continue
        if converted.raw == "*":
            continue
        arguments.append(converted)
    return arguments


def _macro(path: Path, text: str, node: Any) -> FrontendMacro:
    start, end = _raw_node_span(node)
    raw = text[start:end]
    name = str(node.macroname)
    command = "\\" + name
    starred = raw.startswith(command + "*")
    return FrontendMacro(
        name=name,
        raw=raw,
        span=_span(path, text, start, end),
        arguments=_arguments(path, text, node),
        starred=starred,
    )


def _environment_is_explicitly_closed(text: str, node: Any) -> bool:
    start, end = _raw_node_span(node)
    name = str(node.environmentname)
    return text[start:end].rstrip().endswith(f"\\end{{{name}}}")


def _environment_body_bounds(text: str, node: Any) -> tuple[int, int]:
    start, end = _raw_node_span(node)
    name = str(node.environmentname)
    begin_token = f"\\begin{{{name}}}"
    body_start = start + len(begin_token)

    nodeargd = getattr(node, "nodeargd", None)
    argnlist = getattr(nodeargd, "argnlist", None) or []
    for arg in argnlist:
        if arg is None:
            continue
        arg_start, arg_end = _raw_node_span(arg)
        if arg_start >= start:
            body_start = max(body_start, arg_end)

    end_token = f"\\end{{{name}}}"
    body_end = text.rfind(end_token, body_start, end)
    if body_end < body_start:
        body_end = end
    return body_start, body_end


def _environment(path: Path, text: str, node: Any) -> FrontendEnvironment:
    start, end = _raw_node_span(node)
    body_start, body_end = _environment_body_bounds(text, node)
    return FrontendEnvironment(
        name=str(node.environmentname),
        raw=text[start:end],
        span=_span(path, text, start, end),
        body_span=_span(path, text, body_start, body_end),
        arguments=_arguments(path, text, node),
    )


def _math(path: Path, text: str, node: Any) -> FrontendMath:
    start, end = _raw_node_span(node)
    delimiters = getattr(node, "delimiters", None)
    if isinstance(delimiters, tuple) and len(delimiters) == 2:
        opening, closing = str(delimiters[0]), str(delimiters[1])
        delimiter = opening if opening == closing else opening + closing
    else:
        raw = text[start:end]
        delimiter = "$$" if raw.startswith("$$") else "$"
    return FrontendMath(
        delimiter=delimiter,
        raw=text[start:end],
        span=_span(path, text, start, end),
    )


def _walk_nodes(nodes: Any) -> list[Any]:
    flattened: list[Any] = []

    def visit(node: Any) -> None:
        flattened.append(node)
        nodelist = getattr(node, "nodelist", None)
        if nodelist:
            for child in nodelist:
                visit(child)

        nodeargd = getattr(node, "nodeargd", None)
        argnlist = getattr(nodeargd, "argnlist", None)
        if argnlist:
            for arg in argnlist:
                if arg is not None:
                    visit(arg)

    for node in nodes:
        visit(node)
    return flattened


def _context_for(text: str) -> Any:
    context = get_default_latex_context_db()

    macros = [MacroSpec(name, "{") for name in sorted(_ONE_ARGUMENT_MACROS)]
    macros.append(MacroSpec("newtheorem", "*{[{["))

    known = set(_ONE_ARGUMENT_MACROS) | {"newtheorem"}
    for match in _UNKNOWN_OPTIONAL_MACRO_RE.finditer(text):
        name = match.group(1)
        if name not in known:
            macros.append(MacroSpec(name, "[{"))
            known.add(name)

    environments: list[Any] = []
    seen_envs: set[str] = set()
    for match in _BEGIN_RE.finditer(text):
        name = match.group(1).strip()
        if not name or name in seen_envs:
            continue
        seen_envs.add(name)
        environments.append(EnvironmentSpec(name, "["))

    context.add_context_category(
        "thorn-frontend",
        macros=macros,
        environments=environments,
        prepend=True,
    )
    return context


def _parse_error(path: Path, text: str, exc: Exception) -> FrontendDiagnostic:
    pos = int(getattr(exc, "pos", 0) or 0)
    end = min(len(text), pos + 1)
    return FrontendDiagnostic(
        kind=FrontendDiagnosticKind.PARSE_ERROR,
        message=str(exc),
        source=_span(path, text, pos, end),
    )


def _parse_file(path: Path) -> tuple[FrontendFile, list[FrontendDiagnostic]]:
    text = path.read_text(encoding="utf-8")
    context = _context_for(text)
    diagnostics: list[FrontendDiagnostic] = []

    try:
        walker = LatexWalker(text, latex_context=context, tolerant_parsing=False)
        nodes, _, _ = walker.get_latex_nodes()
    except LatexWalkerParseError as exc:
        diagnostics.append(_parse_error(path, text, exc))
        walker = LatexWalker(text, latex_context=context, tolerant_parsing=True)
        try:
            nodes, _, _ = walker.get_latex_nodes()
        except LatexWalkerParseError:
            nodes = []

    flattened = _walk_nodes(nodes)
    macros = [
        _macro(path, text, node) for node in flattened if isinstance(node, LatexMacroNode)
    ]
    environments = [
        _environment(path, text, node)
        for node in flattened
        if isinstance(node, LatexEnvironmentNode)
        and _environment_is_explicitly_closed(text, node)
    ]
    math = [_math(path, text, node) for node in flattened if isinstance(node, LatexMathNode)]

    macros.sort(key=lambda item: item.span.start_offset)
    environments.sort(key=lambda item: item.span.start_offset)
    math.sort(key=lambda item: item.span.start_offset)

    return (
        FrontendFile(
            path=str(path),
            raw=text,
            macros=macros,
            environments=environments,
            math=math,
        ),
        diagnostics,
    )


class PylatexencLatexFrontend:
    """LaTeX frontend backed by pylatexenc's source-preserving LatexWalker."""

    name = "pylatexenc"

    def parse_project(self, main_file: str | Path) -> ParsedProject:
        main = Path(main_file).resolve()
        if not main.exists():
            raise FileNotFoundError(main)

        files: list[FrontendFile] = []
        diagnostics: list[FrontendDiagnostic] = []
        pending: list[tuple[Path, SourceSpan | None]] = [(main, None)]
        seen: set[Path] = set()

        while pending:
            path, include_source = pending.pop(0)
            path = path.resolve()
            if path in seen:
                continue
            if not path.exists():
                diagnostics.append(
                    FrontendDiagnostic(
                        kind=FrontendDiagnosticKind.MISSING_FILE,
                        message=f"included LaTeX file not found: {path}",
                        source=include_source,
                    )
                )
                continue

            seen.add(path)
            parsed_file, file_diagnostics = _parse_file(path)
            files.append(parsed_file)
            diagnostics.extend(file_diagnostics)

            for macro in parsed_file.macros:
                if macro.name not in {"input", "include"} or not macro.arguments:
                    continue
                argument = macro.arguments[0]
                if argument.optional:
                    continue
                child = Path(argument.value.strip())
                if child.suffix == "":
                    child = child.with_suffix(".tex")
                child = (path.parent / child).resolve()
                if child not in seen:
                    pending.append((child, macro.span))

        return ParsedProject(
            main_file=str(main),
            files=files,
            diagnostics=diagnostics,
        )
