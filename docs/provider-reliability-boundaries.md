# Provider reliability boundary map

This document defines Thorn's trust boundary for provider-backed mathematical review.
It is intentionally narrower than the deterministic analysis/Proof-IR architecture:
the #134 reliability failures were concentrated after the stable IR handoff, so this
audit does not rewrite the front-end without a concrete invariant violation.

## Core invariant

> There is exactly one canonical provider execution contract, and every provider-
> significant stage agrees on its identity.

`ProviderRequestEnvelope` remains the provider-neutral semantic description and the
identity used by historical v1 recordings. New live evidence uses
`ProviderExecutionContract` (`thorn-provider-execution/2`). That contract contains:

- the complete kwargs passed to `responses.create`;
- the final strict JSON Schema, after Thorn-owned schema conversion;
- model, endpoint, input transcript, output cap, and storage setting;
- an explicit response-acceptance/validator contract;
- exact provider-sensitive Python/OpenAI/Pydantic and serialization/HTTP runtime
  versions; and
- the SHA-256 identity of the provider-neutral semantic envelope.

The execution contract is built before dispatch. The provider receives a deep copy of
its already-canonical `wire_request`; no schema conversion or provider wrapper is
allowed after the execution fingerprint exists.

## Boundary map

| # | Boundary | Owner | Required invariant / evidence |
|---|---|---|---|
| 1 | LaTeX/project -> canonical IR / Proof-IR | deterministic analysis | Existing canonical IR remains the handoff; provider work must not mutate it. |
| 2 | Proof-IR -> proof-review turn | `proof_language_review` | Representation, protocol, source universe, stage, and transcript are explicit and deterministic. |
| 3 | Turn -> response state/schema | Thorn | Request-specific Pydantic/schema state is constructed before provider execution. Relational semantics are separately versioned. |
| 4 | Provider-neutral request -> final wire request | `execution_contract` | Final schema conversion and `responses.create` wrapper happen exactly once, before fingerprinting. |
| 5 | SDK/client construction | `OpenAIProvider` | OpenAI client retries are forced to zero. Provider-sensitive versions are recorded in execution identity and frozen in Actions. |
| 6 | Dispatch -> outcome | `OpenAIProvider` | `provider_attempts` increments before dispatch. Transport failures become typed evidence rather than generic log-only exceptions. |
| 7 | Usage / billing evidence | provider adapter | Attempts, responses received, known model generations, input/output/total tokens, live attempts, and replay hits are separate quantities. Unknown usage remains unknown/zero rather than inferred. |
| 8 | Accepted/rejected recording | `RecordingProvider` | Accepted v2 evidence is immutable. Identical rewrites are no-ops; conflicts are preserved separately and fail loudly. Rejections preserve distinct response fingerprints and typed transport evidence. |
| 9 | Exact / forensic replay | replay providers | v2 replay reconstructs the current final execution contract and requires an exact match. Legacy v1 envelope-only evidence remains replayable but is explicitly counted as `legacy_replay_hits`. |
| 10 | Source-rescue turn | proof-review protocol | Rescue transcript, carried review state, requested source addresses, exhausted rescue state, schema, and validator semantics are all in the execution identity. |
| 11 | Experiment manifest/freeze | experiment tooling | Freeze must cover source/runner revision, final execution fingerprints, runtime lock, model policy, budgets, and readiness evidence; mathematics alone is not a freeze. |
| 12 | GitHub Actions/runtime | workflows | Provider-sensitive workflows use CPython 3.11.16 and `constraints/provider-runtime.txt`; the execution artifact records the resolved provider-sensitive dependency versions as well. |
| 13 | Artifact preservation/adjudication | workflow + experiment | Preflight, live outcome, rejected evidence, replay, runtime, and adjudication stay distinct. Readiness evidence never grants scientific authorization. |

## Accounting vocabulary

These names are deliberately non-interchangeable:

- `provider_attempts`: calls whose dispatch boundary was entered; incremented before
  the SDK/network call;
- `responses_received`: provider calls that returned a response object to Thorn;
- `model_generations`: responses for which generation is known from response status,
  output, or output-token evidence;
- token counters: provider-reported token usage only;
- `live_requests`: compatibility/live-attempt count;
- `requests`: compatibility logical invocation count (live providers count attempts;
  replay providers count replay invocations);
- `replay_hits`: accepted recording lookups;
- `legacy_replay_hits`: replay hits backed only by the historical v1 envelope identity.

An HTTP 400/401/403/429/5xx, connectivity error, or timeout therefore counts as a
provider attempt even if no model generation or token usage is known.

## Transport-failure evidence

`ProviderTransportError` carries `ProviderTransportEvidence`. Thorn preserves safe,
JSON-serializable fields when available: exception type/message, HTTP status, provider
request ID, structured provider error body, error type/code/parameter, and `Retry-After`.
Authorization headers, API keys, and arbitrary request headers are never recorded.

A returned response that is empty, malformed JSON, or fails the request-specific
Pydantic schema is a different class: `ProviderResponseValidationError`. It records
the provider response payload and any provider-reported usage because the transport
itself succeeded.

## Recording and replay identity

### v2 exact evidence

New accepted and rejected evidence is keyed by
`ProviderExecutionContract.fingerprint()`. This means any of the following changes the
identity even when the mathematical input is unchanged:

- provider-visible schema or wrapper;
- transcript or output cap;
- model/endpoint;
- validator/normalization semantics;
- OpenAI SDK, Pydantic/pydantic-core, Python patch, provider serialization/HTTP
  dependencies, or execution-contract version.

Accepted recording files are immutable. Re-running an identical execution and
obtaining byte/semantic-identical evidence is a no-op. A different accepted result for
the same execution fingerprint is preserved under `conflicts/<fingerprint>/` and
raises `RecordingConflictError`; the original evidence is never replaced.

### v1 historical evidence

Older recordings keyed only by `ProviderRequestEnvelope.fingerprint()` did not capture
final provider schema conversion, SDK-owned `.parse()` conversion, validator identity,
or runtime identity. Thorn continues to replay them for historical reconstruction,
but marks the replay via `legacy_replay_hits`. Such evidence is **not exact-comparable**
to v2 scientific measurements and must not be silently upgraded by rewriting files.

The historical #134 attempts therefore remain evidence of what happened under their
recorded contracts, but any post-#146 A3 measurement requires a new freeze and is a
new comparability epoch. A1/A2 are not to be resampled merely to migrate recording
formats.

## Reproducible provider runtime

Provider-sensitive Actions run on CPython 3.11.16 and install through
`constraints/provider-runtime.txt`, frozen from the last known-green environment
observed before this audit:

- OpenAI 3.3.0;
- Pydantic 2.13.4;
- pydantic-core 2.46.4;
- httpx2 2.12.0;
- httpcore2 2.12.0; and
- jiter 0.16.0.

The constraints make Actions deterministic; `ProviderRuntimeIdentity` embeds all of
these resolved versions in every v2 execution fingerprint, so an out-of-band local
dependency change cannot masquerade as the same exact execution.

## Provider readiness is not scientific authorization

`provider_readiness_canary.py` and the `Provider readiness canary` workflow exercise
the exact production proof-review request construction with synthetic material only.
The canary advertises the normal rescue-capable **initial-turn** action schema so it
exercises the schema branch that previously failed in production, but the runner makes
exactly one request: a valid `need_source` response is readiness success and is never
followed by a rescue request. The live canary also has zero SDK retries and a 256-token
output cap. It has two separate gates: workflow `confirm_live` plus the runner's
`--confirm-paid-readiness-canary` flag.

Its evidence always contains:

```text
readiness_only = true
scientific_authorization = false
synthetic_input = true
```

Keyless preflight records the exact final execution contract without constructing a
provider client. A successful live canary records the exact contract, runtime, attempt
and usage counters, normalized response, and provider response metadata. A returned
response that fails local schema or protocol validation is preserved as explicit
`live-response-failure` evidence rather than disappearing into workflow logs. Keyless
replay reconstructs the current execution contract and re-runs local response/protocol
validation. A scientific freeze may cite matching readiness evidence, but still needs
its own explicit paid-run authorization and frozen scientific request fingerprints.

No A3 scientific request is part of this reliability tranche.

## Failure-injection invariant matrix

The provider invariant suite, together with proof-review protocol tests, must cover:

| Failure / change | Expected invariant |
|---|---|
| accepted structured response | one attempt, one response, known generation/usage where exposed; exact v2 replay works keylessly |
| pre-generation schema rejection | one attempt; typed HTTP evidence; zero generation unless provider proves otherwise |
| auth/permission error | one attempt; typed status/body/request-ID evidence when exposed |
| rate limit | one attempt; retry metadata retained; no implicit SDK retry |
| provider 5xx | one attempt; typed transport evidence |
| network/connectivity error | one attempt; no invented HTTP metadata |
| timeout | one attempt; no implicit retry |
| empty output | response received; response-validation failure, not transport failure |
| malformed JSON | response received; response-validation failure with usage preserved |
| request-schema failure | response received; response-validation failure with raw response evidence |
| Thorn protocol-validator failure | quarantined structured response; forensic replay must reproduce the same validator rejection |
| source-rescue initial/final turns | distinct execution identities containing stage/transcript/source state |
| duplicate live execution | original accepted evidence immutable; conflicting result preserved and rejected as a recording conflict |
| stale/tampered recording | replay fails closed |
| changed final wire request | execution fingerprint changes |
| changed validator semantics | execution fingerprint changes |
| changed SDK/runtime | execution fingerprint changes |
| exact accepted replay | no provider client/network/token use; v2 execution contract must match exactly |

Issue-number regression tests remain useful historical witnesses, but the reusable
provider invariant suite is the primary statement of these guarantees.

## Rules for future experiments

A provider-backed scientific experiment is not frozen until its manifest identifies:

1. the production source/runner revision;
2. the exact final execution fingerprint(s), not only semantic envelopes;
3. exact provider-sensitive runtime/constraint identity;
4. model identity policy;
5. request/output/token/request-count budgets and zero/explicit retry policy;
6. successful readiness evidence whose execution/runtime contract matches the intended
   provider seam;
7. recording/replay directories and artifact policy; and
8. a distinct scientific authorization record.

The manifest may be committed after the production revision it names. The generic
runner verifies that the named revision resolves to the frozen `src/thorn` tree and
that the current checkout has the same tree, runner bytes, constraints, protocol,
prompt, and runtime. This avoids a self-referential manifest commit without weakening
the production freeze.

Issue-specific scripts may remain only as historical frozen runners. New experiments
should use shared provider-readiness, execution-contract, recording/replay, budget, and
manifest primitives rather than cloning operational logic into another workflow.
