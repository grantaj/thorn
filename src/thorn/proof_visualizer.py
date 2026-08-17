from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from thorn.dependencies import ExtractedProject
from thorn.frontend import SourceSpan
from thorn.models import TheoremUnit
from thorn.proof_visualizer_assets import CSS, JS
from thorn.support import SupportKind


def _path_uri(file: str) -> str | None:
    try:
        return Path(file).expanduser().resolve().as_uri()
    except (OSError, ValueError):
        return None


def _source_payload(source: SourceSpan) -> dict[str, Any]:
    return {
        "file": source.file,
        "startLine": source.start_line,
        "endLine": source.end_line,
        "uri": _path_uri(source.file),
    }


def _result_source(unit: TheoremUnit) -> dict[str, Any]:
    source = unit.statement_range
    return {
        "file": source.file,
        "startLine": source.start_line,
        "endLine": source.end_line,
        "uri": _path_uri(source.file),
    }


def _result_name(unit: TheoremUnit) -> str:
    return unit.title or unit.label or unit.identifier


def build_proof_visualizer_data(project: ExtractedProject) -> dict[str, Any]:
    """Project existing proof-support IR into transient browser presentation data.

    The overview is intentionally an argument graph, not a generic document-reference graph.
    Only existing result-reference support edges become theorem/lemma-level edges. Drill-down
    uses the existing claim/support objects directly. No mathematical relationship is inferred
    by this projection.
    """

    result_order = {unit.identifier: index for index, unit in enumerate(project.units)}
    results = [
        {
            "id": unit.identifier,
            "name": _result_name(unit),
            "kind": unit.environment,
            "statement": unit.statement,
            "source": _result_source(unit),
            "hasProof": unit.proof is not None,
            "order": index,
        }
        for index, unit in enumerate(project.units)
    ]
    label_to_result = {unit.identifier: unit.identifier for unit in project.units}
    label_to_result.update(
        {unit.label: unit.identifier for unit in project.units if unit.label is not None}
    )

    overview_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    rank = {"unresolved": 0, "ambiguous": 1, "confident": 2}
    for support in project.proof_support_graph.edges:
        if support.kind != SupportKind.RESULT_REFERENCE or not support.target_label:
            continue
        referenced = label_to_result.get(support.target_label)
        try:
            dependent = project.proof_support_graph.claim(
                support.target_claim_identifier
            ).result_identifier
        except KeyError:
            continue
        if referenced is None or dependent not in result_order:
            continue
        key = (referenced, dependent)
        item = overview_by_pair.setdefault(
            key,
            {
                "id": f"result:{referenced}->{dependent}",
                "from": referenced,
                "to": dependent,
                "kind": SupportKind.RESULT_REFERENCE.value,
                "status": support.status.value,
                "sources": [],
            },
        )
        if rank[support.status.value] > rank[item["status"]]:
            item["status"] = support.status.value
        item["sources"].append(_source_payload(support.source))

    overview_edges = sorted(
        overview_by_pair.values(),
        key=lambda item: (
            result_order.get(item["from"], 10**9),
            result_order.get(item["to"], 10**9),
            item["id"],
        ),
    )

    proof_units: dict[str, Any] = {}
    for unit in project.units:
        claims = project.proof_support_graph.claims_for_result(unit.identifier)
        claim_ids = {claim.identifier for claim in claims}
        claim_payloads: dict[str, dict[str, Any]] = {
            claim.identifier: {
                "id": claim.identifier,
                "kind": "claim",
                "name": f"Claim {index + 1}",
                "form": claim.form.value,
                "text": claim.raw,
                "source": _source_payload(claim.source),
                "order": index,
                "supports": [],
            }
            for index, claim in enumerate(claims)
        }
        external: dict[str, dict[str, Any]] = {}
        topology: list[dict[str, Any]] = []

        for support in project.proof_support_graph.edges:
            if support.target_claim_identifier not in claim_ids:
                continue
            claim_payloads[support.target_claim_identifier]["supports"].append(
                {
                    "id": support.identifier,
                    "kind": support.kind.value,
                    "status": support.status.value,
                    "explicit": support.explicit,
                    "justification": support.raw_justification,
                    "namedProperty": support.named_property,
                    "targetLabel": support.target_label,
                    "source": _source_payload(support.source),
                }
            )
            if (
                support.source_claim_identifier is not None
                and support.source_claim_identifier in claim_ids
            ):
                topology.append(
                    {
                        "id": support.identifier,
                        "from": support.source_claim_identifier,
                        "to": support.target_claim_identifier,
                        "kind": support.kind.value,
                        "status": support.status.value,
                    }
                )
                continue
            if support.kind != SupportKind.RESULT_REFERENCE or not support.target_label:
                continue
            referenced = label_to_result.get(support.target_label)
            if referenced is None:
                continue
            external_id = f"external-result:{referenced}"
            if external_id not in external:
                referenced_unit = project.unit(referenced)
                external[external_id] = {
                    "id": external_id,
                    "kind": "external_result",
                    "resultId": referenced,
                    "name": _result_name(referenced_unit),
                    "resultKind": referenced_unit.environment,
                    "statement": referenced_unit.statement,
                    "source": _result_source(referenced_unit),
                    "order": result_order.get(referenced, 10**9),
                }
            topology.append(
                {
                    "id": support.identifier,
                    "from": external_id,
                    "to": support.target_claim_identifier,
                    "kind": support.kind.value,
                    "status": support.status.value,
                }
            )

        node_order = {
            **{key: (0, value["order"]) for key, value in external.items()},
            **{key: (1, value["order"]) for key, value in claim_payloads.items()},
        }
        topology.sort(
            key=lambda item: (
                node_order.get(item["from"], (9, 10**9)),
                node_order.get(item["to"], (9, 10**9)),
                item["id"],
            )
        )
        proof_units[unit.identifier] = {
            "claims": list(claim_payloads.values()),
            "externalResults": sorted(
                external.values(), key=lambda item: (item["order"], item["id"])
            ),
            "edges": topology,
        }

    return {
        "manuscript": project.main_file,
        "results": results,
        "overviewEdges": overview_edges,
        "proofUnits": proof_units,
    }


def _json_for_html(data: dict[str, Any]) -> str:
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_proof_visualizer_html(project: ExtractedProject) -> str:
    payload = _json_for_html(build_proof_visualizer_data(project))
    manuscript = escape(project.main_file, quote=True)
    name = escape(Path(project.main_file).name, quote=True)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Thorn proof graph — {name}</title>
<style>{CSS}</style>
</head>
<body>
<div class="shell">
  <nav class="sidebar" aria-label="Proof graph navigation">
    <div class="brand">Thorn proof graph</div>
    <div class="manuscript">{manuscript}</div>
    <input
      class="search"
      id="search"
      type="search"
      aria-label="Find a result"
      placeholder="Find theorem or lemma…"
    >
  </nav>
  <main class="main">
    <div class="breadcrumb"><button id="back" type="button" hidden>← Paper</button></div>
    <header class="header">
      <div>
        <h1 id="view-title">Paper</h1>
        <p class="lede" id="view-lede"></p>
      </div>
      <div class="controls" aria-label="Graph controls">
        <button class="control" id="redundant" type="button" aria-pressed="false">
          All edges
        </button>
      </div>
    </header>
    <section class="graph-box" aria-label="Interactive proof argument graph">
      <div class="scroller">
        <div id="frame">
          <div class="canvas" id="stage">
            <svg class="edges" id="edges" aria-hidden="true"></svg>
          </div>
        </div>
      </div>
    </section>
    <section class="detail" hidden>
      <div id="detail-main"></div>
      <aside class="inspector" id="inspector" aria-live="polite"></aside>
    </section>
  </main>
</div>
<script type="application/json" id="thorn-graph-data">{payload}</script>
<script>{JS}</script>
</body>
</html>
'''


def write_proof_visualizer_html(project: ExtractedProject, destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_proof_visualizer_html(project), encoding="utf-8")
    return destination
