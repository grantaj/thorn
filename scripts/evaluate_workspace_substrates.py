#!/usr/bin/env python3
"""Executable #159 project/workspace substrate evaluation.

Evaluation adapters consume only public/normalized interfaces: current Thorn's
frontend facts, TexLab's standard LSP, and LaTeXML's converter output. Fixture
markers measure expansion order; they are not used to recover LaTeX syntax.
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
FIXTURES = ROOT / "eval" / "workspace" / "fixtures.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "thorn-workspace-eval/1":
        raise ValueError(f"unexpected workspace fixture schema in {path}")
    return list(data["cases"])


def materialize(case: dict[str, Any], root: Path) -> Path:
    for relative, source in case["files"].items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root / case["main"]


def relative(root: Path, path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def needles(case: dict[str, Any]) -> dict[str, tuple[str, int]]:
    result = {
        marker: (filename, case["files"][filename].find(marker))
        for marker, filename in case.get("markers", {}).items()
    }
    for label in case.get("expected", {}).get("label_order", []):
        for filename, source in case["files"].items():
            offset = source.find(label)
            if offset >= 0:
                result[label] = (filename, offset)
                break
    return result


def flat_order(case: dict[str, Any], files: list[str]) -> list[str]:
    grouped: dict[str, list[tuple[int, str]]] = {}
    for needle, (filename, offset) in needles(case).items():
        if offset >= 0:
            grouped.setdefault(filename, []).append((offset, needle))
    return [
        needle
        for filename in files
        for _, needle in sorted(grouped.get(filename, []))
    ]


def version(executable: str, *args: str) -> str:
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
    text = run.stdout.strip()
    return text.splitlines()[0] if text else f"exit {run.returncode}"


def probe_current(cases: list[dict[str, Any]]) -> dict[str, Any]:
    from thorn.frontends import RegexLatexFrontend
    from thorn.project_partiality import classify_includes, normalize_project_structure

    observations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="thorn-workspace-current-") as temp:
        base = Path(temp)
        for case in cases:
            root = base / case["name"]
            root.mkdir()
            main = materialize(case, root)
            started = time.perf_counter()
            parsed = normalize_project_structure(RegexLatexFrontend().parse_project(main))
            elapsed_ms = (time.perf_counter() - started) * 1000
            physical_files = [relative(root, item.path) for item in parsed.files]
            includes: list[dict[str, Any]] = []
            macro_counts = {name: 0 for name in ("input", "include", "label", "ref")}
            for file in parsed.files:
                for macro in file.macros:
                    if macro.name in macro_counts:
                        macro_counts[macro.name] += 1
                targets, _ = classify_includes(file)
                for target in targets:
                    includes.append(
                        {
                            "parent": relative(root, file.path),
                            "target": target.value,
                            "line": target.source.start_line,
                            "column": target.source.start_column,
                        }
                    )
            observations.append(
                {
                    "case": case["name"],
                    "physical_files_in_frontend_order": physical_files,
                    "flat_marker_or_label_order": flat_order(case, physical_files),
                    "direct_include_facts": includes,
                    "macro_counts": macro_counts,
                    "diagnostics": [
                        {
                            "kind": diagnostic.kind.value,
                            "message": diagnostic.message,
                            "file": (
                                relative(root, diagnostic.source.file)
                                if diagnostic.source is not None
                                else None
                            ),
                            "line": (
                                diagnostic.source.start_line
                                if diagnostic.source is not None
                                else None
                            ),
                        }
                        for diagnostic in parsed.diagnostics
                    ],
                    "expanded_occurrence_order_exposed": False,
                    "elapsed_ms": round(elapsed_ms, 3),
                }
            )
    return {
        "available": True,
        "interface": "RegexLatexFrontend + normalize_project_structure",
        "observations": observations,
    }


def uri_path(uri: str | None) -> Path | None:
    if not uri:
        return None
    parsed = urlparse(uri)
    return Path(unquote(parsed.path)).resolve() if parsed.scheme == "file" else None


def utf16_index(text: str, units: int) -> int:
    consumed = 0
    for index, char in enumerate(text):
        if consumed >= units:
            return index
        consumed += len(char.encode("utf-16-le")) // 2
    return len(text)


def position_offset(text: str, position: dict[str, int]) -> int:
    lines = text.splitlines(keepends=True)
    line = position["line"]
    if line >= len(lines):
        return len(text)
    prefix = sum(map(len, lines[:line]))
    logical = lines[line].rstrip("\r\n")
    return prefix + utf16_index(logical, position["character"])


def offset_position(text: str, offset: int) -> dict[str, int]:
    before = text[:offset]
    line = before.count("\n")
    start = before.rfind("\n") + 1
    units = len(text[start:offset].encode("utf-16-le")) // 2
    return {"line": line, "character": units}


@dataclass
class LspClient:
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
            bufsize=0,
        )

    def send(self, payload: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
        self.process.stdin.write(body)
        self.process.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: Any, timeout: float = 10.0) -> Any:
        request_id = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            message = self.read(max(0.0, deadline - time.monotonic()))
            if "method" in message:
                if "id" in message:
                    requested = message.get("params", {}).get("items", [])
                    result = [None] * len(requested) if message["method"] == "workspace/configuration" else None
                    self.send({"jsonrpc": "2.0", "id": message["id"], "result": result})
                else:
                    self.notifications.append(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"TexLab {method}: {message['error']}")
            return message.get("result")

    def read(self, timeout: float) -> dict[str, Any]:
        assert self.process.stdout is not None
        if timeout <= 0 or not select.select([self.process.stdout], [], [], timeout)[0]:
            raise TimeoutError("timed out waiting for TexLab LSP response")
        headers: dict[str, str] = {}
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("TexLab exited while reading LSP")
            if line in {b"\n", b"\r\n"}:
                break
            key, value = line.decode("ascii").split(":", 1)
            headers[key.lower()] = value.strip()
        return json.loads(self.process.stdout.read(int(headers["content-length"])).decode())

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                self.request("shutdown", None, timeout=5)
                self.notify("exit", {})
                self.process.wait(timeout=5)
        except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired):
            self.process.kill()
            self.process.wait(timeout=5)


def texlab_links(
    client: LspClient, root: Path, main: Path
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str], list[str]]:
    links: dict[str, list[dict[str, Any]]] = {}
    texts: dict[str, str] = {}
    errors: list[str] = []
    pending = [main.resolve()]
    opened: set[Path] = set()
    while pending:
        path = pending.pop(0)
        if path in opened or not path.exists() or path.suffix.lower() != ".tex":
            continue
        opened.add(path)
        filename = relative(root, path)
        text = path.read_text(encoding="utf-8")
        texts[filename] = text
        client.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": path.as_uri(), "languageId": "latex", "version": 1, "text": text}},
        )
        try:
            raw = client.request(
                "textDocument/documentLink", {"textDocument": {"uri": path.as_uri()}}
            ) or []
        except (RuntimeError, TimeoutError) as exc:
            errors.append(f"{filename}: {exc}")
            raw = []
        normalized: list[dict[str, Any]] = []
        for item in raw:
            if not item.get("target"):
                try:
                    item = client.request("documentLink/resolve", item) or item
                except (RuntimeError, TimeoutError) as exc:
                    errors.append(f"{filename}: documentLink/resolve: {exc}")
            target_path = uri_path(item.get("target"))
            target = relative(root, target_path) if target_path is not None else item.get("target")
            entry = {
                "range": item.get("range"),
                "target": target,
                "target_exists": target_path.exists() if target_path is not None else None,
            }
            normalized.append(entry)
            if target_path is not None and target_path.exists() and target_path.suffix.lower() == ".tex":
                pending.append(target_path)
        links[filename] = normalized
    return links, texts, errors


def expand_from_links(
    case: dict[str, Any], links: dict[str, list[dict[str, Any]]], texts: dict[str, str]
) -> tuple[list[str], list[dict[str, str]], list[dict[str, str]]]:
    grouped: dict[str, list[tuple[int, str]]] = {}
    for needle, (filename, offset) in needles(case).items():
        if offset >= 0:
            grouped.setdefault(filename, []).append((offset, needle))
    order: list[str] = []
    cycles: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    def visit(filename: str, stack: tuple[str, ...]) -> None:
        text = texts.get(filename)
        if text is None:
            return
        include_links: list[tuple[int, dict[str, Any]]] = []
        for link in links.get(filename, []):
            target, span = link.get("target"), link.get("range")
            if not target or not str(target).endswith(".tex") or not span:
                continue
            include_links.append((position_offset(text, span["start"]), link))
        include_links.sort(key=lambda item: item[0])
        local = sorted(grouped.get(filename, []))
        index = 0
        for include_offset, link in include_links:
            while index < len(local) and local[index][0] < include_offset:
                order.append(local[index][1])
                index += 1
            target = str(link["target"])
            if link.get("target_exists") is False:
                missing.append({"from": filename, "to": target})
            elif target == filename or target in stack:
                cycles.append({"from": filename, "to": target})
            else:
                visit(target, (*stack, filename))
        order.extend(needle for _, needle in local[index:])

    visit(case["main"], ())
    return order, cycles, missing


def definition_results(client: LspClient, root: Path, case: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for query in case.get("definition_queries", []):
        path = (root / query["file"]).resolve()
        text = path.read_text(encoding="utf-8")
        offset = -1
        cursor = 0
        for _ in range(query.get("occurrence", 1)):
            offset = text.find(query["needle"], cursor)
            if offset < 0:
                break
            cursor = offset + len(query["needle"])
        if offset < 0:
            results.append({**query, "error": "needle not found"})
            continue
        try:
            response = client.request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": path.as_uri()},
                    "position": offset_position(text, offset + len(query["needle"]) // 2),
                },
            )
            locations = response if isinstance(response, list) else [response] if response else []
            targets = []
            for location in locations:
                target_path = uri_path(location.get("targetUri") or location.get("uri"))
                targets.append(relative(root, target_path) if target_path is not None else None)
            results.append({**query, "targets": targets})
        except (RuntimeError, TimeoutError) as exc:
            results.append({**query, "error": str(exc)})
    return results


def probe_texlab(cases: list[dict[str, Any]]) -> dict[str, Any]:
    executable = shutil.which("texlab")
    if executable is None:
        return {"available": False, "blocker": "texlab executable is not installed"}
    observations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="thorn-workspace-texlab-") as temp:
        base = Path(temp)
        for case in cases:
            root = base / case["name"]
            root.mkdir()
            main = materialize(case, root)
            client = LspClient(executable, root)
            started = time.perf_counter()
            try:
                init = client.request(
                    "initialize",
                    {
                        "processId": None,
                        "rootUri": root.as_uri(),
                        "workspaceFolders": [{"uri": root.as_uri(), "name": case["name"]}],
                        "capabilities": {"workspace": {"workspaceFolders": True}},
                    },
                )
                client.notify("initialized", {})
                links, texts, errors = texlab_links(client, root, main)
                order, cycles, missing = expand_from_links(case, links, texts)
                observations.append(
                    {
                        "case": case["name"],
                        "document_link_provider": init.get("capabilities", {}).get("documentLinkProvider"),
                        "definition_provider": init.get("capabilities", {}).get("definitionProvider"),
                        "links": links,
                        "expanded_marker_or_label_order_from_links": order,
                        "cycles_from_link_graph": cycles,
                        "missing_targets_from_links": missing,
                        "definition_queries": definition_results(client, root, case),
                        "link_errors": errors,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    }
                )
            except (RuntimeError, TimeoutError) as exc:
                observations.append({"case": case["name"], "error": str(exc)})
            finally:
                client.close()
    return {
        "available": True,
        "version": version(executable, "--version"),
        "interface": "stdio Language Server Protocol",
        "executable_bytes": Path(executable).stat().st_size,
        "observations": observations,
    }


def ordered_substrings(text: str, candidates: list[str]) -> list[str]:
    found: list[tuple[int, str]] = []
    for candidate in candidates:
        cursor = 0
        while (offset := text.find(candidate, cursor)) >= 0:
            found.append((offset, candidate))
            cursor = offset + len(candidate)
    return [candidate for _, candidate in sorted(found)]


def sourceish_xml_attributes(xml: str) -> list[str]:
    import re

    names = set(re.findall(r"\s([A-Za-z_:][A-Za-z0-9_.:-]*)=", xml))
    return sorted(name for name in names if any(key in name.casefold() for key in ("source", "src", "file", "line", "loc")))


def text_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def probe_latexml(cases: list[dict[str, Any]]) -> dict[str, Any]:
    executable = shutil.which("latexml")
    if executable is None:
        return {"available": False, "blocker": "latexml executable is not installed"}
    observations: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="thorn-workspace-latexml-") as temp:
        base = Path(temp)
        for case in cases:
            root = base / case["name"]
            root.mkdir()
            main = materialize(case, root)
            output = root / "out.xml"
            started = time.perf_counter()
            try:
                run = subprocess.run(
                    [executable, "--quiet", f"--destination={output}", str(main)],
                    cwd=root,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15,
                )
                returncode, timed_out = run.returncode, False
                stdout, stderr = run.stdout, run.stderr
            except subprocess.TimeoutExpired as exc:
                returncode, timed_out = None, True
                stdout, stderr = text_output(exc.stdout), text_output(exc.stderr)
            xml = output.read_text(encoding="utf-8") if output.exists() else ""
            observations.append(
                {
                    "case": case["name"],
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "marker_order_in_expanded_xml": ordered_substrings(xml, list(case.get("markers", {}))),
                    "label_order_in_expanded_xml": ordered_substrings(xml, list(case.get("expected", {}).get("label_order", []))),
                    "source_locator_like_attributes": sourceish_xml_attributes(xml),
                    "idref_count": xml.count("idref="),
                    "stderr_tail": stderr[-2000:],
                    "stdout_tail": stdout[-1000:],
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "xml_bytes": len(xml.encode()),
                }
            )
    reported = version(executable, "--VERSION")
    if reported.startswith("exit "):
        reported = version(executable, "--version")
    return {
        "available": True,
        "version": reported,
        "interface": "latexml subprocess -> expanded XML",
        "executable_bytes": Path(executable).stat().st_size,
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--candidate", choices=("all", "current", "texlab", "latexml"), default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = load_cases(args.fixtures)
    probes = {"current": probe_current, "texlab": probe_texlab, "latexml": probe_latexml}
    selected = probes if args.candidate == "all" else {args.candidate: probes[args.candidate]}
    result: dict[str, Any] = {
        "schema": "thorn-workspace-evaluation/1",
        "fixture_schema": "thorn-workspace-eval/1",
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "provider_model_calls": 0,
        "candidates": {name: probe(cases) for name, probe in selected.items()},
    }
    rendered = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
