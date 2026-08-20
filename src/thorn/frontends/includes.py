from __future__ import annotations

import re
from dataclasses import dataclass

from thorn.frontend import (
    FrontendDiagnostic,
    FrontendDiagnosticKind,
    FrontendFile,
    FrontendMacro,
    SourceSpan,
)

_INCLUDE_NAMES = {"include", "input"}
_LITERAL_ENVIRONMENTS = {"Verbatim", "comment", "lstlisting", "minted", "verbatim"}
_STATIC_TARGET_RE = re.compile(r"[A-Za-z0-9._/ -]+")


@dataclass(frozen=True)
class IncludeTarget:
    value: str
    source: SourceSpan


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _span(file: FrontendFile, start: int, end: int) -> SourceSpan:
    start_line, start_column = _line_column(file.raw, start)
    end_line, end_column = _line_column(file.raw, end)
    return SourceSpan(
        file=file.path,
        start_offset=start,
        end_offset=end,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _inside_literal_environment(file: FrontendFile, macro: FrontendMacro) -> bool:
    return any(
        environment.name in _LITERAL_ENVIRONMENTS
        and environment.body_span.start_offset <= macro.span.start_offset
        and macro.span.end_offset <= environment.body_span.end_offset
        for environment in file.environments
    )


def _inside_macro_argument(file: FrontendFile, macro: FrontendMacro) -> bool:
    return any(
        other is not macro
        and other.span.start_offset < macro.span.start_offset
        and macro.span.end_offset <= other.span.end_offset
        for other in file.macros
    )


def _available_include_span(file: FrontendFile, macro: FrontendMacro) -> SourceSpan:
    start = macro.span.start_offset
    end = macro.span.end_offset
    cursor = end
    while cursor < len(file.raw) and file.raw[cursor] in " \t":
        cursor += 1
    if cursor < len(file.raw) and file.raw[cursor] == "{":
        line_end = file.raw.find("\n", cursor)
        end = len(file.raw) if line_end < 0 else line_end
    return _span(file, start, end)


def _partiality(file: FrontendFile, macro: FrontendMacro, reason: str) -> FrontendDiagnostic:
    return FrontendDiagnostic(
        kind=FrontendDiagnosticKind.PROJECT_PARTIALITY,
        message=f"indeterminate \\{macro.name} project structure: {reason}",
        source=_available_include_span(file, macro),
    )


def classify_includes(
    file: FrontendFile,
) -> tuple[list[IncludeTarget], list[FrontendDiagnostic]]:
    """Return statically safe includes and explicit project partiality.

    This is a narrow authority-boundary check, not a general TeX expander. Include
    commands are traversable only when the frontend exposes one complete static path
    and the command is not demonstrably literal content or nested in another macro,
    where execution semantics would require macro expansion to determine safely.
    """

    targets: list[IncludeTarget] = []
    diagnostics: list[FrontendDiagnostic] = []
    for macro in file.macros:
        if macro.name not in _INCLUDE_NAMES or _inside_literal_environment(file, macro):
            continue
        if _inside_macro_argument(file, macro):
            diagnostics.append(_partiality(file, macro, "include occurs inside another macro"))
            continue

        required = [argument for argument in macro.arguments if not argument.optional]
        if len(required) != 1:
            diagnostics.append(_partiality(file, macro, "complete static target is unavailable"))
            continue

        target = required[0].value.strip()
        if not target or _STATIC_TARGET_RE.fullmatch(target) is None:
            diagnostics.append(_partiality(file, macro, "target is not a static file path"))
            continue

        targets.append(IncludeTarget(value=target, source=macro.span))

    return targets, diagnostics
