#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thorn.frontends.regex import RegexLatexFrontend  # noqa: E402

CASES = Path(__file__).with_name("cases.json")


def _rel(path: str | Path, fixture: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(fixture.resolve()))
    except ValueError:
        return str(Path(path).resolve())


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items()) if k != "elapsed_ms"}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def _digest(value: Any) -> str:
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def run_thorn(fixture: Path) -> dict[str, Any]:
    start = time.perf_counter()
    parsed = RegexLatexFrontend().parse_project(fixture / "main.tex")
    includes: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    for file in parsed.files:
        for macro in file.macros:
            if not macro.arguments:
                continue
            item = {
                "file": _rel(file.path, fixture),
                "line": macro.span.start_line,
                "name": macro.arguments[0].value.strip(),
            }
            if macro.name in {"input", "include"}:
                item["command"] = macro.name
                includes.append(item)
            elif macro.name == "label":
                labels.append(item)
            elif macro.name in {"ref", "eqref", "cref", "Cref", "autoref"}:
                item["command"] = macro.name
                refs.append(item)
    return {
        "backend": "thorn-regex-current",
        "version": "repository-main",
        "files": [_rel(x.path, fixture) for x in parsed.files],
        "includes": includes,
        "labels": labels,
        "references": refs,
        "diagnostics": [
            {
                "kind": str(x.kind),
                "message": x.message,
                "file": _rel(x.source.file, fixture) if x.source else None,
                "line": x.source.start_line if x.source else None,
            }
            for x in parsed.diagnostics
        ],
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
    }


class LspClient:
    def __init__(self, executable: str) -> None:
        self.proc = subprocess.Popen(
            [executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert self.proc.stdout is not None
        self._responses: dict[int, Any] = {}
        self.notifications: list[dict[str, Any]] = []
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._next_id = 1
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        while True:
            headers: dict[str, str] = {}
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    return
                if line in {b"\r\n", b"\n"}:
                    break
                key, value = line.decode().split(":", 1)
                headers[key.lower()] = value.strip()
            size = int(headers["content-length"])
            payload = json.loads(self.proc.stdout.read(size))
            self._queue.put(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        data = json.dumps(payload, separators=(",", ":")).encode()
        self.proc.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _accept(self, payload: dict[str, Any]) -> None:
        if "method" in payload and "id" in payload:
            method = payload["method"]
            params = payload.get("params", {})
            if method == "workspace/configuration":
                items = params.get("items", []) if isinstance(params, dict) else []
                result: Any = [{} for _ in items]
            elif method == "workspace/workspaceFolders":
                result = None
            else:
                result = None
            self._send({"jsonrpc": "2.0", "id": payload["id"], "result": result})
        elif "id" in payload:
            self._responses[int(payload["id"])] = payload
        else:
            self.notifications.append(payload)

    def request(self, method: str, params: dict[str, Any], timeout: float = 8.0) -> Any:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if request_id in self._responses:
                payload = self._responses.pop(request_id)
                if "error" in payload:
                    return {"lsp_error": payload["error"]}
                return payload.get("result")
            try:
                payload = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            self._accept(payload)
        raise TimeoutError(f"LSP request timed out: {method}")

    def drain(self, seconds: float = 0.4) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                payload = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            self._accept(payload)

    def close(self) -> None:
        try:
            self.request("shutdown", {}, timeout=2.0)
            self.notify("exit", {})
        finally:
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _uri(path: Path) -> str:
    return path.resolve().as_uri()


def _uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    return Path(unquote(parsed.path))


def run_texlab(fixture: Path, expected: dict[str, Any]) -> dict[str, Any]:
    executable = shutil.which("texlab")
    if executable is None:
        return {"backend": "texlab", "available": False, "reason": "texlab executable not found"}
    version = subprocess.run(
        [executable, "--version"], check=False, capture_output=True, text=True
    ).stdout.strip()
    start = time.perf_counter()
    client = LspClient(executable)
    try:
        init = client.request(
            "initialize",
            {
                "processId": None,
                "rootUri": _uri(fixture),
                "capabilities": {"textDocument": {"documentLink": {}, "definition": {}}},
                "workspaceFolders": [{"uri": _uri(fixture), "name": fixture.name}],
            },
        )
        client.notify("initialized", {})
        tex_files = sorted(fixture.glob("*.tex"))
        for path in tex_files:
            client.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": _uri(path),
                        "languageId": "latex",
                        "version": 1,
                        "text": path.read_text(encoding="utf-8"),
                    }
                },
            )
        client.drain()
        links: list[dict[str, Any]] = []
        for path in tex_files:
            result = client.request(
                "textDocument/documentLink", {"textDocument": {"uri": _uri(path)}}
            )
            if not isinstance(result, list):
                continue
            for link in result:
                target = link.get("target")
                if not target or not target.startswith("file:"):
                    continue
                target_path = _uri_to_path(target)
                if target_path.suffix.lower() != ".tex":
                    continue
                links.append(
                    {
                        "file": _rel(path, fixture),
                        "line": int(link["range"]["start"]["line"]) + 1,
                        "target": _rel(target_path, fixture),
                    }
                )
        definitions: list[dict[str, Any]] = []
        for probe in expected.get("definition_probes", []):
            path = fixture / probe["file"]
            result = client.request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": _uri(path)},
                    "position": {"line": probe["line"] - 1, "character": probe["character"] - 1},
                },
            )
            definitions.append({"probe": probe, "result": _normalise_locations(result, fixture)})
        client.drain()
        diagnostics = []
        for notification in client.notifications:
            if notification.get("method") != "textDocument/publishDiagnostics":
                continue
            params = notification.get("params", {})
            diagnostics.append(
                {
                    "file": _rel(_uri_to_path(params["uri"]), fixture),
                    "diagnostics": [
                        {
                            "message": d.get("message"),
                            "severity": d.get("severity"),
                            "code": d.get("code"),
                        }
                        for d in params.get("diagnostics", [])
                    ],
                }
            )
        return {
            "backend": "texlab",
            "available": True,
            "version": version,
            "initialize_capabilities": sorted((init or {}).get("capabilities", {}).keys()),
            "document_links": sorted(links, key=lambda x: (x["file"], x["line"], x["target"])),
            "definitions": definitions,
            "diagnostics": diagnostics,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }
    finally:
        client.close()


def _normalise_locations(result: Any, fixture: Path) -> Any:
    if result is None or (isinstance(result, dict) and "lsp_error" in result):
        return result
    items = result if isinstance(result, list) else [result]
    normalised = []
    for item in items:
        uri = item.get("uri") or item.get("targetUri")
        rng = item.get("range") or item.get("targetSelectionRange")
        normalised.append(
            {
                "file": _rel(_uri_to_path(uri), fixture) if uri else None,
                "line": int(rng["start"]["line"]) + 1 if rng else None,
            }
        )
    return normalised


def run_latexml(fixture: Path, expected: dict[str, Any]) -> dict[str, Any]:
    executable = shutil.which("latexml")
    if executable is None:
        return {"backend": "latexml", "available": False, "reason": "latexml executable not found"}
    version_proc = subprocess.run(
        [executable, "--VERSION"], check=False, capture_output=True, text=True
    )
    version = (version_proc.stdout or version_proc.stderr).strip().splitlines()[0]
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.xml"
        proc = subprocess.run(
            [executable, "--quiet", f"--destination={out}", str(fixture / "main.tex")],
            cwd=fixture,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        xml = out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""
    markers = []
    for marker in expected.get("markers", []):
        markers.append({"marker": marker, "count": xml.count(marker), "first": xml.find(marker)})
    names = set(expected.get("file_names", []))
    source_mentions = sorted(name for name in names if name in xml)
    return {
        "backend": "latexml",
        "available": True,
        "version": version,
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-2000:],
        "xml_sha256": hashlib.sha256(xml.encode()).hexdigest() if xml else None,
        "markers": markers,
        "source_file_mentions": source_mentions,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
    }


def materialize_case(name: str, case: dict[str, Any], parent: Path) -> Path:
    fixture = parent / name
    fixture.mkdir(parents=True, exist_ok=True)
    for relative, content in case["files"].items():
        path = fixture / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return fixture


def evaluate_case(name: str, case: dict[str, Any], backends: list[str]) -> dict[str, Any]:
    config = case["expectation"]
    with tempfile.TemporaryDirectory() as tmp:
        fixture = materialize_case(name, case, Path(tmp))
        result: dict[str, Any] = {"case": name, "expectation": config}
        runners = {
            "thorn": lambda: run_thorn(fixture),
            "texlab": lambda: run_texlab(fixture, config),
            "latexml": lambda: run_latexml(fixture, config),
        }
        for backend in backends:
            first = runners[backend]()
            second = runners[backend]()
            result[backend] = first
            result[f"{backend}_deterministic"] = _digest(first) == _digest(second)
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["thorn", "texlab", "latexml", "all"], default="all")
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    names = args.cases or list(cases)
    backends = ["thorn", "texlab", "latexml"] if args.backend == "all" else [args.backend]
    payload = {
        "schema": "thorn-workspace-eval/1",
        "platform": {
            "python": sys.version.split()[0],
            "os": os.uname().sysname,
            "machine": os.uname().machine,
        },
        "results": [evaluate_case(name, cases[name], backends) for name in names],
    }
    raw = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw + "\n", encoding="utf-8")
    else:
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
