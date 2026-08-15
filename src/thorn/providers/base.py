from __future__ import annotations

from typing import Protocol

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit
from thorn.semantic_review_render import SemanticReviewRequest


class AuditProvider(Protocol):
    model: str

    def attack(self, unit: TheoremUnit) -> AttackReport: ...

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport: ...


class SemanticReviewProvider(Protocol):
    """Provider boundary for one Thorn-owned, IR-derived semantic review request."""

    model: str

    def review_semantic(self, request: SemanticReviewRequest) -> AttackReport: ...


class EvaluationProvider(AuditProvider, SemanticReviewProvider, Protocol):
    """Combined evaluator boundary with provider usage/replay accounting.

    ``requests`` counts logical provider invocations. Live providers also increment
    ``live_requests``; replay providers increment ``replay_hits`` instead. Token
    counters describe tokens consumed by the current run, so replay keeps them at
    zero while recorded historical usage remains in the recording fixture itself.
    """

    requests: int
    live_requests: int
    replay_hits: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
