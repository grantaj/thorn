from thorn.models import (
    AuditFinding,
    DefenseVerdict,
    FindingCategory,
    Severity,
    SourceRange,
)


def test_surviving_confidence_is_conservative() -> None:
    finding = AuditFinding(
        unit_id="u",
        rule="TH302",
        category=FindingCategory.COUNTEREXAMPLE,
        severity=Severity.ERROR,
        title="Counterexample",
        explanation="Broken.",
        attacker_confidence=0.9,
        defender_verdict=DefenseVerdict.SURVIVES,
        defender_explanation="Still broken.",
        defender_confidence=0.8,
        source=SourceRange(file="x.tex", start_line=1, end_line=2),
    )
    assert finding.confidence == 0.8
