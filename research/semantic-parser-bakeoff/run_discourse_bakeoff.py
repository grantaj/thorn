from __future__ import annotations

import argparse
import json
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def _segment_for(root: ET.Element, token: str) -> str | None:
    for segment in root.findall(".//segment"):
        if token in "".join(segment.itertext()):
            return segment.get("id")
    return None


def _nodes(root: ET.Element) -> dict[str, tuple[str | None, str]]:
    result: dict[str, tuple[str | None, str]] = {}
    for tag in ("segment", "group"):
        for node in root.findall(f".//{tag}"):
            identifier = node.get("id")
            if identifier is not None:
                result[identifier] = (node.get("parent"), node.get("relname", "span"))
    return result


def _path(nodes: dict[str, tuple[str | None, str]], start: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    current: str | None = start
    while current is not None and current not in seen:
        seen.add(current)
        parent, relation = nodes[current]
        result.append((current, relation))
        current = parent
    return result


def _signature(root: ET.Element, source: str, target: str) -> str | None:
    source_segment = _segment_for(root, source)
    target_segment = _segment_for(root, target)
    if source_segment is None or target_segment is None:
        return None
    if source_segment == target_segment:
        return "same-edu"
    nodes = _nodes(root)
    source_path = _path(nodes, source_segment)
    target_path = _path(nodes, target_segment)
    target_ids = {identifier for identifier, _ in target_path}
    lca = next((identifier for identifier, _ in source_path if identifier in target_ids), None)
    if lca is None:
        return None

    def relations(path: list[tuple[str, str]]) -> str:
        values: list[str] = []
        for identifier, relation in path:
            if identifier == lca:
                break
            values.append(relation)
        return ">".join(values) or "self"

    return f"{relations(source_path)}||{relations(target_path)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("cases.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    from iudex.rst.parsers.dmrst.modeling_dmrst import DMRSTParser

    model = DMRSTParser.from_pretrained("larc-iu/dmrst-gum-12.1.0", device="cpu")
    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    selected = [case for case in payload["cases"] if case["task"] in {"result_support", "prior_claim"}]
    started = time.perf_counter()
    rows: list[dict[str, object]] = []

    for case in selected:
        tree = model.predict_from_text(str(case["text"]))
        rs4 = tree.to_rs4_string()
        root = ET.fromstring(rs4)
        expected = case["expected"]
        source = str(expected["source"])
        target = str(expected["target"])
        rows.append({
            "id": case["id"],
            "task": case["task"],
            "family": case["family"],
            "relation": expected["relation"],
            "rst_signature": _signature(root, source, target),
            "rs4": rs4,
        })

    task_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        task_rows[str(row["task"])].append(row)
    metrics: dict[str, object] = {}
    for task, items in sorted(task_rows.items()):
        positives = [item for item in items if item["family"] == "positive"]
        negatives = [item for item in items if item["family"] == "negative"]
        positive_signatures = {item["rst_signature"] for item in positives}
        negative_signatures = {item["rst_signature"] for item in negatives}
        metrics[task] = {
            "positive_cases": len(positives),
            "negative_cases": len(negatives),
            "distinct_positive_rst_templates": len(positive_signatures),
            "positive_template_ratio": round(len(positive_signatures) / len(positives), 3),
            "positive_negative_template_collisions": len(positive_signatures & negative_signatures),
            "unmapped": sum(item["rst_signature"] is None for item in items),
        }

    report = {
        "candidate": "iudex-dmrst-gum-12.1.0",
        "cases": len(rows),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "metrics": metrics,
        "rows": rows,
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output is not None:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
