#!/usr/bin/env python3
"""Executable #159 workspace/project-resolution differential evaluation.

The adapters in this file are evaluation-only. They intentionally normalize only
externally observable source/workspace facts and do not become Thorn's production
workspace path. In particular, there is no raw-source include scanner here:

* current Thorn is observed through its existing frontend/project-partiality API;
* TexLab is observed through standard LSP document-link/definition requests;
* LaTeXML is observed through its executable conversion output.

Fixture marker strings are test instrumentation, not syntax recovery.
"""

from __future__ import annotations

import argparse
import json
import select
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "eval" / "workspace" / "fixtures.json"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "thorn-workspace-eval/1":
        raise ValueError(f"unexpected workspace fixture schema in {path}")
    return list(payload["cases"])


def _materialize(case: dict[str, Any], directory: Path) -> Path:
    for relative, source in case["files"].items():
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return directory / case["main"]


def _relative(root: Path, path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _fixture_needles(case: dict[str, Any]) -> dict[str, tuple[str, int]]:
    needles: dict[str, tuple[str, int]] = {}
    for marker, relative in case.get("markers", {}).items():
        needles[marker] = (relative, case["files"][relative].find(marker))
    for label in case.get("expected", {}).get("label_order", []):
        for relative, source in case["files"].items():
            offset = source.find(label)
            if offset >= 0:
                needles[label] = (relative, offset)
                break
    return needles


def _flat_observed_order(case: dict[str, Any], files: list[str]) -> list[str]:
    needles = _fixture_needles(case)
    by_file: dict[str, list[tuple[int, str]]] = {}
    for needle, (relative, offset) in needles.items():
        if offset >= 0:
            by_file.setdefault(relative, []).append((offset, needle))
    result: list[str] = []
    for relative in files:
        result.extend(needle for _, needle in sorted(by_file.get(relative, [])))
    return result


def _version(executable: str, *args: str) -> str:
    try:
        run = subprocess.run(
            [executable, *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"unavailable: {exc}"
    return run.stdout.strip().splitlines()[0] if run.stdout.strip() else f"exit {run.returncode}"


def probe_current(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Observe the current production-compatible source/project path."""

    from thorn.frontends import RegexLatexFrontend
    from thorn.project_partiality import classify_includes, normalize_project_structure

    observations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="thorn-workspace-current-") as temp:
        base = Path(temp)
        for case in cases:
            case_dir = base / case["name"]
            case_dir.mkdir()
            main = _materialize(case, case_dir)
            started = time.perf_counter()
            parsed = normalize_project_structure(RegexLatexFrontend().parse_project(main))
            elapsed_ms = (time.perf_counter() - started) * 1000

            physical_files = [_relative(case_dir, file.path) for file in parsed.files]
            include_targets: list[dict[str, Any]] = []
            macro_counts = {"input": 0, "include": 0, "label": 0, "ref": 0}
            for file in parsed.files:
                for macro in file.macros:
                    if macro.name in macro_counts:
                        macro_counts[macro.name] += 1
                for target in classify_includes(file).targets:
                    include_targets.append(
                        {
                            "parent": _relative(case_dir, file.path),
                            "target": target.value,
                            "line": target.source.start_line,
                            "column": target.source.start_column,
                        }
                    )

            observations.append(
                {
                    "case": case["name"],
                    "physical_files_in_frontend_order": physical_files,
                    "flat_marker_or_label_order": _flat_observed_order(case, physical_files),
                    "include_targets_from_existing_normalized_source_facts": include_targets,
                    "macro_counts": macro_counts,
                    "diagnostics": [
                        {
                            "kind": diagnostic.kind.value,
                            "message": diagnostic.message,
                            "source_file": (
                                _relative(case_dir, diagnostic.source.file)
                                if diagnostic.source is not None
                                else None
                            ),
                            "source_line": (
                                diagnostic.source.start_line
                                if diagnostic.source is not None
                                else None
                            ),
                        }
                        for diagnostic in parsed.diagnostics
                    ],
                    "elapsed_ms": round(elapsed_ms, 3),
                    "expanded_occurrence_order_exposed": False,
                }
            )

    return {
        "available": True,
        "backend": "current Thorn RegexLatexFrontend + normalize_project_structure",
        "observations": observations,
    }


def _uri_to_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path)).resolve()


def _utf16_column_to_index(text: str, units: int) -> int:
    consumed = 0
    for index, char in enumerate(text):
        if consumed >= units:
            return index
        consumed += len(char.encode("utf-16-le")) // 2
    return len(text)


def _position_to_offset(text: str, position: dict[str, int]) -> int:
    lines = text.splitlines(keepends=True)
    line = position["line"]
    if line >= len(lines):
        return len(text)
    prefix = sum(len(item) for item in lines[:line])
    logical = lines[line].rstrip("\r\n")
    return prefix + _utf16_column_to_index(logical, position["character"])


def _offset_to_position(text: str, offset: int) -> dict[str, int]:
    before = text[:offset]
    line = before.count("\n")
    line_start = before.rfind("\n") + 1
    column_text = text[line_start:offset]
    character = len(column_text.encode("utf-16-le")) // 2
    return {"line": line, "character": character}


@dataclass
class _LspClient:
    executable: str
    cwd: Path
    process: subprocess.Popen[bytes] = field(init=False)
    next_id: int = 1
    notifications: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.process = subprocess.Popen(
            [self.executable],
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.process.stdin.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
        self.process.stdin.write(encoded)
        self.process.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(
        self, method: str, params: dict[str, Any] | None, timeout: float = 10.0
    ) -> Any:
        request_id = self.next_id
        self.next_id += 1
        self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        deadline = time.monotonic() + timeout
        while True:
            message = self._read(max(0.0, deadline - time.monotonic()))
            if "method" in message:
                if "id" not in message:
                    self.notifications.append(message)
                else:
                    self._reply_to_server_request(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"TexLab {method} failed: {message['error']}")
            return message.get("result")

    def _reply_to_server_request(self, message: dict[str, Any]) -> None:
        result: Any = None
        if message.get("method") == "workspace/configuration":
            items = message.get("params", {}).get("items", [])
            result = [None for _ in items]
        self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def _read(self, timeout: float) -> dict[str, Any]:
        assert self.process.stdout is not None
        if timeout <= 0 or not select.select([self.process.stdout], [], [], timeout)[0]:
            raise TimeoutError("timed out waiting for TexLab LSP response")
        headers: dict[str, str] = {}
        while True:
            line = self.process.stdout.readline()
            if not line:
                stderr = b""
                if self.process.stderr is not None:
                    stderr = self.process.stderr.read()
                detail = stderr.decode(errors="replace")
                raise RuntimeError(f"TexLab exited while reading LSP: {detail}")
            if line in {b"\r\n", b"\n"}:
                break
            key, value = line.decode("ascii").split(":", 1)
            headers[key.lower()] = value.strip()
        length = int(headers["content-length"])
        body = self.process.stdout.read(length)
        return json.loads(body.decode("utf-8"))

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.request("shutdown", None, timeout=5.0)
                self.notify("exit", {})
                self.process.wait(timeout=5.0)
        except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait(timeout=5.0)


def _texlab_links_for_project(
    client: _LspClient,
    root: Path,
    main: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str], list[str]]:
    links_by_file: dict[str, list[dict[str, Any]]] = {}
    texts: dict[str, str] = {}
    errors: list[str] = []
    pending = [main.resolve()]
    opened: set[Path] = set()

    while pending:
        path = pending.pop(0)
        if path in opened or not path.exists() or path.suffix.lower() != ".tex":
            continue
        opened.add(path)
        text = path.read_text(encoding="utf-8")
        relative = _relative(root, path)
        texts[relative] = text
        client.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path.as_uri(),
                    "languageId": "latex",
                    "version": 1,
                    "text": text,
                }
            },
        )
        try:
            raw_links = client.request(
                "textDocument/documentLink",
                {"textDocument": {"uri": path.as_uri()}},
            ) or []
        except (RuntimeError, TimeoutError) as exc:
            errors.append(f"{relative}: {exc}")
            raw_links = []

        normalized: list[dict[str, Any]] = []
        for item in raw_links:
            if not item.get("target"):
                try:
                    resolved = client.request("documentLink/resolve", item)
                    if resolved:
                        item = resolved
                except (RuntimeError, TimeoutError) as exc:
                    errors.append(f"{relative}: documentLink/resolve: {exc}")
            target_uri = item.get("target")
            target_path = _uri_to_path(target_uri) if target_uri else None
            target_relative = _relative(root, target_path) if target_path is not None else None
            link = {
                "range": item.get("range"),
                "target": target_relative,
                "target_uri": target_uri,
                "target_exists": target_path.exists() if target_path is not None else None,
            }
            normalized.append(link)
            if (
                target_path is not None
                and target_path.exists()
                and target_path.suffix.lower() == ".tex"
                and target_path not in opened
            ):
                pending.append(target_path)
        links_by_file[relative] = normalized
    return links_by_file, texts, errors


def _expanded_needles_from_links(
    case: dict[str, Any],
    links_by_file: dict[str, list[dict[str, Any]]],
    texts: dict[str, str],
) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]]]:
    needle_map = _fixture_needles(case)
    needles_by_file: dict[str, list[tuple[int, str]]] = {}
    for needle, (relative, offset) in needle_map.items():
        if offset >= 0:
            needles_by_file.setdefault(relative, []).append((offset, needle))

    observed: list[str] = []
    cycles: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    def visit(relative: str, stack: tuple[str, ...]) -> None:
        if relative in stack:
            cycles.append({"from": stack[-1], "to": relative})
            return
        text = texts.get(relative)
        if text is None:
            return
        links: list[tuple[int, int, dict[str, Any]]] = []
        for link in links_by_file.get(relative, []):
            target = link.get("target")
            range_ = link.get("range")
            if not target or not range_ or not str(target).endswith(".tex"):
                continue
            start = _position_to_offset(text, range_["start"])
            end = _position_to_offset(text, range_["end"])
            links.append((start, end, link))
        links.sort(key=lambda item: (item[0], item[1]))
        needles = sorted(needles_by_file.get(relative, []))
        needle_index = 0
        cursor = 0
        for start, end, link in links:
            while needle_index < len(needles) and needles[needle_index][0] < start:
                if needles[needle_index][0] >= cursor:
                    observed.append(needles[needle_index][1])
                needle_index += 1
            target = str(link["target"])
            if link.get("target_exists") is False:
                missing.append({"from": relative, "to": target})
            elif target in stack or target == relative:
                cycles.append({"from": relative, "to": target})
            else:
                visit(target, (*stack, relative))
            cursor = max(cursor, end)
        while needle_index < len(needles):
            observed.append(needles[needle_index][1])
            needle_index += 1

    visit(case["main"], ())
    return observed, cycles, missing


def _definition_queries(
    client: _LspClient,
    root: Path,
    case: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for query in case.get("definition_queries", []):
        path = (root / query["file"]).resolve()
        text = path.read_text(encoding="utf-8")
        start = -1
        search_from = 0
        for _ in range(query.get("occurrence", 1)):
            start = text.find(query["needle"], search_from)
            if start < 0:
                break
            search_from = start + len(query["needle"])
        if start < 0:
            results.append({**query, "error": "needle not found"})
            continue
        position = _offset_to_position(text, start + max(0, len(query["needle"]) // 2))
        try:
            response = client.request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": position,
                },
            )
            locations = response if isinstance(response, list) else [response] if response else []
            targets: list[str] = []
            for location in locations:
                uri = location.get("targetUri") or location.get("uri")
                target_path = _uri_to_path(uri) if uri else None
                target = (
                    _relative(root, target_path)
                    if target_path is not None
                    else str(uri)
                )
                targets.append(target)
            results.append({**query, "targets": targets})
        except (RuntimeError, TimeoutError) as exc:
            results.append({**query, "error": str(exc)})
    return results


def probe_texlab(cases: list[dict[str, Any]]) -> dict[str, Any]:
    executable = shutil.which("texlab")
    if executable is None:
        return {
            "available": False,
            "blocker": "texlab executable is not installed in this environment",
        }

    observations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="thorn-workspace-texlab-") as temp:
        base = Path(temp)
        for case in cases:
            case_dir = base / case["name"]
            case_dir.mkdir()
            main = _materialize(case, case_dir)
            client = _LspClient(executable, case_dir)
            started = time.perf_counter()
            try:
                initialize = client.request(
                    "initialize",
                    {
                        "processId": None,
                        "rootUri": case_dir.as_uri(),
                        "workspaceFolders": [
                            {"uri": case_dir.as_uri(), "name": case["name"]}
                        ],
                        "capabilities": {
                            "workspace": {"workspaceFolders": True},
                            "textDocument": {
                                "definition": {"linkSupport": True},
                                "documentLink": {},
                            },
                        },
                    },
                )
                client.notify("initialized", {})
                links, texts, link_errors = _texlab_links_for_project(
                    client, case_dir, main
                )
                expanded, cycles, missing = _expanded_needles_from_links(
                    case, links, texts
                )
                definitions = _definition_queries(client, case_dir, case)
                diagnostics = [
                    notification["params"]
                    for notification in client.notifications
                    if notification.get("method") == "textDocument/publishDiagnostics"
                ]
                elapsed_ms = (time.perf_counter() - started) * 1000
                observations.append(
                    {
                        "case": case["name"],
                        "server_capabilities": {
                            "documentLinkProvider": initialize.get("capabilities", {}).get(
                                "documentLinkProvider"
                            ),
                            "definitionProvider": initialize.get("capabilities", {}).get(
                                "definitionProvider"
                            ),
                        },
                        "links": links,
                        "expanded_marker_or_label_order_from_links": expanded,
                        "cycles_from_link_graph": cycles,
                        "missing_targets_from_links": missing,
                        "definition_queries": definitions,
                        "diagnostics": diagnostics,
                        "link_errors": link_errors,
                        "elapsed_ms": round(elapsed_ms, 3),
                    }
                )
            except (RuntimeError, TimeoutError) as exc:
                observations.append({"case": case["name"], "error": str(exc)})
            finally:
                client.close()

    return {
        "available": True,
        "version": _version(executable, "--version"),
        "interface": "stdio Language Server Protocol",
        "executable_bytes": Path(executable).stat().st_size,
        "observations": observations,
    }


def _ordered_substrings(text: str, candidates: list[str]) -> list[str]:
    occurrences: list[tuple[int, str]] = []
    for candidate in candidates:
        start = 0
        while True:
            offset = text.find(candidate, start)
            if offset < 0:
                break
            occurrences.append((offset, candidate))
            start = offset + len(candidate)
    return [candidate for _, candidate in sorted(occurrences)]


def _latexml_locator_attributes(xml: str) -> list[str]:
    # This inspects output XML metadata only; it does not parse TeX source.
    import re

    names = set(re.findall(r"\s([A-Za-z_:][A-Za-z0-9_.:-]*)=", xml))
    return sorted(
        name
        for name in names
        if any(token in name.casefold() for token in ("source", "src", "file", "line", "loc"))
    )


def _subprocess_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def probe_latexml(cases: list[dict[str, Any]]) -> dict[str, Any]:
    executable = shutil.which("latexml")
    if executable is None:
        return {
            "available": False,
            "blocker": "latexml executable is not installed in this environment",
        }

    observations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="thorn-workspace-latexml-") as temp:
        base = Path(temp)
        for case in cases:
            case_dir = base / case["name"]
            case_dir.mkdir()
            main = _materialize(case, case_dir)
            destination = case_dir / "out.xml"
            started = time.perf_counter()
            try:
                run = subprocess.run(
                    [
                        executable,
                        "--quiet",
                        f"--destination={destination}",
                        str(main),
                    ],
                    cwd=case_dir,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15,
                )
                timed_out = False
            except subprocess.TimeoutExpired as exc:
                run = None
                timed_out = True
                stdout = _subprocess_text(exc.stdout)
                stderr = _subprocess_text(exc.stderr)
            elapsed_ms = (time.perf_counter() - started) * 1000
            xml = destination.read_text(encoding="utf-8") if destination.exists() else ""
            marker_candidates = list(case.get("markers", {}))
            label_candidates = list(case.get("expected", {}).get("label_order", []))
            observations.append(
                {
                    "case": case["name"],
                    "returncode": None if run is None else run.returncode,
                    "timed_out": timed_out,
                    "marker_order_in_expanded_xml": _ordered_substrings(xml, marker_candidates),
                    "label_order_in_expanded_xml": _ordered_substrings(xml, label_candidates),
                    "source_locator_like_attributes": _latexml_locator_attributes(xml),
                    "idref_count": xml.count("idref="),
                    "stderr_tail": (
                        (stderr if run is None else run.stderr)[-2000:]
                    ),
                    "stdout_tail": (
                        (stdout if run is None else run.stdout)[-1000:]
                    ),
                    "elapsed_ms": round(elapsed_ms, 3),
                    "xml_bytes": len(xml.encode("utf-8")),
                }
            )

    version = _version(executable, "--VERSION")
    if version.startswith("exit "):
        version = _version(executable, "--version")
    return {
        "available": True,
        "version": version,
        "interface": "latexml subprocess -> expanded XML",
        "executable_bytes": Path(executable).stat().st_size,
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument(
        "--candidate",
        choices=("all", "current", "texlab", "latexml"),
        default="all",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = _load_cases(args.fixtures)

    probes = {
        "current": probe_current,
        "texlab": probe_texlab,
        "latexml": probe_latexml,
    }
    selected = probes if args.candidate == "all" else {args.candidate: probes[args.candidate]}
    result: dict[str, Any] = {
        "schema": "thorn-workspace-evaluation/1",
        "fixture_schema": "thorn-workspace-eval/1",
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "provider_model_calls": 0,
        "candidates": {},
    }
    for name, probe in selected.items():
        result["candidates"][name] = probe(cases)

    rendered = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
