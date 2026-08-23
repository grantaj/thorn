"""Backend-independent contract for Thorn-owned semantic dependency behavior."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pytest

from thorn.dependencies import DependencyResolution, ExtractedProject
from thorn.frontend import LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticFrontend, LinguisticToken
from thorn.llm_proof_language import parse_source_rescue_request, render_source_rescue
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review

FrontendFactory = Callable[[], LatexFrontend]
LinguisticFactory = Callable[[], LinguisticFrontend]


class ContractCapability(StrEnum):
    PROJECT_SEMANTICS = "project-semantics"


@dataclass(frozen=True)
class ContractConfiguration:
    name: str
    frontend_factory: FrontendFactory
    linguistic_factory: LinguisticFactory | None = None
    capabilities: frozenset[ContractCapability] = frozenset()

    def require(self, capability: ContractCapability) -> None:
        if capability not in self.capabilities:
            pytest.skip(f"{self.name} explicitly does not advertise {capability.value}")


STRUCTURAL_CONFIGURATIONS = (
    ContractConfiguration(
        name="regex-structural",
        frontend_factory=RegexLatexFrontend,
        capabilities=frozenset({ContractCapability.PROJECT_SEMANTICS}),
    ),
    ContractConfiguration(
        name="pylatexenc-structural",
        frontend_factory=PylatexencLatexFrontend,
        capabilities=frozenset({ContractCapability.PROJECT_SEMANTICS}),
    ),
)


@dataclass(frozen=True)
class ContractRun:
    main_file: Path
    project: ExtractedProject

    def document_for(self, result_identifier: str):
        unit = self.project.unit(result_identifier)
        return prepare_proof_review(self.project, unit).document

    def assert_not_authoritative(self, name: str) -> None:
        table = self.project.symbol_table
        symbol_ids = {
            symbol.identifier
            for symbol in table.symbols
            if symbol.name.casefold() == name.casefold()
        }
        assert not any(
            item.symbol_identifier in symbol_ids
            for item in [*table.definitions, *table.constraints]
        )


def _write_project(
    tmp_path: Path,
    configuration: ContractConfiguration,
    body: str,
    *,
    includes: dict[str, str] | None = None,
) -> ContractRun:
    configuration.require(ContractCapability.PROJECT_SEMANTICS)
    main = tmp_path / "main.tex"
    main.write_text(
        "\\documentclass{article}\n"
        "\\usepackage{amsthm}\n"
        "\\newtheorem{lemma}{Lemma}\n"
        "\\newtheorem{theorem}{Theorem}\n"
        "\\begin{document}\n"
        f"{body.strip()}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    for relative_path, source in (includes or {}).items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source.strip() + "\n", encoding="utf-8")

    linguistic_frontend = (
        configuration.linguistic_factory()
        if configuration.linguistic_factory is not None
        else None
    )
    project = extract_project(
        main,
        frontend=configuration.frontend_factory(),
        linguistic_frontend=linguistic_frontend,
    )
    return ContractRun(main_file=main, project=project)


def _frontend_id(configuration: ContractConfiguration) -> str:
    return configuration.name


@pytest.mark.parametrize("configuration", STRUCTURAL_CONFIGURATIONS, ids=_frontend_id)
def test_structured_result_dependency_is_canonical_and_source_addressable(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    run = _write_project(
        tmp_path,
        configuration,
        r"""
\begin{lemma}\label{lem:criterion}
The needed local estimate is valid.
\end{lemma}
\begin{proof}Use the stated hypotheses.\end{proof}

\begin{theorem}\label{thm:main}
The conclusion follows from Lemma~\ref{lem:criterion}.
\end{theorem}
\begin{proof}Apply Lemma~\ref{lem:criterion}.\end{proof}
""",
    )

    graph = run.project.dependency_graph
    assert graph.direct_dependency_ids("thm:main") == ["lem:criterion"]
    assert all(
        edge.resolution == DependencyResolution.RESOLVED
        for edge in graph.edges
        if edge.source_identifier == "thm:main"
    )

    document = run.document_for("thm:main")
    referenced = [
        source
        for source in document.sources
        if source.referenced_result_identifier == "lem:criterion"
    ]
    assert referenced
    advertised = advertised_source_addresses(document)
    rescuable = next(source for source in referenced if source.address in advertised)
    request = parse_source_rescue_request(
        document,
        f"NEED_SOURCE {rescuable.address}",
    )
    rescue = render_source_rescue(document, request)
    assert rescuable.text in rescue.text

    with pytest.raises(KeyError, match="unknown proof-language source addresses"):
        parse_source_rescue_request(document, "NEED_SOURCE NOT_ADVERTISED")


@pytest.mark.parametrize("configuration", STRUCTURAL_CONFIGURATIONS, ids=_frontend_id)
def test_missing_and_ambiguous_dependencies_never_gain_arbitrary_targets(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    run = _write_project(
        tmp_path,
        configuration,
        r"""
\begin{lemma}\label{lem:dup}First candidate.\end{lemma}
\begin{lemma}\label{lem:dup}Second candidate.\end{lemma}
\begin{theorem}\label{thm:main}
Use Lemma~\ref{lem:dup} and Lemma~\ref{lem:missing}.
\end{theorem}
\begin{proof}Apply the cited results.\end{proof}
""",
    )

    unresolved = run.project.dependency_graph.unresolved_edges()
    assert {edge.resolution for edge in unresolved} == {
        DependencyResolution.AMBIGUOUS,
        DependencyResolution.MISSING,
    }
    assert all(edge.target_identifier is None for edge in unresolved)


class _StaticDependencyFrontend:
    name = "contract-static-dependencies"

    def parse(self, text: str) -> LinguisticDocument:
        matches = list(re.finditer(r"\S+", text))
        tokens = [
            LinguisticToken(
                index=index,
                text=match.group(0),
                lemma=match.group(0),
                pos="VERB" if index == 0 else "X",
                dependency="ROOT" if index == 0 else "dep",
                head_index=0,
                sentence_index=0,
                start=match.start(),
                end=match.end(),
            )
            for index, match in enumerate(matches)
        ]
        return LinguisticDocument(text=text, tokens=tokens)


LINGUISTIC_CONFIGURATION = ContractConfiguration(
    name="regex-static-nlp",
    frontend_factory=RegexLatexFrontend,
    linguistic_factory=_StaticDependencyFrontend,
    capabilities=frozenset({ContractCapability.PROJECT_SEMANTICS}),
)


def test_linguistic_source_evidence_remains_non_authoritative(tmp_path: Path) -> None:
    run = _write_project(
        tmp_path,
        LINGUISTIC_CONFIGURATION,
        r"""
\begin{theorem}\label{thm:main}
A conclusion holds.
\end{theorem}
\begin{proof}
Fix $x\in X$ for the argument.
\end{proof}
""",
    )

    # Generic linguistic observations remain source evidence, not an independent
    # mathematical symbol interpretation capability.
    assert run.project.symbol_table.candidates == []
    assert all(symbol.name != "x" for symbol in run.project.symbol_table.symbols)
    run.assert_not_authoritative("x")

    inventory = run.project.linguistic_statements
    assert inventory is not None
    assert inventory.complete
    assert any(r"$x\in X$" in statement.text for statement in inventory.statements)
