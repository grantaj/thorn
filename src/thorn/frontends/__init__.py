from __future__ import annotations

from thorn.frontend import LatexFrontend
from thorn.frontends.regex import RegexLatexFrontend

# Tree-sitter is the production source frontend. Its exact released grammar/runtime
# identity is pinned in pyproject.toml and recorded in docs/tree-sitter-packaging.md.
# Regex remains available as a compatibility/conformance backend; do not grow it into a
# second TeX parser merely to chase source-parser corner cases.
DEFAULT_FRONTEND_NAME = "tree-sitter"


def get_frontend(name: str) -> LatexFrontend:
    normalized = name.strip().lower()
    if normalized == "current":
        normalized = DEFAULT_FRONTEND_NAME
    if normalized == "regex":
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
    if normalized in {"tree-sitter", "treesitter"}:
        from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

        return TreeSitterLatexFrontend()
    raise ValueError(f"unknown LaTeX frontend {name!r}")


def get_default_frontend() -> LatexFrontend:
    """Return a fresh instance of the explicitly selected production frontend."""

    return get_frontend(DEFAULT_FRONTEND_NAME)


__all__ = [
    "DEFAULT_FRONTEND_NAME",
    "RegexLatexFrontend",
    "get_default_frontend",
    "get_frontend",
]
