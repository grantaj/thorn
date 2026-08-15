from __future__ import annotations

from importlib.resources import files
from typing import Literal

from thorn.models import AttackReport, TheoremUnit
from thorn.providers.request_envelope import ProviderRequestEnvelope, render_theorem_unit
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import SemanticReviewRequest

ExperimentArm = Literal["raw", "compact_ir", "raw_plus_compact"]
EXPERIMENT_ARMS: tuple[ExperimentArm, ...] = (
    "raw",
    "compact_ir",
    "raw_plus_compact",
)


def _semantic_reviewer_prompt() -> str:
    return files("thorn.prompts").joinpath("semantic_reviewer.md").read_text(encoding="utf-8")


def render_experiment_user_content(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
    arm: ExperimentArm,
) -> str:
    """Render one representation arm while holding the review task fixed."""

    raw = render_theorem_unit(unit)
    compact_ir = render_compact_semantic_review_request(request)

    if arm == "raw":
        return raw
    if arm == "compact_ir":
        return compact_ir
    if arm == "raw_plus_compact":
        return (
            "# Raw theorem packet\n"
            + raw
            + "\n# Thorn compact Math IR\n"
            + compact_ir
        )
    raise ValueError(f"unknown semantic experiment arm: {arm!r}")


def semantic_experiment_envelope(
    unit: TheoremUnit,
    request: SemanticReviewRequest,
    model: str,
    arm: ExperimentArm,
) -> ProviderRequestEnvelope:
    """Build a keyless provider envelope for a fair representation comparison.

    Every arm uses the same model-facing review task, response schema, provider
    contract, and model identifier. Only ``user_content`` changes. This avoids
    conflating the representation comparison with the existing attacker-vs-semantic
    reviewer prompt difference in ``thorn-eval --review-context raw|ir``.
    """

    return ProviderRequestEnvelope(
        kind="semantic",
        model=model,
        system_prompt=_semantic_reviewer_prompt(),
        user_content=render_experiment_user_content(unit, request, arm),
        response_schema=AttackReport.model_json_schema(),
    )
