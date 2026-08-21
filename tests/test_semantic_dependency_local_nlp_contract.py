"""Real Local NLP coverage for the backend-independent semantic dependency contract."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_semantic_dependency_contract import (
    LINGUISTIC_CONFIGURATIONS,
    ContractCapability,
    ContractConfiguration,
    _write_project,
)

from thorn.evidence import InferenceStatus
from thorn.frontends import RegexLatexFrontend
from thorn.linguistic import LinguisticDocument, LinguisticFrontend, LinguisticToken
from thorn.linguistic_declarations import ProseDeclarationCapability
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


def _assert_candidate_contract(
    tmp_path: Path,
    configuration: ContractConfiguration,
    frontend: LinguisticFrontend,
) -> None:
    """Run the same Thorn-owned candidate assertions for fixture and real NLP."""

    configuration.require(ContractCapability.LINGUISTIC_CANDIDATES)
    tmp_path.mkdir(parents=True, exist_ok=True)
    _assert_normalized_frontend_boundary(frontend)
    run = _write_project(
        tmp_path,
        ContractConfiguration(
            name=configuration.name,
            frontend_factory=configuration.frontend_factory,
            linguistic_factory=lambda: frontend,
            capabilities=configuration.capabilities,
        ),
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
    assert candidate.evidence
    assert all(evidence.frontend == frontend.name for evidence in candidate.evidence)
    assert all(evidence.source == candidate.math_source for evidence in candidate.evidence)
    assert all(evidence.target == candidate.source for evidence in candidate.evidence)
    assert all(evidence.dependency_path for evidence in candidate.evidence)

    prose = run.project.prose_declarations
    assert prose is not None
    assert prose.capability == ProseDeclarationCapability.COMPLETE
    assert prose.frontend == frontend.name

    # Generic linguistic symbol candidates remain non-authoritative. Slice D only
    # changes the separate Thorn policy for complete prose declaration candidates.
    assert all(symbol.name != "x" for symbol in run.project.symbol_table.symbols)
    run.assert_not_authoritative("x")

    payload = candidate.model_dump(mode="json")
    assert isinstance(payload, dict)
    assert "spacy.tokens" not in repr(payload)
    assert "prose_declarations" not in run.project.model_dump(mode="json")


def test_fixture_and_real_spacy_share_the_candidate_contract(tmp_path: Path) -> None:
    fixture_configuration = LINGUISTIC_CONFIGURATIONS[1]
    assert fixture_configuration.linguistic_factory is not None
    fixture_frontend = fixture_configuration.linguistic_factory()
    _assert_candidate_contract(tmp_path / "fixture", fixture_configuration, fixture_frontend)

    spacy_frontend = _spacy_frontend_or_skip()
    spacy_configuration = ContractConfiguration(
        name="regex-local-spacy",
        frontend_factory=RegexLatexFrontend,
        linguistic_factory=lambda: spacy_frontend,
        capabilities=frozenset(
            {
                ContractCapability.PROJECT_SEMANTICS,
                ContractCapability.LINGUISTIC_CANDIDATES,
            }
        ),
    )
    _assert_candidate_contract(tmp_path / "spacy", spacy_configuration, spacy_frontend)


def test_real_spacy_prose_proposal_is_exact_then_thorn_promotes_it(tmp_path: Path) -> None:
    frontend = _spacy_frontend_or_skip()
    run = _write_project(
        tmp_path,
        ContractConfiguration(
            name="regex-local-spacy",
            frontend_factory=RegexLatexFrontend,
            linguistic_factory=lambda: frontend,
            capabilities=frozenset(
                {
                    ContractCapability.PROJECT_SEMANTICS,
                    ContractCapability.PROSE_AUTHORITY,
                    ContractCapability.LINGUISTIC_CANDIDATES,
                }
            ),
        ),
        r"""
We call a map admissible if it is continuous.
\begin{theorem}\label{thm:main}
The map $f$ is admissible.
\end{theorem}
""",
    )

    prose = run.project.prose_declarations
    assert prose is not None
    assert prose.capability == ProseDeclarationCapability.COMPLETE
    candidate = next(item for item in prose.candidates if item.term == "admissible")
    raw = run.main_file.read_text(encoding="utf-8")
    assert candidate.status == InferenceStatus.AMBIGUOUS
    assert candidate.term_source.text(raw) == "admissible"
    assert candidate.source.text(raw) == "We call a map admissible if it is continuous."
    assert candidate.payload_source is not None
    assert candidate.payload_source.text(raw).strip() == "it is continuous."
    assert candidate.evidence
    assert candidate.evidence[0].frontend == frontend.name
    assert candidate.evidence[0].target == candidate.term_source

    # The linguistic backend still proposes only ambiguous grammatical evidence.
    # Thorn separately adjudicates substantive payload, project order, visibility,
    # shadowing, and result use before emitting canonical mathematical authority.
    symbol = run.assert_authoritative(
        "thm:main",
        "admissible",
        "We call a map admissible if it is continuous.",
    )
    assert symbol.introduction_source == candidate.source


def test_structural_only_configuration_explicitly_omits_linguistic_capability() -> None:
    structural_configuration = LINGUISTIC_CONFIGURATIONS[0]
    assert ContractCapability.PROJECT_SEMANTICS in structural_configuration.capabilities
    assert ContractCapability.PROSE_AUTHORITY not in structural_configuration.capabilities
    assert ContractCapability.LINGUISTIC_CANDIDATES not in structural_configuration.capabilities
