from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thorn.linguistic import LinguisticDocument, LinguisticToken
from thorn.spacy_linguistic import SpacyLinguisticFrontend

# Frozen before the first semantic measurement for #215. These are deliberately
# graph-semantic operator classes, not whole-sentence templates. Do not expand
# them after inspecting results from the frozen corpora.
INTRODUCE = frozenset({"assume", "suppose", "fix", "let", "define", "set"})
NAME = frozenset({"call", "term", "mean", "say"})
SUPPORT_VERBS = frozenset({"use", "apply", "invoke", "follow"})
SUPPORT_NOUNS = frozenset({"consequence"})
CONDITIONS = frozenset({"if", "when", "whenever", "provided"})
HYPOTHETICAL = frozenset({"would", "could", "might"})
PLACEHOLDER_RE = re.compile(r"\bTHORN(?:MATH|REF)\d+\b")


@dataclass(frozen=True)
class Segment:
    raw: str
    projected: str
    source_start: int
    projected_start: int


@dataclass(frozen=True)
class CaseText:
    source: str
    projected: str
    segments: tuple[Segment, ...]

    def source_span(self, start: int, end: int) -> tuple[int, int] | None:
        for segment in self.segments:
            projected_end = segment.projected_start + len(segment.projected)
            if not (segment.projected_start <= start and end <= projected_end):
                continue
            if start == segment.projected_start and end == projected_end:
                return segment.source_start, segment.source_start + len(segment.raw)
            if len(segment.raw) != len(segment.projected):
                return None
            delta = start - segment.projected_start
            source_start = segment.source_start + delta
            return source_start, source_start + (end - start)
        return None


@dataclass(frozen=True)
class Grounding:
    text: str
    start: int
    end: int
    source: tuple[int, int] | None

    @property
    def exact(self) -> bool:
        return self.source is not None


@dataclass(frozen=True)
class Frame:
    operation: str
    rule: str
    sentence: int
    bind: Grounding | None = None
    payload: tuple[Grounding, ...] = ()
    prerequisites: tuple[Grounding, ...] = ()
    evidence: tuple[Grounding, ...] = ()

    @property
    def exact(self) -> bool:
        parts = [*self.payload, *self.prerequisites, *self.evidence]
        if self.bind is not None:
            parts.append(self.bind)
        return bool(parts) and all(part.exact for part in parts)


def build_case(raw_case: dict[str, Any]) -> CaseText:
    items = raw_case["segments"] if "segments" in raw_case else [raw_case["text"]]
    source_parts: list[str] = []
    projected_parts: list[str] = []
    segments: list[Segment] = []
    source_cursor = projected_cursor = 0
    for item in items:
        if isinstance(item, str):
            raw = projected = item
        else:
            raw = str(item["raw"])
            projected = str(item.get("projected", item.get("token", raw)))
        segments.append(Segment(raw, projected, source_cursor, projected_cursor))
        source_parts.append(raw)
        projected_parts.append(projected)
        source_cursor += len(raw)
        projected_cursor += len(projected)
    return CaseText("".join(source_parts), "".join(projected_parts), tuple(segments))


def sentence_groups(document: LinguisticDocument) -> list[list[LinguisticToken]]:
    grouped: dict[int, list[LinguisticToken]] = defaultdict(list)
    for token in document.tokens:
        grouped[token.sentence_index].append(token)
    return [grouped[index] for index in sorted(grouped)]


def grounding(case: CaseText, text: str, start: int, end: int) -> Grounding:
    return Grounding(text, start, end, case.source_span(start, end))


def placeholders(case: CaseText, tokens: list[LinguisticToken], prefix: str) -> list[Grounding]:
    start = min(token.start for token in tokens)
    end = max(token.end for token in tokens)
    return [
        grounding(case, match.group(), match.start(), match.end())
        for match in PLACEHOLDER_RE.finditer(case.projected, start, end)
        if match.group().startswith(prefix)
    ]


def children(tokens: list[LinguisticToken], index: int) -> list[LinguisticToken]:
    return [token for token in tokens if token.head_index == index and token.index != index]


def subjects(tokens: list[LinguisticToken], anchor: LinguisticToken) -> list[LinguisticToken]:
    return [
        token
        for token in children(tokens, anchor.index)
        if token.dependency in {"nsubj", "nsubjpass"}
    ]


def passive(tokens: list[LinguisticToken], anchor: LinguisticToken) -> bool:
    return any(token.dependency == "nsubjpass" for token in subjects(tokens, anchor)) or any(
        token.dependency == "auxpass" for token in children(tokens, anchor.index)
    )


def ancestors(tokens: list[LinguisticToken], token: LinguisticToken) -> list[LinguisticToken]:
    by_index = {item.index: item for item in tokens}
    result = [token]
    seen = {token.index}
    while token.head_index in by_index and token.head_index not in seen:
        token = by_index[token.head_index]
        result.append(token)
        seen.add(token.index)
    return result


def token_at(tokens: list[LinguisticToken], item: Grounding) -> LinguisticToken | None:
    return next(
        (token for token in tokens if token.start < item.end and item.start < token.end),
        None,
    )


def quote_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for left, right in (("“", "”"), ("‘", "’"), ('"', '"')):
        cursor = 0
        while (start := text.find(left, cursor)) >= 0:
            end = text.find(right, start + len(left))
            if end < 0:
                break
            ranges.append((start, end + len(right)))
            cursor = end + len(right)
    return ranges


def quoted(ranges: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(left <= start and end <= right for left, right in ranges)


def blocked(tokens: list[LinguisticToken]) -> bool:
    return any(
        token.dependency == "neg" or token.lemma.casefold() == "not" for token in tokens
    )


def authorial(tokens: list[LinguisticToken], anchor: LinguisticToken, *, naming: bool) -> bool:
    if passive(tokens, anchor):
        return True
    found = subjects(tokens, anchor)
    if naming and anchor.lemma.casefold() == "say":
        return False
    if not naming:
        return not found or all(token.lemma.casefold() == "we" for token in found)
    return bool(found) and all(token.lemma.casefold() == "we" for token in found)


def condition_after(
    tokens: list[LinguisticToken], anchor: LinguisticToken
) -> LinguisticToken | None:
    found = [
        token
        for token in tokens
        if token.start > anchor.end and token.text.casefold() in CONDITIONS
    ]
    return min(found, key=lambda token: token.start) if found else None


def naming_term(
    tokens: list[LinguisticToken], anchor: LinguisticToken, condition: LinguisticToken | None
) -> tuple[str, int, int] | None:
    if condition is None:
        candidates = [
            token
            for token in tokens
            if token.start < anchor.start and token.pos in {"NOUN", "PROPN"}
        ]
        if not candidates:
            return None
        head = candidates[-1]
        modifiers = [
            token
            for token in children(tokens, head.index)
            if token.dependency in {"amod", "compound"}
        ]
        parts = sorted([*modifiers, head], key=lambda token: token.start)
        return " ".join(token.text for token in parts), parts[0].start, parts[-1].end

    candidates = [
        token
        for token in tokens
        if anchor.end <= token.start < condition.start
        and token.pos in {"ADJ", "NOUN", "PROPN"}
        and token.dependency not in {"nsubj", "nsubjpass", "dobj", "pobj"}
    ]
    if not candidates:
        return None
    token = candidates[-1]
    return token.text, token.start, token.end


def declaration_frames(
    case: CaseText,
    tokens: list[LinguisticToken],
    quotes: list[tuple[int, int]],
) -> list[Frame]:
    if blocked(tokens):
        return []
    maths = placeholders(case, tokens, "THORNMATH")
    result: list[Frame] = []

    for anchor in tokens:
        lemma = anchor.lemma.casefold()
        if lemma not in INTRODUCE or quoted(quotes, anchor.start, anchor.end):
            continue
        if not authorial(tokens, anchor, naming=False) or not maths:
            continue
        bind = maths[0] if lemma in {"fix", "let", "define", "set"} else None
        payload = tuple(maths[1:] if bind is not None and len(maths) > 1 else maths)
        if payload:
            result.append(
                Frame(
                    "declare",
                    "introduction-operator",
                    anchor.sentence_index,
                    bind=bind,
                    payload=payload,
                    evidence=(grounding(case, anchor.text, anchor.start, anchor.end),),
                )
            )

    for anchor in tokens:
        lemma = anchor.lemma.casefold()
        if lemma not in NAME or quoted(quotes, anchor.start, anchor.end):
            continue
        if not authorial(tokens, anchor, naming=True):
            continue
        condition = None if lemma == "mean" else condition_after(tokens, anchor)
        if lemma != "mean" and condition is None:
            continue
        term = naming_term(tokens, anchor, condition)
        payload = [
            item
            for item in maths
            if item.start > (anchor.end if condition is None else condition.end)
        ]
        if term is None or not payload:
            continue
        term_text, term_start, term_end = term
        evidence = [grounding(case, anchor.text, anchor.start, anchor.end)]
        if condition is not None:
            evidence.append(grounding(case, condition.text, condition.start, condition.end))
        result.append(
            Frame(
                "declare",
                "naming-operator",
                anchor.sentence_index,
                bind=grounding(case, term_text, term_start, term_end),
                payload=tuple(payload),
                evidence=tuple(evidence),
            )
        )

    conditions = [token for token in tokens if token.text.casefold() in CONDITIONS]
    exacts = [token for token in tokens if token.lemma.casefold() == "exactly"]
    if conditions and exacts:
        condition = conditions[0]
        candidates = [
            token
            for token in tokens
            if token.start < condition.start
            and token.pos in {"ADJ", "NOUN", "PROPN"}
            and token.dependency not in {"nsubj", "nsubjpass", "dobj", "pobj"}
        ]
        payload = [item for item in maths if item.start > condition.end]
        if candidates and payload:
            term = candidates[-1]
            result.append(
                Frame(
                    "declare",
                    "exact-biconditional",
                    condition.sentence_index,
                    bind=grounding(case, term.text, term.start, term.end),
                    payload=tuple(payload),
                    evidence=(
                        grounding(case, exacts[0].text, exacts[0].start, exacts[0].end),
                        grounding(case, condition.text, condition.start, condition.end),
                    ),
                )
            )
    return result


def requirement_frames(
    case: CaseText,
    tokens: list[LinguisticToken],
    quotes: list[tuple[int, int]],
) -> list[Frame]:
    refs = placeholders(case, tokens, "THORNREF")
    maths = placeholders(case, tokens, "THORNMATH")
    if not refs or blocked(tokens) or any(
        token.lemma.casefold() in HYPOTHETICAL for token in tokens
    ):
        return []

    grouped: dict[int, tuple[LinguisticToken, list[Grounding]]] = {}
    for ref in refs:
        if quoted(quotes, ref.start, ref.end):
            continue
        ref_token = token_at(tokens, ref)
        if ref_token is None:
            continue
        operator = next(
            (
                token
                for token in ancestors(tokens, ref_token)
                if token.lemma.casefold() in SUPPORT_VERBS | SUPPORT_NOUNS
            ),
            None,
        )
        if operator is None or quoted(quotes, operator.start, operator.end):
            continue
        lemma = operator.lemma.casefold()
        if not maths and lemma not in SUPPORT_NOUNS:
            continue
        if lemma not in {"follow"} | SUPPORT_NOUNS:
            found_subjects = subjects(tokens, operator)
            if found_subjects and not passive(tokens, operator) and any(
                token.lemma.casefold() != "we" for token in found_subjects
            ):
                continue
        grouped.setdefault(operator.index, (operator, []))[1].append(ref)

    return [
        Frame(
            "require",
            "support-operator",
            operator.sentence_index,
            prerequisites=tuple(sorted(items, key=lambda item: item.start)),
            evidence=(grounding(case, operator.text, operator.start, operator.end),),
        )
        for operator, items in grouped.values()
    ]


def compile_effects(case: CaseText, document: LinguisticDocument) -> list[Frame]:
    quotes = quote_ranges(case.projected)
    result: list[Frame] = []
    for tokens in sentence_groups(document):
        result.extend(declaration_frames(case, tokens, quotes))
        result.extend(requirement_frames(case, tokens, quotes))
    return result


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def declaration_metrics(path: Path, frontend: SpacyLinguisticFrontend) -> dict[str, Any]:
    cases = json.loads(path.read_text())["cases"]
    tp = fp = fn = unsafe = negatives = lexical_tp = lexical_total = grounded = 0
    records: list[dict[str, Any]] = []
    for raw in cases:
        case = build_case(raw)
        frames = compile_effects(case, frontend.parse(case.projected))
        actual_frames = [
            frame for frame in frames if frame.operation == "declare" and frame.bind is not None
        ]
        expected = [" ".join(item["term"].casefold().split()) for item in raw.get("expected", [])]
        actual = [
            " ".join(frame.bind.text.casefold().split())
            for frame in actual_frames
            if frame.bind is not None
        ]
        matched = 0
        remaining = list(enumerate(actual))
        for term in expected:
            hit = next(((index, value) for index, value in remaining if value == term), None)
            if hit is None:
                continue
            matched += 1
            grounded += int(actual_frames[hit[0]].exact)
            remaining.remove(hit)
        tp += matched
        fp += len(actual) - matched
        fn += len(expected) - matched
        if raw.get("family") == "negative":
            negatives += 1
            unsafe += int(bool(actual))
        if raw.get("lexical_challenge"):
            lexical_tp += matched
            lexical_total += len(expected)
        records.append(
            {
                "id": raw["id"],
                "expected": expected,
                "actual": actual,
                "rules": [frame.rule for frame in frames],
            }
        )
    return {
        "cases": len(cases),
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "unsafe_negative_cases": unsafe,
        "negative_cases": negatives,
        "false_authority_case_rate": ratio(unsafe, negatives),
        "lexical_challenge_recall": ratio(lexical_tp, lexical_total),
        "exact_grounding_rate_on_matched": ratio(grounded, tp),
        "records": records,
    }


def effect_metrics(path: Path, frontend: SpacyLinguisticFrontend) -> dict[str, Any]:
    cases = json.loads(path.read_text())["cases"]
    require_tp = require_fp = require_fn = endpoint_exact = 0
    declare_total = declare_seen = declare_payload_exact = 0
    visibility_total = visibility_exact = unsafe = negatives = 0
    baseline_tp = baseline_fp = 0
    records: list[dict[str, Any]] = []
    for raw in cases:
        case = build_case(raw)
        frames = compile_effects(case, frontend.parse(case.projected))
        expected = set(raw["expected_effects"])
        operations = {frame.operation for frame in frames}
        want_require = "require" in expected
        got_require = "require" in operations
        require_tp += int(want_require and got_require)
        require_fp += int(not want_require and got_require)
        require_fn += int(want_require and not got_require)

        resolved_ref_baseline = "THORNREF" in case.projected
        baseline_tp += int(want_require and resolved_ref_baseline)
        baseline_fp += int(not want_require and resolved_ref_baseline)

        if want_require:
            actual_refs = {
                item.text
                for frame in frames
                if frame.operation == "require"
                for item in frame.prerequisites
            }
            endpoint_exact += int(actual_refs == set(raw.get("expected_refs", [])))
        if "declare" in expected:
            declare_total += 1
            declarations = [frame for frame in frames if frame.operation == "declare"]
            declare_seen += int(bool(declarations))
            declare_payload_exact += int(
                bool(declarations)
                and all(
                    frame.payload and all(item.exact for item in frame.payload)
                    for frame in declarations
                )
            )
        if "visibility" in expected:
            visibility_total += 1
            # Deliberately unsupported by the first structural compiler. We record
            # the gap instead of teaching the screen a phrase after seeing heldouts.
            visibility_exact += 0
        if not expected:
            negatives += 1
            unsafe += int(bool(operations))
        records.append(
            {
                "id": raw["id"],
                "expected": sorted(expected),
                "actual": sorted(operations),
                "prerequisites": [
                    item.text
                    for frame in frames
                    if frame.operation == "require"
                    for item in frame.prerequisites
                ],
                "rules": [frame.rule for frame in frames],
                "calculus_pressure": raw.get("calculus_pressure"),
            }
        )
    return {
        "cases": len(cases),
        "require_precision": ratio(require_tp, require_tp + require_fp),
        "require_recall": ratio(require_tp, require_tp + require_fn),
        "require_tp": require_tp,
        "require_fp": require_fp,
        "require_fn": require_fn,
        "require_endpoint_exact_rate": ratio(endpoint_exact, require_tp + require_fn),
        "declare_recall": ratio(declare_seen, declare_total),
        "declare_payload_exact_rate": ratio(declare_payload_exact, declare_total),
        "visibility_exact_grounding_rate": ratio(visibility_exact, visibility_total),
        "status_supported": False,
        "unsafe_negative_cases": unsafe,
        "negative_cases": negatives,
        "false_authority_case_rate": ratio(unsafe, negatives),
        "resolved_reference_implies_require_baseline": {
            "precision": ratio(baseline_tp, baseline_tp + baseline_fp),
            "recall": 1.0,
            "tp": baseline_tp,
            "fp": baseline_fp,
        },
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--declarations",
        type=Path,
        default=Path("research/semantic-parser-bakeoff/declaration_cases.json"),
    )
    parser.add_argument(
        "--effects",
        type=Path,
        default=Path("research/dependency-semantics/effect_cases.json"),
    )
    parser.add_argument("--model", default="en_core_web_sm")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    frontend = SpacyLinguisticFrontend(model_name=args.model)
    result = {
        "version": 1,
        "model": args.model,
        "operator_inventory": {
            "introduce": sorted(INTRODUCE),
            "name": sorted(NAME),
            "support_verbs": sorted(SUPPORT_VERBS),
            "support_nouns": sorted(SUPPORT_NOUNS),
            "conditions": sorted(CONDITIONS),
            "hypothetical_auxiliaries": sorted(HYPOTHETICAL),
        },
        "declarations": declaration_metrics(args.declarations, frontend),
        "effects": effect_metrics(args.effects, frontend),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
