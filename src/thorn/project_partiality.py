from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from thorn.frontend import (
    FrontendDiagnostic,
    FrontendDiagnosticKind,
    FrontendFile,
    FrontendMacro,
    ParsedProject,
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


def _complete_braced_argument(raw: str) -> bool:
    if len(raw) < 2 or raw[0] != "{" or raw[-1] != "}":
        return False

    depth = 0
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0 or (depth == 0 and index != len(raw) - 1):
                return False
    return depth == 0


def _available_include_span(file: FrontendFile, macro: FrontendMacro) -> SourceSpan:
    required = [argument for argument in macro.arguments if not argument.optional]
    if len(required) == 1 and _complete_braced_argument(required[0].raw):
        return macro.span

    line_end = file.raw.find("\n", macro.span.start_offset)
    end = len(file.raw) if line_end < 0 else line_end
    return _span(file, macro.span.start_offset, end)


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
        if len(required) != 1 or not _complete_braced_argument(required[0].raw):
            diagnostics.append(_partiality(file, macro, "complete static target is unavailable"))
            continue

        target = required[0].value.strip()
        if not target or _STATIC_TARGET_RE.fullmatch(target) is None:
            diagnostics.append(_partiality(file, macro, "target is not a static file path"))
            continue

        targets.append(IncludeTarget(value=target, source=macro.span))

    return targets, diagnostics


def _source_key(source: SourceSpan | None) -> tuple[str, int, int] | None:
    if source is None:
        return None
    return source.file, source.start_offset, source.end_offset


def _target_path(file: FrontendFile, target: IncludeTarget) -> Path:
    child = Path(target.value)
    if child.suffix == "":
        child = child.with_suffix(".tex")
    return (Path(file.path).parent / child).resolve()


def normalize_project_structure(project: ParsedProject) -> ParsedProject:
    """Normalize the safely reachable project without trusting guessed traversal.

    Existing frontends currently perform their own include traversal. Until #159
    decides the long-term workspace substrate, this guard re-derives only the safety
    boundary from normalized source facts: unsafe include-like evidence is explicit
    partiality, and files reached only through that evidence are not semantic input.
    """

    files_by_path = {str(Path(file.path).resolve()): file for file in project.files}
    main = str(Path(project.main_file).resolve())
    pending = [main]
    reachable: set[str] = set()
    safe_source_keys: set[tuple[str, int, int] | None] = set()
    partiality: list[FrontendDiagnostic] = []

    while pending:
        path = pending.pop(0)
        if path in reachable:
            continue
        file = files_by_path.get(path)
        if file is None:
            continue
        reachable.add(path)

        targets, include_diagnostics = classify_includes(file)
        partiality.extend(include_diagnostics)
        for target in targets:
            safe_source_keys.add(_source_key(target.source))
            child = str(_target_path(file, target))
            if child in files_by_path:
                pending.append(child)

    normalized_diagnostics: list[FrontendDiagnostic] = []
    for diagnostic in project.diagnostics:
        if (
            diagnostic.kind == FrontendDiagnosticKind.MISSING_FILE
            and _source_key(diagnostic.source) not in safe_source_keys
        ):
            continue
        if (
            diagnostic.source is not None
            and str(Path(diagnostic.source.file).resolve()) not in reachable
        ):
            continue
        normalized_diagnostics.append(diagnostic)
    normalized_diagnostics.extend(partiality)

    return project.model_copy(
        update={
            "files": [
                file
                for file in project.files
                if str(Path(file.path).resolve()) in reachable
            ],
            "diagnostics": normalized_diagnostics,
        }
    )
