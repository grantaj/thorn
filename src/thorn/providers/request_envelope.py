from __future__ import annotations

import hashlib
import json
import os
from importlib.resources import files
from typing import Literal, cast

from pydantic import BaseModel

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import PROMPT_VERSION, ProofReviewTurnRequest
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import SemanticReviewRequest, render_semantic_review_request

RequestKind = Literal["attack", "defend", "semantic", "proof_review"]
PROOF_REVIEW_MAX_OUTPUT_TOKENS = 4096


class ProviderRequestEnvelope(BaseModel):
    """Canonical provider-neutral description of one model request.

    This remains useful semantic metadata and preserves legacy replay identity. New
    live execution identity is defined by ``ProviderExecutionContract`` after all
    provider-specific request construction has completed.
    """

    format_version: int = 1
    provider: str = "openai-responses-parse"
    kind: RequestKind
    model: str
    system_prompt: str
    user_content: str
    response_schema: dict[str, object]
    protocol_version: str | None = None
    representation: str | None = None
    stage: str | None = None
    initial_packet_fingerprint: str | None = None
    requested_source_addresses: tuple[str, ...] | None = None
    messages: tuple[dict[str, str], ...] | None = None
    max_output_tokens: int | None = None

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def fingerprint(self) -> str:
        """Return the historical provider-neutral envelope fingerprint.

        Do not use this for new live execution, recording, replay, or experiment
        freezes. It is retained so historical v1 evidence can be identified exactly.
        """

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def input_messages(self) -> list[dict[str, str]]:
        if self.messages is not None:
            return [dict(message) for message in self.messages]
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_content},
        ]


def _read_prompt(name: str) -> str:
    return files("thorn.prompts").joinpath(name).read_text(encoding="utf-8")


def render_theorem_unit(unit: TheoremUnit) -> str:
    refs = "\n\n".join(unit.referenced_results) or "(none extracted)"
    proof = unit.proof or "(no proof environment extracted)"
    return f"""# Result
ID: {unit.identifier}
Environment: {unit.environment}
Source: {unit.statement_range.file}:
  {unit.statement_range.start_line}-{unit.statement_range.end_line}

## Statement
{unit.statement}

## Proof
{proof}

## Local preceding context
{unit.local_context or "(none)"}

## Explicitly referenced extracted results
{refs}
"""


def _render_findings(findings: list[CandidateFinding]) -> str:
    return "\n\n".join(
        f"[{item.id}] {item.title}\n{item.explanation}\nEvidence: {item.evidence}\n"
        f"Counterexample: {item.counterexample or '(none)'}"
        for item in findings
    )


def attack_request_envelope(unit: TheoremUnit, model: str) -> ProviderRequestEnvelope:
    return ProviderRequestEnvelope(
        kind="attack",
        model=model,
        system_prompt=_read_prompt("attacker.md"),
        user_content=render_theorem_unit(unit),
        response_schema=AttackReport.model_json_schema(),
    )


def semantic_request_envelope(
    request: SemanticReviewRequest,
    model: str,
) -> ProviderRequestEnvelope:
    rendering = os.getenv("THORN_SEMANTIC_RENDERING", "full")
    if rendering == "full":
        user_content = render_semantic_review_request(request)
    elif rendering == "compact":
        user_content = render_compact_semantic_review_request(request)
    else:
        raise ValueError(
            "THORN_SEMANTIC_RENDERING must be 'full' or 'compact', "
            f"got {rendering!r}"
        )
    return ProviderRequestEnvelope(
        kind="semantic",
        model=model,
        system_prompt=_read_prompt("semantic_reviewer.md"),
        user_content=user_content,
        response_schema=AttackReport.model_json_schema(),
    )


def _proof_review_action_branch(
    schema: dict[str, object],
    *,
    action: Literal["review", "need_source"],
    constraints: dict[str, dict[str, object]],
) -> dict[str, object]:
    """Build a complete closed object branch for one proof-review action."""

    base_properties = schema.get("properties")
    if not isinstance(base_properties, dict):
        raise ValueError("proof-review response schema is missing top-level properties")
    properties = cast(
        dict[str, object],
        json.loads(json.dumps(base_properties)),
    )

    action_schema = properties.get("action")
    if not isinstance(action_schema, dict):
        raise ValueError("proof-review response schema is missing the action property")
    properties["action"] = {**action_schema, "const": action}

    for name, overlay in constraints.items():
        property_schema = properties.get(name)
        if not isinstance(property_schema, dict):
            raise ValueError(f"proof-review response schema is missing {name!r}")
        properties[name] = {**property_schema, **overlay}

    required = schema.get("required")
    if not isinstance(required, list):
        raise ValueError("proof-review response schema is missing required fields")
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _proof_review_response_schema(
    request: ProofReviewTurnRequest,
) -> dict[str, object]:
    """Expose request-specific action-safe proof-review states to the provider."""

    schema = cast(dict[str, object], json.loads(json.dumps(request.response_schema())))
    if request.stage != "initial" or not request.source_rescue_allowed:
        return schema

    schema["anyOf"] = [
        _proof_review_action_branch(
            schema,
            action="review",
            constraints={
                "source_addresses": {"maxItems": 0},
                "review_items": {"maxItems": 0},
                "source_review_item_ids": {"maxItems": 0},
            },
        ),
        _proof_review_action_branch(
            schema,
            action="need_source",
            constraints={
                "findings": {"maxItems": 0},
                "source_addresses": {"minItems": 1},
                "review_items": {"minItems": 1},
                "source_review_item_ids": {"minItems": 1},
            },
        ),
    ]
    return schema


def proof_review_request_envelope(
    request: ProofReviewTurnRequest,
    model: str,
) -> ProviderRequestEnvelope:
    """Build one provider-neutral proof-review turn."""

    system_prompt = _read_prompt(f"{PROMPT_VERSION}.md")
    messages: tuple[dict[str, str], ...] | None = None
    if (
        request.stage == "rescue"
        and (request.initial_user_content is None or request.prior_response is None)
    ):
        raise ValueError("rescue turn is missing its initial transcript")
    if request.stage == "rescue":
        assert request.initial_user_content is not None
        assert request.prior_response is not None
        messages = (
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.initial_user_content},
            {"role": "assistant", "content": request.prior_response.canonical_json()},
            {"role": "user", "content": request.user_content},
        )
    return ProviderRequestEnvelope(
        provider="openai-responses-create-json-schema",
        kind="proof_review",
        model=model,
        system_prompt=system_prompt,
        user_content=request.user_content,
        response_schema=_proof_review_response_schema(request),
        protocol_version=request.protocol_version,
        representation=request.representation,
        stage=request.stage,
        initial_packet_fingerprint=request.initial_packet_fingerprint,
        requested_source_addresses=(
            request.requested_source_addresses if request.requested_source_addresses else None
        ),
        messages=messages,
        max_output_tokens=PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    )


def defense_request_envelope(
    unit: TheoremUnit,
    findings: list[CandidateFinding],
    model: str,
) -> ProviderRequestEnvelope:
    return ProviderRequestEnvelope(
        kind="defend",
        model=model,
        system_prompt=_read_prompt("defender.md"),
        user_content=(
            render_theorem_unit(unit)
            + "\n\n# Proposed findings to defend against\n"
            + _render_findings(findings)
        ),
        response_schema=DefenseReport.model_json_schema(),
    )
