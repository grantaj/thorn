from __future__ import annotations

import builtins
from pathlib import Path

from thorn.cli import main
from thorn.latex import extract_project
from thorn.proof_visualizer import (
    build_proof_visualizer_data,
    render_proof_visualizer_html,
    write_proof_visualizer_html,
)


def _write_argument_project(path: Path) -> None:
    path.write_text(
        r"""\newtheorem{theorem}{Theorem}
\newtheorem{lemma}{Lemma}

\begin{theorem}\label{thm:base}
Every object in $A$ has property $P$.
\end{theorem}
\begin{proof}
The defining condition gives $P$.
\end{proof}

\begin{lemma}\label{lem:middle}
Theorem~\ref{thm:base} supplies the ambient fact, and every object in $B$ has property $Q$.
\end{lemma}
\begin{proof}
By Theorem~\ref{thm:base}, every chosen object has property $P$.
Therefore the chosen object has property $Q$.
\end{proof}

\begin{theorem}\label{thm:final}
Theorem~\ref{thm:base} motivates the construction, and every object in $C$ has property $R$.
\end{theorem}
\begin{proof}
For comparison, see Theorem~\ref{thm:base}.
By Lemma~\ref{lem:middle}, every chosen object has property $Q$.
Thus the chosen object has property $R$.
\end{proof}
""",
        encoding="utf-8",
    )


def test_overview_is_proof_argument_not_generic_reference_graph(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    data = build_proof_visualizer_data(extract_project(tex))

    pairs = {(edge["from"], edge["to"]) for edge in data["overviewEdges"]}

    assert pairs == {
        ("thm:base", "lem:middle"),
        ("lem:middle", "thm:final"),
    }
    # thm:final mentions thm:base in its statement and again incidentally inside its proof,
    # but neither reference is recovered as argument support.
    assert ("thm:base", "thm:final") not in pairs


def test_proof_drilldown_uses_existing_support_graph_edges(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    project = extract_project(tex)
    data = build_proof_visualizer_data(project)
    middle = data["proofUnits"]["lem:middle"]

    claim_ids = {claim["id"] for claim in middle["claims"]}
    assert claim_ids == {"lem:middle:claim:1", "lem:middle:claim:2"}

    external = middle["externalResults"]
    assert [item["resultId"] for item in external] == ["thm:base"]
    topology = {(edge["from"], edge["to"], edge["kind"]) for edge in middle["edges"]}
    assert (
        "external-result:thm:base",
        "lem:middle:claim:1",
        "result_reference",
    ) in topology
    assert (
        "lem:middle:claim:1",
        "lem:middle:claim:2",
        "prior_claim",
    ) in topology

    underlying = {
        (edge.source_claim_identifier, edge.target_claim_identifier, edge.kind.value)
        for edge in project.proof_support_graph.edges
        if edge.source_claim_identifier is not None
    }
    assert (
        "lem:middle:claim:1",
        "lem:middle:claim:2",
        "prior_claim",
    ) in underlying


def test_visualizer_is_self_contained_interactive_and_source_linked(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    project = extract_project(tex)

    html = render_proof_visualizer_html(project)

    assert "Thorn proof graph" in html
    assert '<h1 id="view-title">Paper</h1>' in html
    assert 'aria-label="Find a result"' in html
    assert "application/json" in html
    assert "external-result:thm:base" in html
    assert str(tex) in html
    assert "file://" in html
    assert '<script src=' not in html
    assert '<link rel="stylesheet"' not in html
    assert "https://" not in html
    assert "cdn" not in html.lower()
    assert "navigator.clipboard" not in html


def test_visualizer_avoids_explanatory_chrome(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    html = render_proof_visualizer_html(extract_project(tex))

    assert "Open proof structure" not in html
    assert "Recovered theorem/lemma support relationships" not in html
    assert "Arrow direction:" not in html
    assert "Presentation over existing Thorn" not in html
    assert '<div class="legend"' not in html
    assert "<footer" not in html


def test_visualizer_fits_width_and_opens_proof_units_directly(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    html = render_proof_visualizer_html(extract_project(tex))

    # The graph grows vertically with the page instead of introducing a sideways canvas.
    assert ".scroller{overflow:visible" in html
    assert "overflow-x:auto" not in html

    # A paper-level proof-unit click drills into its proof immediately; there is no
    # intermediate selection followed by a second "open" action.
    assert "if(r?.hasProof){openProof(n.id);return}" in html


def test_visualizer_json_cannot_be_terminated_by_manuscript_text(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""\newtheorem{theorem}{Theorem}
\begin{theorem}\label{thm:x}
A hostile-looking string: </script><script>alert(1)</script>.
\end{theorem}
\begin{proof}
The claim is immediate.
\end{proof}
""",
        encoding="utf-8",
    )

    html = render_proof_visualizer_html(extract_project(tex))

    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script\\u003e\\u003cscript\\u003ealert(1)" in html


def test_visualizer_rendering_is_deterministic_for_fixed_project(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    project = extract_project(tex)

    assert render_proof_visualizer_html(project) == render_proof_visualizer_html(project)


def test_visualizer_generation_does_not_import_model_provider(tmp_path: Path, monkeypatch) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    project = extract_project(tex)
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"thorn.audit", "thorn.providers.openai", "openai"}:
            raise AssertionError(f"proof graph attempted model-backed import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    html = render_proof_visualizer_html(project)
    assert "Thorn proof graph" in html


def test_graph_cli_writes_keyless_visualizer(tmp_path: Path, monkeypatch) -> None:
    tex = tmp_path / "main.tex"
    output = tmp_path / "argument.html"
    _write_argument_project(tex)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert main(["graph", str(tex), "--structural-only", "--output", str(output)]) == 0
    assert output.exists()
    assert "Thorn proof graph" in output.read_text(encoding="utf-8")


def test_write_visualizer_uses_requested_destination(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    _write_argument_project(tex)
    destination = tmp_path / "nested" / "graph.html"

    written = write_proof_visualizer_html(extract_project(tex), destination)

    assert written == destination.resolve()
    assert written.exists()
