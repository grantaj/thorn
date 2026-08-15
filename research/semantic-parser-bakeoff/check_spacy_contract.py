from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from thorn.evidence import InferenceStatus
from thorn.latex import extract_project
from thorn.linguistic import (
    LinguisticDocument,
    LinguisticToken,
    NormalizedLinguisticRelation,
)
from thorn.spacy_linguistic import SpacyLinguisticFrontend
from thorn.support import QualifierKind, SupportKind
from thorn.symbols import SymbolCandidateKind

_CASES = Path(__file__).with_name("cases.json")
_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


def _cases() -> list[dict[str, Any]]:
    payload = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = payload["cases"]
    if not isinstance(cases, list):
        raise AssertionError("benchmark cases must be a list")
    return cases


def _assert_normalized_parser_boundary(
    frontend: SpacyLinguisticFrontend,
    cases: list[dict[str, Any]],
) -> None:
    """Exercise every corpus sentence without freezing backend dependency templates."""

    for case in cases:
        text = str(case["text"])
        document = frontend.parse(text)
        assert type(document) is LinguisticDocument
        assert all(type(token) is LinguisticToken for token in document.tokens)

        expected_placeholders = set(_PLACEHOLDER_RE.findall(text))
        parsed_placeholders = {
            token.text for token in document.tokens if _PLACEHOLDER_RE.fullmatch(token.text)
        }
        assert expected_placeholders <= parsed_placeholders, (
            case["id"],
            expected_placeholders - parsed_placeholders,
        )
        for token in document.tokens:
            assert document.text[token.start : token.end] == token.text

        expected = case["expected"]
        relation = document.normalized_relation(
            expected.get("source"),
            expected.get("target"),
        )
        assert type(relation) is NormalizedLinguisticRelation
        # This serialization boundary is intentionally Thorn-owned. No spaCy Doc/Token
        # object is permitted to escape into the mathematical IR.
        relation.model_dump(mode="json")


def _paper(proof: str) -> str:
    return rf"""\documentclass{{article}}
\newtheorem{{lemma}}{{Lemma}}
\newtheorem{{theorem}}{{Theorem}}
\begin{{document}}
\begin{{lemma}}\label{{lem:base}}
A base fact.
\end{{lemma}}
\begin{{theorem}}\label{{thm:main}}
A conclusion.
\end{{theorem}}
\begin{{proof}}
{proof}
\end{{proof}}
\end{{document}}
"""


def _write_case(root: Path, identifier: str, proof: str) -> Path:
    path = root / f"{identifier}.tex"
    path.write_text(_paper(proof), encoding="utf-8")
    return path


def _assert_result_support_contract(
    root: Path,
    frontend: SpacyLinguisticFrontend,
    cases: list[dict[str, Any]],
) -> int:
    checked = 0
    for case in cases:
        if case["task"] != "result_support":
            continue
        proof = str(case["text"]).replace(
            "THORNRESULT1",
            r"Lemma~\ref{lem:base}",
        ).replace("THORNCLAIM1", "the conclusion")
        path = _write_case(root, str(case["id"]), proof)
        project = extract_project(path, linguistic_frontend=frontend)
        graph = project.proof_support_graph
        edges = [
            edge
            for edge in graph.edges
            if edge.kind == SupportKind.RESULT_REFERENCE and edge.target_label == "lem:base"
        ]
        assert edges, case["id"]
        assert all(edge.status != InferenceStatus.CONFIDENT for edge in edges), case["id"]
        assert all(edge not in graph.confident_edges() for edge in edges)

        # Positive paraphrases are equivalent at the Thorn relation level even when
        # their raw parser dependency paths differ. Expository controls may still be
        # retained as candidates, but never as confident mathematical support.
        if case["family"] == "positive":
            assert any(edge.status == InferenceStatus.AMBIGUOUS for edge in edges), case["id"]

        evidence = edges[0].evidence
        assert evidence, case["id"]
        assert evidence[0].frontend == "spacy"
        assert evidence[0].source == edges[0].source
        source_text = path.read_text(encoding="utf-8")
        assert evidence[0].source.text(source_text) == r"\ref{lem:base}"
        assert evidence[0].context
        checked += 1
    return checked


def _assert_prior_claim_contract(
    root: Path,
    frontend: SpacyLinguisticFrontend,
    cases: list[dict[str, Any]],
) -> int:
    checked = 0
    for case in cases:
        if case["task"] != "prior_claim":
            continue
        proof = str(case["text"]).replace("THORNCLAIM1", "A base fact").replace(
            "THORNCLAIM2",
            "the conclusion",
        )
        path = _write_case(root, str(case["id"]), proof)
        project = extract_project(path, linguistic_frontend=frontend)
        graph = project.proof_support_graph
        edges = [edge for edge in graph.edges if edge.kind == SupportKind.PRIOR_CLAIM]
        assert all(edge.status != InferenceStatus.CONFIDENT for edge in edges), case["id"]
        if case["family"] == "positive":
            assert edges, case["id"]
            assert any(edge.status == InferenceStatus.AMBIGUOUS for edge in edges), case["id"]
        for edge in edges:
            assert edge.evidence, case["id"]
            assert edge.evidence[0].frontend == "spacy"
            assert edge not in graph.confident_edges()
        checked += 1
    return checked


def _assert_symbol_and_binder_contract(
    root: Path,
    frontend: SpacyLinguisticFrontend,
) -> None:
    symbol_path = _write_case(
        root,
        "symbol-contract",
        r"Fix $x\in X$ for the argument. Put $c:=a+b$ for later use.",
    )
    symbol_project = extract_project(symbol_path, linguistic_frontend=frontend)
    candidates = {item.name: item for item in symbol_project.symbol_table.candidates}
    assert candidates["x"].kind == SymbolCandidateKind.INTRODUCTION
    assert candidates["c"].kind == SymbolCandidateKind.DEFINITION
    assert candidates["x"].status == InferenceStatus.AMBIGUOUS
    assert candidates["c"].status == InferenceStatus.AMBIGUOUS
    assert candidates["x"].evidence[0].frontend == "spacy"
    assert candidates["c"].evidence[0].frontend == "spacy"
    assert all(symbol.name not in {"x", "c"} for symbol in symbol_project.symbol_table.symbols)

    binder_path = _write_case(
        root,
        "binder-contract",
        r"""\[
a_n = 0.
\]
where $n\ge 1$ throughout the argument.""",
    )
    binder_project = extract_project(binder_path, linguistic_frontend=frontend)
    claims = binder_project.proof_support_graph.claims_for_result("thm:main")
    qualifiers = [
        qualifier
        for claim in claims
        for qualifier in claim.qualifiers
        if qualifier.kind == QualifierKind.TRAILING_BINDER
    ]
    assert qualifiers
    assert qualifiers[0].status == InferenceStatus.AMBIGUOUS
    assert qualifiers[0].evidence
    assert qualifiers[0].evidence[0].frontend == "spacy"


def main() -> int:
    cases = _cases()
    assert len(cases) == 70
    frontend = SpacyLinguisticFrontend()
    _assert_normalized_parser_boundary(frontend, cases)

    with tempfile.TemporaryDirectory(prefix="thorn-spacy-contract-") as directory:
        root = Path(directory)
        support_cases = _assert_result_support_contract(root, frontend, cases)
        prior_cases = _assert_prior_claim_contract(root, frontend, cases)
        _assert_symbol_and_binder_contract(root, frontend)

    print(
        json.dumps(
            {
                "cases_parsed": len(cases),
                "result_support_cases_checked": support_cases,
                "prior_claim_cases_checked": prior_cases,
                "contract": (
                    "Thorn-owned normalized structures, ambiguity/provenance semantics, "
                    "and deterministic-graph isolation"
                ),
                "note": (
                    "raw dependency-template counts are diagnostic research output and are "
                    "not a production invariant"
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
