from __future__ import annotations

from pathlib import Path

from declaration_contract_frontend import DeclarationContractFrontend
from thorn.latex import extract_project
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review


def test_prose_defined_result_property_is_available_to_semantic_review(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.tex"
    paper.write_text(
        r"""\documentclass{article}
\usepackage{amsthm}
\newtheorem{theorem}{Theorem}
\begin{document}
A map will be called \emph{balanced} when one constant works uniformly
for every point of its domain.

\begin{theorem}\label{thm:main}
The map \(f\) is balanced.
\end{theorem}
\begin{proof}
The required estimate follows from the preceding discussion.
\end{proof}
\end{document}
""",
        encoding="utf-8",
    )

    project = extract_project(
        paper,
        linguistic_frontend=DeclarationContractFrontend(),
    )
    prepared = prepare_proof_review(project, project.unit("thm:main"))
    document = prepared.document
    packet = document.render_initial()
    advertised = set(advertised_source_addresses(document))
    defining_sources = [
        source for source in document.sources if "one constant works uniformly" in source.text
    ]

    assert defining_sources
    assert "one constant works uniformly" not in packet
    assert any(source.address in advertised for source in defining_sources)
