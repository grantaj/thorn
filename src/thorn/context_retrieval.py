from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from thorn.dependencies import ExtractedProject
from thorn.frontend import SourceSpan
from thorn.linguistic_statements import LinguisticStatement, StatementScopeKind
from thorn.workspace import ProjectPosition, ProjectPositionLookup, WorkspaceResolution


class ContextProposalStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class ContextCandidate(BaseModel):
    """One exact prior statement occurrence offered to a generic ranker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    statement_identifier: str
    occurrence_id: str
    text: str
    source: SourceSpan


class ContextRank(BaseModel):
    """A ranker's advisory ordering observation for one known candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_identifier: str
    score: float


class ContextRanker(Protocol):
    """Generic ranking substrate; ranking is never mathematical authority."""

    name: str

    def rank(
        self,
        query: str,
        candidates: tuple[ContextCandidate, ...],
    ) -> tuple[ContextRank, ...]: ...


class RankedContextCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate: ContextCandidate
    rank: int = Field(ge=1)
    score: float


class ResultContextPool(BaseModel):
    """Occurrence-aware prior context available before one result occurrence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ContextProposalStatus
    result_identifier: str
    target_occurrence_id: str | None = None
    query: str = ""
    candidates: tuple[ContextCandidate, ...] = ()
    partial_reason: str | None = None


class RankedContextProposal(BaseModel):
    """Complete advisory ranking over an exact eligible candidate pool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ContextProposalStatus
    result_identifier: str
    target_occurrence_id: str | None = None
    ranker: str | None = None
    query: str = ""
    ranking: tuple[RankedContextCandidate, ...] = ()
    partial_reason: str | None = None

    def bounded(self, limit: int) -> BoundedContextProposal:
        if limit < 1:
            raise ValueError("context proposal limit must be positive")
        selected = self.ranking[:limit]
        return BoundedContextProposal(
            status=self.status,
            result_identifier=self.result_identifier,
            target_occurrence_id=self.target_occurrence_id,
            ranker=self.ranker,
            query=self.query,
            candidates=selected,
            total_candidate_count=len(self.ranking),
            truncated=len(self.ranking) > len(selected),
            partial_reason=self.partial_reason,
        )


class BoundedContextProposal(BaseModel):
    """Finite downstream view whose truncation never asserts irrelevance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ContextProposalStatus
    result_identifier: str
    target_occurrence_id: str | None = None
    ranker: str | None = None
    query: str = ""
    candidates: tuple[RankedContextCandidate, ...] = ()
    total_candidate_count: int = Field(ge=0)
    truncated: bool = False
    partial_reason: str | None = None


def _target_statements(
    project: ExtractedProject, result_identifier: str
) -> list[LinguisticStatement]:
    inventory = project.linguistic_statements
    assert inventory is not None
    return [
        statement
        for statement in inventory.statements
        if statement.result_identifier == result_identifier
        and statement.scope_kind
        in {StatementScopeKind.RESULT_STATEMENT, StatementScopeKind.RESULT_PROOF}
    ]


def _position_for_occurrence(
    lookup: ProjectPositionLookup,
    file: str,
    offset: int,
    occurrence_id: str,
) -> ProjectPosition | None:
    return next(
        (
            position
            for position in lookup.positions(file, offset)
            if position.occurrence_id == occurrence_id
        ),
        None,
    )


def build_result_context_pools(
    project: ExtractedProject,
    result_identifier: str,
) -> tuple[ResultContextPool, ...]:
    """Build exact prior-statement pools without making a relevance judgment."""

    inventory = project.linguistic_statements
    workspace = project.workspace
    if inventory is None or not inventory.complete:
        return (
            ResultContextPool(
                status=ContextProposalStatus.PARTIAL,
                result_identifier=result_identifier,
                partial_reason="linguistic statement inventory is unavailable or partial",
            ),
        )
    if workspace is None or workspace.resolution != WorkspaceResolution.RESOLVED:
        return (
            ResultContextPool(
                status=ContextProposalStatus.PARTIAL,
                result_identifier=result_identifier,
                partial_reason="workspace occurrence facts are unavailable or partial",
            ),
        )

    target_statements = _target_statements(project, result_identifier)
    if not target_statements:
        return (
            ResultContextPool(
                status=ContextProposalStatus.PARTIAL,
                result_identifier=result_identifier,
                partial_reason="target has no source-mapped linguistic statements",
            ),
        )

    lookup = ProjectPositionLookup(workspace)
    target_occurrence_ids: set[str] | None = None
    for statement in target_statements:
        occurrence_ids = {
            position.occurrence_id
            for position in lookup.positions(
                statement.source.file,
                statement.source.start_offset,
            )
        }
        target_occurrence_ids = (
            occurrence_ids
            if target_occurrence_ids is None
            else target_occurrence_ids.intersection(occurrence_ids)
        )
    if not target_occurrence_ids:
        return (
            ResultContextPool(
                status=ContextProposalStatus.PARTIAL,
                result_identifier=result_identifier,
                partial_reason="target statements have no common workspace occurrence",
            ),
        )

    query = " ".join(statement.text for statement in target_statements)
    pools: list[ResultContextPool] = []
    for occurrence_id in sorted(
        target_occurrence_ids,
        key=lambda item: next(
            occurrence.ordinal
            for occurrence in workspace.occurrences
            if occurrence.occurrence_id == item
        ),
    ):
        target_positions = [
            position
            for statement in target_statements
            if (
                position := _position_for_occurrence(
                    lookup,
                    statement.source.file,
                    statement.source.start_offset,
                    occurrence_id,
                )
            )
            is not None
        ]
        if not target_positions:
            continue
        target_position = min(target_positions)

        candidates: list[tuple[ProjectPosition, ContextCandidate]] = []
        for statement in inventory.statements:
            if statement.scope_kind != StatementScopeKind.PROJECT:
                continue
            for position in lookup.positions(
                statement.source.file,
                statement.source.end_offset,
            ):
                if position >= target_position:
                    continue
                candidate_id = f"context:{position.occurrence_id}:{statement.identifier}"
                candidates.append(
                    (
                        position,
                        ContextCandidate(
                            identifier=candidate_id,
                            statement_identifier=statement.identifier,
                            occurrence_id=position.occurrence_id,
                            text=statement.text,
                            source=statement.source,
                        ),
                    )
                )
        candidates.sort(key=lambda item: (item[0], item[1].identifier))
        pools.append(
            ResultContextPool(
                status=ContextProposalStatus.COMPLETE,
                result_identifier=result_identifier,
                target_occurrence_id=occurrence_id,
                query=query,
                candidates=tuple(candidate for _, candidate in candidates),
            )
        )

    if pools:
        return tuple(pools)
    return (
        ResultContextPool(
            status=ContextProposalStatus.PARTIAL,
            result_identifier=result_identifier,
            partial_reason="target occurrence could not be located in project order",
        ),
    )


def rank_context_pool(
    pool: ResultContextPool,
    ranker: ContextRanker,
) -> RankedContextProposal:
    """Require a total ordering so omitted items cannot silently mean irrelevant."""

    if pool.status != ContextProposalStatus.COMPLETE:
        return RankedContextProposal(
            status=pool.status,
            result_identifier=pool.result_identifier,
            target_occurrence_id=pool.target_occurrence_id,
            ranker=ranker.name,
            query=pool.query,
            partial_reason=pool.partial_reason,
        )

    ranked = ranker.rank(pool.query, pool.candidates)
    expected = {candidate.identifier for candidate in pool.candidates}
    observed = [item.candidate_identifier for item in ranked]
    if len(observed) != len(set(observed)):
        raise ValueError("context ranker returned duplicate candidate identifiers")
    if set(observed) != expected:
        missing = sorted(expected.difference(observed))
        unknown = sorted(set(observed).difference(expected))
        raise ValueError(
            "context ranker must order the complete candidate pool; "
            f"missing={missing}, unknown={unknown}"
        )

    candidates = {candidate.identifier: candidate for candidate in pool.candidates}
    return RankedContextProposal(
        status=ContextProposalStatus.COMPLETE,
        result_identifier=pool.result_identifier,
        target_occurrence_id=pool.target_occurrence_id,
        ranker=ranker.name,
        query=pool.query,
        ranking=tuple(
            RankedContextCandidate(
                candidate=candidates[item.candidate_identifier],
                rank=index,
                score=item.score,
            )
            for index, item in enumerate(ranked, start=1)
        ),
    )
