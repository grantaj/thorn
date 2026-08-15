from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from thorn.eval import CaseExpectation
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.local_nlp import select_linguistic_frontend
from thorn.semantic_experiment import EXPERIMENT_ARMS, semantic_experiment_envelope
from thorn.semantic_review_render import build_semantic_review_request
from thorn.spacy_linguistic import LinguisticFrontendUnavailable, SpacyLinguisticFrontend


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the keyless raw/compact-IR/raw+IR experiment packet inventory."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval/ir-value-challenge.json"),
    )
    parser.add_argument("--model", default="gpt-5.6")
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="skip the normal local spaCy frontend; intended only for debugging",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optional path for the JSON inventory; stdout is always written",
    )
    return parser


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("experiment manifest must be a JSON object")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("experiment manifest must contain a non-empty cases list")
    return payload


def _select_unit(project: Any, expectation: CaseExpectation):
    if expectation.target_identifier is not None:
        matches = [
            unit
            for unit in project.units
            if unit.identifier == expectation.target_identifier
        ]
        if len(matches) != 1:
            raise ValueError(
                f"target {expectation.target_identifier!r} matched {len(matches)} units"
            )
        return matches[0]
    if len(project.units) != 1:
        raise ValueError(
            f"case {expectation.name!r} has {len(project.units)} units but no target_identifier"
        )
    return project.units[0]


def build_inventory(
    manifest_path: Path,
    *,
    model: str,
    structural_only: bool,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    linguistic_frontend = select_linguistic_frontend(
        structural_only=structural_only,
        factory=SpacyLinguisticFrontend,
    )
    totals = {
        arm: {"characters": 0, "utf8_bytes": 0}
        for arm in EXPERIMENT_ARMS
    }
    records: list[dict[str, Any]] = []
    shared_prompt_sha256: str | None = None

    for entry in manifest["cases"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("metadata"), str):
            raise ValueError("every manifest case must contain a metadata path")
        metadata_path = Path(entry["metadata"])
        tex_path = metadata_path.with_suffix(".tex")
        expectation = CaseExpectation.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
        project = extract_project(
            tex_path,
            linguistic_frontend=linguistic_frontend,
        )
        unit = _select_unit(project, expectation)
        context = build_result_review_context(project, unit.identifier)
        if len(context.items) != 1:
            raise ValueError(
                f"expected exactly one result review item for {unit.identifier!r}"
            )
        request = build_semantic_review_request(context.items[0])

        arm_records: dict[str, dict[str, object]] = {}
        case_prompt_sha256: str | None = None
        for arm in EXPERIMENT_ARMS:
            envelope = semantic_experiment_envelope(unit, request, model, arm)
            prompt_sha256 = hashlib.sha256(
                envelope.system_prompt.encode("utf-8")
            ).hexdigest()
            if case_prompt_sha256 is None:
                case_prompt_sha256 = prompt_sha256
            elif prompt_sha256 != case_prompt_sha256:
                raise ValueError("experiment arms do not share one system prompt")
            if shared_prompt_sha256 is None:
                shared_prompt_sha256 = prompt_sha256
            elif prompt_sha256 != shared_prompt_sha256:
                raise ValueError("experiment cases do not share one system prompt")

            characters = len(envelope.user_content)
            utf8_bytes = len(envelope.user_content.encode("utf-8"))
            totals[arm]["characters"] += characters
            totals[arm]["utf8_bytes"] += utf8_bytes
            arm_records[arm] = {
                "characters": characters,
                "utf8_bytes": utf8_bytes,
                "fingerprint": envelope.fingerprint(),
            }

        records.append(
            {
                "metadata": str(metadata_path),
                "fixture": str(tex_path),
                "case_name": expectation.name,
                "expected_kind": expectation.kind,
                "accepted_categories": [
                    category.value for category in expectation.accepted_categories
                ],
                "target_identifier": unit.identifier,
                "pair": entry.get("pair"),
                "role": entry.get("role"),
                "arms": arm_records,
            }
        )

    return {
        "manifest": str(manifest_path),
        "manifest_version": manifest.get("version"),
        "issue": manifest.get("issue"),
        "frozen": manifest.get("frozen"),
        "model": model,
        "semantic_prompt_sha256": shared_prompt_sha256,
        "cases": len(records),
        "experiment_arms": list(EXPERIMENT_ARMS),
        "provider_requests": 0,
        "live_requests": 0,
        "api_key_required": False,
        "size_units": (
            "exact model-facing user-content characters and UTF-8 bytes; actual token "
            "usage is measured only during an explicitly authorized live run"
        ),
        "totals": totals,
        "records": records,
    }


def main() -> int:
    args = _parser().parse_args()
    try:
        inventory = build_inventory(
            args.manifest,
            model=args.model,
            structural_only=args.structural_only,
        )
    except LinguisticFrontendUnavailable as exc:
        print(
            "IR-value inventory: local linguistic frontend unavailable: "
            f"{exc}. Install en_core_web_sm or use --structural-only for debugging."
        )
        return 2

    rendered = json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
