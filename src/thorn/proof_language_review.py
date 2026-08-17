from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from typing import Annotated, Any, Literal, Protocol, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

from thorn.llm_proof_language import (
    DEFAULT_MAX_SOURCE_REQUESTS,
    LLMProofLanguage,
    parse_source_rescue_request,
    render_source_rescue,
)
from thorn.models import AttackReport, CandidateFinding

PROTOCOL_VERSION: Literal["thorn-proof-review/2"] = "thorn-proof-review/2"
PROMPT_VERSION: Literal["proof_language_reviewer_v2"] = "proof_language_reviewer_v2"
Representation = Literal["raw", "thorn-proof/1"]
ReviewStage = Literal["initial", "rescue"]
ReviewAction = Literal["review", "need_source"]
ReviewItemKind = Literal["question", "concern"]
ReviewDispositionStatus = Literal["confirmed", "revised", "discharged", "unresolved"]
SourceAddress = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9:._-]*$"),
]
ReviewItemId = Annotated[
    str,
    StringConstraints(pattern=r"^RV[1-9][0-9]*$"),
]

_SOURCE_HANDLE_RE = re.compile(
    r"@([A-Za-z][A-Za-z0-9:._-]*(?:,[A-Za-z][A-Za-z0-9:._-]*)*)"
)
_OBLIGATION_CONTEXT_RE = re.compile(
    r"^(?:HOLE|GOAL)\s+\S+\s+([A-Za-z][A-Za-z0-9:._-]*):"
    r".*?\|\s*ctx\s+([^|]+?)\s*\|"
)

_PROOF_IR_REVIEW_POLICY = (
    "REVIEW_POLICY unresolved Proof-IR recovery markers (?, ~, HOLE, NEED) are "
    "not mathematical defects. Use source rescue when needed. Never report a "
    "defect solely because deterministic recovery remains unresolved."
)
_FINAL_RESCUE_POLICY = (
    "FINAL_RESCUE_POLICY source rescue is now exhausted. Treat supplied source as "
    "new evidence for the carried review state. Every carried review item must receive "
    "exactly one disposition; new findings may also be reported. Use unresolved when "
    "the bounded evidence still does not settle an item; unresolved is not a mathematical "
    "finding. If deterministic recovery remains unresolved, do not convert that uncertainty "
    "into a mathematical finding unless the supplied mathematical content itself establishes "
    "the defect."
)


def _source_addresses_in_text(text: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for match in _SOURCE_HANDLE_RE.finditer(text):
        for address in match.group(1).split(","):
            seen.setdefault(address, None)
    return tuple(seen)


def advertised_source_addresses(document: LLMProofLanguage) -> tuple[str, ...]:
    """Return the canonical finite set of source handles advertised to review."""

    return tuple(sorted(_source_addresses_in_text(document.render_initial())))


def _expanded_source_addresses(
    document: LLMProofLanguage,
    requested: tuple[str, ...],
    *,
    advertised: tuple[str, ...],
) -> tuple[str, ...]:
    """Expand requested source to unresolved Proof-IR prerequisite context.

    ``HOLE`` and ``GOAL`` lines already expose the deterministic local context of
    unresolved propositions. When the model asks for a proposition's exact
    source, include the exact source for unresolved context propositions first.
    This is a bounded source-selection operation over the existing proof-language
    packet; it does not infer any new mathematical edge.

    ``advertised`` is the initial turn's stored closed-world contract. It is
    deliberately passed in rather than recomputed so schema generation, runtime
    validation, rescue expansion, fingerprinting, and replay share one set.
    """

    contexts: dict[str, tuple[str, ...]] = {}
    proposition_source: dict[str, str] = {}
    for line in document.lines:
        match = _OBLIGATION_CONTEXT_RE.match(line)
        if match is None:
            continue
        proposition = match.group(1)
        raw_context = match.group(2).strip()
        contexts[proposition] = tuple(
            item.strip()
            for item in raw_context.split(",")
            if item.strip() and item.strip() != "-"
        )
        handles = _source_addresses_in_text(line)
        if proposition in handles:
            proposition_source[proposition] = proposition
        elif handles:
            proposition_source[proposition] = handles[-1]

    source_proposition = {
        source: proposition for proposition, source in proposition_source.items()
    }
    advertised_set = set(advertised)
    expanded: list[str] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def add_source(address: str) -> None:
        if address in advertised_set and address not in expanded:
            expanded.append(address)

    def visit(proposition: str) -> None:
        if proposition in visited or proposition in visiting:
            return
        visiting.add(proposition)
        for dependency in contexts.get(proposition, ()):
            visit(dependency)
        visiting.remove(proposition)
        visited.add(proposition)
        source = proposition_source.get(proposition)
        if source is not None:
            add_source(source)
        else:
            # Global hypotheses/definitions are proposition addresses in ``ctx``
            # but do not have their own HOLE/GOAL line, so #86's original map
            # could not discover their exact source. If the proposition itself
            # is already an advertised source handle, it is a mechanically
            # reachable prerequisite and belongs in the same bounded closure.
            add_source(proposition)

    for address in requested:
        proposition = address if address in contexts else source_proposition.get(address)
        if proposition is None:
            add_source(address)
        else:
            visit(proposition)

    return tuple(expanded)


class ProofReviewProtocolError(RuntimeError):
    """Raised when a proof-language review violates Thorn's bounded protocol."""


class ProofReviewItem(BaseModel):
    """One local question or concern carried across the single rescue boundary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: ReviewItemId
    kind: ReviewItemKind
    summary: str = Field(min_length=1)


class ProofReviewDisposition(BaseModel):
    """Explicit final accounting for one carried review item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: ReviewItemId
    status: ReviewDispositionStatus
    explanation: str = Field(min_length=1)
    finding: CandidateFinding | None = None

    @model_validator(mode="after")
    def _validate_finding(self) -> ProofReviewDisposition:
        if self.status in {"discharged", "unresolved"} and self.finding is not None:
            raise ValueError(f"{self.status} review items must not produce a finding")
        if self.status in {"confirmed", "revised"} and self.finding is None:
            raise ValueError(f"{self.status} review items must produce a finding")
        return self


class ProofReviewModelResponse(BaseModel):
    """One structured model response in the proof-language review protocol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ReviewAction
    findings: tuple[CandidateFinding, ...] = ()
    source_addresses: tuple[SourceAddress, ...] = ()
    review_items: tuple[ProofReviewItem, ...] = ()
    source_review_item_ids: tuple[ReviewItemId, ...] = ()
    dispositions: tuple[ProofReviewDisposition, ...] = ()

    @model_validator(mode="after")
    def _validate_action_payload(self) -> ProofReviewModelResponse:
        if self.action == "review":
            if self.source_addresses:
                raise ValueError("review responses must not request source")
            if self.review_items or self.source_review_item_ids:
                raise ValueError("review responses must not introduce carried review state")
            return self
        if self.findings:
            raise ValueError("source requests must not include final findings")
        if self.dispositions:
            raise ValueError("source requests must not include final dispositions")
        if not self.source_addresses:
            raise ValueError("source requests must contain at least one address")
        if not self.review_items:
            raise ValueError("source requests must contain explicit review items")

        ids = tuple(item.id for item in self.review_items)
        expected = tuple(f"RV{index}" for index in range(1, len(ids) + 1))
        if ids != expected:
            raise ValueError(
                "review item identities must be the canonical sequence RV1, RV2, ..."
            )
        if not self.source_review_item_ids:
            raise ValueError("source requests must identify which review items motivate rescue")
        if len(set(self.source_review_item_ids)) != len(self.source_review_item_ids):
            raise ValueError("source-request review item identities must be unique")
        unknown = [item_id for item_id in self.source_review_item_ids if item_id not in ids]
        if unknown:
            raise ValueError(
                "source request references unknown review item identities: " + ", ".join(unknown)
            )
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


@lru_cache(maxsize=256)
def _carried_disposition_model(
    carried_review_item_ids: tuple[str, ...],
) -> type[ProofReviewDisposition]:
    item_literal: Any = cast(Any, Literal)[carried_review_item_ids]
    return create_model(
        "ProofReviewDisposition",
        __base__=ProofReviewDisposition,
        item_id=(item_literal, ...),
    )


@lru_cache(maxsize=256)
def _closed_world_response_model(
    allowed_source_addresses: tuple[str, ...],
    max_source_addresses: int,
    source_rescue_allowed: bool,
    stage: ReviewStage,
    carried_review_item_ids: tuple[str, ...],
) -> type[ProofReviewModelResponse]:
    """Build the existing response shape with request-specific protocol typing.

    Every array retains an explicit JSON-Schema ``items`` type, including arrays
    that are mechanically constrained to length zero. OpenAI Structured Outputs
    requires array schemas to declare ``items``; ``maxItems: 0`` still makes the
    empty tuple the only representable value and therefore preserves #88's
    closed-world source-selection contract.

    The generated class deliberately keeps the stable ``ProofReviewModelResponse``
    schema title. The fingerprint therefore records protocol content, not an
    incidental generated Python name.
    """

    empty_source_addresses = (
        tuple[SourceAddress, ...],
        Field(default=(), max_length=0),
    )
    empty_review_items = (
        tuple[ProofReviewItem, ...],
        Field(default=(), max_length=0),
    )
    empty_source_review_item_ids = (
        tuple[ReviewItemId, ...],
        Field(default=(), max_length=0),
    )
    empty_dispositions = (
        tuple[ProofReviewDisposition, ...],
        Field(default=(), max_length=0),
    )

    if stage == "rescue":
        disposition_model: Any = _carried_disposition_model(carried_review_item_ids)
        dispositions_type: Any = tuple[disposition_model, ...]
        return create_model(
            "ProofReviewModelResponse",
            __base__=ProofReviewModelResponse,
            action=(Literal["review"], ...),
            source_addresses=empty_source_addresses,
            review_items=empty_review_items,
            source_review_item_ids=empty_source_review_item_ids,
            dispositions=(
                dispositions_type,
                Field(
                    ...,
                    min_length=len(carried_review_item_ids),
                    max_length=len(carried_review_item_ids),
                ),
            ),
        )

    if not source_rescue_allowed or not allowed_source_addresses:
        return create_model(
            "ProofReviewModelResponse",
            __base__=ProofReviewModelResponse,
            action=(Literal["review"], ...),
            source_addresses=empty_source_addresses,
            review_items=empty_review_items,
            source_review_item_ids=empty_source_review_item_ids,
            dispositions=empty_dispositions,
        )

    address_literal: Any = cast(Any, Literal)[allowed_source_addresses]
    source_addresses_type: Any = tuple[address_literal, ...]
    return create_model(
        "ProofReviewModelResponse",
        __base__=ProofReviewModelResponse,
        source_addresses=(
            source_addresses_type,
            Field(default=(), max_length=max_source_addresses),
        ),
        dispositions=empty_dispositions,
    )


class ProofReviewTurnRequest(BaseModel):
    """Provider-neutral description of one transport turn and response contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal["thorn-proof-review/2"] = PROTOCOL_VERSION
    representation: Representation
    stage: ReviewStage
    initial_packet_fingerprint: str
    user_content: str
    source_rescue_allowed: bool
    allowed_source_addresses: tuple[SourceAddress, ...] = ()
    max_source_addresses: int = Field(
        default=DEFAULT_MAX_SOURCE_REQUESTS,
        ge=0,
        le=DEFAULT_MAX_SOURCE_REQUESTS,
    )
    requested_source_addresses: tuple[str, ...] = ()
    initial_user_content: str | None = None
    prior_response: ProofReviewModelResponse | None = None

    @field_validator("allowed_source_addresses", mode="before")
    @classmethod
    def _canonicalize_allowed_source_addresses(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted(set(value)))
        return value

    @model_validator(mode="after")
    def _validate_stage(self) -> ProofReviewTurnRequest:
        if self.stage == "initial" and self.requested_source_addresses:
            raise ValueError("initial turns cannot contain requested source addresses")
        if self.stage == "initial" and (
            self.initial_user_content is not None or self.prior_response is not None
        ):
            raise ValueError("initial turns cannot contain rescue transcript fields")
        if self.stage == "rescue" and not self.requested_source_addresses:
            raise ValueError("rescue turns require source addresses")
        if self.stage == "rescue" and (
            self.initial_user_content is None or self.prior_response is None
        ):
            raise ValueError("rescue turns require the exact initial turn and prior response")
        if self.stage == "rescue" and self.prior_response is not None:
            if self.prior_response.action != "need_source":
                raise ValueError("rescue prior response must be the source-request turn")
            if not self.prior_response.review_items:
                raise ValueError("rescue prior response must contain carried review state")
        if self.stage == "rescue" and self.source_rescue_allowed:
            raise ValueError("source rescue is exhausted after the first request")
        if self.stage == "rescue" and self.allowed_source_addresses:
            raise ValueError("rescue turns cannot advertise another source-selection universe")
        if not self.source_rescue_allowed and self.allowed_source_addresses:
            raise ValueError("disabled source rescue cannot expose selectable source addresses")
        if self.source_rescue_allowed and self.max_source_addresses < 1:
            raise ValueError("enabled source rescue requires a positive source-address cap")
        return self

    def carried_review_item_ids(self) -> tuple[str, ...]:
        """Return the exact local item identities carried by the rescue transcript."""

        if self.stage != "rescue" or self.prior_response is None:
            return ()
        return tuple(item.id for item in self.prior_response.review_items)

    def response_model(self) -> type[ProofReviewModelResponse]:
        """Return the structured-output model for this exact turn contract."""

        return _closed_world_response_model(
            self.allowed_source_addresses,
            self.max_source_addresses,
            self.source_rescue_allowed,
            self.stage,
            self.carried_review_item_ids(),
        )

    def response_schema(self) -> dict[str, object]:
        """Return the deterministic provider-neutral effective response schema."""

        return self.response_model().model_json_schema()


class ProofLanguageReviewRequest(BaseModel):
    """Thorn-owned request for semantic review over one ``thorn-proof/1`` packet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal["thorn-proof-review/2"] = PROTOCOL_VERSION
    document: LLMProofLanguage
    allow_source_rescue: bool = True
    max_source_addresses: int = Field(
        default=DEFAULT_MAX_SOURCE_REQUESTS,
        ge=1,
        le=DEFAULT_MAX_SOURCE_REQUESTS,
    )


class ProofReviewTransport(Protocol):
    model: str

    def review_proof_turn(self, request: ProofReviewTurnRequest) -> ProofReviewModelResponse: ...


def _validate_rescue_accountability(
    request: ProofReviewTurnRequest,
    response: ProofReviewModelResponse,
) -> None:
    if request.stage != "rescue":
        if response.dispositions:
            raise ProofReviewProtocolError("initial review responses cannot contain dispositions")
        return

    expected = request.carried_review_item_ids()
    disposition_ids = tuple(item.item_id for item in response.dispositions)
    if len(set(disposition_ids)) != len(disposition_ids):
        raise ProofReviewProtocolError("a carried review item was dispositioned more than once")

    unknown = [item_id for item_id in disposition_ids if item_id not in expected]
    if unknown:
        raise ProofReviewProtocolError(
            "final response disposition references unknown review item: " + ", ".join(unknown)
        )

    missing = [item_id for item_id in expected if item_id not in disposition_ids]
    if missing:
        raise ProofReviewProtocolError(
            "final response omitted carried review item: " + ", ".join(missing)
        )

    reused = [finding.id for finding in response.findings if finding.id in expected]
    if reused:
        raise ProofReviewProtocolError(
            "new finding reuses a carried review identity: " + ", ".join(reused)
        )


def validate_proof_review_response(
    request: ProofReviewTurnRequest,
    response: ProofReviewModelResponse,
) -> ProofReviewModelResponse:
    """Validate and normalize a response against this exact turn contract."""

    if response.action == "need_source":
        if not request.source_rescue_allowed:
            raise ProofReviewProtocolError("model requested source but source rescue is disabled")
        if not request.allowed_source_addresses:
            raise ProofReviewProtocolError(
                "model requested source but the initial packet advertised no source addresses"
            )
        if len(response.source_addresses) > request.max_source_addresses:
            raise ProofReviewProtocolError(
                "source rescue requests at most "
                f"{request.max_source_addresses} addresses, got {len(response.source_addresses)}"
            )
        allowed = set(request.allowed_source_addresses)
        unadvertised = [
            address for address in response.source_addresses if address not in allowed
        ]
        if unadvertised:
            raise ProofReviewProtocolError(
                "source address was not advertised in the initial packet: "
                + ", ".join(unadvertised)
            )

    _validate_rescue_accountability(request, response)
    try:
        effective = request.response_model().model_validate(response.model_dump(mode="python"))
    except ValidationError as exc:
        raise ProofReviewProtocolError(
            f"model response violates the {request.stage} proof-review contract: {exc}"
        ) from exc
    normalized = ProofReviewModelResponse.model_validate(effective.model_dump(mode="python"))
    _validate_rescue_accountability(request, normalized)
    return normalized


def _content_fingerprint(representation: Representation, content: str) -> str:
    payload = representation + "\n" + content
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _initial_user_content(
    *,
    representation: Representation,
    packet_fingerprint: str,
    content: str,
    source_rescue_allowed: bool,
) -> str:
    rescue = "allowed-once" if source_rescue_allowed else "disabled"
    policy = f"{_PROOF_IR_REVIEW_POLICY}\n" if representation == "thorn-proof/1" else ""
    return (
        "THORN-REVIEW 2\n"
        f"REPRESENTATION {representation}\n"
        f"INITIAL_PACKET_FINGERPRINT {packet_fingerprint}\n"
        f"SOURCE_RESCUE {rescue}\n"
        f"{policy}\n"
        f"{content}"
    )


def build_raw_review_turn(content: str) -> ProofReviewTurnRequest:
    fingerprint = _content_fingerprint("raw", content)
    return ProofReviewTurnRequest(
        representation="raw",
        stage="initial",
        initial_packet_fingerprint=fingerprint,
        user_content=_initial_user_content(
            representation="raw",
            packet_fingerprint=fingerprint,
            content=content,
            source_rescue_allowed=False,
        ),
        source_rescue_allowed=False,
        max_source_addresses=0,
    )


def build_proof_review_turn(request: ProofLanguageReviewRequest) -> ProofReviewTurnRequest:
    document = request.document
    advertised = (
        advertised_source_addresses(document) if request.allow_source_rescue else ()
    )
    source_rescue_allowed = request.allow_source_rescue and bool(advertised)
    return ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint=document.fingerprint(),
        user_content=_initial_user_content(
            representation="thorn-proof/1",
            packet_fingerprint=document.fingerprint(),
            content=document.render_initial(),
            source_rescue_allowed=source_rescue_allowed,
        ),
        source_rescue_allowed=source_rescue_allowed,
        allowed_source_addresses=advertised,
        max_source_addresses=request.max_source_addresses if source_rescue_allowed else 0,
    )


def _parse_rescue_source_content(source_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current: str | None = None
    chunks: list[str] = []
    for line in source_text.splitlines():
        if line.startswith("SOURCE @"):
            if current is not None:
                result[current] = "\n".join(chunks).strip()
            current = line[len("SOURCE @") :].strip()
            chunks = []
            continue
        chunks.append(line)
    if current is not None:
        result[current] = "\n".join(chunks).strip()
    return result


def _render_rescue_user_content(
    source_text: str,
) -> str:
    return f"THORN-SOURCE-RESCUE 2\n{_FINAL_RESCUE_POLICY}\n\n{source_text}"


def build_rescue_turn(
    request: ProofLanguageReviewRequest,
    initial_turn: ProofReviewTurnRequest,
    response: ProofReviewModelResponse,
) -> ProofReviewTurnRequest:
    document = request.document
    if initial_turn.representation != "thorn-proof/1":
        raise ProofReviewProtocolError("source rescue is only defined for thorn-proof/1")
    if not initial_turn.source_rescue_allowed:
        raise ProofReviewProtocolError("source rescue was not enabled for this initial turn")
    if response.action != "need_source":
        raise ProofReviewProtocolError("source rescue requires a need_source response")
    if initial_turn.initial_packet_fingerprint != document.fingerprint():
        raise ProofReviewProtocolError("initial turn is not bound to this proof-language packet")
    if len(response.source_addresses) > initial_turn.max_source_addresses:
        raise ProofReviewProtocolError("source rescue exceeds the configured address cap")

    # Rebind the stored selection universe to the actual initial packet before any
    # source disclosure. The stored turn contract remains authoritative for all
    # downstream behavior; this recomputation is only an integrity assertion that
    # prevents a forged/copied turn from widening that contract to another held
    # source handle.
    advertised = advertised_source_addresses(document)
    if initial_turn.allowed_source_addresses != advertised:
        raise ProofReviewProtocolError(
            "initial turn source-selection contract does not match proof-language packet"
        )

    response = validate_proof_review_response(initial_turn, response)
    expanded = _expanded_source_addresses(
        document,
        response.source_addresses,
        advertised=initial_turn.allowed_source_addresses,
    )
    if len(expanded) > initial_turn.max_source_addresses:
        raise ProofReviewProtocolError(
            "source rescue prerequisite expansion exceeds the configured address cap"
        )
    rescue = render_source_rescue(
        document,
        parse_source_rescue_request(
            document,
            "NEED_SOURCE " + ",".join(expanded),
        ),
    )
    return ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="rescue",
        initial_packet_fingerprint=document.fingerprint(),
        user_content=_render_rescue_user_content(rescue.text),
        source_rescue_allowed=False,
        max_source_addresses=0,
        requested_source_addresses=expanded,
        initial_user_content=initial_turn.user_content,
        prior_response=response,
    )


def _attack_report_from_response(
    result_identifier: str,
    response: ProofReviewModelResponse,
) -> AttackReport:
    findings = list(response.findings)
    findings.extend(
        disposition.finding
        for disposition in response.dispositions
        if disposition.finding is not None
    )
    return AttackReport(
        result_identifier=result_identifier,
        findings=tuple(findings),
    )


def review_proof_language(
    request: ProofLanguageReviewRequest,
    transport: ProofReviewTransport,
) -> AttackReport:
    first_turn = build_proof_review_turn(request)
    first_response = validate_proof_review_response(
        first_turn,
        transport.review_proof_turn(first_turn),
    )
    if first_response.action == "review":
        return _attack_report_from_response(request.document.result_identifier, first_response)

    rescue_turn = build_rescue_turn(request, first_turn, first_response)
    second_response = validate_proof_review_response(
        rescue_turn,
        transport.review_proof_turn(rescue_turn),
    )
    if second_response.action != "review":
        raise ProofReviewProtocolError("source rescue is exhausted after one round")
    return _attack_report_from_response(request.document.result_identifier, second_response)
