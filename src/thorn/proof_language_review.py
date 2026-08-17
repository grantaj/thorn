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

PROTOCOL_VERSION: Literal["thorn-proof-review/1"] = "thorn-proof-review/1"
Representation = Literal["raw", "thorn-proof/1"]
ReviewStage = Literal["initial", "rescue"]
ReviewAction = Literal["review", "need_source"]
SourceAddress = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9:._-]*$"),
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
    "FINAL_RESCUE_POLICY source rescue is now exhausted. If deterministic "
    "recovery remains unresolved, do not convert that uncertainty into a "
    "mathematical finding unless the supplied mathematical content itself "
    "establishes the defect."
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


class ProofReviewModelResponse(BaseModel):
    """One structured model response in the proof-language review protocol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ReviewAction
    findings: tuple[CandidateFinding, ...] = ()
    source_addresses: tuple[SourceAddress, ...] = ()

    @model_validator(mode="after")
    def _validate_action_payload(self) -> ProofReviewModelResponse:
        if self.action == "review" and self.source_addresses:
            raise ValueError("review responses must not request source")
        if self.action == "need_source" and self.findings:
            raise ValueError("source requests must not include findings")
        if self.action == "need_source" and not self.source_addresses:
            raise ValueError("source requests must contain at least one address")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


@lru_cache(maxsize=256)
def _closed_world_response_model(
    allowed_source_addresses: tuple[str, ...],
    max_source_addresses: int,
    source_rescue_allowed: bool,
) -> type[ProofReviewModelResponse]:
    """Build the existing response shape with request-specific source typing.

    The generated class deliberately keeps the stable ``ProofReviewModelResponse``
    schema title. The fingerprint therefore records protocol content (the finite
    allowed values and request cap), not an incidental generated Python name.
    """

    if not source_rescue_allowed or not allowed_source_addresses:
        model = create_model(
            "ProofReviewModelResponse",
            __base__=ProofReviewModelResponse,
            action=(Literal["review"], ...),
            source_addresses=(tuple[()], ()),
        )
        return model

    address_literal: Any = cast(Any, Literal)[allowed_source_addresses]
    source_addresses_type: Any = tuple[address_literal, ...]
    model = create_model(
        "ProofReviewModelResponse",
        __base__=ProofReviewModelResponse,
        source_addresses=(
            source_addresses_type,
            Field(default=(), max_length=max_source_addresses),
        ),
    )
    return model


class ProofReviewTurnRequest(BaseModel):
    """Provider-neutral description of one transport turn and response contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal["thorn-proof-review/1"] = PROTOCOL_VERSION
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
        if (
            self.stage == "initial"
            and (self.initial_user_content is not None or self.prior_response is not None)
        ):
            raise ValueError("initial turns cannot contain rescue transcript fields")
        if self.stage == "rescue" and not self.requested_source_addresses:
            raise ValueError("rescue turns require source addresses")
        if (
            self.stage == "rescue"
            and (self.initial_user_content is None or self.prior_response is None)
        ):
            raise ValueError("rescue turns require the exact initial turn and prior response")
        if self.stage == "rescue" and self.source_rescue_allowed:
            raise ValueError("source rescue is exhausted after the first request")
        if self.stage == "rescue" and self.allowed_source_addresses:
            raise ValueError("rescue turns cannot advertise another source-selection universe")
        if not self.source_rescue_allowed and self.allowed_source_addresses:
            raise ValueError("disabled source rescue cannot expose selectable source addresses")
        if self.source_rescue_allowed and self.max_source_addresses < 1:
            raise ValueError("enabled source rescue requires a positive source-address cap")
        return self

    def response_model(self) -> type[ProofReviewModelResponse]:
        """Return the structured-output model for this exact turn contract."""

        return _closed_world_response_model(
            self.allowed_source_addresses,
            self.max_source_addresses,
            self.source_rescue_allowed,
        )

    def response_schema(self) -> dict[str, object]:
        """Return the deterministic provider-neutral effective response schema."""

        return self.response_model().model_json_schema()


class ProofLanguageReviewRequest(BaseModel):
    """Thorn-owned request for semantic review over one ``thorn-proof/1`` packet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol_version: Literal["thorn-proof-review/1"] = PROTOCOL_VERSION
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


def validate_proof_review_response(
    request: ProofReviewTurnRequest,
    response: ProofReviewModelResponse,
) -> ProofReviewModelResponse:
    """Validate and normalize a response against the request-specific source contract."""

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
    return ProofReviewModelResponse.model_validate(response.model_dump(mode="python"))


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
        "THORN-REVIEW 1\n"
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


def build_proof_review_turn(
    request: ProofLanguageReviewRequest,
) -> ProofReviewTurnRequest:
    document = request.document
    allowed_source_addresses = (
        advertised_source_addresses(document) if request.allow_source_rescue else ()
    )
    return ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="initial",
        initial_packet_fingerprint=document.fingerprint(),
        user_content=_initial_user_content(
            representation="thorn-proof/1",
            packet_fingerprint=document.fingerprint(),
            content=document.render_initial(),
            source_rescue_allowed=request.allow_source_rescue,
        ),
        source_rescue_allowed=request.allow_source_rescue,
        allowed_source_addresses=allowed_source_addresses,
        max_source_addresses=(request.max_source_addresses if request.allow_source_rescue else 0),
    )


def _source_command(addresses: tuple[str, ...]) -> str:
    return "NEED_SOURCE " + ",".join(addresses)


def build_rescue_turn(
    request: ProofLanguageReviewRequest,
    initial_turn: ProofReviewTurnRequest,
    source_request: ProofReviewModelResponse,
) -> ProofReviewTurnRequest:
    if initial_turn.representation != "thorn-proof/1":
        raise ProofReviewProtocolError("raw review does not support source rescue")
    if not request.allow_source_rescue or not initial_turn.source_rescue_allowed:
        raise ProofReviewProtocolError("source rescue is disabled for this review arm")
    if source_request.action != "need_source":
        raise ProofReviewProtocolError("rescue turn requires a structured source request")
    if initial_turn.initial_packet_fingerprint != request.document.fingerprint():
        raise ProofReviewProtocolError("initial turn does not match the proof-language packet")
    if initial_turn.max_source_addresses != request.max_source_addresses:
        raise ProofReviewProtocolError("initial turn does not match the review source-address cap")

    source_request = validate_proof_review_response(initial_turn, source_request)
    expanded_addresses = _expanded_source_addresses(
        request.document,
        source_request.source_addresses,
        advertised=initial_turn.allowed_source_addresses,
    )
    try:
        parsed = parse_source_rescue_request(
            request.document,
            _source_command(expanded_addresses),
            max_addresses=initial_turn.max_source_addresses,
            round_number=1,
        )
        rescue = render_source_rescue(request.document, parsed)
    except (KeyError, ValueError) as exc:
        raise ProofReviewProtocolError(str(exc)) from exc

    return ProofReviewTurnRequest(
        representation="thorn-proof/1",
        stage="rescue",
        initial_packet_fingerprint=request.document.fingerprint(),
        user_content=(
            "THORN-REVIEW SOURCE-RESCUE 1\n"
            f"INITIAL_PACKET_FINGERPRINT {request.document.fingerprint()}\n"
            "SOURCE_RESCUE exhausted\n"
            f"{_FINAL_RESCUE_POLICY}\n\n"
            f"{rescue.text}"
        ),
        source_rescue_allowed=False,
        allowed_source_addresses=(),
        max_source_addresses=0,
        requested_source_addresses=parsed.addresses,
        initial_user_content=initial_turn.user_content,
        prior_response=source_request,
    )


def review_proof_language(
    request: ProofLanguageReviewRequest,
    transport: ProofReviewTransport,
) -> AttackReport:
    """Review a proof-language packet with at most one exact source-rescue round."""

    initial_turn = build_proof_review_turn(request)
    first = validate_proof_review_response(
        initial_turn,
        transport.review_proof_turn(initial_turn),
    )
    if first.action == "review":
        return AttackReport(findings=list(first.findings))

    rescue_turn = build_rescue_turn(request, initial_turn, first)
    second = transport.review_proof_turn(rescue_turn)
    if second.action != "review":
        raise ProofReviewProtocolError("a second source-rescue request is not allowed")
    second = validate_proof_review_response(rescue_turn, second)
    return AttackReport(findings=list(second.findings))
