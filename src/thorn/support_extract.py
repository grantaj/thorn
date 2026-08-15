from __future__ import annotations

import re
from pathlib import Path

from thorn.evidence import InferenceStatus, StructuralEvidence
from thorn.frontend import FrontendFile, FrontendMacro, ParsedProject, SourceSpan
from thorn.linguistic import LinguisticDocument, LinguisticFrontend
from thorn.semantic_projection import (
    SemanticPlaceholder,
    SemanticPlaceholderKind,
    project_semantic_span,
)
from thorn.support import (
    BoundName,
    Claim,
    ClaimForm,
    ClaimQualifier,
    ProofSupportGraph,
    QualifierKind,
    SupportEdge,
    SupportKind,
)
from thorn.symbols import ResultRegion

_SENTENCE_RE = re.compile(r".*?(?:[.!?](?=\s|$)|\n\s*\n|$)", re.DOTALL)
_TRAILING_BINDER_RE = re.compile(
    r"^\s*for\s+(?:every|all|each)\s+\$?\s*([A-Za-z](?:_[A-Za-z0-9{}]+)?)",
    re.IGNORECASE,
)
_TRAILING_BINDER_CANDIDATE_RE = re.compile(r"^\s*(?:for|where|given)\b", re.IGNORECASE)
_CONCLUSION_RE = re.compile(r"^\s*(?:therefore|hence|thus|consequently)\b", re.IGNORECASE)
_SINCE_RE = re.compile(r"^\s*since\s+(.+?),\s*(.+)$", re.IGNORECASE | re.DOTALL)
_BY_DEFINITION_RE = re.compile(r"\bby\s+(?:the\s+)?definition\b", re.IGNORECASE)
_NAMED_PROPERTY_RE = re.compile(
    r"\bby\s+(compactness|continuity|linearity|monotonicity|convexity)\b",
    re.IGNORECASE,
)
_REFERENCE_SUPPORT_CUE_RE = re.compile(
    r"\b(?:by|from|using|apply|applying|invoke|invoking)\b",
    re.IGNORECASE,
)
_BOUND_NAME_RE = re.compile(
    r"(?P<name>\\[A-Za-z]+|[A-Za-z](?:_(?:\{[^{}]+\}|[A-Za-z0-9]+))?)"
)
_REF_MACROS = {"ref", "eqref", "autoref", "cref", "Cref"}


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _span(file: FrontendFile, start: int, end: int) -> SourceSpan:
    start_line, start_column = _line_column(file.raw, start)
    end_line, end_column = _line_column(file.raw, end)
    return SourceSpan(
        file=file.path,
        start_offset=start,
        end_offset=end,
        start_line=start_line,
        start_column=start_column,
        end_line=end_line,
        end_column=end_column,
    )


def _proof_body_span(file: FrontendFile, region: ResultRegion) -> SourceSpan | None:
    if region.proof_span is None:
        return None
    for environment in file.environments:
        if (
            environment.name == "proof"
            and environment.span.start_offset == region.proof_span.start_offset
            and environment.span.end_offset == region.proof_span.end_offset
        ):
            return environment.body_span
    return None


def _display_math_spans(file: FrontendFile, body: SourceSpan) -> list[SourceSpan]:
    return [
        item.span
        for item in file.math
        if item.span.start_offset >= body.start_offset
        and item.span.end_offset <= body.end_offset
        and item.delimiter not in {"$", "\\(\\)"}
    ]


def _sentence_spans(file: FrontendFile, start: int, end: int) -> list[SourceSpan]:
    text = file.raw[start:end]
    spans: list[SourceSpan] = []
    for match in _SENTENCE_RE.finditer(text):
        raw = match.group(0)
        if not raw.strip():
            continue
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        absolute_start = start + match.start() + left
        absolute_end = start + match.start() + right
        if absolute_end > absolute_start:
            spans.append(_span(file, absolute_start, absolute_end))
    return spans


def _claim_spans(file: FrontendFile, body: SourceSpan) -> list[tuple[SourceSpan, ClaimForm]]:
    displays = _display_math_spans(file, body)
    pieces: list[tuple[SourceSpan, ClaimForm]] = []
    cursor = body.start_offset
    for display in displays:
        if cursor < display.start_offset:
            pieces.extend(
                (span, ClaimForm.PROSE)
                for span in _sentence_spans(file, cursor, display.start_offset)
            )
        pieces.append((display, ClaimForm.DISPLAY))
        cursor = display.end_offset
    if cursor < body.end_offset:
        pieces.extend(
            (span, ClaimForm.PROSE)
            for span in _sentence_spans(file, cursor, body.end_offset)
        )
    return sorted(pieces, key=lambda item: item[0].start_offset)


def _first_required_argument(macro: FrontendMacro) -> str | None:
    for argument in macro.arguments:
        if not argument.optional:
            return argument.value.strip()
    return None


def _macros_in_span(file: FrontendFile, span: SourceSpan) -> list[FrontendMacro]:
    return [
        macro
        for macro in file.macros
        if macro.name in _REF_MACROS
        and macro.span.start_offset >= span.start_offset
        and macro.span.end_offset <= span.end_offset
    ]


def _reference_is_explicit_support(
    file: FrontendFile,
    claim: Claim,
    macro: FrontendMacro,
) -> bool:
    prefix = file.raw[claim.source.start_offset : macro.span.start_offset]
    # Keep the cue local to the reference rather than treating an unrelated
    # word near the start of a long sentence as evidence for every later ref.
    return _REFERENCE_SUPPORT_CUE_RE.search(prefix[-96:]) is not None


def _add_edge(
    edges: list[SupportEdge],
    *,
    target: Claim,
    kind: SupportKind,
    source: SourceSpan,
    raw: str,
    source_claim_identifier: str | None = None,
    target_label: str | None = None,
    named_property: str | None = None,
    explicit: bool = True,
    confidence: float | None = 1.0,
    status: InferenceStatus = InferenceStatus.CONFIDENT,
    evidence: list[StructuralEvidence] | None = None,
) -> None:
    edges.append(
        SupportEdge(
            identifier=f"{target.identifier}:support:{len(edges) + 1}",
            target_claim_identifier=target.identifier,
            kind=kind,
            source=source,
            raw_justification=raw,
            source_claim_identifier=source_claim_identifier,
            target_label=target_label,
            named_property=named_property,
            explicit=explicit,
            confidence=confidence,
            status=status,
            evidence=evidence or [],
        )
    )


def _attach_explicit_support(
    file: FrontendFile,
    claim: Claim,
    result_identifiers: set[str],
    previous_claim: Claim | None,
    edges: list[SupportEdge],
) -> None:
    raw = claim.raw.strip()

    for macro in _macros_in_span(file, claim.source):
        if not _reference_is_explicit_support(file, claim, macro):
            continue
        labels = _first_required_argument(macro)
        if not labels:
            continue
        for label in (item.strip() for item in labels.split(",")):
            if not label:
                continue
            if macro.name == "eqref":
                kind = SupportKind.EQUATION_REFERENCE
            elif label in result_identifiers:
                kind = SupportKind.RESULT_REFERENCE
            else:
                # A plain non-result \ref may be a section, figure, table, or
                # equation. Do not guess that it is mathematical support.
                continue
            _add_edge(
                edges,
                target=claim,
                kind=kind,
                source=macro.span,
                raw=macro.raw,
                target_label=label,
            )

    definition = _BY_DEFINITION_RE.search(raw)
    if definition is not None:
        start = claim.source.start_offset + definition.start()
        end = claim.source.start_offset + definition.end()
        _add_edge(
            edges,
            target=claim,
            kind=SupportKind.DEFINITION,
            source=_span(file, start, end),
            raw=definition.group(0),
        )

    for property_match in _NAMED_PROPERTY_RE.finditer(raw):
        start = claim.source.start_offset + property_match.start()
        end = claim.source.start_offset + property_match.end()
        _add_edge(
            edges,
            target=claim,
            kind=SupportKind.NAMED_PROPERTY,
            source=_span(file, start, end),
            raw=property_match.group(0),
            named_property=property_match.group(1).lower(),
        )

    since = _SINCE_RE.match(raw)
    if since is not None:
        reason = since.group(1).strip()
        reason_start = raw.find(since.group(1))
        absolute_start = claim.source.start_offset + reason_start
        _add_edge(
            edges,
            target=claim,
            kind=SupportKind.EXPLICIT_REASON,
            source=_span(file, absolute_start, absolute_start + len(since.group(1))),
            raw=reason,
        )

    if previous_claim is not None and _CONCLUSION_RE.match(raw):
        cue = _CONCLUSION_RE.match(raw)
        assert cue is not None
        _add_edge(
            edges,
            target=claim,
            kind=SupportKind.PRIOR_CLAIM,
            source=_span(
                file,
                claim.source.start_offset + cue.start(),
                claim.source.start_offset + cue.end(),
            ),
            raw=cue.group(0).strip(),
            source_claim_identifier=previous_claim.identifier,
        )


def _projection_document(
    file: FrontendFile,
    span: SourceSpan,
    result_identifiers: set[str],
    frontend: LinguisticFrontend,
) -> tuple[LinguisticDocument, list[SemanticPlaceholder]]:
    projection = project_semantic_span(
        file,
        span,
        result_identifiers=result_identifiers,
    )
    return frontend.parse(projection.text), projection.placeholders


def _placeholder_path(
    document: LinguisticDocument,
    placeholder: SemanticPlaceholder,
) -> list[str]:
    token = document.token_by_text(placeholder.token)
    if token is None:
        return []
    return document.root_path_signature(token.index)


def _attach_linguistic_reference_candidates(
    file: FrontendFile,
    claim: Claim,
    result_identifiers: set[str],
    frontend: LinguisticFrontend,
    edges: list[SupportEdge],
) -> None:
    document, placeholders = _projection_document(
        file,
        claim.source,
        result_identifiers,
        frontend,
    )
    for placeholder in placeholders:
        if placeholder.kind == SemanticPlaceholderKind.RESULT_REFERENCE:
            kind = SupportKind.RESULT_REFERENCE
        elif placeholder.kind == SemanticPlaceholderKind.EQUATION_REFERENCE:
            kind = SupportKind.EQUATION_REFERENCE
        else:
            continue
        if any(
            edge.target_claim_identifier == claim.identifier
            and edge.kind == kind
            and edge.target_label == placeholder.label
            for edge in edges
        ):
            continue

        dependency_path = _placeholder_path(document, placeholder)
        status = (
            InferenceStatus.AMBIGUOUS if dependency_path else InferenceStatus.UNRESOLVED
        )
        _add_edge(
            edges,
            target=claim,
            kind=kind,
            source=placeholder.source,
            raw=placeholder.raw,
            target_label=placeholder.label,
            explicit=False,
            confidence=None,
            status=status,
            evidence=[
                StructuralEvidence(
                    reason=(
                        "typed mathematical reference is grammatically attached inside "
                        "the claim; support versus exposition remains unresolved"
                    ),
                    source=placeholder.source,
                    target=claim.source,
                    context=claim.raw,
                    dependency_path=dependency_path,
                    frontend=frontend.name,
                )
            ],
        )


def _attach_adjacent_claim_candidate(
    claim: Claim,
    previous_claim: Claim | None,
    result_identifiers: set[str],
    file: FrontendFile,
    frontend: LinguisticFrontend,
    edges: list[SupportEdge],
) -> None:
    if previous_claim is None:
        return
    if any(
        edge.target_claim_identifier == claim.identifier
        and edge.status == InferenceStatus.CONFIDENT
        for edge in edges
    ):
        return
    if any(
        edge.target_claim_identifier == claim.identifier
        and edge.kind == SupportKind.PRIOR_CLAIM
        for edge in edges
    ):
        return

    document, _ = _projection_document(file, claim.source, result_identifiers, frontend)
    roots = [
        token
        for token in document.tokens
        if token.head_index == token.index and token.pos in {"VERB", "AUX"}
    ]
    root_path = document.root_path_signature(roots[0].index) if roots else []
    status = InferenceStatus.AMBIGUOUS if root_path else InferenceStatus.UNRESOLVED
    if root_path:
        reason = (
            "adjacent claim and dependency-root structure permit a conclusion reading; "
            "semantic dependence is not resolved offline"
        )
    else:
        reason = (
            "adjacent claims remain a possible local support relation even though the "
            "linguistic parse has no verbal root; semantic dependence is unresolved"
        )
    _add_edge(
        edges,
        target=claim,
        kind=SupportKind.PRIOR_CLAIM,
        source=previous_claim.source,
        raw=previous_claim.raw,
        source_claim_identifier=previous_claim.identifier,
        explicit=False,
        confidence=None,
        status=status,
        evidence=[
            StructuralEvidence(
                reason=reason,
                source=previous_claim.source,
                target=claim.source,
                context=f"{previous_claim.raw}\n{claim.raw}",
                dependency_path=root_path,
                frontend=frontend.name,
            )
        ],
    )


def _qualifier_for(
    file: FrontendFile,
    claim: Claim,
    raw: str,
    source: SourceSpan,
) -> ClaimQualifier | None:
    match = _TRAILING_BINDER_RE.match(raw)
    if match is None:
        return None
    name = match.group(1)
    local_start = raw.find(name, match.start(1))
    absolute_start = source.start_offset + local_start
    bound_source = _span(file, absolute_start, absolute_start + len(name))
    qualifier_id = f"{claim.identifier}:qualifier:{len(claim.qualifiers) + 1}"
    return ClaimQualifier(
        identifier=qualifier_id,
        kind=QualifierKind.TRAILING_BINDER,
        raw=raw.strip(),
        source=source,
        bound_names=[
            BoundName(
                identifier=f"{qualifier_id}:bound:1",
                name=name,
                source=bound_source,
            )
        ],
    )


def _ambiguous_qualifier_for(
    file: FrontendFile,
    claim: Claim,
    raw: str,
    source: SourceSpan,
    result_identifiers: set[str],
    frontend: LinguisticFrontend,
) -> ClaimQualifier | None:
    if _TRAILING_BINDER_CANDIDATE_RE.match(raw) is None:
        return None

    document, placeholders = _projection_document(
        file,
        source,
        result_identifiers,
        frontend,
    )
    math_placeholders = [
        placeholder
        for placeholder in placeholders
        if placeholder.kind == SemanticPlaceholderKind.MATH
    ]
    if len(math_placeholders) != 1:
        return None

    placeholder = math_placeholders[0]
    match = _BOUND_NAME_RE.search(placeholder.raw)
    bound_names: list[BoundName] = []
    qualifier_id = f"{claim.identifier}:qualifier:{len(claim.qualifiers) + 1}"
    if match is not None:
        name = match.group("name")
        name_source = _span(
            file,
            placeholder.source.start_offset + match.start("name"),
            placeholder.source.start_offset + match.end("name"),
        )
        bound_names.append(
            BoundName(
                identifier=f"{qualifier_id}:bound:1",
                name=name,
                source=name_source,
            )
        )

    dependency_path = _placeholder_path(document, placeholder)
    status = InferenceStatus.AMBIGUOUS if dependency_path else InferenceStatus.UNRESOLVED
    return ClaimQualifier(
        identifier=qualifier_id,
        kind=QualifierKind.TRAILING_BINDER,
        raw=raw.strip(),
        source=source,
        bound_names=bound_names,
        status=status,
        evidence=[
            StructuralEvidence(
                reason=(
                    "binder-shaped prose immediately trailing a display contains one "
                    "grammatically attached mathematical entity and may qualify the display"
                ),
                source=placeholder.source,
                target=claim.source,
                context=f"{claim.raw}\n{raw.strip()}",
                dependency_path=dependency_path,
                frontend=frontend.name,
            )
        ],
    )


def extract_proof_support_graph(
    project: ParsedProject,
    regions: list[ResultRegion],
    *,
    linguistic_frontend: LinguisticFrontend | None = None,
) -> ProofSupportGraph:
    """Recover an explicit-first proof skeleton with optional local NLP candidates."""

    files = {file.path: file for file in project.files}
    result_identifiers = {region.identifier for region in regions}
    claims: list[Claim] = []
    edges: list[SupportEdge] = []

    for region in regions:
        file = files.get(str(Path(region.file).resolve())) or files.get(region.file)
        if file is None:
            continue
        body = _proof_body_span(file, region)
        if body is None:
            continue

        result_claims: list[Claim] = []
        for span, form in _claim_spans(file, body):
            raw = span.text(file.raw)
            if form == ClaimForm.PROSE and result_claims:
                qualifier = _qualifier_for(file, result_claims[-1], raw, span)
                if qualifier is not None and result_claims[-1].form == ClaimForm.DISPLAY:
                    updated = result_claims[-1].model_copy(
                        update={"qualifiers": [*result_claims[-1].qualifiers, qualifier]}
                    )
                    result_claims[-1] = updated
                    claims[-1] = updated
                    continue
                if (
                    linguistic_frontend is not None
                    and result_claims[-1].form == ClaimForm.DISPLAY
                ):
                    qualifier = _ambiguous_qualifier_for(
                        file,
                        result_claims[-1],
                        raw,
                        span,
                        result_identifiers,
                        linguistic_frontend,
                    )
                    if qualifier is not None:
                        updated = result_claims[-1].model_copy(
                            update={"qualifiers": [*result_claims[-1].qualifiers, qualifier]}
                        )
                        result_claims[-1] = updated
                        claims[-1] = updated

            claim = Claim(
                identifier=f"{region.identifier}:claim:{len(result_claims) + 1}",
                result_identifier=region.identifier,
                form=form,
                raw=raw.strip(),
                source=span,
            )
            previous = result_claims[-1] if result_claims else None
            result_claims.append(claim)
            claims.append(claim)
            _attach_explicit_support(
                file,
                claim,
                result_identifiers,
                previous,
                edges,
            )
            if linguistic_frontend is not None and form == ClaimForm.PROSE:
                _attach_linguistic_reference_candidates(
                    file,
                    claim,
                    result_identifiers,
                    linguistic_frontend,
                    edges,
                )
                _attach_adjacent_claim_candidate(
                    claim,
                    previous,
                    result_identifiers,
                    file,
                    linguistic_frontend,
                    edges,
                )

    return ProofSupportGraph(claims=claims, edges=edges)
