#!/usr/bin/env python3
"""Keyless issue #101 red-team observer.

This script deliberately does not adjudicate model reasoning.  It exercises the
production deterministic review preparation, source contract, cache policy,
Lean projection, report and proof-visualizer boundaries and records what reaches
those boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from thorn.analysis import analyze_project
from thorn.latex import extract_project
from thorn.lean_export import project_lean
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    advertised_source_addresses,
    build_proof_review_turn,
)
from thorn.proof_visualizer import write_proof_visualizer_html
from thorn.providers.request_envelope import proof_review_request_envelope
from thorn.report import build_report
from thorn.report_html import write_report_html
from thorn.review_cache import ProofReviewCache
from thorn.review_workflow import prepare_proof_review, run_cached_proof_review

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "eval" / "adversarial" / "issue_101"
MANIFEST = CORPUS / "manifest.json"
FROZEN_LIVE_MODEL = "gpt-5.6"


class _CleanTransport:
    """Deterministic protocol stand-in; never performs a provider call."""

    model = "issue-101-keyless-fake"

    def __init__(self, count: int = 8) -> None:
        self.responses = [ProofReviewModelResponse(action="review") for _ in range(count)]
        self.requests = 0

    def review_proof_turn(self, request: object) -> ProofReviewModelResponse:
        del request
        self.requests += 1
        return self.responses.pop(0)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reachability(document: Any, fragment: str) -> dict[str, object]:
    packet = document.render_initial()
    advertised = set(advertised_source_addresses(document))
    matching = [source for source in document.sources if fragment in source.text]
    return {
        "in_initial_packet": fragment in packet,
        "matching_source_addresses": [source.address for source in matching],
        "advertised_matching_addresses": [
            source.address for source in matching if source.address in advertised
        ],
        "reachable": fragment in packet
        or any(source.address in advertised for source in matching),
    }


def _observe_case(case: dict[str, Any]) -> dict[str, object]:
    path = CORPUS / case["path"]
    actual_hash = _sha256(path)
    project = extract_project(path)
    review_target = case.get("review_target", case["target"])
    unit = project.unit(review_target)
    prepared = prepare_proof_review(project, unit)
    document = prepared.document
    analysis = analyze_project(project)
    lean = project_lean(prepared.state)
    advertised = advertised_source_addresses(document)
    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=document))
    envelope = proof_review_request_envelope(turn, FROZEN_LIVE_MODEL)

    with tempfile.TemporaryDirectory(prefix="thorn-101-") as raw_tmp:
        tmp = Path(raw_tmp)
        report_path = tmp / "report.html"
        graph_path = tmp / "graph.html"
        report = build_report(
            project,
            analysis_findings=analysis,
            proof_states={unit.identifier: prepared.state},
            proof_documents={unit.identifier: document},
            lean_exports={unit.identifier: lean},
            thorn_version="issue-101-keyless",
        )
        write_report_html(report, report_path)
        write_proof_visualizer_html(project, graph_path)
        report_text = report_path.read_text(encoding="utf-8")
        graph_text = graph_path.read_text(encoding="utf-8")

    return {
        "id": case["id"],
        "path": case["path"],
        "source_sha256": actual_hash,
        "source_hash_matches_frozen": actual_hash == case["source_sha256"],
        "target_result_identifier": case["target"],
        "review_result_identifier": unit.identifier,
        "direct_dependencies": project.dependency_graph.direct_dependency_ids(unit.identifier),
        "transitive_dependencies": project.dependency_graph.transitive_dependency_ids(
            unit.identifier
        ),
        "structural_findings": [finding.rule for finding in analysis],
        "thorn_proof_fingerprint": document.fingerprint(),
        "thorn_proof_lines": len(document.lines),
        "source_handles": len(document.sources),
        "advertised_source_addresses": list(advertised),
        "review_contract_addresses_match": (
            tuple(turn.allowed_source_addresses) == tuple(advertised)
        ),
        "frozen_live_model": FROZEN_LIVE_MODEL,
        "initial_request_fingerprint": envelope.fingerprint(),
        "initial_request_characters": sum(
            len(message.get("role", "")) + len(message.get("content", ""))
            for message in envelope.input_messages()
        ),
        "required_source_reachability": {
            fragment: _reachability(document, fragment)
            for fragment in case["required_source_fragments"]
        },
        "lean_status": lean.status.value,
        "lean_mechanically_checkable": lean.is_mechanically_checkable,
        "report_mentions_result": unit.identifier in report_text,
        "graph_mentions_result": unit.identifier in graph_text,
    }


def _prepare_text(path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    project = extract_project(path)
    return prepare_proof_review(project, project.unit("thm:uniform-decay"))


def _cache_scenario(
    before_text: str,
    after_text: str,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="thorn-101-cache-") as raw_tmp:
        tmp = Path(raw_tmp)
        paper = tmp / "paper.tex"
        before = _prepare_text(paper, before_text)
        cache = ProofReviewCache(tmp / "cache")
        transport = _CleanTransport()
        first = run_cached_proof_review(before, transport, cache)
        after = _prepare_text(paper, after_text)
        second = run_cached_proof_review(after, transport, cache)
        return {
            "initial_packet_equal": before.document.fingerprint() == after.document.fingerprint(),
            "first_status": first.cache.status.value,
            "first_reason": first.cache.reason.value,
            "second_status": second.cache.status.value,
            "second_reason": second.cache.reason.value,
            "provider_turns": transport.requests,
        }


def _cache_observations() -> dict[str, object]:
    baseline = (CORPUS / "baseline.tex").read_text(encoding="utf-8")
    lemma = (CORPUS / "variant_lemma_laundering.tex").read_text(encoding="utf-8")

    exposition_after = baseline.replace(
        "\\maketitle\n",
        "\\maketitle\n\nThis paragraph is expository and changes no mathematical claim.\n",
        1,
    )
    normalized_after = baseline.replace(
        "for each \\(x\\in I\\)\nchoose",
        "for every \\(x\\in I\\)\nchoose",
        1,
    )
    upstream_after = lemma.replace(
        "The neighbourhoods supplied by Lemma~\\ref{lem:local} form an open cover",
        "The neighbourhoods obtained from Lemma~\\ref{lem:local} form an open cover",
        1,
    )
    edge_after = lemma.replace("lem:uniformize", "lem:uniformize-renamed")

    return {
        "unrelated_exposition_edit": _cache_scenario(baseline, exposition_after),
        "local_wording_edit": _cache_scenario(baseline, normalized_after),
        "upstream_proof_edit": _cache_scenario(lemma, upstream_after),
        "dependency_label_edit": _cache_scenario(lemma, edge_after),
    }


def observe() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = [manifest["control"], *manifest["variants"]]
    return {
        "format_version": 1,
        "issue": 101,
        "assurance_revision": manifest["assurance_revision"],
        "cases": [_observe_case(case) for case in cases],
        "cache_attacks": _cache_observations(),
        "semantic_adjudication": (
            "not performed: no paid/live model call and no exact replay was available "
            "for these new request fingerprints"
        ),
    }


def _check(payload: dict[str, object]) -> None:
    cases = payload["cases"]
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        if not case["source_hash_matches_frozen"]:
            raise SystemExit(f"{case['id']}: source hash no longer matches frozen manifest")
        if not case["review_contract_addresses_match"]:
            raise SystemExit(f"{case['id']}: advertised NEED_SOURCE contract drifted")
        if not case["report_mentions_result"]:
            raise SystemExit(f"{case['id']}: report lost result identity")
        if not case["graph_mentions_result"]:
            raise SystemExit(f"{case['id']}: proof visualizer lost result identity")

    cache = payload["cache_attacks"]
    assert isinstance(cache, dict)
    unsafe = []
    for name in ("local_wording_edit", "upstream_proof_edit", "dependency_label_edit"):
        item = cache[name]
        assert isinstance(item, dict)
        if item["second_status"] == "reused":
            unsafe.append((name, item["second_reason"]))
    if unsafe:
        raise SystemExit(f"unsafe semantic cache reuse: {unsafe}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = observe()
    if args.check:
        _check(payload)
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
