from __future__ import annotations

import re
from bisect import bisect_right
from pathlib import Path
from typing import Any

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

_ENVIRONMENT_RE = re.compile(r"^\\begin\s*\{([^{}]+)\}")
_OPAQUE_ENVIRONMENT_KINDS = {
    "comment": FrontendRegionKind.COMMENT,
    "verbatim": FrontendRegionKind.VERBATIM,
    "verbatim*": FrontendRegionKind.VERBATIM,
    "lstlisting": FrontendRegionKind.LISTING,
    "minted": FrontendRegionKind.MINTED,
}
_NATIVE_OPAQUE_TYPES = {
    "comment_environment": FrontendRegionKind.COMMENT,
    "verbatim_environment": FrontendRegionKind.VERBATIM,
    "listing_environment": FrontendRegionKind.LISTING,
    "minted_environment": FrontendRegionKind.MINTED,
}
_GROUP_PREFIXES = ("curly_group", "brack_group")
_MATH_TYPES = {"inline_formula", "displayed_equation", "math_environment"}


class _Coordinates:
    """Translate Tree-sitter UTF-8 byte positions to Thorn character positions."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._byte_boundaries = [0]
        byte_offset = 0
        for char in text:
            byte_offset += len(char.encode("utf-8"))
            self._byte_boundaries.append(byte_offset)

    def character_offset(self, byte_offset: int) -> int:
        # Nodes are expected to end on UTF-8 boundaries. bisect keeps malformed
        # parser coordinates fail-closed instead of inventing a later offset.
        return max(0, bisect_right(self._byte_boundaries, byte_offset) - 1)

    def line_column(self, offset: int) -> tuple[int, int]:
        line = self.text.count("\n", 0, offset) + 1
        last_newline = self.text.rfind("\n", 0, offset)
        column = offset + 1 if last_newline < 0 else offset - last_newline
        return line, column

    def span(self, path: Path, start_byte: int, end_byte: int) -> SourceSpan:
        start = self.character_offset(start_byte)
        end = self.character_offset(end_byte)
        start_line, start_column = self.line_column(start)
        end_line, end_column = self.line_column(end)
        return SourceSpan(
            file=str(path),
            start_offset=start,
            end_offset=end,
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column,
        )

    def byte_slice(self, source_bytes: bytes, node: Any) -> str:
        return source_bytes[int(node.start_byte) : int(node.end_byte)].decode("utf-8")


def _is_escaped(text: str, offset: int) -> bool:
    backslashes = 0
    index = offset - 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _surface_groups(
    path: Path,
    coordinates: _Coordinates,
    start: int,
) -> tuple[list[FrontendArgument], int]:
    """Recover generic command groups that the grammar leaves as siblings.

    tree-sitter-latex intentionally gives generic commands no package-specific
    signature. In particular an optional bracket interrupts `generic_command`.
    This bounded recovery is applied only from a Tree-sitter-recognized command
    boundary; it is not a second whole-document scanner.
    """
    text = coordinates.text
    cursor = start
    recovered_end = start
    arguments: list[FrontendArgument] = []
    while True:
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] not in "[{":
            break
        opening = text[cursor]
        closing = "]" if opening == "[" else "}"
        depth = 1
        index = cursor + 1
        while index < len(text):
            if text[index] == opening and not _is_escaped(text, index):
                depth += 1
            elif text[index] == closing and not _is_escaped(text, index):
                depth -= 1
                if depth == 0:
                    end = index + 1
                    raw = text[cursor:end]
                    arguments.append(
                        FrontendArgument(
                            raw=raw,
                            value=raw[1:-1],
                            span=_span_from_characters(path, coordinates, cursor, end),
                            optional=opening == "[",
                        )
                    )
                    cursor = end
                    recovered_end = end
                    break
            index += 1
        else:
            break
    return arguments, recovered_end


def _load_parser() -> Any:
    try:
        import tree_sitter_latex  # type: ignore
        from tree_sitter import Language, Parser  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "tree-sitter frontend requires tree-sitter plus the tree-sitter-latex grammar; "
            "see docs/parser-evaluation.md for the pinned optional installation"
        ) from exc

    language = Language(tree_sitter_latex.language())
    return Parser(language)


def _walk(node: Any) -> list[Any]:
    nodes: list[Any] = []
    stack = [node]
    while stack:
        current = stack.pop()
        nodes.append(current)
        stack.extend(reversed(list(current.children)))
    return nodes


def _field(node: Any, name: str) -> Any | None:
    return node.child_by_field_name(name)


def _same_node(left: Any, right: Any | None) -> bool:
    return (
        right is not None
        and left.type == right.type
        and int(left.start_byte) == int(right.start_byte)
        and int(left.end_byte) == int(right.end_byte)
    )


def _group_argument(
    path: Path,
    source_bytes: bytes,
    coordinates: _Coordinates,
    node: Any,
) -> FrontendArgument:
    raw = coordinates.byte_slice(source_bytes, node)
    optional = raw.startswith("[") and raw.endswith("]")
    value = raw[1:-1] if (raw.startswith("{") and raw.endswith("}")) or optional else raw
    return FrontendArgument(
        raw=raw,
        value=value,
        span=coordinates.span(path, int(node.start_byte), int(node.end_byte)),
        optional=optional,
    )


def _command_macro(
    path: Path,
    source_bytes: bytes,
    coordinates: _Coordinates,
    node: Any,
) -> FrontendMacro | None:
    command = _field(node, "command")
    if command is None:
        return None
    command_raw = coordinates.byte_slice(source_bytes, command)
    if not command_raw.startswith("\\"):
        return None

    starred = command_raw.endswith("*")
    name = command_raw[1:-1] if starred else command_raw[1:]
    if not name:
        return None

    arguments: list[FrontendArgument] = []
    for child in node.children:
        if _same_node(child, command):
            continue
        if child.type.startswith(_GROUP_PREFIXES):
            arguments.append(_group_argument(path, source_bytes, coordinates, child))

    start = coordinates.character_offset(int(node.start_byte))
    end = coordinates.character_offset(int(node.end_byte))
    if node.type == "generic_command":
        command_end = coordinates.character_offset(int(command.end_byte))
        recovered, recovered_end = _surface_groups(path, coordinates, command_end)
        if recovered:
            arguments = recovered
            end = max(end, recovered_end)

    raw = coordinates.text[start:end]
    return FrontendMacro(
        name=name,
        raw=raw,
        span=_span_from_characters(path, coordinates, start, end),
        arguments=arguments,
        starred=starred,
    )


def _environment_name(source_bytes: bytes, coordinates: _Coordinates, begin: Any) -> str | None:
    name_node = _field(begin, "name")
    if name_node is not None:
        raw = coordinates.byte_slice(source_bytes, name_node)
        if raw.startswith("{") and raw.endswith("}"):
            return raw[1:-1].strip()
    raw_begin = coordinates.byte_slice(source_bytes, begin)
    match = _ENVIRONMENT_RE.match(raw_begin)
    return match.group(1).strip() if match else None


def _environment(
    path: Path,
    source_bytes: bytes,
    coordinates: _Coordinates,
    node: Any,
) -> tuple[FrontendEnvironment | None, FrontendDiagnostic | None]:
    begin = _field(node, "begin")
    end = _field(node, "end")
    if begin is None or end is None:
        return None, None
    begin_name = _environment_name(source_bytes, coordinates, begin)
    end_name = _environment_name(source_bytes, coordinates, end)
    if not begin_name:
        return None, None
    if end_name != begin_name:
        return (
            None,
            FrontendDiagnostic(
                kind=FrontendDiagnosticKind.PARSE_ERROR,
                message=(
                    f"tree-sitter recovered mismatched environment: "
                    f"\\begin{{{begin_name}}} closed by \\end{{{end_name or '?'}}}"
                ),
                source=coordinates.span(path, int(begin.start_byte), int(begin.end_byte)),
            ),
        )

    arguments: list[FrontendArgument] = []
    name_node = _field(begin, "name")
    for child in begin.children:
        if _same_node(child, name_node):
            continue
        if child.type.startswith(_GROUP_PREFIXES):
            arguments.append(_group_argument(path, source_bytes, coordinates, child))

    return (
        FrontendEnvironment(
            name=begin_name,
            raw=coordinates.byte_slice(source_bytes, node),
            span=coordinates.span(path, int(node.start_byte), int(node.end_byte)),
            body_span=coordinates.span(path, int(begin.end_byte), int(end.start_byte)),
            arguments=arguments,
        ),
        None,
    )


def _math(path: Path, source_bytes: bytes, coordinates: _Coordinates, node: Any) -> FrontendMath:
    raw = coordinates.byte_slice(source_bytes, node)
    if raw.startswith("$$"):
        delimiter = "$$"
    elif raw.startswith("$"):
        delimiter = "$"
    elif raw.startswith("\\["):
        delimiter = r"\[\]"
    elif raw.startswith("\\("):
        delimiter = r"\(\)"
    elif raw.startswith("\\begin"):
        match = _ENVIRONMENT_RE.match(raw)
        delimiter = f"environment:{match.group(1).strip()}" if match else "environment"
    else:
        delimiter = node.type
    return FrontendMath(
        delimiter=delimiter,
        raw=raw,
        span=coordinates.span(path, int(node.start_byte), int(node.end_byte)),
    )


def _diagnostic_for_error(path: Path, coordinates: _Coordinates, node: Any) -> FrontendDiagnostic:
    missing = bool(getattr(node, "is_missing", False))
    detail = f"missing {node.type}" if missing else f"tree-sitter parse error ({node.type})"
    return FrontendDiagnostic(
        kind=FrontendDiagnosticKind.PARSE_ERROR,
        message=detail,
        source=coordinates.span(path, int(node.start_byte), int(node.end_byte)),
    )


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _span_from_characters(
    path: Path, coordinates: _Coordinates, start: int, end: int
) -> SourceSpan:
    start_line, start_column = coordinates.line_column(start)
    end_line, end_column = coordinates.line_column(end)
    return SourceSpan(
        file=str(path),
        start_offset=start,
        end_offset=end,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _regions(
    path: Path,
    text: str,
    coordinates: _Coordinates,
    nodes: list[Any],
    macros: list[FrontendMacro],
    environments: list[FrontendEnvironment],
    math: list[FrontendMath],
) -> list[FrontendRegion]:
    document = next((item for item in environments if item.name == "document"), None)
    body_start = document.body_span.start_offset if document else 0
    body_end = document.body_span.end_offset if document else len(text)
    regions: list[FrontendRegion] = []

    if document is not None and document.span.start_offset > 0:
        regions.append(
            FrontendRegion(
                kind=FrontendRegionKind.PREAMBLE,
                span=_span_from_characters(
                    path, coordinates, 0, document.span.start_offset
                ),
            )
        )

    excluded: list[tuple[int, int]] = []
    for macro in macros:
        if macro.span.start_offset >= body_start and macro.span.end_offset <= body_end:
            excluded.append((macro.span.start_offset, macro.span.end_offset))

    for item in math:
        if item.span.start_offset >= body_start and item.span.end_offset <= body_end:
            excluded.append((item.span.start_offset, item.span.end_offset))
            regions.append(FrontendRegion(kind=FrontendRegionKind.MATH, span=item.span))

    for node in nodes:
        if node.type == "line_comment":
            span = coordinates.span(path, int(node.start_byte), int(node.end_byte))
            if span.start_offset >= body_start and span.end_offset <= body_end:
                excluded.append((span.start_offset, span.end_offset))
                regions.append(FrontendRegion(kind=FrontendRegionKind.COMMENT, span=span))
        native_kind = _NATIVE_OPAQUE_TYPES.get(node.type)
        if native_kind is None:
            continue
        span = coordinates.span(path, int(node.start_byte), int(node.end_byte))
        if span.start_offset >= body_start and span.end_offset <= body_end:
            excluded.append((span.start_offset, span.end_offset))
            regions.append(FrontendRegion(kind=native_kind, span=span))

    # Some common opaque variants (notably verbatim*) are not dedicated grammar
    # node types. We still rely on Tree-sitter for the environment boundary and
    # apply only a small Thorn-owned classification to fail closed for prose.
    for environment in environments:
        kind = _OPAQUE_ENVIRONMENT_KINDS.get(environment.name)
        if kind is None:
            continue
        if environment.span.start_offset >= body_start and environment.span.end_offset <= body_end:
            excluded.append((environment.span.start_offset, environment.span.end_offset))
            if not any(
                region.kind == kind
                and region.span.start_offset == environment.span.start_offset
                and region.span.end_offset == environment.span.end_offset
                for region in regions
            ):
                regions.append(FrontendRegion(kind=kind, span=environment.span))

    cursor = body_start
    for start, end in _merge_intervals(excluded):
        start = max(start, body_start)
        end = min(end, body_end)
        if cursor < start:
            regions.append(
                FrontendRegion(
                    kind=FrontendRegionKind.DOCUMENT_TEXT,
                    span=_span_from_characters(path, coordinates, cursor, start),
                )
            )
        cursor = max(cursor, end)
    if cursor < body_end:
        regions.append(
            FrontendRegion(
                kind=FrontendRegionKind.DOCUMENT_TEXT,
                span=_span_from_characters(path, coordinates, cursor, body_end),
            )
        )

    regions.sort(key=lambda item: (item.span.start_offset, item.kind.value))
    return regions


def _parse_file(path: Path, parser: Any) -> tuple[FrontendFile, list[FrontendDiagnostic]]:
    text = path.read_text(encoding="utf-8")
    source_bytes = text.encode("utf-8")
    coordinates = _Coordinates(text)
    tree = parser.parse(source_bytes)
    nodes = _walk(tree.root_node)

    diagnostics: list[FrontendDiagnostic] = []
    seen_diagnostics: set[tuple[int, int, str]] = set()
    for node in nodes:
        if node.type == "ERROR" or bool(getattr(node, "is_error", False)) or bool(
            getattr(node, "is_missing", False)
        ):
            diagnostic = _diagnostic_for_error(path, coordinates, node)
            source = diagnostic.source
            diagnostic_key = (
                source.start_offset if source else 0,
                source.end_offset if source else 0,
                diagnostic.message,
            )
            if diagnostic_key not in seen_diagnostics:
                diagnostics.append(diagnostic)
                seen_diagnostics.add(diagnostic_key)

    macros_by_key: dict[tuple[int, str], FrontendMacro] = {}
    for node in nodes:
        macro = _command_macro(path, source_bytes, coordinates, node)
        if macro is None:
            continue
        macro_key = (macro.span.start_offset, macro.name)
        incumbent = macros_by_key.get(macro_key)
        if incumbent is None or macro.span.end_offset > incumbent.span.end_offset:
            macros_by_key[macro_key] = macro
    macros = sorted(macros_by_key.values(), key=lambda item: item.span.start_offset)

    environments: list[FrontendEnvironment] = []
    environment_types = {"generic_environment", "math_environment", *_NATIVE_OPAQUE_TYPES}
    for node in nodes:
        if node.type not in environment_types:
            continue
        converted, disagreement = _environment(path, source_bytes, coordinates, node)
        if disagreement is not None:
            source = disagreement.source
            diagnostic_key = (
                source.start_offset if source else 0,
                source.end_offset if source else 0,
                disagreement.message,
            )
            if diagnostic_key not in seen_diagnostics:
                diagnostics.append(disagreement)
                seen_diagnostics.add(diagnostic_key)
        if converted is not None:
            environments.append(converted)
    environments.sort(key=lambda item: item.span.start_offset)

    opaque_bodies = [
        environment.body_span
        for environment in environments
        if environment.name in _OPAQUE_ENVIRONMENT_KINDS
    ]
    macros = [
        macro
        for macro in macros
        if not any(
            body.start_offset <= macro.span.start_offset < body.end_offset
            for body in opaque_bodies
        )
    ]

    math = [
        _math(path, source_bytes, coordinates, node)
        for node in nodes
        if node.type in _MATH_TYPES
    ]
    math.sort(key=lambda item: item.span.start_offset)

    return (
        FrontendFile(
            path=str(path),
            raw=text,
            macros=macros,
            environments=environments,
            math=math,
            regions=_regions(path, text, coordinates, nodes, macros, environments, math),
        ),
        diagnostics,
    )


class TreeSitterLatexFrontend:
    """Experimental source-preserving frontend backed by tree-sitter-latex.

    Tree-sitter objects are consumed only inside this adapter. Downstream Thorn
    receives the same parser-neutral models as every other frontend.
    """

    name = "tree-sitter"

    def __init__(self) -> None:
        self._parser = _load_parser()

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
            parsed_file, file_diagnostics = _parse_file(path, self._parser)
            files.append(parsed_file)
            diagnostics.extend(file_diagnostics)

            for macro in parsed_file.macros:
                if macro.name not in {"input", "include"} or not macro.arguments:
                    continue
                argument = next((item for item in macro.arguments if not item.optional), None)
                if argument is None:
                    continue
                child = Path(argument.value.strip())
                if child.suffix == "":
                    child = child.with_suffix(".tex")
                child = (path.parent / child).resolve()
                if child not in seen:
                    pending.append((child, macro.span))

        return ParsedProject(main_file=str(main), files=files, diagnostics=diagnostics)