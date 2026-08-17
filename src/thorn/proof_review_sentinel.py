from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from thorn.local_nlp import select_linguistic_frontend
from thorn.proof_language_experiment import (
    PROOF_REVIEW_EXPERIMENT_ARMS,
    ProofReviewExperimentArm,
    proof_review_experiment_envelope,
)
from thorn.proof_language_review import (
    PROMPT_VERSION,
    PROTOCOL_VERSION,
    advertised_source_addresses,
)
from thorn.proof_review_eval import (
    ProofReviewChallengeEntry,
    build_case_proof_document,
    current_thorn_revision,
)
from thorn.providers.request_envelope import (
    PROOF_REVIEW_MAX_OUTPUT_TOKENS,
    render_theorem_unit,
)
from thorn.spacy_linguistic import SpacyLinguisticFrontend

SENTINEL_EXPERIMENT: Literal["post-90-v2-sentinel"] = "post-90-v2-sentinel"


class FrozenInitialRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fingerprint: str
    packet_fingerprint: str
    response_schema_sha256: str


class ProofReviewSentinelManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    experiment: Literal["post-90-v2-sentinel"]
    issue: int
    frozen: bool
    description: str
    thorn_base_revision: str
    prompt_version: str
    protocol_version: str
    model: str
    seed: int
    max_output_tokens: int = Field(gt=0)
    sdk_max_retries: int = Field(ge=0)
    max_live_requests: int = Field(gt=0)
    representation_arms: tuple[ProofReviewExperimentArm, ...]
    semantic_prompt_sha256: str | None = None
    file_sha256: dict[str, str] = Field(default_factory=dict)
    initial_requests: dict[str, dict[str, FrozenInitialRequest]] = Field(
        default_factory=dict
    )
    intended_scoring: dict[str, object]
    cases: tuple[ProofReviewChallengeEntry, ...]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _prompt_sha256() -> str:
    prompt = files("thorn.prompts").joinpath(f"{PROMPT_VERSION}.md").read_bytes()
    return _sha256_bytes(prompt)


def _case_file_hashes(
    manifest: ProofReviewSentinelManifest,
) -> dict[str, str]:
    paths: list[Path] = []
    for entry in manifest.cases:
        metadata = Path(entry.metadata)
        paths.extend((metadata, metadata.with_suffix(".tex")))
    return {str(path): _sha256_file(path) for path in sorted(set(paths))}


def _validate_sentinel_shape(manifest: ProofReviewSentinelManifest) -> None:
    if manifest.issue != 90:
        raise ValueError("post-#90 sentinel must remain associated with issue 90")
    if manifest.prompt_version != PROMPT_VERSION:
        raise ValueError("sentinel prompt version does not match current review prompt")
    if manifest.protocol_version != PROTOCOL_VERSION:
        raise ValueError("sentinel protocol version does not match current review protocol")
    if manifest.representation_arms != PROOF_REVIEW_EXPERIMENT_ARMS:
        raise ValueError("sentinel must retain the frozen raw/proof_ir/proof_ir_rescue arms")
    if manifest.max_output_tokens != PROOF_REVIEW_MAX_OUTPUT_TOKENS:
        raise ValueError("sentinel output-token cap does not match transport contract")
    if manifest.sdk_max_retries != 0:
        raise ValueError("sentinel requires zero implicit SDK retries")
    expected_max_requests = len(manifest.cases) * (
        len(PROOF_REVIEW_EXPERIMENT_ARMS) + 1
    )
    if manifest.max_live_requests != expected_max_requests:
        raise ValueError(
            "sentinel live-request cap must equal six initial turns plus at most "
            "one rescue turn per case"
        )
    if len(manifest.cases) != 2:
        raise ValueError("v2 transfer sentinel must remain a two-case matched pair")
    roles = sorted(entry.role for entry in manifest.cases)
    if roles != ["clean", "defect"]:
        raise ValueError("v2 transfer sentinel must contain one clean and one defect case")
    pairs = {entry.pair for entry in manifest.cases}
    if len(pairs) != 1 or None in pairs:
        raise ValueError("v2 transfer sentinel cases must remain one explicit matched pair")


def load_proof_review_sentinel_manifest(path: Path) -> ProofReviewSentinelManifest:
    manifest = ProofReviewSentinelManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    _validate_sentinel_shape(manifest)
    if manifest.frozen:
        observed_prompt = _prompt_sha256()
        if manifest.semantic_prompt_sha256 != observed_prompt:
            raise ValueError(
                "frozen sentinel prompt bytes changed: "
                f"expected {manifest.semantic_prompt_sha256}, got {observed_prompt}"
            )
        observed_files = _case_file_hashes(manifest)
        if manifest.file_sha256 != observed_files:
            raise ValueError("frozen sentinel fixture/metadata bytes changed")
        expected_metadata = {entry.metadata for entry in manifest.cases}
        if set(manifest.initial_requests) != expected_metadata:
            raise ValueError(
                "frozen sentinel must record initial requests for every case"
            )
        for metadata, arm_records in manifest.initial_requests.items():
            if set(arm_records) != set(PROOF_REVIEW_EXPERIMENT_ARMS):
                raise ValueError(
                    f"frozen sentinel request set is incomplete for {metadata}"
                )
    return manifest


def _schema_sha256(schema: dict[str, object]) -> str:
    rendered = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(rendered.encode("utf-8"))


def build_sentinel_case_data(
    manifest: ProofReviewSentinelManifest,
    *,
    structural_only: bool,
):
    linguistic_frontend = select_linguistic_frontend(
        structural_only=structural_only,
        factory=SpacyLinguisticFrontend,
    )
    result = []
    for entry in manifest.cases:
        expectation, unit, document = build_case_proof_document(
            Path(entry.metadata),
            linguistic_frontend=linguistic_frontend,
        )
        result.append((entry, expectation, unit, document))
    return result


def build_proof_review_sentinel_inventory(
    manifest_path: Path,
    *,
    structural_only: bool,
) -> dict[str, object]:
    """Build the exact six initial request contracts without constructing a provider."""

    manifest = load_proof_review_sentinel_manifest(manifest_path)
    case_data = build_sentinel_case_data(manifest, structural_only=structural_only)
    records: list[dict[str, object]] = []
    observed_initial: dict[str, dict[str, FrozenInitialRequest]] = {}
    prompt_sha: str | None = None
    response_schema_hashes: set[str] = set()

    for entry, expectation, unit, document in case_data:
        advertised = advertised_source_addresses(document)
        arm_records: dict[str, dict[str, object]] = {}
        frozen_arm_records: dict[str, FrozenInitialRequest] = {}
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS:
            envelope = proof_review_experiment_envelope(
                unit,
                document,
                manifest.model,
                arm,
            )
            current_prompt_sha = _sha256_bytes(envelope.system_prompt.encode("utf-8"))
            if prompt_sha is None:
                prompt_sha = current_prompt_sha
            elif prompt_sha != current_prompt_sha:
                raise ValueError("sentinel arms do not share identical prompt bytes")
            schema_sha = _schema_sha256(envelope.response_schema)
            response_schema_hashes.add(schema_sha)
            frozen_request = FrozenInitialRequest(
                fingerprint=envelope.fingerprint(),
                packet_fingerprint=envelope.initial_packet_fingerprint or "",
                response_schema_sha256=schema_sha,
            )
            frozen_arm_records[arm] = frozen_request
            arm_records[arm] = {
                **frozen_request.model_dump(mode="json"),
                "source_rescue_allowed": (
                    "SOURCE_RESCUE allowed-once" in envelope.user_content
                ),
                "characters": len(envelope.user_content),
                "utf8_bytes": len(envelope.user_content.encode("utf-8")),
                "user_content": envelope.user_content,
            }

        observed_initial[entry.metadata] = frozen_arm_records
        records.append(
            {
                "metadata": entry.metadata,
                "fixture": str(Path(entry.metadata).with_suffix(".tex")),
                "case_name": expectation.name,
                "role": entry.role,
                "expected_issue": entry.expected_issue,
                "target_identifier": unit.identifier,
                "raw_payload": render_theorem_unit(unit),
                "proof_ir_payload": document.render_initial(),
                "advertised_source_addresses": list(advertised),
                "thorn_held_source_handles": [
                    {
                        "address": source.address,
                        "text": source.text,
                    }
                    for source in document.sources
                ],
                "arms": arm_records,
            }
        )

    freeze_candidate = {
        "semantic_prompt_sha256": prompt_sha,
        "file_sha256": _case_file_hashes(manifest),
        "initial_requests": {
            metadata: {
                arm: record.model_dump(mode="json")
                for arm, record in arm_records.items()
            }
            for metadata, arm_records in observed_initial.items()
        },
    }

    request_freeze_verified = False
    if manifest.frozen and not structural_only:
        expected_initial = {
            metadata: {
                arm: record.model_dump(mode="json")
                for arm, record in arm_records.items()
            }
            for metadata, arm_records in manifest.initial_requests.items()
        }
        if manifest.semantic_prompt_sha256 != freeze_candidate["semantic_prompt_sha256"]:
            raise ValueError("frozen sentinel prompt hash no longer matches initial requests")
        if manifest.file_sha256 != freeze_candidate["file_sha256"]:
            raise ValueError("frozen sentinel file hashes no longer match initial requests")
        if expected_initial != freeze_candidate["initial_requests"]:
            raise ValueError("frozen sentinel initial request contracts changed")
        request_freeze_verified = True

    return {
        "experiment": manifest.experiment,
        "issue": manifest.issue,
        "manifest": str(manifest_path),
        "frozen": manifest.frozen,
        "thorn_base_revision": manifest.thorn_base_revision,
        "thorn_revision": current_thorn_revision(),
        "prompt_version": manifest.prompt_version,
        "protocol_version": manifest.protocol_version,
        "model": manifest.model,
        "seed": manifest.seed,
        "max_output_tokens": manifest.max_output_tokens,
        "sdk_max_retries": manifest.sdk_max_retries,
        "max_live_requests": manifest.max_live_requests,
        "structural_only": structural_only,
        "cases": len(records),
        "initial_packets": len(records) * len(PROOF_REVIEW_EXPERIMENT_ARMS),
        "semantic_prompt_sha256": prompt_sha,
        "response_schema_sha256s": sorted(response_schema_hashes),
        "provider_instantiated": False,
        "provider_requests": 0,
        "live_requests": 0,
        "frozen_request_contract_verified": request_freeze_verified,
        "freeze_candidate": freeze_candidate,
        "records": records,
    }
