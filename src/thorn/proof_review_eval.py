from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from thorn.dependencies import ExtractedProject
from thorn.eval import CaseExpectation
from thorn.eval_review import build_result_review_context
from thorn.latex import extract_project
from thorn.linguistic import LinguisticFrontend
from thorn.llm_proof_language import LLMProofLanguage, project_llm_proof_language
from thorn.local_nlp import select_linguistic_frontend
from thorn.models import TheoremUnit
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
from thorn.providers.request_envelope import render_theorem_unit
from thorn.semantic_review_render import build_semantic_review_request
from thorn.semantic_transformations import build_semantic_transformation_ir
from thorn.spacy_linguistic import SpacyLinguisticFrontend

_FROZEN_PROMPT_VERSION = "proof_language_reviewer_v1"
_FROZEN_PROTOCOL_VERSION = "thorn-proof-review/1"


class ProofReviewChallengeEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metadata: str
    pair: str | None = None
    role: str
    expected_issue: str


class ProofReviewChallengeManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int
    issue: int
    frozen: bool
    description: str
    thorn_base_revision: str
    prompt_version: str
    protocol_version: str
    representation_arms: tuple[ProofReviewExperimentArm, ...]
    intended_scoring: dict[str, object]
    cases: tuple[ProofReviewChallengeEntry, ...]


def load_proof_review_manifest(path: Path) -> ProofReviewChallengeManifest:
    """Load the immutable #83-era challenge manifest as a historical case set."""

    manifest = ProofReviewChallengeManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if not manifest.cases:
        raise ValueError("experiment manifest must contain a non-empty cases list")
    if manifest.issue != 78 or not manifest.frozen:
        raise ValueError("proof-review challenge must be the frozen issue-78 manifest")
    if manifest.prompt_version != _FROZEN_PROMPT_VERSION:
        raise ValueError(
            "proof-review challenge prompt freeze does not match the archived v1 contract"
        )
    if manifest.protocol_version != _FROZEN_PROTOCOL_VERSION:
        raise ValueError(
            "proof-review challenge protocol freeze does not match the archived v1 contract"
        )
    if manifest.representation_arms != PROOF_REVIEW_EXPERIMENT_ARMS:
        raise ValueError("manifest representation arms do not match the frozen A/B/C arms")
    return manifest


def current_thorn_revision() -> str:
    """Return the exact checkout revision for reproducibility when git is available."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _select_unit(project: ExtractedProject, expectation: CaseExpectation) -> TheoremUnit:
    if expectation.target_identifier is not None:
        return project.unit(expectation.target_identifier)
    if len(project.units) != 1:
        raise ValueError(
            f"case {expectation.name!r} has {len(project.units)} units but no target_identifier"
        )
    return project.units[0]


def build_case_proof_document(
    metadata_path: Path,
    *,
    linguistic_frontend: LinguisticFrontend | None,
) -> tuple[CaseExpectation, TheoremUnit, LLMProofLanguage]:
    expectation = CaseExpectation.model_validate_json(
        metadata_path.read_text(encoding="utf-8")
    )
    tex_path = metadata_path.with_suffix(".tex")
    project = extract_project(tex_path, linguistic_frontend=linguistic_frontend)
    unit = _select_unit(project, expectation)
    context = build_result_review_context(project, unit.identifier)
    if len(context.items) != 1:
        raise ValueError(f"expected exactly one result review item for {unit.identifier!r}")
    semantic_request = build_semantic_review_request(context.items[0])
    semantic = build_semantic_transformation_ir(
        unit,
        semantic_request,
        symbol_table=project.symbol_table,
        dependency_graph=project.dependency_graph,
    )
    return expectation, unit, project_llm_proof_language(semantic)


def build_proof_review_inventory(
    manifest_path: Path,
    *,
    model: str,
    structural_only: bool,
) -> dict[str, object]:
    """Apply the current keyless protocol to the immutable historical case set.

    The archived manifest still records the exact v1 paid experiment contract. Once
    the review prompt/protocol changes, this inventory is a structural regression
    inventory over the same cases, not a continuation of that frozen paid condition.
    """

    manifest = load_proof_review_manifest(manifest_path)
    linguistic_frontend = select_linguistic_frontend(
        structural_only=structural_only,
        factory=SpacyLinguisticFrontend,
    )
    totals: dict[str, dict[str, int]] = {
        arm: {"characters": 0, "utf8_bytes": 0}
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS
    }
    payload_totals: dict[str, dict[str, int]] = {
        "raw": {"characters": 0, "utf8_bytes": 0},
        "proof_ir": {"characters": 0, "utf8_bytes": 0},
    }
    records: list[dict[str, object]] = []
    shared_prompt_sha256: str | None = None
    response_schema_sha256s: set[str] = set()
    total_source_addresses = 0
    total_source_handles = 0

    for entry in manifest.cases:
        metadata_path = Path(entry.metadata)
        expectation, unit, document = build_case_proof_document(
            metadata_path,
            linguistic_frontend=linguistic_frontend,
        )
        advertised = advertised_source_addresses(document)
        total_source_addresses += len(advertised)
        total_source_handles += len(document.sources)

        raw_payload = render_theorem_unit(unit)
        proof_payload = document.render_initial()
        for key, content in (("raw", raw_payload), ("proof_ir", proof_payload)):
            payload_totals[key]["characters"] += len(content)
            payload_totals[key]["utf8_bytes"] += len(content.encode("utf-8"))

        arm_records: dict[str, dict[str, object]] = {}
        for arm in PROOF_REVIEW_EXPERIMENT_ARMS:
            envelope = proof_review_experiment_envelope(unit, document, model, arm)
            prompt_sha = hashlib.sha256(envelope.system_prompt.encode("utf-8")).hexdigest()
            schema_json = json.dumps(
                envelope.response_schema,
                sort_keys=True,
                separators=(",", ":"),
            )
            schema_sha = hashlib.sha256(schema_json.encode("utf-8")).hexdigest()
            response_schema_sha256s.add(schema_sha)
            if shared_prompt_sha256 is None:
                shared_prompt_sha256 = prompt_sha
            elif shared_prompt_sha256 != prompt_sha:
                raise ValueError("experiment arms do not share one system prompt")

            characters = len(envelope.user_content)
            utf8_bytes = len(envelope.user_content.encode("utf-8"))
            totals[arm]["characters"] += characters
            totals[arm]["utf8_bytes"] += utf8_bytes
            arm_records[arm] = {
                "characters": characters,
                "utf8_bytes": utf8_bytes,
                "fingerprint": envelope.fingerprint(),
                "packet_fingerprint": envelope.initial_packet_fingerprint,
                "response_schema_sha256": schema_sha,
                "source_rescue_allowed": (
                    "SOURCE_RESCUE allowed-once" in envelope.user_content
                ),
            }

        records.append(
            {
                "metadata": str(metadata_path),
                "fixture": str(metadata_path.with_suffix(".tex")),
                "case_name": expectation.name,
                "expected_kind": expectation.kind,
                "expected_issue": entry.expected_issue,
                "accepted_categories": [
                    category.value for category in expectation.accepted_categories
                ],
                "target_identifier": unit.identifier,
                "pair": entry.pair,
                "role": entry.role,
                "advertised_source_addresses": list(advertised),
                "advertised_source_address_count": len(advertised),
                "thorn_held_source_handle_count": len(document.sources),
                "arms": arm_records,
            }
        )

    schema_hashes = sorted(response_schema_sha256s)
    comparable_to_frozen_paid_run = (
        manifest.prompt_version == PROMPT_VERSION
        and manifest.protocol_version == PROTOCOL_VERSION
    )
    return {
        "manifest": str(manifest_path),
        "manifest_version": manifest.version,
        "issue": manifest.issue,
        "frozen": manifest.frozen,
        "thorn_base_revision": manifest.thorn_base_revision,
        "thorn_revision": current_thorn_revision(),
        "manifest_prompt_version": manifest.prompt_version,
        "manifest_protocol_version": manifest.protocol_version,
        "prompt_version": PROMPT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "historical_frozen_manifest": True,
        "comparable_to_frozen_paid_run": comparable_to_frozen_paid_run,
        "model": model,
        "cases": len(records),
        "initial_packets": len(records) * len(PROOF_REVIEW_EXPERIMENT_ARMS),
        "experiment_arms": list(PROOF_REVIEW_EXPERIMENT_ARMS),
        "semantic_prompt_sha256": shared_prompt_sha256,
        "response_schema_sha256": schema_hashes[0] if len(schema_hashes) == 1 else None,
        "response_schema_sha256s": schema_hashes,
        "response_schema_policy": (
            "request-specific closed-world source selection plus rescue review-state accountability"
        ),
        "payload_totals": payload_totals,
        "request_totals": totals,
        "advertised_source_addresses": total_source_addresses,
        "thorn_held_source_handles": total_source_handles,
        "provider_instantiated": False,
        "provider_requests": 0,
        "live_requests": 0,
        "api_key_required": False,
        "token_accounting": (
            "exact token usage, request count, rescue source size, and cost are recorded "
            "only during a separately authorized live/replay run"
        ),
        "records": records,
    }