from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

_PLACEHOLDER_RE = re.compile(r"THORN[A-Z]+\d+")


@dataclass(frozen=True)
class Token:
    text: str
    lemma: str
    pos: str
    dep: str
    head: int
    sentence: int


class DependencyCandidate(Protocol):
    name: str

    def parse(self, text: str) -> list[Token]: ...


class SpacyCandidate:
    name = "spacy"

    def __init__(self) -> None:
        import spacy

        self._nlp = spacy.load("en_core_web_sm")

    def parse(self, text: str) -> list[Token]:
        doc = self._nlp(text)
        sentence_by_index: dict[int, int] = {}
        for sentence_index, sentence in enumerate(doc.sents):
            for token in sentence:
                sentence_by_index[token.i] = sentence_index
        return [
            Token(
                text=token.text,
                lemma=token.lemma_,
                pos=token.pos_,
                dep=token.dep_,
                head=token.head.i,
                sentence=sentence_by_index[token.i],
            )
            for token in doc
        ]


class StanzaCandidate:
    name = "stanza"

    def __init__(self) -> None:
        import stanza

        self._nlp = stanza.Pipeline(
            "en",
            processors="tokenize,pos,lemma,depparse",
            use_gpu=False,
            verbose=False,
        )

    def parse(self, text: str) -> list[Token]:
        document = self._nlp(text)
        tokens: list[Token] = []
        offset = 0
        for sentence_index, sentence in enumerate(document.sentences):
            for word in sentence.words:
                local_index = int(word.id) - 1
                head = offset + int(word.head) - 1 if int(word.head) > 0 else offset + local_index
                tokens.append(
                    Token(
                        text=word.text,
                        lemma=word.lemma or word.text,
                        pos=word.upos or "",
                        dep=word.deprel or "",
                        head=head,
                        sentence=sentence_index,
                    )
                )
            offset += len(sentence.words)
        return tokens


def _candidate(name: str) -> DependencyCandidate:
    if name == "spacy":
        return SpacyCandidate()
    if name == "stanza":
        return StanzaCandidate()
    raise ValueError(name)


def _placeholder_indices(tokens: list[Token], text: str) -> dict[str, int]:
    expected = set(_PLACEHOLDER_RE.findall(text))
    return {token.text: index for index, token in enumerate(tokens) if token.text in expected}


def _path_signature(tokens: list[Token], index: int) -> str:
    """Dependency-only signature: deliberately excludes surface lexemes."""

    signature: list[str] = []
    seen: set[int] = set()
    current = index
    while current not in seen and 0 <= current < len(tokens):
        seen.add(current)
        token = tokens[current]
        signature.append(f"{token.pos}:{token.dep}")
        if token.head == current or token.head < 0 or token.head >= len(tokens):
            break
        if tokens[token.head].sentence != token.sentence:
            break
        current = token.head
    return ">".join(signature)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=("spacy", "stanza"), required=True)
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    candidate = _candidate(args.candidate)
    started = time.perf_counter()
    rows: list[dict[str, object]] = []
    missing_placeholders = 0

    for case in payload["cases"]:
        text = str(case["text"])
        tokens = candidate.parse(text)
        positions = _placeholder_indices(tokens, text)
        expected_placeholders = set(_PLACEHOLDER_RE.findall(text))
        missing = sorted(expected_placeholders - positions.keys())
        missing_placeholders += len(missing)
        expected = case["expected"]
        source = expected.get("source")
        target = expected.get("target")
        rows.append(
            {
                "id": case["id"],
                "task": case["task"],
                "family": case["family"],
                "relation": expected["relation"],
                "missing_placeholders": missing,
                "source_signature": (
                    _path_signature(tokens, positions[source])
                    if isinstance(source, str) and source in positions
                    else None
                ),
                "target_signature": (
                    _path_signature(tokens, positions[target])
                    if isinstance(target, str) and target in positions
                    else None
                ),
                "tokens": [asdict(token) for token in tokens],
            }
        )

    task_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        task_rows[str(row["task"])].append(row)

    metrics: dict[str, object] = {}
    for task, items in sorted(task_rows.items()):
        positives = [item for item in items if item["family"] == "positive"]
        negatives = [item for item in items if item["family"] == "negative"]
        positive_signatures = {
            (item["source_signature"], item["target_signature"]) for item in positives
        }
        negative_signatures = {
            (item["source_signature"], item["target_signature"]) for item in negatives
        }
        metrics[task] = {
            "positive_cases": len(positives),
            "negative_cases": len(negatives),
            "distinct_positive_dependency_templates": len(positive_signatures),
            "positive_template_ratio": (
                round(len(positive_signatures) / len(positives), 3) if positives else None
            ),
            "positive_negative_template_collisions": len(
                positive_signatures & negative_signatures
            ),
        }

    report = {
        "candidate": candidate.name,
        "cases": len(rows),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "missing_placeholder_tokens": missing_placeholders,
        "metrics": metrics,
        "rows": rows,
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if missing_placeholders == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
