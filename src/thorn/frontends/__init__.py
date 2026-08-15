from __future__ import annotations

from thorn.frontend import LatexFrontend
from thorn.frontends.regex import RegexLatexFrontend


def get_frontend(name: str) -> LatexFrontend:
    normalized = name.strip().lower()
    if normalized in {"current", "regex"}:
        return RegexLatexFrontend()
    if normalized == "pylatexenc":
        try:
            from thorn.frontends.pylatexenc import PylatexencLatexFrontend
        except ModuleNotFoundError as exc:
            if exc.name == "pylatexenc":
                raise RuntimeError(
                    "pylatexenc frontend requires `pip install 'thorn-math[pylatexenc]'`"
                ) from exc
            raise
        return PylatexencLatexFrontend()
    raise ValueError(f"unknown LaTeX frontend {name!r}")


__all__ = ["RegexLatexFrontend", "get_frontend"]
