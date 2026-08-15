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
    """Combined evaluator boundary with per-provider usage accounting.

    The ordinary raw and semantic-review provider protocols remain independent.
    ``thorn-eval`` needs both boundaries on one provider so a controlled run can
    compare them while taking usage snapshots before and after each case.
    """

    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
