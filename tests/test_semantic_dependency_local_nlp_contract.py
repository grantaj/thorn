"""Real Local NLP coverage for the backend-independent semantic dependency contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_semantic_dependency_contract import (
    LINGUISTIC_CONFIGURATION,
    STRUCTURAL_CONFIGURATIONS,
    ContractCapability,
    ContractConfiguration,
    _write_project,
)

from thorn.context_retrieval import build_result_context_pools
from thorn.frontends.tree_sitter import TreeSitterLatexFrontend
from thorn.linguistic import LinguisticDocument, LinguisticFrontend, LinguisticToken
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend


def _spacy_frontend_or_skip() -> SpacyLinguisticFrontend:
    frontend = SpacyLinguisticFrontend()
    try:
        frontend.parse("Thorn normalizes local linguistic evidence.")
    except LinguisticFrontendUnavailable as exc:
        pytest.skip(str(exc))
    return frontend


def _assert_normalized_frontend_boundary(frontend: LinguisticFrontend) -> None:
    document = frontend.parse("Fix THORNMATH1 for the argument.")
    assert isinstance(document, LinguisticDocument)
    assert document.tokens
    assert all(isinstance(token, LinguisticToken) for token in document.tokens)


def _production_source_configuration(
    configuration: ContractConfiguration,
    frontend: LinguisticFrontend,
) -> ContractConfiguration:
    return ContractConfiguration(
        name=f"tree-sitter-{configuration.name}",
        frontend_factory=TreeSitterLatexFrontend,
        linguistic_factory=lambda: frontend,
        capabilities=configuration.capabilities,
    )


def _assert_linguistic_source_contract(
    tmp_path: Path,
    configuration: ContractConfiguration,
    frontend: LinguisticFrontend,
) -> None:
    """Require source preservation without generic mathematical interpretation."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    _assert_normalized_frontend_boundary(frontend)
    run = _write_project(
        tmp_path,
        _production_source_configuration(configuration, frontend),
        r"""
\begin{theorem}\label{thm:main}
A conclusion holds.
\end{theorem}
\begin{proof}
Fix $x\in X$ for the argument.
\end{proof}
""",
    )

    assert run.project.symbol_table.candidates == []
    assert all(symbol.name != "x" for symbol in run.project.symbol_table.symbols)
    run.assert_not_authoritative("x")

    statements = run.project.linguistic_statements
    assert statements is not None
    assert statements.complete
    assert statements.frontend == frontend.name
    assert any(r"$x\in X$" in statement.text for statement in statements.statements)

    payload = statements.model_dump(mode="json")
    assert isinstance(payload, dict)
    assert "spacy.tokens" not in repr(payload)
    assert "prose_declarations" not in run.project.model_dump(mode="json")


def test_fixture_and_real_spacy_share_source_only_symbol_contract(tmp_path: Path) -> None:
    assert LINGUISTIC_CONFIGURATION.linguistic_factory is not None
    fixture_frontend = LINGUISTIC_CONFIGURATION.linguistic_factory()
    _assert_linguistic_source_contract(
        tmp_path / "fixture",
        LINGUISTIC_CONFIGURATION,
        fixture_frontend,
    )

    spacy_frontend = _spacy_frontend_or_skip()
    spacy_configuration = ContractConfiguration(
        name="local-spacy",
        frontend_factory=TreeSitterLatexFrontend,
        linguistic_factory=lambda: spacy_frontend,
        capabilities=frozenset({ContractCapability.PROJECT_SEMANTICS}),
    )
    _assert_linguistic_source_contract(tmp_path / "spacy", spacy_configuration, spacy_frontend)


def test_real_spacy_prose_is_exact_retrievable_source_not_authority(tmp_path: Path) -> None:
    frontend = _spacy_frontend_or_skip()
    sentence = "We call a map admissible if it is continuous."
    run = _write_project(
        tmp_path,
        ContractConfiguration(
            name="tree-sitter-local-spacy",
            frontend_factory=TreeSitterLatexFrontend,
            linguistic_factory=lambda: frontend,
            capabilities=frozenset({ContractCapability.PROJECT_SEMANTICS}),
        ),
        rf"""
{sentence}
\begin{{theorem}}\label{{thm:main}}
The map $f$ is admissible.
\end{{theorem}}
""",
    )

    statements = run.project.linguistic_statements
    assert statements is not None and statements.complete
    exact = next(statement for statement in statements.statements if statement.text == sentence)
    raw = run.main_file.read_text(encoding="utf-8")
    assert exact.source.text(raw) == sentence

    pools = build_result_context_pools(run.project, "thm:main")
    assert pools
    assert any(candidate.text == sentence for pool in pools for candidate in pool.candidates)

    # Retrieval eligibility is not authority. The old declaration grammar used to
    # promote this sentence; production now preserves it as exact advisory evidence.
    run.assert_not_authoritative("admissible")


def test_structural_only_configuration_omits_local_nlp() -> None:
    structural_configuration = STRUCTURAL_CONFIGURATIONS[0]
    assert ContractCapability.PROJECT_SEMANTICS in structural_configuration.capabilities
    assert structural_configuration.linguistic_factory is None
