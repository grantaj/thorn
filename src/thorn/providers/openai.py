from __future__ import annotations

from openai import OpenAI

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.providers.request_envelope import (
    ProviderRequestEnvelope,
    attack_request_envelope,
    defense_request_envelope,
    semantic_request_envelope,
)
from thorn.semantic_review_render import SemanticReviewRequest


class OpenAIProvider:
    def __init__(self, model: str = "gpt-5.6") -> None:
        self.model = model
        self.client = OpenAI()
        self.requests = 0
        self.live_requests = 0
        self.replay_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

    def _record_usage(self, response: object) -> None:
        self.requests += 1
        self.live_requests += 1
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)

    def _parse(self, envelope: ProviderRequestEnvelope, text_format: object) -> object:
        return self.client.responses.parse(
            model=self.model,
            input=envelope.input_messages(),
            text_format=text_format,
        )

    def attack(self, unit: TheoremUnit) -> AttackReport:
        response = self._parse(attack_request_envelope(unit, self.model), AttackReport)
        self._record_usage(response)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise RuntimeError("attacker returned no structured result")
        return parsed

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        response = self._parse(semantic_request_envelope(request, self.model), AttackReport)
        self._record_usage(response)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise RuntimeError("semantic reviewer returned no structured result")
        return parsed

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport:
        response = self._parse(
            defense_request_envelope(unit, findings, self.model),
            DefenseReport,
        )
        self._record_usage(response)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise RuntimeError("defender returned no structured result")
        return parsed
