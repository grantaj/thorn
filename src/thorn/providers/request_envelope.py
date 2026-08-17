from __future__ import annotations

import hashlib
import json
import os
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.proof_language_review import PROMPT_VERSION, ProofReviewTurnRequest
from thorn.semantic_review_compact import render_compact_semantic_review_request
from thorn.semantic_review_render import SemanticReviewRequest, render_semantic_review_request

RequestKind = Literal["attack", "defend", "semantic", "proof_review"]
PROOF_REVIEW_MAX_OUTPUT_TOKENS = 4096


class ProviderRequestEnvelope(BaseModel):
    """Canonical description of one model request made by Thorn.

    Optional protocol metadata is omitted from legacy envelopes, preserving their
    existing canonical representation while making proof-review and rescue turns
    materially distinct at the replay boundary.
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


def proof_review_request_envelope(
    request: ProofReviewTurnRequest,
    model: str,
) -> ProviderRequestEnvelope:
    """Build one exact transport envelope for a proof-review protocol turn."""

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
        kind="proof_review",
        model=model,
        system_prompt=system_prompt,
        user_content=request.user_content,
        response_schema=request.response_schema(),
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