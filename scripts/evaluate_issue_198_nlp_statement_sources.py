#!/usr/bin/env python3
"""Evaluate a dictionary-free NLP sentence source path for issue #198.

This is a speculative measurement harness only. It does not change Thorn's
production source selection. spaCy supplies sentence boundaries, Tree-sitter
supplies source/math spans, and project order bounds eligibility. No English cue
words or declaration-role classification are used by the candidate algorithm.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from thorn.frontends import DEFAULT_FRONTEND_NAME, get_frontend
from thorn.latex import extract_project
from thorn.linguistic import LinguisticToken
from thorn.llm_proof_language import (
    LLMProofLanguage,
    ProofLanguageSourceHandle,
    parse_source_rescue_request,
    render_source_rescue,
)
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    advertised_source_addresses,
    build_proof_review_turn,
)
from thorn.project_partiality import normalize_project_structure
from thorn.review_workflow import prepare_proof_review
from thorn.source_projection import ProjectionTokenKind, build_linguistic_projection
from thorn.spacy_linguistic import SpacyLinguisticFrontend

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "eval" / "robustness" / "issue_198" / "qualification_manifest.json"
DEFAULT_OUTPUT = ROOT / "eval" / "robustness" / "issue_198" / "nlp_statement_source_spike.json"


def _line_start(text: str, line: int) -> int:
    if line <= 1:
        return 0
    cursor = 0
    for _ in range(1, line):
        newline = text.find("\n", cursor)
        if newline < 0:
            return len(text)
        cursor = newline + 1
    return cursor


def _sentence_groups(tokens: list[LinguisticToken]) -> list[list[LinguisticToken]]:
    grouped: dict[int, list[LinguisticToken]] = defaultdict(list)
    for token in tokens:
        grouped[token.sentence_index].append(token)
    return [grouped[index] for index in sorted(grouped)]


def _nlp_math_sentence_sources(
    source: Path,
    *,
    target_line: int,
    nlp: SpacyLinguisticFrontend,
) -> tuple[list[ProofLanguageSourceHandle], list[dict[str, Any]]]:
    """Return prior NLP sentences containing parser-owned math.

    Candidate selection is intentionally lexical-free: a source is eligible only
    because spaCy says it is one sentence, Tree-sitter says it contains math, the
    normalized source-role boundary says it is eligible document text, and it
    precedes the target result. No declaration cue or mathematical role is inferred.
    """

    parsed = normalize_project_structure(get_frontend(DEFAULT_FRONTEND_NAME).parse_project(source))
    file = parsed.file(source)
    projection = build_linguistic_projection(file)
    if not projection.complete:
        raise RuntimeError(f"partial linguistic projection for {source}")

    document = nlp.parse(projection.text)
    target_offset = _line_start(file.raw, target_line)
    handles: list[ProofLanguageSourceHandle] = []
    evidence: list[dict[str, Any]] = []

    for tokens in _sentence_groups(document.tokens):
        if not tokens:
            continue
        start = min(token.start for token in tokens)
        end = max(token.end for token in tokens)
        if start >= target_offset or end <= start:
            continue
        span = file.span(start, end)
        if not projection.source_span_eligible(span):
            continue

        math_tokens = [
            token
            for token in projection.tokens
            if token.kind == ProjectionTokenKind.MATH
            and token.source.start_offset < span.end_offset
            and span.start_offset < token.source.end_offset
        ]
        if not math_tokens:
            continue

        address = f"NLP{len(handles) + 1}"
        raw = span.text(file.raw)
        handle = ProofLanguageSourceHandle(
            address=address,
            ir_identifier=f"nlp-sentence:{Path(file.path).name}:{span.start_offset}",
            text=raw,
            source_span=span,
            source_range=span.source_range(),
        )
        handles.append(handle)
        evidence.append(
            {
                "address": address,
                "source": handle.model_dump(mode="json"),
                "math_spans": [token.source.model_dump(mode="json") for token in math_tokens],
                "tokens": [
                    {
                        "text": token.text,
                        "lemma": token.lemma,
                        "pos": token.pos,
                        "dependency": token.dependency,
                        "head_index": token.head_index,
                    }
                    for token in tokens
                ],
            }
        )

    return handles, evidence


def _augment_document(
    document: LLMProofLanguage,
    handles: list[ProofLanguageSourceHandle],
) -> LLMProofLanguage:
    existing = {source.address for source in document.sources}
    additions = [source for source in handles if source.address not in existing]
    if not additions:
        return document
    index_line = "NLP_CONTEXT @" + ",".join(source.address for source in additions)
    return document.model_copy(
        update={
            "lines": (*document.lines, index_line),
            "sources": (*document.sources, *additions),
        }
    )


def _matches(document: LLMProofLanguage, needle: str) -> list[ProofLanguageSourceHandle]:
    return [source for source in document.sources if needle in source.text]


def _case_evidence(case: dict[str, Any], nlp: SpacyLinguisticFrontend) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    source = ROOT / case["source"]
    project = extract_project(
        source,
        frontend=get_frontend(DEFAULT_FRONTEND_NAME),
        linguistic_frontend=nlp,
    )
    unit = project.unit(case["target"])
    prepared = prepare_proof_review(project, unit)
    baseline = prepared.document

    generic, generic_evidence = _nlp_math_sentence_sources(
        source,
        target_line=unit.statement_range.start_line,
        nlp=nlp,
    )
    augmented = _augment_document(baseline, generic)
    advertised = set(advertised_source_addresses(augmented))
    baseline_addresses = {source.address for source in baseline.sources}
    generic_addresses = {source.address for source in generic}

    required: list[dict[str, Any]] = []
    for needle in case["required_reachable_sources"]:
        matches = _matches(augmented, needle)
        if len(matches) != 1:
            errors.append(
                f"{case['id']}: expected exactly one reachable source containing {needle!r}, got {len(matches)}"
            )
            continue
        handle = matches[0]
        if handle.address not in advertised:
            errors.append(f"{case['id']}: {handle.address} is not advertised")
            continue
        rescue = render_source_rescue(
            augmented,
            parse_source_rescue_request(augmented, f"NEED_SOURCE {handle.address}"),
        )
        if needle not in rescue.text:
            errors.append(f"{case['id']}: rescue omitted {needle!r}")
        required.append(
            {
                "needle": needle,
                "address": handle.address,
                "origin": (
                    "baseline"
                    if handle.address in baseline_addresses
                    else "nlp_math_sentence"
                    if handle.address in generic_addresses
                    else "unknown"
                ),
                "rescue": rescue.text,
            }
        )

    packet = augmented.render_initial()
    for needle in case["required_absent_from_initial"]:
        if needle in packet:
            errors.append(f"{case['id']}: source text leaked into initial packet: {needle!r}")

    all_source_text = "\n".join(source.text for source in augmented.sources)
    for needle in case["irrelevant_source_needles"]:
        if needle in all_source_text or needle in packet:
            errors.append(f"{case['id']}: irrelevant source became reachable: {needle!r}")

    turn = build_proof_review_turn(ProofLanguageReviewRequest(document=augmented))
    for address in generic_addresses:
        if address not in turn.allowed_source_addresses:
            errors.append(f"{case['id']}: generic source {address} absent from closed-world review contract")

    return (
        {
            "id": case["id"],
            "status": "pass" if not errors else "fail",
            "baseline_source_count": len(baseline.sources),
            "generic_source_count": len(generic),
            "generic_sources": generic_evidence,
            "required_reachability": required,
            "advertised_source_addresses": sorted(advertised),
            "errors": errors,
        },
        errors,
    )


def build_evidence(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    nlp = SpacyLinguisticFrontend(model_name="en_core_web_sm")
    errors: list[str] = []
    cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        evidence, case_errors = _case_evidence(case, nlp)
        cases.append(evidence)
        errors.extend(case_errors)

    return {
        "format": "thorn-issue-198-nlp-statement-source-spike/1",
        "issue": 198,
        "status": "pass" if not errors else "fail",
        "algorithm": {
            "sentence_boundary": "spaCy sentence_index",
            "source_eligibility": "Tree-sitter normalized source regions",
            "mathematical_attachment": "sentence overlaps parser-owned math span",
            "scope_bound": "source sentence precedes target theorem",
            "english_cue_dictionary": False,
            "declaration_role_classification": False,
            "provider_or_model_call": False,
        },
        "cases": cases,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    evidence = build_evidence(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if evidence["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
