from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from thorn.models import AttackReport
from thorn.proof_language_review import PROMPT_VERSION, ProofReviewTurnRequest
from thorn.providers.request_envelope import ProviderRequestEnvelope

CACHE_FORMAT_VERSION = 1
CACHE_SEMANTICS_VERSION = "proof-review-cache/1"


class ReviewCacheStatus(StrEnum):
    REUSED = "reused"
    RECHECKED = "rechecked"


class ReviewCacheReason(StrEnum):
    CACHE_HIT_EXACT_PACKET = "cache_hit_exact_packet"
    CACHE_HIT_UNAFFECTED_DEPENDENCY_SLICE = "cache_hit_unaffected_dependency_slice"
    RECHECK_NO_PRIOR_REVIEW = "recheck_no_prior_review"
    RECHECK_LOCAL_IR_CHANGED = "recheck_local_ir_changed"
    RECHECK_UPSTREAM_DEPENDENCY_CHANGED = "recheck_upstream_dependency_changed"
    RECHECK_DEPENDENCY_EDGE_CHANGED = "recheck_dependency_edge_changed"
    RECHECK_REVIEW_CONTRACT_CHANGED = "recheck_review_contract_changed"
    RECHECK_RESCUED_SOURCE_CHANGED = "recheck_rescued_source_changed"
    RECHECK_CACHE_ENTRY_MISSING = "recheck_cache_entry_missing"
    RECHECK_CACHE_IDENTITY_CHANGED = "recheck_cache_identity_changed"


class ReviewDependencyState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    content_fingerprint: str


class ReviewDependencySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dependencies: tuple[ReviewDependencyState, ...] = ()
    edges_fingerprint: str

    def content_by_identifier(self) -> dict[str, str]:
        return {item.identifier: item.content_fingerprint for item in self.dependencies}


class ReviewCacheProvenance(BaseModel):
    """Non-semantic cache metadata derived from Thorn's canonical review inputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_identifier: str
    target_content_fingerprint: str
    packet_fingerprint: str
    dependency_snapshot: ReviewDependencySnapshot


class ReviewContractIdentity(BaseModel):
    """Stable identity of the model-facing proof-review contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cache_semantics_version: str = CACHE_SEMANTICS_VERSION
    provider: str
    model: str
    prompt_version: str
    protocol_version: str
    representation: str
    system_prompt_fingerprint: str
    response_schema_fingerprint: str
    source_rescue_allowed: bool
    max_source_addresses: int
    max_output_tokens: int | None = None


class ProofReviewCacheEntry(BaseModel):
    """One reusable completed semantic review and the exact inputs that justify it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: int = CACHE_FORMAT_VERSION
    cache_key: str
    provenance: ReviewCacheProvenance
    contract: ReviewContractIdentity
    initial_request_fingerprint: str
    rescue_request_fingerprint: str | None = None
    report: AttackReport
    initial_turn: ProofReviewTurnRequest
    rescue_turn: ProofReviewTurnRequest | None = None


class _ProofReviewCacheHead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: int = CACHE_FORMAT_VERSION
    result_identifier: str
    cache_key: str


class ReviewCacheDecision(BaseModel):
    """Machine-readable reuse/recheck provenance suitable for reports and graphs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_identifier: str
    status: ReviewCacheStatus
    reason: ReviewCacheReason
    cache_key: str
    provider_requests_avoided: int = 0
    estimated_input_tokens_avoided: int = 0


class ReviewCacheSummary(BaseModel):
    """Aggregate keyless measurement for one incremental review run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    review_units: int
    reused_units: int
    rechecked_units: int
    provider_requests_avoided: int
    estimated_input_tokens_avoided: int

    @classmethod
    def from_decisions(cls, decisions: tuple[ReviewCacheDecision, ...]) -> ReviewCacheSummary:
        reused = [item for item in decisions if item.status == ReviewCacheStatus.REUSED]
        return cls(
            review_units=len(decisions),
            reused_units=len(reused),
            rechecked_units=len(decisions) - len(reused),
            provider_requests_avoided=sum(item.provider_requests_avoided for item in decisions),
            estimated_input_tokens_avoided=sum(
                item.estimated_input_tokens_avoided for item in decisions
            ),
        )


def canonical_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_contract_identity(
    turn: ProofReviewTurnRequest,
    envelope: ProviderRequestEnvelope,
) -> ReviewContractIdentity:
    return ReviewContractIdentity(
        provider=envelope.provider,
        model=envelope.model,
        prompt_version=PROMPT_VERSION,
        protocol_version=turn.protocol_version,
        representation=turn.representation,
        system_prompt_fingerprint=canonical_fingerprint(envelope.system_prompt),
        response_schema_fingerprint=canonical_fingerprint(envelope.response_schema),
        source_rescue_allowed=turn.source_rescue_allowed,
        max_source_addresses=turn.max_source_addresses,
        max_output_tokens=envelope.max_output_tokens,
    )


def proof_review_cache_key(
    provenance: ReviewCacheProvenance,
    contract: ReviewContractIdentity,
    initial_request_fingerprint: str,
) -> str:
    return canonical_fingerprint(
        {
            "cache_semantics_version": CACHE_SEMANTICS_VERSION,
            "result_identifier": provenance.result_identifier,
            "packet_fingerprint": provenance.packet_fingerprint,
            "dependency_snapshot": provenance.dependency_snapshot.model_dump(mode="json"),
            "contract": contract.model_dump(mode="json"),
            "initial_request_fingerprint": initial_request_fingerprint,
        }
    )


def estimate_input_tokens(envelope: ProviderRequestEnvelope) -> int:
    """Conservative provider-neutral estimate used only for avoided-work reporting."""

    characters = sum(
        len(message.get("role", "")) + len(message.get("content", ""))
        for message in envelope.input_messages()
    )
    return max(1, (characters + 3) // 4)


class ProofReviewCache:
    """Content-addressed semantic-review cache with per-result history heads."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _entry_path(self, cache_key: str) -> Path:
        return self.root / "entries" / f"{cache_key}.json"

    def _head_path(self, result_identifier: str) -> Path:
        result_key = hashlib.sha256(result_identifier.encode("utf-8")).hexdigest()
        return self.root / "heads" / f"{result_key}.json"

    @staticmethod
    def _read_model(path: Path, model: type[BaseModel]) -> BaseModel | None:
        if not path.exists():
            return None
        try:
            return model.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError, json.JSONDecodeError):
            return None

    def get(self, cache_key: str) -> ProofReviewCacheEntry | None:
        value = self._read_model(self._entry_path(cache_key), ProofReviewCacheEntry)
        return value if isinstance(value, ProofReviewCacheEntry) else None

    def latest(self, result_identifier: str) -> ProofReviewCacheEntry | None:
        value = self._read_model(self._head_path(result_identifier), _ProofReviewCacheHead)
        if not isinstance(value, _ProofReviewCacheHead):
            return None
        if value.result_identifier != result_identifier:
            return None
        entry = self.get(value.cache_key)
        if entry is None or entry.provenance.result_identifier != result_identifier:
            return None
        return entry

    def put(self, entry: ProofReviewCacheEntry) -> None:
        entry_path = self._entry_path(entry.cache_key)
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = entry_path.with_suffix(".json.tmp")
        temporary.write_text(entry.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(entry_path)
        self.set_head(entry.provenance.result_identifier, entry.cache_key)

    def set_head(self, result_identifier: str, cache_key: str) -> None:
        head_path = self._head_path(result_identifier)
        head_path.parent.mkdir(parents=True, exist_ok=True)
        head = _ProofReviewCacheHead(result_identifier=result_identifier, cache_key=cache_key)
        temporary = head_path.with_suffix(".json.tmp")
        temporary.write_text(head.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(head_path)
