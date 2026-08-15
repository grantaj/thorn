from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from thorn.frontend import LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project


def _fixture(root: Path, results: int) -> Path:
    main = root / "main.tex"
    section = root / "section.tex"
    main.write_text(
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\input{section}\n",
        encoding="utf-8",
    )

    blocks: list[str] = []
    for index in range(results):
        blocks.append(
            f"\\begin{{lemma}}\\label{{lem:{index}}}\n"
            f"For $x_{{{index}}}\\in\\mathbb R$, we have $x_{{{index}}}^2\\ge 0$.\n"
            "\\end{lemma}\n"
            "\\begin{proof}This follows from the order axioms.\\end{proof}\n"
            f"\\begin{{theorem}}\\label{{thm:{index}}}\n"
            f"The previous bound holds; see \\ref{{lem:{index}}}.\n"
            "\\end{theorem}\n"
            f"\\begin{{proof}}Apply \\ref{{lem:{index}}}.\\end{{proof}}\n"
        )
    section.write_text("".join(blocks), encoding="utf-8")
    return main


def _median_ms(operation: Callable[[], object], iterations: int) -> float:
    samples: list[float] = []
    operation()  # warm-up import/caches before timed samples
    for _ in range(iterations):
        start = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples)


def _measure(frontend: LatexFrontend, main: Path, iterations: int) -> dict[str, float]:
    return {
        "parse_ms_median": round(
            _median_ms(lambda: frontend.parse_project(main), iterations),
            3,
        ),
        "extract_ms_median": round(
            _median_ms(lambda: extract_project(main, frontend=frontend), iterations),
            3,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Thorn LaTeX frontends")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--results", type=int, default=40)
    args = parser.parse_args()
    if args.iterations < 1 or args.results < 1:
        parser.error("--iterations and --results must be positive")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        main_file = _fixture(root, args.results)
        section = root / "section.tex"
        backends = {
            "regex": _measure(RegexLatexFrontend(), main_file, args.iterations),
            "pylatexenc": _measure(PylatexencLatexFrontend(), main_file, args.iterations),
        }
        regex_parse = backends["regex"]["parse_ms_median"]
        pylatexenc_parse = backends["pylatexenc"]["parse_ms_median"]
        regex_extract = backends["regex"]["extract_ms_median"]
        pylatexenc_extract = backends["pylatexenc"]["extract_ms_median"]
        payload = {
            "fixture": {
                "result_pairs": args.results,
                "bytes": len(main_file.read_bytes()) + len(section.read_bytes()),
                "iterations": args.iterations,
            },
            "backends": backends,
            "ratios": {
                "pylatexenc_over_regex_parse": round(pylatexenc_parse / regex_parse, 3),
                "pylatexenc_over_regex_extract": round(pylatexenc_extract / regex_extract, 3),
            },
        }
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
