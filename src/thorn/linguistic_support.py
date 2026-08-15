from __future__ import annotations

from pathlib import Path

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import FrontendFile, ParsedProject
from thorn.linguistic import LinguisticDocument, LinguisticFrontend
from thorn.semantic_projection import project_semantic_span
from thorn.support import ProofSupportGraph, SupportEdge, SupportKind
from thorn.symbols import ResultRegion

_CUE_ONLY_KINDS = {
    SupportKind.RESULT_REFERENCE,
    SupportKind.EQUATION_REFERENCE,
    SupportKind.PRIOR_CLAIM,
}


def _file_for(project: ParsedProject, path: str) -> FrontendFile | None:
    resolved = str(Path(path).resolve())
    for file in project.files:
        if file.path == path or file.path == resolved:
            return file
    return None


def _root_path(document: LinguisticDocument) -> list[str]:
    roots = [
        token
        for token in document.tokens
        if token.head_index == token.index and token.pos in {"VERB", "AUX"}
    ]
    if not roots:
        return []
    return document.root_path_signature(roots[0].index)


def _evidence_for(
    project: ParsedProject,
    graph: ProofSupportGraph,
    edge: SupportEdge,
    result_identifiers: set[str],
    frontend: LinguisticFrontend,
) -> StructuralEvidence:
    target_claim = graph.claim(edge.target_claim_identifier)
    file = _file_for(project, target_claim.source.file)
    dependency_path: list[str] = []
    context = target_claim.raw

    if edge.kind == SupportKind.PRIOR_CLAIM:
        if edge.source_claim_identifier is not None:
            source_claim = graph.claim(edge.source_claim_identifier)
            context = f"{source_claim.raw}\n{target_claim.raw}"
        if file is not None:
            projection = project_semantic_span(
                file,
                target_claim.source,
                result_identifiers=result_identifiers,
            )
            dependency_path = _root_path(frontend.parse(projection.text))
        reason = (
            "explicit conclusion wording and local dependency structure permit a prior-claim "
            "support reading; lexical overlap alone is not enough for confidence"
        )
    else:
        if file is not None:
            projection = project_semantic_span(
                file,
                target_claim.source,
                result_identifiers=result_identifiers,
            )
            document = frontend.parse(projection.text)
            placeholder = next(
                (
                    item
                    for item in projection.placeholders
                    if item.source.start_offset == edge.source.start_offset
                    and item.source.end_offset == edge.source.end_offset
                    and item.label == edge.target_label
                ),
                None,
            )
            if placeholder is not None:
                token = document.token_by_text(placeholder.token)
                if token is not None:
                    dependency_path = document.root_path_signature(token.index)
        reason = (
            "explicit reference wording and local dependency structure permit a support "
            "reading; support versus exposition remains unresolved offline"
        )

    return StructuralEvidence(
        reason=reason,
        source=edge.source,
        target=target_claim.source,
        context=context,
        dependency_path=dependency_path,
        frontend=frontend.name,
    )


def apply_linguistic_uncertainty(
    project: ParsedProject,
    regions: list[ResultRegion],
    graph: ProofSupportGraph,
    frontend: LinguisticFrontend,
) -> ProofSupportGraph:
    """Keep cue-only relations as candidates when local NLP is enabled.

    The legacy #19 extractor remains unchanged for core/offline compatibility.
    With a linguistic frontend present, cue-only conclusion/reference edges are
    not allowed to become deterministic premises merely because a familiar word
    appeared. Their exact source relation is retained, enriched with parser-neutral
    evidence, and marked ambiguous/unresolved for later targeted review.
    """

    result_identifiers = {region.identifier for region in regions}
    edges: list[SupportEdge] = []
    for edge in graph.edges:
        if (
            edge.status != InferenceStatus.CONFIDENT
            or edge.kind not in _CUE_ONLY_KINDS
            or edge.evidence
        ):
            edges.append(edge)
            continue

        evidence = _evidence_for(
            project,
            graph,
            edge,
            result_identifiers,
            frontend,
        )
        status = (
            InferenceStatus.AMBIGUOUS
            if evidence.dependency_path
            else InferenceStatus.UNRESOLVED
        )
        edges.append(
            edge.model_copy(
                update={
                    "confidence": None,
                    "status": status,
                    "evidence": [evidence],
                }
            )
        )

    return graph.model_copy(update={"edges": edges})
