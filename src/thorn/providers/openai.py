from __future__ import annotations

from openai import OpenAI

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.providers.request_envelope import (
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

    def attack(self, unit: TheoremUnit) -> AttackReport:
        envelope = attack_request_envelope(unit, self.model)
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": envelope.system_prompt},
                {"role": "user", "content": envelope.user_content},
            ],
            text_format=AttackReport,
        )
        self._record_usage(response)
        if response.output_parsed is None:
            raise RuntimeError("attacker returned no structured result")
        return response.output_parsed

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport:
        envelope = semantic_request_envelope(request, self.model)
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": envelope.system_prompt},
                {"role": "user", "content": envelope.user_content},
            ],
            text_format=AttackReport,
        )
        self._record_usage(response)
        if response.output_parsed is None:
            raise RuntimeError("semantic reviewer returned no structured result")
        return response.output_parsed

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport:
        envelope = defense_request_envelope(unit, findings, self.model)
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": envelope.system_prompt},
                {"role": "user", "content": envelope.user_content},
            ],
            text_format=DefenseReport,
        )
        self._record_usage(response)
        if response.output_parsed is None:
            raise RuntimeError("defender returned no structured result")
        return response.output_parsed
