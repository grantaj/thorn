from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.providers.request_envelope import render_theorem_unit
from thorn.semantic_experiment import EXPERIMENT_ARMS, semantic_experiment_envelope
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import build_semantic_review_request


def _experiment_inputs():
    project = extract_project(
        Path("eval/cases/ladder/03_hypotheses/missing_nonzero_hypothesis.tex")
    )
    unit = project.unit("thm:missing-hypothesis")
    context = build_result_review_context(project, unit.identifier)
    assert len(context.items) == 1
    request = build_semantic_review_request(context.items[0])
    return unit, request


def test_experiment_arms_hold_prompt_model_and_schema_fixed(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    unit, request = _experiment_inputs()

    envelopes = {
        arm: semantic_experiment_envelope(unit, request, "fixture-model", arm)
        for arm in EXPERIMENT_ARMS
    }

    assert {envelope.kind for envelope in envelopes.values()} == {"semantic"}
    assert {envelope.model for envelope in envelopes.values()} == {"fixture-model"}
    assert len({envelope.system_prompt for envelope in envelopes.values()}) == 1
    assert len(
        {
            json.dumps(envelope.response_schema, sort_keys=True)
            for envelope in envelopes.values()
        }
    ) == 1
    assert len({envelope.fingerprint() for envelope in envelopes.values()}) == 3


def test_experiment_arms_change_only_model_facing_mathematical_context() -> None:
    unit, request = _experiment_inputs()
    raw = render_theorem_unit(unit)
    compact_ir = render_compact_semantic_review_request(request)

    raw_envelope = semantic_experiment_envelope(unit, request, "fixture-model", "raw")
    compact_envelope = semantic_experiment_envelope(
        unit,
        request,
        "fixture-model",
        "compact_ir",
    )
    hybrid_envelope = semantic_experiment_envelope(
        unit,
        request,
        "fixture-model",
        "raw_plus_compact",
    )

    assert raw_envelope.user_content == raw
    assert compact_envelope.user_content == compact_ir
    assert hybrid_envelope.user_content == (
        "# Raw theorem packet\n"
        + raw
        + "\n# Thorn compact Math IR\n"
        + compact_ir
    )
    assert raw in hybrid_envelope.user_content
    assert compact_ir in hybrid_envelope.user_content


def test_ir_value_challenge_manifest_is_frozen_and_balanced() -> None:
    manifest_path = Path("eval/ir-value-challenge.json")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["version"] == 1
    assert payload["issue"] == 47
    assert payload["frozen"] is True
    cases = payload["cases"]
    assert len(cases) == 16

    metadata_paths = [Path(case["metadata"]) for case in cases]
    assert len(metadata_paths) == len(set(metadata_paths))
    for metadata_path in metadata_paths:
        assert metadata_path.exists()
        assert metadata_path.with_suffix(".tex").exists()

    pair_roles: dict[str, set[str]] = defaultdict(set)
    hard_defects = 0
    for case in cases:
        if case["pair"] is None:
            assert case["role"] == "hard_defect"
            hard_defects += 1
        else:
            pair_roles[case["pair"]].add(case["role"])

    assert len(pair_roles) == 6
    assert all(roles == {"clean", "defect"} for roles in pair_roles.values())
    assert hard_defects == 4
