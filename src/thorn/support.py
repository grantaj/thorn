from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import SourceSpan


class ClaimForm(StrEnum):
    PROSE = "prose"
    DISPLAY = "display"


class SupportKind(StrEnum):
    RESULT_REFERENCE = "result_reference"
    EQUATION_REFERENCE = "equation_reference"
    DEFINITION = "definition"
    NAMED_PROPERTY = "named_property"
    PRIOR_CLAIM = "prior_claim"
    EXPLICIT_REASON = "explicit_reason"


class QualifierKind(StrEnum):
    TRAILING_BINDER = "trailing_binder"


class BoundName(BaseModel):
    """One binding occurrence, deliberately distinct from spelling identity."""

    identifier: str
    name: str
    source: SourceSpan


class ClaimQualifier(BaseModel):
    identifier: str
    kind: QualifierKind
    raw: str
    source: SourceSpan
    bound_names: list[BoundName] = Field(default_factory=list)
    status: InferenceStatus = InferenceStatus.CONFIDENT
    evidence: list[StructuralEvidence] = Field(default_factory=list)


class Claim(BaseModel):
    identifier: str
    result_identifier: str
    form: ClaimForm
    raw: str
    source: SourceSpan
    qualifiers: list[ClaimQualifier] = Field(default_factory=list)


class SupportEdge(BaseModel):
    identifier: str
    target_claim_identifier: str
    kind: SupportKind
    source: SourceSpan
    raw_justification: str
    source_claim_identifier: str | None = None
    target_label: str | None = None
    named_property: str | None = None
    explicit: bool = True
    # Kept for compatibility with the #19 IR. Ambiguous linguistic candidates
    # deliberately leave this unset rather than inventing a calibrated score.
    confidence: float | None = Field(default=1.0, ge=0.0, le=1.0)
    status: InferenceStatus = InferenceStatus.CONFIDENT
    evidence: list[StructuralEvidence] = Field(default_factory=list)


class ProofSupportGraph(BaseModel):
    """Mechanically recovered proof claims and proposed support relationships.

    Edges record that the manuscript or a local structural parser presents a
    candidate support relation. They do not assert that the mathematical
    implication is valid. Ambiguous edges are preserved for later review but
    are deliberately excluded from deterministic graph reasoning.
    """

    claims: list[Claim] = Field(default_factory=list)
    edges: list[SupportEdge] = Field(default_factory=list)

    def claim(self, identifier: str) -> Claim:
        for claim in self.claims:
            if claim.identifier == identifier:
                return claim
        raise KeyError(f"unknown claim {identifier!r}")

    def claims_for_result(self, result_identifier: str) -> list[Claim]:
        return [
            claim for claim in self.claims if claim.result_identifier == result_identifier
        ]

    def confident_edges(self) -> list[SupportEdge]:
        return [edge for edge in self.edges if edge.status == InferenceStatus.CONFIDENT]

    def incoming_edges(self, claim_identifier: str) -> list[SupportEdge]:
        self.claim(claim_identifier)
        return [
            edge for edge in self.edges if edge.target_claim_identifier == claim_identifier
        ]

    def confident_incoming_edges(self, claim_identifier: str) -> list[SupportEdge]:
        return [
            edge
            for edge in self.incoming_edges(claim_identifier)
            if edge.status == InferenceStatus.CONFIDENT
        ]

    def outgoing_edges(self, claim_identifier: str) -> list[SupportEdge]:
        self.claim(claim_identifier)
        return [
            edge for edge in self.edges if edge.source_claim_identifier == claim_identifier
        ]

    def confident_outgoing_edges(self, claim_identifier: str) -> list[SupportEdge]:
        return [
            edge
            for edge in self.outgoing_edges(claim_identifier)
            if edge.status == InferenceStatus.CONFIDENT
        ]

    def downstream_claim_ids(self, claim_identifier: str) -> list[str]:
        self.claim(claim_identifier)
        order = {claim.identifier: index for index, claim in enumerate(self.claims)}
        visited: set[str] = set()
        pending = [
            edge.target_claim_identifier
            for edge in self.confident_outgoing_edges(claim_identifier)
        ]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(
                edge.target_claim_identifier
                for edge in self.confident_outgoing_edges(current)
            )
        return sorted(visited, key=order.__getitem__)

    def load_bearing_claim_ids(self) -> list[str]:
        """Claims confidently consumed by at least one later recovered claim."""

        source_ids = {
            edge.source_claim_identifier
            for edge in self.confident_edges()
            if edge.source_claim_identifier is not None
        }
        return [claim.identifier for claim in self.claims if claim.identifier in source_ids]

    def unsupported_load_bearing_claim_ids(self) -> list[str]:
        """Structural candidates only; this is not a correctness judgment."""

        return [
            identifier
            for identifier in self.load_bearing_claim_ids()
            if not self.confident_incoming_edges(identifier)
        ]
