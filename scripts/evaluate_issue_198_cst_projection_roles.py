from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tree_sitter_language_pack import get_parser


SAMPLES: dict[str, str] = {
    "ordinary_prose": "Ordinary mathematical prose remains ordinary prose.\n",
    "presentation_wrapper": "A sequence is called \\emph{stable} when the condition holds.\n",
    "inline_math": "For \\(x\\in X\\), the value is finite.\n",
    "display_math": "The observation window is\n\\[\n  \\mathcal W=\\{x:0\\le x<1\\}.\n\\]\n",
    "section_and_label": "\\section{Setup}\\label{sec:setup}\nThe assumptions follow.\n",
    "theorem_environment": (
        "\\begin{theorem}\\label{thm:sample}\n"
        "Every stable object has property \\(P\\).\n"
        "\\end{theorem}\n"
    ),
    "unknown_macro": "An object is \\mystyle{regular} when property \\(Q\\) holds.\n",
}


def _text(source: bytes, node: Any) -> str:
    return source[int(node.start_byte) : int(node.end_byte)].decode("utf-8")


def _fields(node: Any) -> dict[str, object]:
    fields: dict[str, object] = {}
    # These are the semantic fields used by Thorn's existing adapter.  We inspect
    # them without using command names or source rescanning.
    for name in ("command", "name", "begin", "end", "body"):
        child = node.child_by_field_name(name)
        if child is not None:
            fields[name] = {
                "type": child.type,
                "start_byte": int(child.start_byte),
                "end_byte": int(child.end_byte),
            }
    return fields


def _node_record(source: bytes, node: Any, depth: int) -> dict[str, object]:
    raw = _text(source, node)
    return {
        "depth": depth,
        "type": node.type,
        "named": bool(node.is_named),
        "start_byte": int(node.start_byte),
        "end_byte": int(node.end_byte),
        "raw": raw,
        "fields": _fields(node),
    }


def _walk(source: bytes, root: Any) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    stack: list[tuple[Any, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        records.append(_node_record(source, node, depth))
        stack.extend((child, depth + 1) for child in reversed(list(node.children)))
    return records


def _structural_summary(records: list[dict[str, object]]) -> dict[str, object]:
    types = {str(record["type"]) for record in records}
    command_nodes = [record for record in records if "command" in record["fields"]]
    environment_nodes = [
        record
        for record in records
        if "begin" in record["fields"] and "end" in record["fields"]
    ]
    math_types = sorted(types & {"inline_formula", "displayed_equation", "math_environment"})
    text_types = sorted(
        node_type
        for node_type in types
        if "text" in node_type or node_type in {"word", "text"}
    )
    return {
        "node_types": sorted(types),
        "command_field_nodes": command_nodes,
        "environment_field_nodes": environment_nodes,
        "math_types": math_types,
        "text_like_types": text_types,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    latex = get_parser("latex")
    samples: dict[str, object] = {}
    all_types: set[str] = set()
    for name, text in SAMPLES.items():
        source = text.encode("utf-8")
        tree = latex.parse(source)
        records = _walk(source, tree.root_node)
        all_types.update(str(record["type"]) for record in records)
        samples[name] = {
            "source": text,
            "has_error": bool(tree.root_node.has_error),
            "tree": records,
            "summary": _structural_summary(records),
        }

    payload = {
        "format": "thorn-issue-198-cst-projection-role-spike/1",
        "issue": 198,
        "question": (
            "Can parser-owned CST roles distinguish linguistic content, mathematical "
            "content, document structure, and ambiguous macro content without a macro-name dictionary?"
        ),
        "constraints": {
            "command_name_dictionary": False,
            "english_cue_dictionary": False,
            "regex_or_raw_tex_rescan": False,
            "production_change": False,
            "provider_or_model_call": False,
        },
        "all_node_types": sorted(all_types),
        "samples": samples,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
