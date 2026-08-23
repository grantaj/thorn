from __future__ import annotations

from pathlib import Path

from sentence_contract_frontend import SentenceContractFrontend

from thorn.latex import extract_project
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review


def test_prose_defined_result_property_is_available_to_semantic_review(
    tmp_path: Path,
) -> None:
    paper = tmp_path / "paper.tex"
    definition = (
        "A map will be called \\emph{balanced} when one constant works uniformly\n"
        "for every point of its domain."
    )
    paper.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{definition}\n\n"
        "\\begin{theorem}\\label{thm:main}\n"
        "The map \\(f\\) is balanced.\n"
        "\\end{theorem}\n"
        "\\begin{proof}\n"
        "The required estimate follows from the preceding discussion.\n"
        "\\end{proof}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )

    project = extract_project(
        paper,
        linguistic_frontend=SentenceContractFrontend(),
    )
    prepared = prepare_proof_review(project, project.unit("thm:main"))
    document = prepared.document
    packet = document.render_initial()
    advertised = set(advertised_source_addresses(document))
    defining_sources = [
        source for source in document.sources if "one constant works uniformly" in source.text
    ]

    assert defining_sources
    assert definition not in packet
    assert any(source.address in advertised for source in defining_sources)
    assert any(line.startswith("CONTEXT target=") for line in document.lines)
    assert not any(symbol.name == "balanced" for symbol in project.symbol_table.symbols)
