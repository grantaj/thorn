from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FindingCategory(StrEnum):
    HYPOTHESIS_MISMATCH = "hypothesis_mismatch"
    INVALID_IMPLICATION = "invalid_implication"
    COUNTEREXAMPLE = "counterexample"
    CONVERGENCE_MISMATCH = "convergence_mismatch"
    QUANTIFIER_ERROR = "quantifier_error"
    BOUNDARY_CASE = "boundary_case"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    ALGEBRA_ERROR = "algebra_error"
    DEFINITION_MISMATCH = "definition_mismatch"
    WELL_DEFINEDNESS = "well_definedness"
    SCOPE_MISMATCH = "scope_mismatch"
    VACUOUS_TRUTH = "vacuous_truth"
    EXTERNAL_DEPENDENCY = "external_dependency"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    UNPROVED_DEPENDENCY = "unproved_dependency"
    UNSTATED_AXIOM = "unstated_axiom"
    NOTATION_AMBIGUITY = "notation_ambiguity"
    SPECIFICATION_AMBIGUITY = "specification_ambiguity"
    SCOPE_SURPLUS = "scope_surplus"
    OTHER = "other"


RULE_CODES: dict[FindingCategory, str] = {
    FindingCategory.HYPOTHESIS_MISMATCH: "TH201",
    FindingCategory.INVALID_IMPLICATION: "TH202",
    FindingCategory.CONVERGENCE_MISMATCH: "TH203",
    FindingCategory.QUANTIFIER_ERROR: "TH204",
    FindingCategory.DEFINITION_MISMATCH: "TH205",
    FindingCategory.VACUOUS_TRUTH: "TH206",
    FindingCategory.WELL_DEFINEDNESS: "TH207",
    FindingCategory.SCOPE_MISMATCH: "TH208",
    FindingCategory.ALGEBRA_ERROR: "TH301",
    FindingCategory.COUNTEREXAMPLE: "TH302",
    FindingCategory.BOUNDARY_CASE: "TH303",
    FindingCategory.CIRCULAR_DEPENDENCY: "TH401",
    FindingCategory.EXTERNAL_DEPENDENCY: "TH501",
    FindingCategory.UNSUPPORTED_CLAIM: "TH502",
    FindingCategory.UNPROVED_DEPENDENCY: "TH503",
    FindingCategory.UNSTATED_AXIOM: "TH504",
    FindingCategory.NOTATION_AMBIGUITY: "TH601",
    FindingCategory.SPECIFICATION_AMBIGUITY: "TH602",
    FindingCategory.SCOPE_SURPLUS: "TH603",
    FindingCategory.OTHER: "TH999",
}


class SourceRange(BaseModel):
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class TheoremUnit(BaseModel):
    identifier: str
    environment: str
    title: str | None = None
    label: str | None = None
    statement: str
    proof: str | None = None
    statement_range: SourceRange
    proof_range: SourceRange | None = None
    local_context: str = ""
    referenced_results: list[str] = Field(default_factory=list)

    @property
    def source_path(self) -> Path:
        return Path(self.statement_range.file)


class CandidateFinding(BaseModel):
    id: str
    category: FindingCategory
    severity: Severity
    title: str
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    counterexample: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def rule(self) -> str:
        return RULE_CODES[self.category]


class AttackReport(BaseModel):
    findings: list[CandidateFinding] = Field(default_factory=list)


class DefenseVerdict(StrEnum):
    SURVIVES = "survives"
    DISMISSED = "dismissed"
    UNCERTAIN = "uncertain"


class DefenseItem(BaseModel):
    finding_id: str
    verdict: DefenseVerdict
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)


class DefenseReport(BaseModel):
    verdicts: list[DefenseItem] = Field(default_factory=list)


class AuditFinding(BaseModel):
    unit_id: str
    rule: str
    category: FindingCategory
    severity: Severity
    title: str
    explanation: str
    evidence: list[str] = Field(default_factory=list)
    counterexample: str | None = None
    attacker_confidence: float = Field(ge=0.0, le=1.0)
    defender_verdict: DefenseVerdict
    defender_explanation: str
    defender_confidence: float = Field(ge=0.0, le=1.0)
    source: SourceRange

    @property
    def confidence(self) -> float:
        if self.defender_verdict == DefenseVerdict.SURVIVES:
            return min(self.attacker_confidence, self.defender_confidence)
        if self.defender_verdict == DefenseVerdict.UNCERTAIN:
            return min(self.attacker_confidence, 1.0 - self.defender_confidence / 2.0)
        return 0.0


class UnitAudit(BaseModel):
    unit: TheoremUnit
    findings: list[AuditFinding] = Field(default_factory=list)
    cached: bool = False
