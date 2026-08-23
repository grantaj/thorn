from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from thorn.frontend import FrontendRegionKind
from thorn.frontends.tree_sitter import TreeSitterLatexFrontend
from thorn.spacy_linguistic import SpacyLinguisticFrontend
from tree_sitter_language_pack import get_parser


_MATH_TYPES = {"inline_formula", "displayed_equation", "math_environment"}
_INELIGIBLE_KINDS = {
    FrontendRegionKind.PREAMBLE,
    FrontendRegionKind.NON_DOCUMENT,
    FrontendRegionKind.COMMENT,
    FrontendRegionKind.VERBATIM,
    FrontendRegionKind.LISTING,
    FrontendRegionKind.MINTED,
    FrontendRegionKind.OPAQUE,
}


def _walk(node: Any) -> list[Any]:
    nodes: list[Any] = []
    stack = [node]
    while stack:
        current = stack.pop()
        nodes.append(current)
        stack.extend(reversed(list(current.children)))
    return nodes


def _mask(characters: list[str], start: int, end: int) -> None:
    for index in range(max(0, start), min(len(characters), end)):
        if characters[index] != "\n":
            characters[index] = " "


def _byte_to_char_map(text: str) -> dict[int, int]:
    mapping = {0: 0}
    byte_offset = 0
    for index, char in enumerate(text, start=1):
        byte_offset += len(char.encode("utf-8"))
        mapping[byte_offset] = index
    return mapping


def _char_span(mapping: dict[int, int], node: Any) -> tuple[int, int]:
    return mapping[int(node.start_byte)], mapping[int(node.end_byte)]


def _terminal_math_punctuation(source: bytes, node: Any) -> int | None:
    """Return the byte offset of CST-owned terminal sentence punctuation, if any."""

    candidate: int | None = None
    for descendant in _walk(node):
        if descendant.type not in {"word", "text"} or descendant.children:
            continue
        raw = source[int(descendant.start_byte) : int(descendant.end_byte)].decode("utf-8")
        if raw and raw[-1] in ".!?":
            candidate = int(descendant.end_byte) - len(raw[-1].encode("utf-8"))
    return candidate


def _structural_segmentation_projection(path: Path) -> tuple[str, str]:
    frontend = TreeSitterLatexFrontend()
    parsed = frontend.parse_project(path)
    file = parsed.file(path)
    if parsed.diagnostics or not file.regions_complete:
        raise RuntimeError("structural projection spike requires a complete Tree-sitter parse")

    text = file.raw
    characters = list(text)
    mapping = _byte_to_char_map(text)
    source = text.encode("utf-8")
    tree = get_parser("latex").parse(source)
    nodes = _walk(tree.root_node)

    # Existing normalized source roles own document eligibility.
    for region in file.regions:
        if region.kind in _INELIGIBLE_KINDS:
            _mask(characters, region.span.start_offset, region.span.end_offset)

    # CST structural syntax is not linguistic input. This uses node roles only:
    # no command names, TeX rescanning, or English vocabulary.
    for node in nodes:
        if node.type in _MATH_TYPES:
            continue
        if node.type in {"begin", "end", "label_definition"}:
            start, end = _char_span(mapping, node)
            _mask(characters, start, end)
            continue

        command = node.child_by_field_name("command")
        if command is None:
            continue
        command_start, command_end = _char_span(mapping, command)
        _mask(characters, command_start, command_end)

        if node.type == "generic_command":
            # Preserve argument content for sentence segmentation while masking
            # parser-owned group delimiters. No semantic transparency is inferred.
            for child in node.children:
                if not child.type.startswith(("curly_group", "brack_group")):
                    continue
                for delimiter in child.children:
                    if delimiter.is_named:
                        continue
                    start, end = _char_span(mapping, delimiter)
                    _mask(characters, start, end)
        else:
            # Specialized structural command nodes (e.g. sectioning) may own
            # following document text. Mask direct argument groups only; keep
            # the structurally owned following prose.
            for child in node.children:
                if child.type.startswith(("curly_group", "brack_group")):
                    start, end = _char_span(mapping, child)
                    _mask(characters, start, end)

    # Mathematics is a typed non-linguistic unit. Preserve only a neutral marker
    # and CST-owned terminal sentence punctuation needed by sentence segmentation.
    outer_math: list[Any] = []
    for node in nodes:
        if node.type not in _MATH_TYPES:
            continue
        if any(
            other is not node
            and other.type in _MATH_TYPES
            and int(other.start_byte) <= int(node.start_byte)
            and int(node.end_byte) <= int(other.end_byte)
            for other in nodes
        ):
            continue
        outer_math.append(node)

    for node in outer_math:
        start, end = _char_span(mapping, node)
        _mask(characters, start, end)
        marker = next((index for index in range(start, end) if text[index] != "\n"), None)
        if marker is not None:
            characters[marker] = "∎"
        punctuation_byte = _terminal_math_punctuation(source, node)
        if punctuation_byte is not None and punctuation_byte in mapping:
            punctuation_char = mapping[punctuation_byte]
            characters[punctuation_char] = text[punctuation_char]

    return text, "".join(characters)


def _sentence_records(source: str, projection: str) -> list[dict[str, object]]:
    document = SpacyLinguisticFrontend().parse(projection)
    grouped: dict[int, list[Any]] = {}
    for token in document.tokens:
        if token.text.isspace():
            continue
        grouped.setdefault(token.sentence_index, []).append(token)

    records: list[dict[str, object]] = []
    for index in sorted(grouped):
        tokens = grouped[index]
        start = min(token.start for token in tokens)
        end = max(token.end for token in tokens)
        while start < end and projection[start].isspace():
            start += 1
        while end > start and projection[end - 1].isspace():
            end -= 1
        records.append(
            {
                "sentence_index": index,
                "projection_text": projection[start:end],
                "source_text": source[start:end],
                "start": start,
                "end": end,
            }
        )
    return records


def _case(path: Path) -> dict[str, object]:
    source, projection = _structural_segmentation_projection(path)
    sentences = _sentence_records(source, projection)
    return {
        "path": str(path),
        "projection": projection,
        "sentences": sentences,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    a2_path = repo / "eval/robustness/issue_101/variant_prose_uniformity.tex"
    c0_path = repo / "eval/robustness/issue_101/clean_control.tex"

    a2 = _case(a2_path)
    c0 = _case(c0_path)
    errors: list[str] = []

    a2_window = [
        sentence
        for sentence in a2["sentences"]
        if "Throughout, the observation window is" in sentence["source_text"]
    ]
    if len(a2_window) != 1:
        errors.append(f"A2 observation-window statement count was {len(a2_window)}, expected 1")
    elif "∎" not in a2_window[0]["projection_text"]:
        errors.append("A2 observation-window statement lost its mathematical attachment")

    c0_motivation = "The next elementary observation records the decay seen at any fixed"
    fused = [
        sentence
        for sentence in c0["sentences"]
        if c0_motivation in sentence["source_text"] and "∎" in sentence["projection_text"]
    ]
    if fused:
        errors.append("C0 motivational prose remained fused to a mathematical statement")

    # Synthetic invariants prove this is not tuned to the A2 spelling.
    synthetic = repo / ".issue-198-structural-nlp-synthetic.tex"
    synthetic.write_text(
        "\\begin{document}\n"
        "A term is \\arbitrarywrapper{regular} when condition \\(P\\) holds.\n"
        "\\section{Metadata Heading}\\label{sec:meta}\n"
        "The next sentence is plain prose.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    try:
        synthetic_case = _case(synthetic)
    finally:
        synthetic.unlink(missing_ok=True)

    projection = synthetic_case["projection"]
    if "arbitrarywrapper" in projection:
        errors.append("generic command syntax leaked into segmentation projection")
    if "regular" not in projection:
        errors.append("generic command argument content disappeared from segmentation projection")
    if "Metadata Heading" in projection or "sec:meta" in projection:
        errors.append("structural section/label metadata leaked into segmentation projection")
    if "The next sentence is plain prose." not in projection:
        errors.append("structurally owned prose after a section was lost")

    payload = {
        "format": "thorn-issue-198-structural-nlp-segmentation-spike/1",
        "issue": 198,
        "hypothesis": (
            "Tree-sitter CST roles can provide a syntax-clean segmentation-only NLP view; "
            "spaCy delimits statements, while exact source remains the semantic authority."
        ),
        "constraints": {
            "command_name_dictionary": False,
            "english_cue_dictionary": False,
            "regex_or_raw_tex_rescan": False,
            "semantic_transparency_inference_for_generic_commands": False,
            "production_change": False,
            "provider_or_model_call": False,
        },
        "a2": a2,
        "c0": c0,
        "synthetic": synthetic_case,
        "errors": errors,
        "status": "pass" if not errors else "fail",
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
