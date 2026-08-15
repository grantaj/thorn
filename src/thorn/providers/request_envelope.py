from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.semantic_review_render import SemanticReviewRequest, render_semantic_review_request

RequestKind = Literal["attack", "defend", "semantic"]


class ProviderRequestEnvelope(BaseModel):
    """Canonical description of one model request made by Thorn.

    The envelope deliberately contains the exact prompt text, rendered user payload,
    model identifier, and expected structured-output schema. Its fingerprint therefore
    changes when a material model input changes, making recorded evaluation responses
    fail closed instead of being silently replayed against stale semantics.
    """

    format_version: int = 1
    provider: str = "openai-responses-parse"
    kind: RequestKind
    model: str
    system_prompt: str
    user_content: str
    response_schema: dict[str, object]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def input_messages(self) -> list[dict[str, str]]:
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
    return ProviderRequestEnvelope(
        kind="semantic",
        model=model,
        system_prompt=_read_prompt("semantic_reviewer.md"),
        user_content=render_semantic_review_request(request),
        response_schema=AttackReport.model_json_schema(),
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
