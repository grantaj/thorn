from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from thorn.linguistic import LinguisticDocument, LinguisticFrontend, LinguisticToken
from thorn.spacy_linguistic import SpacyLinguisticFrontend


@dataclass(frozen=True)
class ProjectionSegment:
    raw: str
    projected: str
    source_start: int
    source_end: int
    projected_start: int
    projected_end: int


@dataclass(frozen=True)
class CaseText:
    source: str
    projected: str
    segments: tuple[ProjectionSegment, ...]

    def source_span(self, start: int, end: int) -> tuple[int, int] | None:
        for segment in self.segments:
            if segment.projected_start <= start and end <= segment.projected_end:
                if len(segment.raw) != len(segment.projected):
                    return None
                delta = start - segment.projected_start
                return segment.source_start + delta, segment.source_start + delta + (end - start)
        return None


@dataclass(frozen=True)
class Candidate:
    role: str
    term: str
    projected_start: int
    projected_end: int
    sentence_index: int
    evidence: str
    ambiguity: str | None = None


def build_case(case: dict[str, Any]) -> CaseText:
    raw_parts: list[str] = []
    projected_parts: list[str] = []
    segments: list[ProjectionSegment] = []
    source_cursor = 0
    projected_cursor = 0
    for item in case.get("segments", [case["text"]] if "text" in case else []):
        if isinstance(item, str):
            raw = projected = item
        else:
            raw = str(item["raw"])
            projected = str(item.get("projected", item.get("token", raw)))
        raw_parts.append(raw)
        projected_parts.append(projected)
        segments.append(
            ProjectionSegment(
                raw=raw,
                projected=projected,
                source_start=source_cursor,
                source_end=source_cursor + len(raw),
                projected_start=projected_cursor,
                projected_end=projected_cursor + len(projected),
            )
        )
        source_cursor += len(raw)
        projected_cursor += len(projected)
    return CaseText("".join(raw_parts), "".join(projected_parts), tuple(segments))


def _sentences(document: LinguisticDocument) -> list[list[LinguisticToken]]:
    grouped: dict[int, list[LinguisticToken]] = defaultdict(list)
    for token in document.tokens:
        grouped[token.sentence_index].append(token)
    return [grouped[index] for index in sorted(grouped)]


def _content_before(tokens: list[LinguisticToken], boundary: int) -> LinguisticToken | None:
    candidates = [
        token
        for token in tokens
        if token.index < boundary
        and token.pos in {"ADJ", "NOUN", "PROPN"}
        and token.dependency not in {"nsubj", "nsubjpass", "pobj"}
    ]
    return candidates[-1] if candidates else None


def _subject(tokens: list[LinguisticToken]) -> LinguisticToken | None:
    subjects = [
        token
        for token in tokens
        if token.dependency in {"nsubj", "nsubjpass"} and token.pos in {"NOUN", "PROPN"}
    ]
    return subjects[-1] if subjects else None


def _mean_term(
    tokens: list[LinguisticToken], cue: LinguisticToken
) -> tuple[str, int, int] | None:
    prior = [
        token
        for token in tokens
        if token.index < cue.index and token.pos in {"ADJ", "NOUN", "PROPN"}
    ]
    modifiers = [
        token for token in prior if token.dependency in {"amod", "acomp", "attr", "oprd"}
    ]
    if modifiers:
        modifier = modifiers[-1]
        heads = [
            token
            for token in prior
            if token.index == modifier.head_index and token.pos in {"NOUN", "PROPN"}
        ]
        if heads:
            head = heads[0]
            start, end = min(modifier.start, head.start), max(modifier.end, head.end)
            pieces = sorted((modifier, head), key=lambda token: token.start)
            return " ".join(piece.text for piece in pieces), start, end
        return modifier.text, modifier.start, modifier.end
    if prior:
        token = prior[-1]
        return token.text, token.start, token.end
    return None


def _negated(tokens: list[LinguisticToken], anchor: LinguisticToken) -> bool:
    return any(
        token.dependency == "neg"
        and (token.head_index == anchor.index or abs(token.index - anchor.index) <= 3)
        for token in tokens
    ) or any(
        token.text.casefold() == "not" and abs(token.index - anchor.index) <= 3
        for token in tokens
    )


def dependency_candidates(document: LinguisticDocument) -> list[Candidate]:
    """Broad structural proposal layer: lexical-light and ambiguity-preserving."""
    out: list[Candidate] = []
    for tokens in _sentences(document):
        if not tokens:
            continue
        conditions = [
            token
            for token in tokens
            if token.text.casefold() in {"if", "when", "whenever", "provided"}
        ]
        for condition in conditions:
            term = _content_before(tokens, condition.index)
            if term is not None:
                out.append(
                    Candidate(
                        "definition",
                        term.text,
                        term.start,
                        term.end,
                        term.sentence_index,
                        "conditional-predicate",
                        "structural-only",
                    )
                )

        means = [token for token in tokens if token.lemma.casefold() == "mean"]
        for cue in means:
            term = _mean_term(tokens, cue)
            if term is not None:
                term_text, start, end = term
                out.append(
                    Candidate(
                        "definition",
                        term_text,
                        start,
                        end,
                        cue.sentence_index,
                        "preposed-mean",
                        "structural-only",
                    )
                )

        subject = _subject(tokens)
        if subject is not None:
            before_subject = [token for token in tokens if token.index < subject.index]
            universal = any(
                token.text.casefold() in {"all", "every", "each"}
                for token in tokens
                if token.head_index == subject.index
            )
            scoped = universal or any(
                token.dependency in {"advcl", "advmod", "prep", "mark"}
                for token in before_subject
            )
            copular = any(token.lemma.casefold() == "be" for token in tokens)
            if scoped and copular:
                out.append(
                    Candidate(
                        "ambient",
                        subject.text,
                        subject.start,
                        subject.end,
                        subject.sentence_index,
                        "scoped-copular-subject",
                        "scope-ambiguous",
                    )
                )
    return _dedupe(out)


_NAMED_CUES = {"call", "term", "say", "mean"}
_AMBIENT_PREFIXES = (
    "throughout",
    "in what follows",
    "henceforth",
    "unless stated otherwise",
    "unless specified otherwise",
    "for the remainder",
)


def hybrid_candidates(document: LinguisticDocument) -> list[Candidate]:
    """Dependency structure plus two deliberately small Thorn-owned lexical guards."""
    out: list[Candidate] = []
    for tokens in _sentences(document):
        if not tokens:
            continue
        sentence_start = min(token.start for token in tokens)
        sentence_end = max(token.end for token in tokens)
        sentence_text = document.text[sentence_start:sentence_end].strip().casefold()
        conditions = [
            token
            for token in tokens
            if token.text.casefold() in {"if", "when", "whenever", "provided"}
        ]
        cues = [token for token in tokens if token.lemma.casefold() in _NAMED_CUES]
        subject_words = {
            token.text.casefold()
            for token in tokens
            if token.dependency in {"nsubj", "nsubjpass"}
        }
        for condition in conditions:
            preceding_cues = [cue for cue in cues if cue.index < condition.index]
            cue = preceding_cues[-1] if preceding_cues else None
            copular_exact = (
                any(
                    token.lemma.casefold() == "be" and token.index < condition.index
                    for token in tokens
                )
                and any(token.text.casefold() == "exactly" for token in tokens)
            )
            if cue is None and not copular_exact:
                continue
            if cue is not None:
                if _negated(tokens, cue):
                    continue
                lemma = cue.lemma.casefold()
                passive = any(
                    token.dependency in {"auxpass", "nsubjpass"} for token in tokens
                )
                if lemma == "say" and "we" not in subject_words and not passive:
                    continue
                if lemma in {"call", "term"}:
                    first_person = "we" in subject_words
                    if not passive and not first_person:
                        continue
            term = _content_before(tokens, condition.index)
            if term is not None:
                out.append(
                    Candidate(
                        "definition",
                        term.text,
                        term.start,
                        term.end,
                        term.sentence_index,
                        "dependency+definition-anchor",
                    )
                )

        for cue in [token for token in cues if token.lemma.casefold() == "mean"]:
            if _negated(tokens, cue) or "we" not in subject_words:
                continue
            term = _mean_term(tokens, cue)
            if term is not None:
                term_text, start, end = term
                out.append(
                    Candidate(
                        "definition",
                        term_text,
                        start,
                        end,
                        cue.sentence_index,
                        "dependency+mean-anchor",
                    )
                )

        if sentence_text.startswith(_AMBIENT_PREFIXES):
            subject = _subject(tokens)
            if subject is not None and any(
                token.lemma.casefold() == "be" for token in tokens
            ):
                out.append(
                    Candidate(
                        "ambient",
                        subject.text,
                        subject.start,
                        subject.end,
                        subject.sentence_index,
                        "dependency+ambient-anchor",
                    )
                )
    return _dedupe(out)


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    unique: dict[tuple[str, int, int], Candidate] = {}
    for candidate in candidates:
        unique[(candidate.role, candidate.projected_start, candidate.projected_end)] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (item.projected_start, item.role, item.term.casefold()),
    )


def baseline_candidates(text: str) -> list[Candidate]:
    from thorn.project_semantic_context import (
        _AMBIENT_RE,
        _BY_MEAN_RE,
        _CALLED_RE,
        _SAID_TO_BE_RE,
        _WE_SAY_RE,
    )

    patterns = (
        ("definition", "called", _CALLED_RE),
        ("definition", "said-to-be", _SAID_TO_BE_RE),
        ("definition", "we-say", _WE_SAY_RE),
        ("definition", "by-mean", _BY_MEAN_RE),
        ("ambient", "ambient", _AMBIENT_RE),
    )
    out: list[Candidate] = []
    for role, evidence, pattern in patterns:
        for match in pattern.finditer(text):
            start, _ = match.span("term")
            term = match.group("term").strip()
            leading = len(match.group("term")) - len(match.group("term").lstrip())
            start += leading
            end = start + len(term)
            out.append(Candidate(role, term, start, end, 0, f"regex:{evidence}"))
    return _dedupe(out)


def _frontend(name: str) -> LinguisticFrontend:
    if name == "spacy":
        return SpacyLinguisticFrontend()
    raise ValueError(name)


def _evaluate_strategy(
    name: str,
    cases: list[dict[str, Any]],
    frontend: LinguisticFrontend | None,
) -> dict[str, Any]:
    tp = fp = fn = 0
    lexical_tp = lexical_total = 0
    provenance_failures = 0
    ambiguity_count = 0
    rows: list[dict[str, Any]] = []
    by_category: dict[str, Counter[str]] = defaultdict(Counter)
    transitive_ok = transitive_total = 0
    for case in cases:
        built = build_case(case)
        if name == "baseline":
            candidates = baseline_candidates(built.projected)
        else:
            assert frontend is not None
            document = frontend.parse(built.projected)
            candidates = (
                dependency_candidates(document)
                if name == "dependency"
                else hybrid_candidates(document)
            )
        expected = {
            (item["role"], item["term"].casefold()) for item in case.get("expected", [])
        }
        actual = {(item.role, item.term.casefold()) for item in candidates}
        case_tp = len(expected & actual)
        case_fp = len(actual - expected)
        case_fn = len(expected - actual)
        tp += case_tp
        fp += case_fp
        fn += case_fn
        category = str(case["category"])
        by_category[category].update(tp=case_tp, fp=case_fp, fn=case_fn)
        if case.get("lexical_challenge"):
            lexical_total += len(expected)
            lexical_tp += case_tp
        candidate_rows = []
        for candidate in candidates:
            span = built.source_span(candidate.projected_start, candidate.projected_end)
            exact = span is not None and built.source[span[0] : span[1]] == candidate.term
            if not exact:
                provenance_failures += 1
            if candidate.ambiguity is not None:
                ambiguity_count += 1
            candidate_rows.append(
                {
                    **asdict(candidate),
                    "source_span": list(span) if span else None,
                    "provenance_exact": exact,
                }
            )
        chain = case.get("transitive_terms")
        if chain:
            transitive_total += 1
            if all(("definition", str(term).casefold()) in actual for term in chain):
                transitive_ok += 1
        rows.append(
            {
                "id": case["id"],
                "expected": sorted([list(item) for item in expected]),
                "candidates": candidate_rows,
                "tp": case_tp,
                "fp": case_fp,
                "fn": case_fn,
            }
        )
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "strategy": name,
        "true_positive_candidates": tp,
        "false_positive_candidates": fp,
        "missed_candidates": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "false_authority_risk": fp,
        "lexical_challenge_recall": (
            round(lexical_tp / lexical_total, 3) if lexical_total else None
        ),
        "provenance_failures": provenance_failures,
        "ambiguity_marked_candidates": ambiguity_count,
        "transitive_cases_satisfied": f"{transitive_ok}/{transitive_total}",
        "by_category": {
            key: dict(value) for key, value in sorted(by_category.items())
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("declaration_cases.json"),
    )
    parser.add_argument("--frontend", choices=("spacy",), default="spacy")
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=("baseline", "dependency", "hybrid"),
        default=["baseline", "dependency", "hybrid"],
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = payload["cases"]
    needs_frontend = any(name != "baseline" for name in args.strategies)
    frontend = _frontend(args.frontend) if needs_frontend else None
    reports = [_evaluate_strategy(name, cases, frontend) for name in args.strategies]
    output = {
        "corpus_version": payload["version"],
        "cases": len(cases),
        "expected_candidates": sum(len(case.get("expected", [])) for case in cases),
        "strategies": reports,
        "grammar_inventory": {
            "baseline": {
                "phrase_regex_families": 5,
                "notes": "current #125 production patterns, imported unchanged",
            },
            "dependency": {
                "structural_rule_families": 3,
                "phrase_regex_families": 0,
                "notes": "conditional predicate, preposed mean, scoped copular subject",
            },
            "hybrid": {
                "structural_rule_families": 3,
                "lexical_guard_families": 2,
                "phrase_regex_families": 0,
                "notes": "definition-verb lemmas and explicit ambient-scope prefixes",
            },
        },
    }
    rendered = json.dumps(output, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 2 if any(report["provenance_failures"] for report in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
