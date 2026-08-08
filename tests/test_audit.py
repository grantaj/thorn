from thorn.audit import audit_unit
from thorn.models import (
    AttackReport,
    CandidateFinding,
    DefenseItem,
    DefenseReport,
    DefenseVerdict,
    FindingCategory,
    Severity,
    SourceRange,
    TheoremUnit,
)


class FakeProvider:
    model = "fake"

    def attack(self, unit: TheoremUnit) -> AttackReport:
        return AttackReport(
            findings=[
                CandidateFinding(
                    id="F1",
                    category=FindingCategory.INVALID_IMPLICATION,
                    severity=Severity.ERROR,
                    title="Bad implication",
                    explanation="A does not imply B.",
                    confidence=0.9,
                ),
                CandidateFinding(
                    id="F2",
                    category=FindingCategory.OTHER,
                    severity=Severity.WARNING,
                    title="False alarm",
                    explanation="Actually fine.",
                    confidence=0.8,
                ),
            ]
        )

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport:
        return DefenseReport(
            verdicts=[
                DefenseItem(
                    finding_id="F1",
                    verdict=DefenseVerdict.SURVIVES,
                    explanation="No repair found.",
                    confidence=0.85,
                ),
                DefenseItem(
                    finding_id="F2",
                    verdict=DefenseVerdict.DISMISSED,
                    explanation="Definition resolves it.",
                    confidence=0.95,
                ),
            ]
        )


def test_defender_filters_dismissed_findings() -> None:
    unit = TheoremUnit(
        identifier="t",
        environment="theorem",
        statement="B.",
        proof="A, therefore B.",
        statement_range=SourceRange(file="main.tex", start_line=1, end_line=2),
    )
    result = audit_unit(unit, FakeProvider(), use_defender=True)
    assert len(result.findings) == 1
    assert result.findings[0].title == "Bad implication"
    assert result.findings[0].confidence == 0.85
