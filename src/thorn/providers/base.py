from __future__ import annotations

from typing import Protocol

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit


class AuditProvider(Protocol):
    model: str

    def attack(self, unit: TheoremUnit) -> AttackReport: ...

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport: ...
