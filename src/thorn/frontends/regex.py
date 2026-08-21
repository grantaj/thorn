from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from thorn.frontend import (
    FrontendArgument,
    FrontendDiagnostic,
    FrontendDiagnosticKind,
    FrontendEnvironment,
    FrontendFile,
    FrontendMacro,
    FrontendMath,
    FrontendRegion,
    FrontendRegionKind,
    ParsedProject,
    SourceSpan,
)
from thorn.frontend_regions import build_frontend_regions

_ONE_ARGUMENT_MACROS = {
    "Cref",
    "autoref",
    "cref",
    "end",
    "eqref",
    "include",
    "input",
    "label",
    "ref",
}


@dataclass(frozen=True)
class _OpenEnvironment:
    name: str
    macro: FrontendMacro


def _is_escaped(text: str, offset: int) -> bool:
    backslashes = 0
    index = offset - 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _span(path: Path, text: str, start: int, end: int) -> SourceSpan:
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


def _skip_space(text: str, offset: int) -> int:
    while offset < len(text) and text[offset].isspace():
        offset += 1
    return offset


def _parse_group(
    path: Path,
    text: str,
    start: int,
) -> tuple[FrontendArgument, int] | None:
    if start >= len(text) or text[start] not in "[{":
        return None
    opening = text[start]
    closing = "]" if opening == "[" else "}"
    depth = 1
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == opening and not _is_escaped(text, index):
            depth += 1
        elif char == closing and not _is_escaped(text, index):
            depth -= 1
            if depth == 0:
                end = index + 1
                return (
                    FrontendArgument(
                        raw=text[start:end],
                        value=text[start + 1 : index],
                        span=_span(path, text, start, end),
                        optional=opening == "[",
                    ),
                    end,
                )
        index += 1
    return None


def _argument_allowed(name: str, arguments: list[FrontendArgument], opening: str) -> bool:
    if name in _ONE_ARGUMENT_MACROS:
        return not arguments and opening == "{"
    if name == "begin":
        if not arguments:
            return opening == "{"
        return len(arguments) == 1 and opening == "["
    if name == "newtheorem":
        # Support the common forms
        #   \newtheorem{env}{Title}
        #   \newtheorem{env}[shared]{Title}
        #   \newtheorem{env}{Title}[within]
        # without allowing an unbounded run of following groups to be swallowed.
        return len(arguments) < 4
    return True


def _parse_macro(
    path: Path,
    text: str,
    start: int,
) -> tuple[FrontendMacro, int]:
    index = start + 1
    if index >= len(text):
        end = start + 1
        return (
            FrontendMacro(name="", raw=text[start:end], span=_span(path, text, start, end)),
            end,
        )

    if text[index].isalpha() or text[index] == "@":
        name_start = index
        while index < len(text) and (text[index].isalpha() or text[index] == "@"):
            index += 1
        name = text[name_start:index]
    else:
        name = text[index]
        index += 1

    starred = False
    if index < len(text) and text[index] == "*":
        starred = True
        index += 1

    command_end = index
    cursor = index
    arguments: list[FrontendArgument] = []
    while True:
        candidate = _skip_space(text, cursor)
        if candidate >= len(text) or text[candidate] not in "[{":
            break
        if not _argument_allowed(name, arguments, text[candidate]):
            break
        parsed = _parse_group(path, text, candidate)
        if parsed is None:
            break
        argument, cursor = parsed
        arguments.append(argument)

    end = cursor if arguments else command_end
    return (
        FrontendMacro(
            name=name,
            raw=text[start:end],
            span=_span(path, text, start, end),
            arguments=arguments,
            starred=starred,
        ),
        command_end,
    )


def _scan_macros(
    path: Path,
    text: str,
) -> tuple[list[FrontendMacro], list[FrontendRegion]]:
    """Scan compatibility macros and record comments in the same source pass."""

    macros: list[FrontendMacro] = []
    comments: list[FrontendRegion] = []
    index = 0
    while index < len(text):
        if text[index] == "%" and not _is_escaped(text, index):
            newline = text.find("\n", index)
            end = len(text) if newline < 0 else newline
            comments.append(
                FrontendRegion(
                    kind=FrontendRegionKind.COMMENT,
                    span=_span(path, text, index, end),
                )
            )
            index = len(text) if newline < 0 else newline + 1
            continue
        if text[index] == "\\":
            macro, next_index = _parse_macro(path, text, index)
            macros.append(macro)
            index = max(next_index, index + 1)
            continue
        index += 1
    return macros, comments


def _environment_name(macro: FrontendMacro) -> str | None:
    if not macro.arguments:
        return None
    first = macro.arguments[0]
    if first.optional:
        return None
    return first.value.strip()


def _scan_environments(
    path: Path,
    text: str,
    macros: list[FrontendMacro],
) -> tuple[list[FrontendEnvironment], list[FrontendDiagnostic]]:
    environments: list[FrontendEnvironment] = []
    diagnostics: list[FrontendDiagnostic] = []
    stack: list[_OpenEnvironment] = []

    for macro in macros:
        if macro.name == "begin":
            name = _environment_name(macro)
            if name:
                stack.append(_OpenEnvironment(name=name, macro=macro))
            continue
        if macro.name != "end":
            continue

        name = _environment_name(macro)
        if not name:
            continue
        match_index = next(
            (index for index in range(len(stack) - 1, -1, -1) if stack[index].name == name),
            None,
        )
        if match_index is None:
            diagnostics.append(
                FrontendDiagnostic(
                    kind=FrontendDiagnosticKind.PARSE_ERROR,
                    message=f"unmatched \\end{{{name}}}",
                    source=macro.span,
                )
            )
            continue

        for orphan in stack[match_index + 1 :]:
            diagnostics.append(
                FrontendDiagnostic(
                    kind=FrontendDiagnosticKind.PARSE_ERROR,
                    message=f"unclosed \\begin{{{orphan.name}}} before \\end{{{name}}}",
                    source=orphan.macro.span,
                )
            )

        opened = stack[match_index]
        del stack[match_index:]
        body_start = opened.macro.span.end_offset
        body_end = macro.span.start_offset
        environments.append(
            FrontendEnvironment(
                name=name,
                raw=text[opened.macro.span.start_offset : macro.span.end_offset],
                span=_span(
                    path,
                    text,
                    opened.macro.span.start_offset,
                    macro.span.end_offset,
                ),
                body_span=_span(path, text, body_start, body_end),
                arguments=opened.macro.arguments[1:],
            )
        )

    for orphan in stack:
        diagnostics.append(
            FrontendDiagnostic(
                kind=FrontendDiagnosticKind.PARSE_ERROR,
                message=f"unclosed \\begin{{{orphan.name}}}",
                source=orphan.macro.span,
            )
        )

    environments.sort(key=lambda item: item.span.start_offset)
    return environments, diagnostics


def _find_dollar_end(text: str, start: int, delimiter: str) -> int | None:
    index = start + len(delimiter)
    while index < len(text):
        if text[index] == "%" and not _is_escaped(text, index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith(delimiter, index) and not _is_escaped(text, index):
            return index + len(delimiter)
        index += 1
    return None


def _scan_math(path: Path, text: str) -> list[FrontendMath]:
    math: list[FrontendMath] = []
    index = 0
    while index < len(text):
        if text[index] == "%" and not _is_escaped(text, index):
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue

        if text.startswith("\\[", index) or text.startswith("\\(", index):
            opening = text[index : index + 2]
            closing = "\\]" if opening == "\\[" else "\\)"
            end_start = text.find(closing, index + 2)
            if end_start >= 0:
                math_end = end_start + 2
                math.append(
                    FrontendMath(
                        delimiter=opening + closing,
                        raw=text[index:math_end],
                        span=_span(path, text, index, math_end),
                    )
                )
                index = math_end
                continue

        if text[index] == "$" and not _is_escaped(text, index):
            delimiter = "$$" if text.startswith("$$", index) else "$"
            dollar_end = _find_dollar_end(text, index, delimiter)
            if dollar_end is not None:
                math.append(
                    FrontendMath(
                        delimiter=delimiter,
                        raw=text[index:dollar_end],
                        span=_span(path, text, index, dollar_end),
                    )
                )
                index = dollar_end
                continue
        index += 1
    return math


def _parse_file(path: Path) -> tuple[FrontendFile, list[FrontendDiagnostic]]:
    text = path.read_text(encoding="utf-8")
    macros, comment_regions = _scan_macros(path, text)
    environments, diagnostics = _scan_environments(path, text, macros)
    file = FrontendFile(
        path=str(path),
        raw=text,
        macros=macros,
        environments=environments,
        math=_scan_math(path, text),
    )
    return (
        file.model_copy(
            update={
                "regions": build_frontend_regions(
                    file,
                    explicit_regions=comment_regions,
                ),
                "regions_complete": True,
            }
        ),
        diagnostics,
    )


class RegexLatexFrontend:
    """Source-preserving adapter around Thorn's initial pragmatic parsing strategy.

    This backend intentionally performs no mathematical interpretation. It is
    the compatibility baseline for the parser A/B work in issue #16.
    """

    name = "regex"

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
