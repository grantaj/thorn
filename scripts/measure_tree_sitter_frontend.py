from __future__ import annotations

import argparse
import importlib.metadata
import json
import statistics
import tempfile
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.frontends.regex import RegexLatexFrontend
from thorn.frontends.tree_sitter import TreeSitterLatexFrontend
from thorn.latex import extract_project


def _fixture(root: Path, pairs: int) -> Path:
    main = root / "main.tex"
    body = root / "body.tex"
    main.write_text(
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n\\input{body}\n\\end{document}\n",
        encoding="utf-8",
    )
    chunks: list[str] = []
    for index in range(pairs):
        chunks.extend(
            [
                (
                    f"\\begin{{lemma}}\\label{{lem:{index}}}L{index}: "
                    f"$x_{index}^2\\ge 0$.\\end{{lemma}}\n"
                ),
                f"\\begin{{proof}}Proof {index}.\\end{{proof}}\n",
                f"\\begin{{theorem}}\\label{{thm:{index}}}T{index}.\\end{{theorem}}\n",
                f"\\begin{{proof}}By \\ref{{lem:{index}}}.\\end{{proof}}\n",
            ]
        )
    body.write_text("".join(chunks), encoding="utf-8")
    return main


def _median_ms(function: Callable[[], object], iterations: int) -> float:
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples)


def _distribution_bytes(name: str) -> int | None:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return None
    total = 0
    for item in distribution.files or ():
        path = distribution.locate_file(item)
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--pairs", type=int, default=40)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="thorn-tree-sitter-") as tmp:
        main_file = _fixture(Path(tmp), args.pairs)
        source_bytes = sum(path.stat().st_size for path in Path(tmp).glob("*.tex"))
        backends = {
            "regex": RegexLatexFrontend(),
            "pylatexenc": PylatexencLatexFrontend(),
            "tree-sitter": TreeSitterLatexFrontend(),
        }
        payload: dict[str, object] = {
            "fixture": {"pairs": args.pairs, "source_bytes": source_bytes},
            "iterations": args.iterations,
            "backends": {},
            "package_versions": {
                "tree-sitter": _distribution_version("tree-sitter"),
                "tree-sitter-language-pack": _distribution_version("tree-sitter-language-pack"),
            },
            "installed_bytes": {
                "pylatexenc": _distribution_bytes("pylatexenc"),
                "tree-sitter": _distribution_bytes("tree-sitter"),
                "tree-sitter-language-pack": _distribution_bytes("tree-sitter-language-pack"),
            },
        }
        results = payload["backends"]
        assert isinstance(results, dict)
        for name, frontend in backends.items():
            frontend.parse_project(main_file)
            extract_project(main_file, frontend=frontend)
            results[name] = {
                "parse_median_ms": round(
                    _median_ms(partial(frontend.parse_project, main_file), args.iterations), 3
                ),
                "extract_median_ms": round(
                    _median_ms(
                        partial(extract_project, main_file, frontend=frontend), args.iterations
                    ),
                    3,
                ),
            }

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
