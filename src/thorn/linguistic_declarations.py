from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import FrontendFile, ParsedProject, SourceSpan
from thorn.linguistic import LinguisticDocument, LinguisticFrontend, LinguisticToken
from thorn.source_projection import LinguisticProjection, build_linguistic_projection
from thorn.symbols import ResultRegion


class ProseDeclarationRole(StrEnum):
    DEFINITION = "definition"
    AMBIENT = "ambient"


class ProseDeclarationCapability(StrEnum):
    """How completely Thorn could obtain grammatical declaration evidence."""

    COMPLETE = "complete"
    REDUCED = "reduced"
    PARTIAL = "partial"


class ProseDeclarationCandidate(BaseModel):
    """Non-authoritative grammatical evidence for one prose declaration occurrence."""

    identifier: str
    role: ProseDeclarationRole
    term: str
    term_source: SourceSpan
    source: SourceSpan
    # Exact sentence tail that the grammatical frontend identified as the
    # proposed defining payload. Mathematical authority remains a Thorn policy
    # decision; this span merely prevents the authority layer from rebuilding
    # grammar or guessing where a complement begins.
    payload_source: SourceSpan | None = None
    status: InferenceStatus = InferenceStatus.AMBIGUOUS
    evidence: list[StructuralEvidence] = Field(default_factory=list)


class ProseDeclarationInventory(BaseModel):
    """Project-level output of the optional linguistic declaration-candidate layer."""

    capability: ProseDeclarationCapability
    frontend: str | None = None
    candidates: list[ProseDeclarationCandidate] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class LinguisticDeclarationProposal:
    """Backend-independent proposal in offsets of a LinguisticDocument."""

    role: ProseDeclarationRole
    term: str
    term_start: int
    term_end: int
    term_token_index: int
    anchor_start: int
    anchor_end: int
    payload_start: int
    sentence_index: int
    evidence: str


_NAMED_CUES = {"call", "term", "say", "mean"}
_AMBIENT_PREFIXES = (
    "throughout",
    "in what follows",
    "henceforth",
    "unless stated otherwise",
    "unless specified otherwise",
    "for the remainder",
)
_CONDITION_WORDS = {"if", "when", "whenever", "provided"}
_CONTENT_POS = {"ADJ", "NOUN", "PROPN"}


def _sentences(document: LinguisticDocument) -> list[list[LinguisticToken]]:
    grouped: dict[int, list[LinguisticToken]] = defaultdict(list)
    for token in document.tokens:
        grouped[token.sentence_index].append(token)
    return [grouped[index] for index in sorted(grouped)]


def _content_before(
    tokens: list[LinguisticToken], boundary: int
) -> LinguisticToken | None:
    candidates = [
        token
        for token in tokens
        if token.index < boundary
        and token.pos in _CONTENT_POS
        and token.dependency not in {"nsubj", "nsubjpass", "pobj"}
    ]
    return candidates[-1] if candidates else None


def _subject(tokens: list[LinguisticToken]) -> LinguisticToken | None:
    subjects = [
        token
        for token in tokens
        if token.dependency in {"nsubj", "nsubjpass"} and token.pos in {"NOUN", "PROPN"}
    ]
    return subjects[-1] if subjects else None


def _mean_term(
    tokens: list[LinguisticToken], cue: LinguisticToken
) -> tuple[str, int, int, int] | None:
    prior = [
        token
        for token in tokens
        if token.index < cue.index and token.pos in _CONTENT_POS
    ]
    modifiers = [
        token for token in prior if token.dependency in {"amod", "acomp", "attr", "oprd"}
    ]
    if modifiers:
        modifier = modifiers[-1]
        heads = [
            token
            for token in prior
            if token.index == modifier.head_index and token.pos in {"NOUN", "PROPN"}
        ]
        if heads:
            head = heads[0]
            start, end = min(modifier.start, head.start), max(modifier.end, head.end)
            pieces = sorted((modifier, head), key=lambda token: token.start)
            return " ".join(piece.text for piece in pieces), start, end, head.index
        return modifier.text, modifier.start, modifier.end, modifier.index
    if prior:
        token = prior[-1]
        return token.text, token.start, token.end, token.index
    return None


def _negated(tokens: list[LinguisticToken], anchor: LinguisticToken) -> bool:
    return any(
        token.dependency == "neg"
        and (token.head_index == anchor.index or abs(token.index - anchor.index) <= 3)
        for token in tokens
    ) or any(
        token.text.casefold() == "not" and abs(token.index - anchor.index) <= 3
        for token in tokens
    )


def _proposal(
    *,
    role: ProseDeclarationRole,
    term: str,
    term_start: int,
    term_end: int,
    term_token_index: int,
    anchor: LinguisticToken,
    payload_start: int,
    evidence: str,
) -> LinguisticDeclarationProposal:
    return LinguisticDeclarationProposal(
        role=role,
        term=term,
        term_start=term_start,
        term_end=term_end,
        term_token_index=term_token_index,
        anchor_start=anchor.start,
        anchor_end=anchor.end,
        payload_start=payload_start,
        sentence_index=anchor.sentence_index,
        evidence=evidence,
    )


def propose_linguistic_declarations(
    document: LinguisticDocument,
) -> list[LinguisticDeclarationProposal]:
    """Propose prose declarations using the bounded #160 hybrid grammar.

    This function consumes only Thorn-normalized linguistic tokens. It does not
    establish mathematical authority, scope, relevance, dependency identity, or truth.
    """

    out: list[LinguisticDeclarationProposal] = []
    for tokens in _sentences(document):
        if not tokens:
            continue
        sentence_start = min(token.start for token in tokens)
        sentence_end = max(token.end for token in tokens)
        sentence_text = document.text[sentence_start:sentence_end].strip().casefold()
        conditions = [
            token for token in tokens if token.text.casefold() in _CONDITION_WORDS
        ]
        cues = [token for token in tokens if token.lemma.casefold() in _NAMED_CUES]
        subject_words = {
            token.text.casefold()
            for token in tokens
            if token.dependency in {"nsubj", "nsubjpass"}
        }

        for condition in conditions:
            preceding_cues = [cue for cue in cues if cue.index < condition.index]
            cue = preceding_cues[-1] if preceding_cues else None
            exact_tokens = [
                token
                for token in tokens
                if token.text.casefold() == "exactly" and token.index < condition.index
            ]
            copular_exact = (
                any(
                    token.lemma.casefold() == "be" and token.index < condition.index
                    for token in tokens
                )
                and bool(exact_tokens)
            )
            if cue is None and not copular_exact:
                continue
            if cue is not None:
                if _negated(tokens, cue):
                    continue
                lemma = cue.lemma.casefold()
                passive = any(
                    token.dependency in {"auxpass", "nsubjpass"} for token in tokens
                )
                if lemma == "say" and "we" not in subject_words and not passive:
                    continue
                if lemma in {"call", "term"}:
                    first_person = "we" in subject_words
                    if not passive and not first_person:
                        continue
                anchor = cue
            else:
                anchor = exact_tokens[-1]

            term = _content_before(tokens, condition.index)
            if term is None:
                continue
            out.append(
                _proposal(
                    role=ProseDeclarationRole.DEFINITION,
                    term=term.text,
                    term_start=term.start,
                    term_end=term.end,
                    term_token_index=term.index,
                    anchor=anchor,
                    payload_start=condition.end,
                    evidence=(
                        "dependency+definition-anchor"
                        if cue is not None
                        else "dependency+exact-copular-anchor"
                    ),
                )
            )

        for cue in [token for token in cues if token.lemma.casefold() == "mean"]:
            if _negated(tokens, cue) or "we" not in subject_words:
                continue
            mean_term = _mean_term(tokens, cue)
            if mean_term is None:
                continue
            term_text, start, end, term_token_index = mean_term
            out.append(
                _proposal(
                    role=ProseDeclarationRole.DEFINITION,
                    term=term_text,
                    term_start=start,
                    term_end=end,
                    term_token_index=term_token_index,
                    anchor=cue,
                    payload_start=cue.end,
                    evidence="dependency+mean-anchor",
                )
            )

        if sentence_text.startswith(_AMBIENT_PREFIXES):
            subject = _subject(tokens)
            copulas = [token for token in tokens if token.lemma.casefold() == "be"]
            if subject is not None and copulas:
                anchor = min(tokens, key=lambda token: token.start)
                copula = min(
                    (token for token in copulas if token.start >= subject.end),
                    key=lambda token: token.start,
                    default=copulas[0],
                )
                out.append(
                    _proposal(
                        role=ProseDeclarationRole.AMBIENT,
                        term=subject.text,
                        term_start=subject.start,
                        term_end=subject.end,
                        term_token_index=subject.index,
                        anchor=anchor,
                        payload_start=copula.end,
                        evidence="dependency+ambient-anchor",
                    )
                )

    unique: dict[tuple[ProseDeclarationRole, int, int], LinguisticDeclarationProposal] = {}
    for candidate in out:
        unique[(candidate.role, candidate.term_start, candidate.term_end)] = candidate
    return sorted(
        unique.values(),
        key=lambda item: (item.term_start, item.role.value, item.term.casefold()),
    )


def _overlaps_result(span: SourceSpan, regions: list[ResultRegion]) -> bool:
    for region in regions:
        spans = [region.statement_span]
        if region.proof_span is not None:
            spans.append(region.proof_span)
        if any(
            span.start_offset < candidate.end_offset
            and candidate.start_offset < span.end_offset
            for candidate in spans
        ):
            return True
    return False


def _candidate_from_proposal(
    *,
    file: FrontendFile,
    projection: LinguisticProjection,
    document: LinguisticDocument,
    frontend: LinguisticFrontend,
    proposal: LinguisticDeclarationProposal,
) -> ProseDeclarationCandidate | None:
    term_source = projection.source_span(proposal.term_start, proposal.term_end)
    if projection.text[proposal.term_start : proposal.term_end] != term_source.text(file.raw):
        return None
    source = projection.sentence_span(proposal.anchor_start)
    if not (source.start_offset <= proposal.payload_start <= source.end_offset):
        return None
    payload_source = projection.source_span(proposal.payload_start, source.end_offset)
    anchor_source = projection.source_span(proposal.anchor_start, proposal.anchor_end)
    try:
        dependency_path = document.root_path_signature(proposal.term_token_index)
    except KeyError:
        dependency_path = []
    return ProseDeclarationCandidate(
        identifier=(
            f"prose-candidate:{proposal.role.value}:{file.path}:"
            f"{term_source.start_offset}"
        ),
        role=proposal.role,
        term=term_source.text(file.raw),
        term_source=term_source,
        source=source,
        payload_source=payload_source,
        status=InferenceStatus.AMBIGUOUS,
        evidence=[
            StructuralEvidence(
                reason=(
                    f"{proposal.evidence}; grammatical declaration evidence is "
                    "non-authoritative until Thorn adjudicates it"
                ),
                source=anchor_source,
                target=term_source,
                context=source.text(file.raw),
                dependency_path=dependency_path,
                frontend=frontend.name,
            )
        ],
    )


def collect_project_prose_declarations(
    project: ParsedProject,
    regions: list[ResultRegion],
    frontend: LinguisticFrontend | None,
) -> ProseDeclarationInventory:
    """Build the project-level non-authoritative prose declaration inventory."""

    if frontend is None:
        return ProseDeclarationInventory(
            capability=ProseDeclarationCapability.REDUCED,
            reasons=[
                "no LinguisticFrontend is configured; prose declaration candidates are unavailable"
            ],
        )

    projections = {file.path: build_linguistic_projection(file) for file in project.files}
    partial = [projection for projection in projections.values() if not projection.complete]
    if partial:
        return ProseDeclarationInventory(
            capability=ProseDeclarationCapability.PARTIAL,
            frontend=frontend.name,
            reasons=[
                (
                    f"{projection.file.path}: "
                    f"{projection.partial_reason or 'partial source projection'}"
                )
                for projection in partial
            ],
        )

    regions_by_file: dict[str, list[ResultRegion]] = defaultdict(list)
    for region in regions:
        regions_by_file[region.file].append(region)

    candidates: list[ProseDeclarationCandidate] = []
    for file in project.files:
        projection = projections[file.path]
        document = frontend.parse(projection.text)
        for proposal in propose_linguistic_declarations(document):
            candidate = _candidate_from_proposal(
                file=file,
                projection=projection,
                document=document,
                frontend=frontend,
                proposal=proposal,
            )
            if candidate is None or _overlaps_result(candidate.source, regions_by_file[file.path]):
                continue
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            item.source.file,
            item.source.start_offset,
            item.term_source.start_offset,
        )
    )
    return ProseDeclarationInventory(
        capability=ProseDeclarationCapability.COMPLETE,
        frontend=frontend.name,
        candidates=candidates,
    )
