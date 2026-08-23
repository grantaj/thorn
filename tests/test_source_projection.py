from __future__ import annotations

from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path

import pytest

from thorn.frontend import FrontendFile, FrontendRegionKind, LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.source_projection import (
    ProjectionStatus,
    ProjectionTokenKind,
    build_linguistic_projection,
)

FrontendFactory = Callable[[], LatexFrontend]

if find_spec("tree_sitter") is not None and find_spec("tree_sitter_latex") is not None:
    from thorn.frontends.tree_sitter import TreeSitterLatexFrontend

    _TREE_SITTER_FRONTENDS: tuple[FrontendFactory, ...] = (TreeSitterLatexFrontend,)
else:
    _TREE_SITTER_FRONTENDS = ()

_FRONTENDS: tuple[FrontendFactory, ...] = (
    RegexLatexFrontend,
    PylatexencLatexFrontend,
    *_TREE_SITTER_FRONTENDS,
)


def _frontend_id(factory: FrontendFactory) -> str:
    return factory().name


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_frontends_expose_complete_reversible_source_eligibility(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    source = r"""\documentclass{article}
Preamble declaration-looking prose.
\begin{document}
Visible café prose before $x\in\mathbb R$ and \ref{item:one}.
% Hidden comment declaration: a graph is called red when every vertex is red.
\begin{verbatim}
Hidden verbatim declaration: a graph is called blue when every vertex is blue.
\end{verbatim}
\begin{lstlisting}
Hidden listing declaration: a graph is called green when every vertex is green.
\end{lstlisting}
\begin{minted}{python}
Hidden minted declaration: a graph is called black when every vertex is black.
\end{minted}
Visible prose after the opaque regions.
\end{document}
Trailing declaration-looking prose.
"""
    tex.write_text(source, encoding="utf-8")

    file = frontend_factory().parse_project(tex).files[0]
    assert file.regions_complete is True
    assert any(region.kind == FrontendRegionKind.PREAMBLE for region in file.regions)
    assert any(region.kind == FrontendRegionKind.NON_DOCUMENT for region in file.regions)
    assert any(region.kind == FrontendRegionKind.COMMENT for region in file.regions)
    assert any(region.kind == FrontendRegionKind.VERBATIM for region in file.regions)
    assert any(region.kind == FrontendRegionKind.LISTING for region in file.regions)
    assert any(region.kind == FrontendRegionKind.MINTED for region in file.regions)
    assert any(region.kind == FrontendRegionKind.MATH for region in file.regions)

    projection = build_linguistic_projection(file)
    assert projection.status == ProjectionStatus.COMPLETE
    assert len(projection.text) == len(source)
    assert "Visible café prose before" in projection.text
    assert "Visible prose after the opaque regions" in projection.text
    assert "Preamble declaration-looking prose" not in projection.text
    assert "Hidden comment declaration" not in projection.text
    assert "Hidden verbatim declaration" not in projection.text
    assert "Hidden listing declaration" not in projection.text
    assert "Hidden minted declaration" not in projection.text
    assert "Trailing declaration-looking prose" not in projection.text

    math = next(token for token in projection.tokens if token.kind == ProjectionTokenKind.MATH)
    assert math.source.text(source) == r"$x\in\mathbb R$"
    reference = next(
        token for token in projection.tokens if token.kind == ProjectionTokenKind.REFERENCE
    )
    assert reference.source.text(source) == r"\ref{item:one}"
    assert reference.value == "item:one"

    visible_offset = source.index("Visible café")
    visible = projection.source_span(visible_offset, visible_offset + len("Visible café"))
    assert visible.text(source) == "Visible café"
    assert visible.start_line == 4


def test_projection_fails_closed_when_frontend_region_coverage_is_partial() -> None:
    source = "A graph is called unsafe when every vertex is red.\n"
    file = FrontendFile(path="paper.tex", raw=source)

    projection = build_linguistic_projection(file)

    assert projection.status == ProjectionStatus.PARTIAL
    assert projection.partial_reason is not None
    assert "unsafe" not in projection.text
    assert projection.tokens == ()


@pytest.mark.parametrize("frontend_factory", _FRONTENDS, ids=_frontend_id)
def test_math_placeholder_preserves_exact_source_provenance(
    tmp_path: Path,
    frontend_factory: FrontendFactory,
) -> None:
    tex = tmp_path / "main.tex"
    source = r"""\begin{document}
Visible prose before $d(v)=2.$ and after it.
\end{document}
"""
    tex.write_text(source, encoding="utf-8")

    file = frontend_factory().parse_project(tex).files[0]
    projection = build_linguistic_projection(file)
    math = next(token for token in projection.tokens if token.kind == ProjectionTokenKind.MATH)

    assert math.source.text(source) == r"$d(v)=2.$"
    assert projection.token_containing(math.source.start_offset) == math
