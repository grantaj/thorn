from __future__ import annotations

from dataclasses import dataclass

from thorn.dependencies import ExtractedProject
from thorn.eval_review import build_result_review_context
from thorn.llm_proof_language import LLMProofLanguage, project_llm_proof_language
from thorn.models import AttackReport, TheoremUnit
from thorn.proof_language_review import (
    ProofLanguageReviewRequest,
    ProofReviewModelResponse,
    ProofReviewTransport,
    ProofReviewTurnRequest,
    review_proof_language,
)
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import (
    SemanticTransformationIR,
    build_semantic_transformation_ir,
)


@dataclass(frozen=True)
class PreparedProofReview:
    """Keyless canonical proof state plus its stable model-facing projection."""

    state: SemanticTransformationIR
    document: LLMProofLanguage


@dataclass(frozen=True)
class CompletedProofReview:
    """A completed review plus the exact protocol turns used to obtain it."""

    report: AttackReport
    initial_turn: ProofReviewTurnRequest
    rescue_turn: ProofReviewTurnRequest | None = None


class _TracingTransport:
    """Observe Thorn-owned review requests without changing provider behavior."""

    def __init__(self, transport: ProofReviewTransport) -> None:
        self._transport = transport
        self.model = transport.model
        self.turns: list[ProofReviewTurnRequest] = []

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse:
        self.turns.append(request)
        return self._transport.review_proof_turn(request)


def prepare_proof_review(
    project: ExtractedProject,
    unit: TheoremUnit,
) -> PreparedProofReview:
    """Build canonical Proof IR and `thorn-proof/1` for one result, keylessly."""

    context = build_result_review_context(project, unit.identifier)
    if len(context.items) != 1:
        raise ValueError(f"expected exactly one review item for {unit.identifier!r}")
    semantic_request = build_semantic_review_request(context.items[0])
    state = build_semantic_transformation_ir(
        unit,
        semantic_request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    return PreparedProofReview(
        state=state,
        document=project_llm_proof_language(state),
    )


def run_proof_review(
    prepared: PreparedProofReview,
    transport: ProofReviewTransport,
) -> CompletedProofReview:
    """Run the normal v2 Proof-IR review protocol with at most one source rescue."""

    tracing = _TracingTransport(transport)
    report = review_proof_language(
        ProofLanguageReviewRequest(document=prepared.document),
        tracing,
    )
    if not tracing.turns:
        raise RuntimeError("proof review completed without a provider turn")
    if len(tracing.turns) > 2:
        raise RuntimeError("proof review exceeded the bounded two-turn protocol")
    return CompletedProofReview(
        report=report,
        initial_turn=tracing.turns[0],
        rescue_turn=tracing.turns[1] if len(tracing.turns) == 2 else None,
    )
