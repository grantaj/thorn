from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from thorn.proof_skeleton import ProofSkeleton

_FORMAT = "SC1"
_REF_MARKER = "@"
_REF_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-"
_MAX_DICTIONARY_ENTRIES = len(_REF_ALPHABET)
_MAX_NGRAM_TOKENS = 20
_MIN_CANDIDATE_CHARS = 5
_MAX_CANDIDATE_CHARS = 192
_MAX_RANKED_CANDIDATES = 384

_GENERIC_LINE_RE = re.compile(r"^([HLDRC])(\d+):(.*)$")
_THEOREM_LINE_RE = re.compile(r"^T0:(.*)$")
_QUALIFIER_LINE_RE = re.compile(r"^Q(\d+)>C(\d+):(.*)$")
_EDGE_LINE_RE = re.compile(r"^E(\d+):([A-Z])(\d*)>([A-Z])(\d*):(.*)$")
_TOKEN_RE = re.compile(r"\\[A-Za-z@]+|[A-Za-z_][A-Za-z0-9_]*|\d+|\s+|.", re.DOTALL)


@dataclass(frozen=True)
class ReversibleSkeletonEncoding:
    """A deterministic, self-contained reversible skeleton wire encoding."""

    wire_text: str
    dictionary: tuple[str, ...]
    skeleton_count: int

    @property
    def characters(self) -> int:
        return len(self.wire_text)

    @property
    def utf8_bytes(self) -> int:
        return len(self.wire_text.encode("utf-8"))


def _expect_counter(counters: dict[str, int], kind: str, observed: int) -> None:
    expected = counters.get(kind, 0) + 1
    if observed != expected:
        raise ValueError(
            f"proof-skeleton {kind} address sequence is not canonical: "
            f"expected {kind}{expected}, got {kind}{observed}"
        )
    counters[kind] = observed


def _encode_endpoint(kind: str, number: str) -> str:
    if kind == "C" and number:
        return number
    if kind == "R" and number:
        return f"r{number}"
    if kind == "X" and not number:
        return "x"
    suffix = number if number else ""
    return f"{kind.lower()}{suffix}"


def _decode_endpoint(text: str) -> str:
    if text.isdigit():
        return f"C{text}"
    if text == "x":
        return "X"
    if text.startswith("r") and text[1:].isdigit():
        return f"R{text[1:]}"
    if text and text[0].isalpha():
        return f"{text[0].upper()}{text[1:]}"
    raise ValueError(f"invalid compressed skeleton endpoint {text!r}")


def _syntax_encode_lines(lines: Iterable[str]) -> list[str]:
    counters: dict[str, int] = {}
    encoded: list[str] = []

    for line in lines:
        theorem_match = _THEOREM_LINE_RE.fullmatch(line)
        if theorem_match is not None:
            if counters.get("T", 0) != 0:
                raise ValueError("proof skeleton contains more than one T0 line")
            counters["T"] = 1
            encoded.append(f"T{theorem_match.group(1)}")
            continue

        qualifier_match = _QUALIFIER_LINE_RE.fullmatch(line)
        if qualifier_match is not None:
            index = int(qualifier_match.group(1))
            _expect_counter(counters, "Q", index)
            target = qualifier_match.group(2)
            payload = qualifier_match.group(3)
            encoded.append(f"Q{target}:{payload}")
            continue

        edge_match = _EDGE_LINE_RE.fullmatch(line)
        if edge_match is not None:
            index = int(edge_match.group(1))
            _expect_counter(counters, "E", index)
            source = _encode_endpoint(edge_match.group(2), edge_match.group(3))
            target = _encode_endpoint(edge_match.group(4), edge_match.group(5))
            suffix = edge_match.group(6)
            encoded.append(f"E{source}>{target}:{suffix}")
            continue

        generic_match = _GENERIC_LINE_RE.fullmatch(line)
        if generic_match is not None:
            kind = generic_match.group(1)
            index = int(generic_match.group(2))
            _expect_counter(counters, kind, index)
            encoded.append(f"{kind}{generic_match.group(3)}")
            continue

        raise ValueError(f"unsupported proof-skeleton line {line!r}")

    if counters.get("T", 0) != 1:
        raise ValueError("proof skeleton must contain exactly one T0 line")
    return encoded


def _syntax_decode_lines(lines: Iterable[str]) -> list[str]:
    counters: dict[str, int] = {}
    decoded: list[str] = []

    for line in lines:
        if not line:
            raise ValueError("compressed proof-skeleton line may not be empty")
        kind = line[0]
        body = line[1:]

        if kind == "T":
            if counters.get("T", 0) != 0:
                raise ValueError("compressed proof skeleton contains more than one theorem line")
            counters["T"] = 1
            decoded.append(f"T0:{body}")
            continue

        if kind == "Q":
            target_text, separator, payload = body.partition(":")
            if not separator or not target_text.isdigit():
                raise ValueError(f"invalid compressed qualifier line {line!r}")
            index = counters.get("Q", 0) + 1
            counters["Q"] = index
            decoded.append(f"Q{index}>C{target_text}:{payload}")
            continue

        if kind == "E":
            endpoints, separator, suffix = body.partition(":")
            if not separator:
                raise ValueError(f"invalid compressed edge line {line!r}")
            source_text, arrow, target_text = endpoints.partition(">")
            if not arrow:
                raise ValueError(f"invalid compressed edge endpoints {line!r}")
            index = counters.get("E", 0) + 1
            counters["E"] = index
            source = _decode_endpoint(source_text)
            target = _decode_endpoint(target_text)
            decoded.append(f"E{index}:{source}>{target}:{suffix}")
            continue

        if kind in {"H", "L", "D", "R", "C"}:
            index = counters.get(kind, 0) + 1
            counters[kind] = index
            decoded.append(f"{kind}{index}:{body}")
            continue

        raise ValueError(f"unknown compressed proof-skeleton line kind {kind!r}")

    if counters.get("T", 0) != 1:
        raise ValueError("compressed proof skeleton must contain exactly one theorem line")
    return decoded


def _candidate_counts(skeleton_lines: list[list[str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for lines in skeleton_lines:
        for line in lines:
            tail = line[1:]
            if len(tail) >= _MIN_CANDIDATE_CHARS:
                counts[tail] += 1

            tokens = _TOKEN_RE.findall(tail)
            for start in range(len(tokens)):
                fragment = ""
                for end in range(start, min(len(tokens), start + _MAX_NGRAM_TOKENS)):
                    fragment += tokens[end]
                    length = len(fragment)
                    if length > _MAX_CANDIDATE_CHARS:
                        break
                    if length >= _MIN_CANDIDATE_CHARS:
                        counts[fragment] += 1
    return counts


def _ref(index: int) -> str:
    if not 0 <= index < len(_REF_ALPHABET):
        raise ValueError(f"dictionary reference index {index} is out of range")
    return f"{_REF_MARKER}{_REF_ALPHABET[index]}"


def _escape_literal(text: str) -> str:
    return text.replace(_REF_MARKER, _REF_MARKER * 2)


def _encode_tail(text: str, dictionary: tuple[str, ...]) -> str:
    if not dictionary:
        return _escape_literal(text)

    by_first: dict[str, list[tuple[int, str]]] = {}
    for index, value in enumerate(dictionary):
        if value:
            by_first.setdefault(value[0], []).append((index, value))
    for candidates in by_first.values():
        candidates.sort(key=lambda item: (-len(item[1]), item[0]))

    output: list[str] = []
    position = 0
    while position < len(text):
        matches = by_first.get(text[position], [])
        match = next(
            (
                (index, value)
                for index, value in matches
                if text.startswith(value, position)
            ),
            None,
        )
        if match is not None:
            index, value = match
            output.append(_ref(index))
            position += len(value)
            continue

        char = text[position]
        output.append("@@" if char == "@" else char)
        position += 1
    return "".join(output)


def _decode_tail(text: str, dictionary: tuple[str, ...]) -> str:
    output: list[str] = []
    position = 0
    while position < len(text):
        if text[position] != "@":
            output.append(text[position])
            position += 1
            continue
        if position + 1 >= len(text):
            raise ValueError("truncated dictionary reference at end of line")
        code = text[position + 1]
        if code == "@":
            output.append("@")
            position += 2
            continue
        try:
            index = _REF_ALPHABET.index(code)
        except ValueError as exc:
            raise ValueError(f"invalid dictionary reference code {code!r}") from exc
        if index >= len(dictionary):
            raise ValueError(f"dictionary reference {_ref(index)!r} is out of range")
        output.append(dictionary[index])
        position += 2
    return "".join(output)


def _apply_dictionary(
    syntax_lines: list[list[str]], dictionary: tuple[str, ...]
) -> list[list[str]]:
    return [
        [f"{line[0]}{_encode_tail(line[1:], dictionary)}" for line in lines]
        for lines in syntax_lines
    ]


def _render_wire(
    syntax_lines: list[list[str]], dictionary: tuple[str, ...]
) -> str:
    encoded_lines = _apply_dictionary(syntax_lines, dictionary)
    wire: list[str] = [_FORMAT, f"D{len(dictionary)}"]
    for index, value in enumerate(dictionary):
        wire.append(_encode_tail(value, dictionary[:index]))
    wire.append("")
    for skeleton_index, lines in enumerate(encoded_lines):
        if skeleton_index:
            wire.append("")
        wire.extend(lines)
    return "\n".join(wire) + "\n"


def _wire_bytes(syntax_lines: list[list[str]], dictionary: tuple[str, ...]) -> int:
    return len(_render_wire(syntax_lines, dictionary).encode("utf-8"))


def _select_dictionary(syntax_lines: list[list[str]]) -> tuple[str, ...]:
    counts = _candidate_counts(syntax_lines)
    ranked: list[tuple[int, int, str]] = []
    for candidate, count in counts.items():
        if count < 2:
            continue
        candidate_bytes = len(candidate.encode("utf-8"))
        estimated = count * (candidate_bytes - 2) - (candidate_bytes + 1)
        if estimated > 0:
            ranked.append((estimated, candidate_bytes, candidate))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))

    selected: tuple[str, ...] = ()
    current_bytes = _wire_bytes(syntax_lines, selected)
    for _, _, candidate in ranked[:_MAX_RANKED_CANDIDATES]:
        if len(selected) >= _MAX_DICTIONARY_ENTRIES:
            break
        trial = (*selected, candidate)
        trial_bytes = _wire_bytes(syntax_lines, trial)
        if trial_bytes < current_bytes:
            selected = trial
            current_bytes = trial_bytes
    return selected


def encode_skeleton_bundle(
    skeletons: Iterable[ProofSkeleton], *, use_dictionary: bool = True
) -> ReversibleSkeletonEncoding:
    """Encode proof skeletons into a self-contained, exactly reversible text bundle."""

    skeleton_list = list(skeletons)
    if not skeleton_list:
        raise ValueError("at least one proof skeleton is required")
    syntax_lines = [_syntax_encode_lines(skeleton.lines) for skeleton in skeleton_list]
    dictionary = _select_dictionary(syntax_lines) if use_dictionary else ()
    wire_text = _render_wire(syntax_lines, dictionary)
    decoded = decode_skeleton_bundle(wire_text)
    expected = [skeleton.render_initial() for skeleton in skeleton_list]
    if decoded != expected:
        raise AssertionError("reversible skeleton codec failed its exact round-trip invariant")
    return ReversibleSkeletonEncoding(
        wire_text=wire_text,
        dictionary=dictionary,
        skeleton_count=len(skeleton_list),
    )


def decode_skeleton_bundle(wire_text: str) -> list[str]:
    """Decode a complete SC1 wire bundle back to exact initial skeleton strings."""

    if not wire_text.endswith("\n"):
        raise ValueError("compressed skeleton bundle must end with a newline")
    lines = wire_text[:-1].split("\n")
    cursor = 0

    def take() -> str:
        nonlocal cursor
        if cursor >= len(lines):
            raise ValueError("truncated compressed skeleton bundle")
        value = lines[cursor]
        cursor += 1
        return value

    if take() != _FORMAT:
        raise ValueError(f"unsupported compressed skeleton format; expected {_FORMAT}")

    dictionary_header = take()
    if not dictionary_header.startswith("D") or not dictionary_header[1:].isdigit():
        raise ValueError("invalid compressed skeleton dictionary header")
    dictionary_count = int(dictionary_header[1:])
    if dictionary_count > _MAX_DICTIONARY_ENTRIES:
        raise ValueError("compressed skeleton dictionary exceeds format capacity")

    dictionary_values: list[str] = []
    for _ in range(dictionary_count):
        encoded_entry = take()
        entry = _decode_tail(encoded_entry, tuple(dictionary_values))
        if not entry:
            raise ValueError("compressed skeleton dictionary entries may not be empty")
        dictionary_values.append(entry)
    dictionary = tuple(dictionary_values)

    if take() != "":
        raise ValueError("compressed skeleton dictionary must be followed by a blank line")
    if cursor >= len(lines):
        raise ValueError("compressed skeleton bundle must contain at least one skeleton")

    blocks: list[list[str]] = []
    block: list[str] = []
    for line in lines[cursor:]:
        if line == "":
            if not block:
                raise ValueError("compressed skeleton bundle contains an empty skeleton")
            blocks.append(block)
            block = []
            continue
        block.append(line)
    if not block:
        raise ValueError("compressed skeleton bundle may not end with an empty skeleton")
    blocks.append(block)

    decoded: list[str] = []
    for encoded_lines in blocks:
        syntax_lines = [
            f"{line[0]}{_decode_tail(line[1:], dictionary)}"
            if line
            else line
            for line in encoded_lines
        ]
        initial_lines = _syntax_decode_lines(syntax_lines)
        decoded.append("\n".join(initial_lines) + "\n")
    return decoded
