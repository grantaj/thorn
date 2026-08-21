"""Backend-independent contract for Thorn-owned semantic dependency behavior."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pytest

from declaration_contract_frontend import DeclarationContractFrontend
from thorn.dependencies import ExtractedProject
from thorn.evidence import InferenceStatus
from thorn.frontend import LatexFrontend
from thorn.frontends import RegexLatexFrontend
from thorn.frontends.pylatexenc import PylatexencLatexFrontend
from thorn.latex import extract_project
from thorn.linguistic import LinguisticDocument, LinguisticFrontend, LinguisticToken
from thorn.llm_proof_language import (
    LLMProofLanguage,
    parse_source_rescue_request,
    render_source_rescue,
)
from thorn.proof_language_review import advertised_source_addresses
from thorn.review_workflow import prepare_proof_review
from thorn.symbols import Symbol

FrontendFactory = Callable[[], LatexFrontend]
LinguisticFactory = Callable[[], LinguisticFrontend]


class ContractCapability(StrEnum):
    PROJECT_SEMANTICS = "project-semantics"
    PROSE_AUTHORITY = "prose-authority"
    LINGUISTIC_CANDIDATES = "linguistic-candidates"


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

PROSE_AUTHORITY_CONFIGURATIONS = tuple(
    ContractConfiguration(
        name=f"{configuration.name}+declaration-nlp",
        frontend_factory=configuration.frontend_factory,
        linguistic_factory=DeclarationContractFrontend,
        capabilities=configuration.capabilities | {ContractCapability.PROSE_AUTHORITY},
    )
    for configuration in STRUCTURAL_CONFIGURATIONS
)


@dataclass(frozen=True)
class ContractRun:
    main_file: Path
    project: ExtractedProject

    def document_for(self, result_identifier: str) -> LLMProofLanguage:
        unit = self.project.unit(result_identifier)
        return prepare_proof_review(self.project, unit).document

    def _result_scope_ids(self, result_identifier: str) -> set[str]:
        return {
            scope.identifier
            for scope in self.project.symbol_table.scopes
            if scope.result_identifier == result_identifier
        }

    def assert_authoritative(
        self,
        result_identifier: str,
        name: str,
        source_text: str,
    ) -> Symbol:
        """Assert result-visible authority without depending on private identifier schemes."""

        table = self.project.symbol_table
        scope_ids = self._result_scope_ids(result_identifier)
        resolved_symbol_ids = {
            use.resolved_symbol_identifier
            for use in table.uses
            if use.resolved_symbol_identifier is not None
            and use.scope_identifier in scope_ids
            and use.name.casefold() == name.casefold()
        }
        declarations = [
            item
            for item in [*table.definitions, *table.constraints]
            if item.symbol_identifier in resolved_symbol_ids and item.raw == source_text
        ]
        assert len(declarations) == 1, (
            f"expected {name!r} at {result_identifier!r} to resolve to exactly one "
            f"authoritative declaration with source {source_text!r}"
        )
        declaration = declarations[0]
        symbol = table.symbol(declaration.symbol_identifier)
        assert symbol.name.casefold() == name.casefold()
        raw_file = Path(declaration.source.file).read_text(encoding="utf-8")
        assert declaration.source.text(raw_file) == source_text
        return symbol

    def assert_not_authoritative_at_result(
        self,
        result_identifier: str,
        name: str,
    ) -> None:
        """Assert absence of result-visible authority without constraining retained history."""

        table = self.project.symbol_table
        scope_ids = self._result_scope_ids(result_identifier)
        assert not any(
            use.resolved_symbol_identifier is not None
            and use.scope_identifier in scope_ids
            and use.name.casefold() == name.casefold()
            for use in table.uses
        )

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

    def assert_observed_result_context(
        self,
        result_identifier: str,
        source_text: str,
    ) -> None:
        """Accept canonical initial context or an exact bounded source-rescue path."""

        document = self.document_for(result_identifier)
        initial = document.render_initial()
        matches = [source for source in document.sources if source.text == source_text]

        if source_text in initial:
            for source in matches:
                if source.source_span is None:
                    continue
                raw_file = Path(source.source_span.file).read_text(encoding="utf-8")
                assert source.source_span.text(raw_file) == source_text
            return

        assert len(matches) == 1
        source = matches[0]
        assert source.address in advertised_source_addresses(document)
        assert source.source_span is not None
        raw_file = Path(source.source_span.file).read_text(encoding="utf-8")
        assert source.source_span.text(raw_file) == source_text

        request = parse_source_rescue_request(document, f"NEED_SOURCE {source.address}")
        rescue = render_source_rescue(document, request)
        assert source_text in rescue.text

    def assert_not_observed_result_source(
        self,
        result_identifier: str,
        source_fragment: str,
    ) -> None:
        document = self.document_for(result_identifier)
        assert not any(source_fragment in source.text for source in document.sources)
        assert source_fragment not in document.render_initial()


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


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_named_definition_is_authoritative_and_boundedly_reachable(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    configuration.require(ContractCapability.PROSE_AUTHORITY)
    definition = (
        "A simplicial complex is called flag-determined when every minimal non-face "
        "has two vertices."
    )
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{definition}

\begin{{theorem}}\label{{thm:main}}
The complex $K$ is flag-determined.
\end{{theorem}}
\begin{{proof}}
This follows from the edge criterion.
\end{{proof}}
""",
    )

    run.assert_authoritative("thm:main", "flag-determined", definition)
    run.assert_observed_result_context("thm:main", definition)
    document = run.document_for("thm:main")
    with pytest.raises(KeyError, match="unknown proof-language source addresses"):
        parse_source_rescue_request(document, "NEED_SOURCE NOT_ADVERTISED")


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_ambient_convention_applies_forward_but_not_backward(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    convention = "Throughout, all topological spaces are Hausdorff."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
\begin{{theorem}}\label{{thm:before}}
Every compact subset is closed.
\end{{theorem}}
\begin{{proof}}Use compactness.\end{{proof}}

{convention}

\begin{{theorem}}\label{{thm:after}}
Every compact subset is closed.
\end{{theorem}}
\begin{{proof}}Use compactness.\end{{proof}}
""",
    )

    run.assert_authoritative("thm:after", "topological spaces", convention)
    run.assert_not_observed_result_source("thm:before", "topological spaces are Hausdorff")
    run.assert_observed_result_context("thm:after", convention)


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_non_document_and_nearby_exposition_are_not_authority(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    definition = "A graph is called chord-guarded when every induced cycle has length three."
    motivation = "Chord-guarded graphs are a useful historical example."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
% A graph is called comment-defined when every vertex is red.
\begin{{verbatim}}
A graph is called listing-defined when every vertex is blue.
\end{{verbatim}}
\begin{{lstlisting}}
A graph is called code-defined when every vertex is green.
\end{{lstlisting}}
{definition}
{motivation}

\begin{{theorem}}\label{{thm:main}}
The graph $G$ is chord-guarded, comment-defined, listing-defined, and code-defined.
\end{{theorem}}
\begin{{proof}}Inspect its induced cycles.\end{{proof}}
""",
    )

    run.assert_authoritative("thm:main", "chord-guarded", definition)
    run.assert_not_authoritative("comment-defined")
    run.assert_not_authoritative("listing-defined")
    run.assert_not_authoritative("code-defined")
    run.assert_observed_result_context("thm:main", definition)
    run.assert_not_observed_result_source("thm:main", motivation)
    run.assert_not_observed_result_source("thm:main", "every vertex is red")
    run.assert_not_observed_result_source("thm:main", "every vertex is blue")
    run.assert_not_observed_result_source("thm:main", "every vertex is green")


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_cross_file_redefinition_shadows_earlier_authority(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    first = "A map is called fibre-regular when every fibre contains two points."
    second = "A map is called fibre-regular when every fibre contains three points."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{first}
\input{{redefine}}
\input{{result}}
""",
        includes={
            "redefine.tex": second,
            "result.tex": r"""
\begin{theorem}\label{thm:main}
The map $f$ is fibre-regular.
\end{theorem}
\begin{proof}Inspect the fibres.\end{proof}
""",
        },
    )

    symbol = run.assert_authoritative("thm:main", "fibre-regular", second)
    assert Path(symbol.introduction_source.file).name == "redefine.tex"
    run.assert_observed_result_context("thm:main", second)
    run.assert_not_observed_result_source("thm:main", "every fibre contains two points")


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_same_file_redefinition_shadows_earlier_authority(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    first = "A map is called fibre-regular when every fibre contains two points."
    second = "A map is called fibre-regular when every fibre contains three points."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{first}
{second}

\begin{{theorem}}\label{{thm:main}}
The map $f$ is fibre-regular.
\end{{theorem}}
\begin{{proof}}Inspect the fibres.\end{{proof}}
""",
    )

    symbol = run.assert_authoritative("thm:main", "fibre-regular", second)
    assert Path(symbol.introduction_source.file).name == "main.tex"
    run.assert_observed_result_context("thm:main", second)
    run.assert_not_observed_result_source("thm:main", "every fibre contains two points")


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_parent_declaration_is_visible_inside_included_child(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    definition = "A graph is called edge-rigid when every edge lies in a triangle."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{definition}
\input{{child}}
""",
        includes={
            "child.tex": r"""
\begin{theorem}\label{thm:child}
The graph $G$ is edge-rigid.
\end{theorem}
\begin{proof}Inspect the edges.\end{proof}
""",
        },
    )

    symbol = run.assert_authoritative("thm:child", "edge-rigid", definition)
    assert Path(symbol.introduction_source.file).name == "main.tex"
    run.assert_observed_result_context("thm:child", definition)


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_child_declaration_is_visible_after_returning_to_parent(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    definition = "A cover is called star-finite when each member meets finitely many others."
    run = _write_project(
        tmp_path,
        configuration,
        r"""
\input{declarations}

\begin{theorem}\label{thm:parent}
The cover $\mathcal U$ is star-finite.
\end{theorem}
\begin{proof}Inspect the intersections.\end{proof}
""",
        includes={"declarations.tex": definition},
    )

    symbol = run.assert_authoritative("thm:parent", "star-finite", definition)
    assert Path(symbol.introduction_source.file).name == "declarations.tex"
    run.assert_observed_result_context("thm:parent", definition)


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_child_shadowing_applies_inside_child_and_after_return_to_parent(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    first = "A cover is called star-finite when each member meets at most four others."
    second = "A cover is called star-finite when each member meets at most five others."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{first}
\input{{child}}

\begin{{theorem}}\label{{thm:parent}}
The cover $\mathcal U$ is star-finite.
\end{{theorem}}
\begin{{proof}}Inspect the intersections.\end{{proof}}
""",
        includes={
            "child.tex": rf"""
{second}
\begin{{theorem}}\label{{thm:child}}
The cover $\mathcal V$ is star-finite.
\end{{theorem}}
\begin{{proof}}Inspect the intersections.\end{{proof}}
""",
        },
    )

    for result_identifier in ("thm:child", "thm:parent"):
        symbol = run.assert_authoritative(result_identifier, "star-finite", second)
        assert Path(symbol.introduction_source.file).name == "child.tex"
        run.assert_observed_result_context(result_identifier, second)
        run.assert_not_observed_result_source(
            result_identifier,
            "each member meets at most four others",
        )


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_parent_declaration_after_include_does_not_leak_backward_into_child(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    later = "A graph is called edge-rigid when every edge lies in two triangles."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
\input{{child}}
{later}
""",
        includes={
            "child.tex": r"""
\begin{theorem}\label{thm:child}
The graph $G$ is edge-rigid.
\end{theorem}
\begin{proof}Inspect the edges.\end{proof}
""",
        },
    )

    run.assert_not_authoritative_at_result("thm:child", "edge-rigid")
    run.assert_not_observed_result_source("thm:child", later)


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_authoritative_context_preserves_exact_report_navigation(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    from thorn.report import report_source

    definition = "A complex is called shell-rigid when every facet meets a prior facet."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{definition}

\begin{{theorem}}\label{{thm:main}}
The complex $K$ is shell-rigid.
\end{{theorem}}
\begin{{proof}}Inspect the facets.\end{{proof}}
""",
    )

    symbol = run.assert_authoritative("thm:main", "shell-rigid", definition)
    run.assert_observed_result_context("thm:main", definition)

    expected = symbol.introduction_source.source_range()
    navigation = report_source(expected, excerpt=definition)

    assert navigation.file == expected.file
    assert navigation.start_line == expected.start_line
    assert navigation.end_line == expected.end_line
    assert navigation.excerpt == definition
    assert navigation.uri == Path(expected.file).resolve().as_uri()


@pytest.mark.parametrize(
    "configuration",
    PROSE_AUTHORITY_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_transitive_semantics_compose_with_structured_dependencies(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    convention = r"Throughout, the base field is $K=\mathbb R$."
    definition = "A matrix is called regular when its determinant is nonzero over the base field."
    run = _write_project(
        tmp_path,
        configuration,
        rf"""
{convention}
{definition}

\begin{{lemma}}\label{{lem:criterion}}
A matrix with nonzero determinant is invertible.
\end{{lemma}}
\begin{{proof}}Use the adjugate formula.\end{{proof}}

\begin{{theorem}}\label{{thm:main}}
Every regular matrix is invertible by Lemma~\ref{{lem:criterion}}.
\end{{theorem}}
\begin{{proof}}Apply Lemma~\ref{{lem:criterion}}.\end{{proof}}
""",
    )

    run.assert_authoritative("thm:main", "base field", convention)
    run.assert_authoritative("thm:main", "regular", definition)
    run.assert_observed_result_context("thm:main", convention)
    run.assert_observed_result_context("thm:main", definition)
    assert run.project.dependency_graph.direct_dependency_ids("thm:main") == ["lem:criterion"]
    document = run.document_for("thm:main")
    assert any(
        source.referenced_result_identifier == "lem:criterion"
        for source in document.sources
    )


_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


class _StaticDependencyFrontend:
    name = "contract-static-dependencies"

    def parse(self, text: str) -> LinguisticDocument:
        tokens = [
            LinguisticToken(
                index=0,
                text="introduces",
                lemma="introduce",
                pos="VERB",
                dependency="ROOT",
                head_index=0,
                sentence_index=0,
                start=0,
                end=0,
            )
        ]
        for match in _PLACEHOLDER_RE.finditer(text):
            tokens.append(
                LinguisticToken(
                    index=len(tokens),
                    text=match.group(0),
                    lemma=match.group(0),
                    pos="PROPN",
                    dependency="obl",
                    head_index=0,
                    sentence_index=0,
                    start=match.start(),
                    end=match.end(),
                )
            )
        return LinguisticDocument(text=text, tokens=tokens)


LINGUISTIC_CONFIGURATIONS = (
    STRUCTURAL_CONFIGURATIONS[0],
    ContractConfiguration(
        name="regex-static-nlp",
        frontend_factory=RegexLatexFrontend,
        linguistic_factory=_StaticDependencyFrontend,
        capabilities=frozenset(
            {
                ContractCapability.PROJECT_SEMANTICS,
                ContractCapability.LINGUISTIC_CANDIDATES,
            }
        ),
    ),
)


@pytest.mark.parametrize(
    "configuration",
    LINGUISTIC_CONFIGURATIONS,
    ids=lambda configuration: configuration.name,
)
def test_linguistic_candidates_remain_non_authoritative(
    tmp_path: Path,
    configuration: ContractConfiguration,
) -> None:
    configuration.require(ContractCapability.LINGUISTIC_CANDIDATES)
    run = _write_project(
        tmp_path,
        configuration,
        r"""
\begin{theorem}\label{thm:main}
A conclusion holds.
\end{theorem}
\begin{proof}
Fix $x\in X$ for the argument.
\end{proof}
""",
    )

    candidate = next(item for item in run.project.symbol_table.candidates if item.name == "x")
    assert candidate.status == InferenceStatus.AMBIGUOUS
    assert candidate.source.text(run.main_file.read_text(encoding="utf-8")) == "x"
    assert all(symbol.name != "x" for symbol in run.project.symbol_table.symbols)
