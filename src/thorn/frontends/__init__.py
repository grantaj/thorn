from __future__ import annotations

from thorn.frontend import LatexFrontend
from thorn.frontends.regex import RegexLatexFrontend

# Slice G disposition: regex remains the compatibility default until the pinned
# tree-sitter-latex grammar has a frictionless reproducible installation path.
# Tree-sitter remains the preferred source-structure backend; this distinction is
# architectural evidence, not an invitation to grow the compatibility scanner.
DEFAULT_FRONTEND_NAME = "regex"
PREFERRED_FRONTEND_NAME = "tree-sitter"


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
    """Return the explicitly selected production compatibility frontend."""

    return get_frontend(DEFAULT_FRONTEND_NAME)


__all__ = [
    "DEFAULT_FRONTEND_NAME",
    "PREFERRED_FRONTEND_NAME",
    "RegexLatexFrontend",
    "get_default_frontend",
    "get_frontend",
]
