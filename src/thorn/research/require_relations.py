from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from thorn.frontend import SourceSpan


class RequireDisposition(StrEnum):
    """Manual semantic disposition for one already-resolved reference occurrence."""

    REQUIRE = "REQUIRE"
    NON_REQUIRE = "NON_REQUIRE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class RequireRelationQuery:
    """Model-neutral research query for the remaining REQUIRE semantic decision.

    The owner and resolved target are supplied by Thorn-owned structure/resolution.
    A candidate model is asked only whether the exact reference occurrence expresses
    direct prerequisite use in the bounded context.
    """

    owner_id: str
    context: str
    context_source: SourceSpan
    reference_token: str
    resolved_target_id: str
    reference_source: SourceSpan


@dataclass(frozen=True)
class RequireRelationScore:
    """Non-authoritative relation score tied to the supplied reference occurrence."""

    relation_label: str
    score: float
    reference_token: str
    reference_source: SourceSpan
    endpoint_exact: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("relation score must lie in [0, 1]")


def assert_exact_reference(query: RequireRelationQuery) -> None:
    """Fail closed if supplied reference provenance cannot map into the context."""

    context = query.context_source
    reference = query.reference_source
    if reference.file != context.file:
        raise ValueError("reference source file differs from context source file")
    if not (
        context.start_offset
        <= reference.start_offset
        <= reference.end_offset
        <= context.end_offset
    ):
        raise ValueError("reference source lies outside query context")

    local_start = reference.start_offset - context.start_offset
    local_end = reference.end_offset - context.start_offset
    if query.context[local_start:local_end] != query.reference_token:
        raise ValueError("reference token does not match supplied source span")
