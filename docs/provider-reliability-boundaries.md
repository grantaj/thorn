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
- the full committed provider dependency-lock digest plus the resolved version of
  every locked package; and
- the SHA-256 identity of the provider-neutral semantic envelope.

The execution contract is built before dispatch. Production recording passes that
same contract object into `OpenAIProvider`; the provider dispatches only its already-
canonical kwargs and retains the dispatched contract. Recording therefore cannot
reconstruct a subtly different request after the call.

## Boundary map

| # | Boundary | Owner | Required invariant / evidence |
|---|---|---|---|
| 1 | LaTeX/project -> canonical IR / Proof-IR | deterministic analysis | Existing canonical IR remains the handoff; provider work must not mutate it. |
| 2 | Proof-IR -> proof-review turn | `proof_language_review` | Representation, protocol, source universe, stage, and transcript are explicit and deterministic. |
| 3 | Turn -> response state/schema | Thorn | Request-specific Pydantic/schema state is constructed before provider execution. Relational semantics are separately versioned. |
| 4 | Provider-neutral request -> final wire request | `execution_contract` | Final schema conversion and `responses.create` wrapper happen exactly once, before fingerprinting. |
| 5 | SDK/client construction | `OpenAIProvider` | SDK retries are zero. The full committed provider dependency closure and its resolved runtime are part of execution identity. |
| 6 | Dispatch -> outcome | `OpenAIProvider` | `provider_attempts` increments before dispatch. Transport failures become typed, redacted evidence rather than generic log-only exceptions. |
| 7 | Usage / billing evidence | provider adapter | Attempts, responses received, known model generations, input/output/total tokens, live attempts, and replay hits are separate quantities. Unknown usage remains unknown/zero rather than inferred. |
| 8 | Accepted/rejected recording | `RecordingProvider` | Recording receives the exact dispatched contract. Accepted v2 evidence is immutable and exact-replayed immediately; conflicts are preserved separately and fail loudly. |
| 9 | Exact / forensic replay | replay providers | v2 replay reconstructs the current final execution contract and requires an exact match. Legacy v1 envelope-only evidence remains replayable but is explicitly counted as `legacy_replay_hits`. |
| 10 | Source-rescue turn | proof-review protocol | Rescue transcript, carried review state, requested source addresses, exhausted rescue state, schema, and validator semantics are all in execution identity and must be covered by readiness before live dispatch. |
| 11 | Experiment manifest/freeze | experiment tooling | Freeze covers source/runner revision, every initial execution fingerprint, full runtime lock, budgets, and the exact successful readiness evidence identity. |
| 12 | GitHub Actions/runtime | workflows | Provider-sensitive workflows use CPython 3.11.16 and the full `constraints/provider-runtime.txt` dependency closure. Historical paid workflows are retired. |
| 13 | Artifact preservation/adjudication | workflow + experiment | Preflight, readiness, live outcome, rejected evidence, immediate exact replay, runtime, and adjudication stay distinct. Readiness never grants scientific authorization. |

## Accounting vocabulary

These names are deliberately non-interchangeable:

- `provider_attempts`: calls whose dispatch boundary was entered; incremented before
  the SDK/network call;
- `responses_received`: provider calls that returned a response object to Thorn;
- `model_generations`: responses for which generation is known from response status,
  output, or output-token evidence;
- token counters: provider-reported token usage only;
- `live_requests`: compatibility/live-attempt count;
- `requests`: compatibility logical invocation count;
- `replay_hits`: accepted recording lookups; and
- `legacy_replay_hits`: replay hits backed only by historical v1 envelope identity.

An HTTP 400/401/403/429/5xx, connectivity error, or timeout therefore counts as a
provider attempt even if no model generation or token usage is known.

## Transport-failure evidence

`ProviderTransportError` carries `ProviderTransportEvidence`. Thorn preserves an
allowlisted set of safe, JSON-serializable metadata when available: exception type,
HTTP status, provider request ID, structured error type/code/parameter, and
`Retry-After`. The persisted message is Thorn-owned fixed text. Arbitrary exception
strings, provider error messages, request headers, authorization headers, and API keys
are not serialized into evidence.

A returned response that is empty, malformed JSON, or fails the request-specific
Pydantic schema is a different class: `ProviderResponseValidationError`. It records
the provider response payload and provider-reported usage because transport itself
succeeded.

## Recording and replay identity

### v2 exact evidence

New accepted and rejected evidence is keyed by
`ProviderExecutionContract.fingerprint()`. Any of the following therefore changes
identity even when the mathematical input is unchanged:

- provider-visible schema or wrapper;
- transcript or output cap;
- model/endpoint;
- validator/normalization semantics;
- Python patch or any package/version in the committed provider dependency closure;
- the provider lock digest; or
- the execution-contract version.

`RecordingProvider` constructs one execution contract and passes it through to the
production provider. It refuses evidence when the provider reports dispatch of a
different contract. This specifically prevents a recorder configured for one output
cap or schema from naming a call made with another.

Accepted recording files are immutable. Re-running an identical execution and
obtaining identical evidence is a no-op. A different accepted result for the same
execution fingerprint is preserved under `conflicts/<fingerprint>/` and raises
`RecordingConflictError`; the original evidence is never replaced.

Every accepted exchange is exact-replayed immediately after its atomic write. Thus a
later provider failure cannot leave earlier accepted scientific evidence awaiting a
workflow step that may never run. The experiment workflow also attempts a final replay
pass under `always()` as an additional artifact-level check.

### v1 historical evidence

Older recordings keyed only by `ProviderRequestEnvelope.fingerprint()` did not capture
final provider schema conversion, validator identity, or runtime identity. Thorn
continues to replay them for historical reconstruction, but marks them via
`legacy_replay_hits`. Such evidence is **not exact-comparable** to v2 scientific
measurements and must not be silently upgraded by rewriting files.

Historical #134 attempts therefore remain evidence of what happened under their
recorded contracts. Any post-#146 A3 measurement is a new comparability epoch; A1/A2
are not resampled merely to migrate recording formats.

## Reproducible provider runtime

Provider-sensitive Actions run on CPython 3.11.16 and install through
`constraints/provider-runtime.txt`. The file now freezes the full resolved dependency
closure used by the OpenAI transport, not only a hand-picked subset. It includes the
OpenAI/Pydantic stack and its provider-side HTTP, serialization, typing, certificate,
and retry/progress dependencies.

`ProviderRuntimeIdentity` records the lock-file SHA-256 plus the actually installed
version of every lock entry. Experiment preflight fails when the installed closure no
longer equals the committed lock, and any lock or resolved-version change alters the
v2 execution identity.

## Provider readiness is not scientific authorization

The readiness canary exercises **two deterministic synthetic transport profiles**:

1. a max-cardinality rescue-capable initial proof-review request; and
2. a deterministic max-carried-state rescue request with the production four-message
   transcript shape.

The canary uses synthetic mathematical content only, zero SDK retries, and a bounded
512-token output cap per request. A live run therefore makes exactly two paid
readiness calls. The rescue probe is constructed deterministically rather than being
conditional on whatever action the model returns in the initial probe.

Each contract is reduced to a provider transport profile containing the endpoint,
request kind, message-role shape, normalized response-schema structure, and maximum
literal-set/array cardinalities. Payload-specific literal values are erased; `const`
and `enum` are treated as one literal-set feature while cardinality remains explicit.
A readiness profile can cover a scientific profile only when structural identity
matches and the readiness cardinality bounds are at least as large.

This matters because production schemas contain request-specific source-address enums
and rescue schemas contain carried review-item IDs. A successful readiness run is not
merely evidence that *some* proof-review request worked: every initial scientific
contract is checked for profile coverage before the experiment begins, and every
runtime-generated rescue contract is checked again before its provider dispatch.
Uncovered profiles fail closed without a paid scientific call.

Readiness evidence always contains:

```text
readiness_only = true
scientific_authorization = false
synthetic_input = true
```

It also records generation time, workflow/run identity, the exact `src/thorn` tree,
provider-adapter digest, provider-lock digest, both execution contracts, both transport
profiles, attempt/usage counters, normalized responses, and provider response metadata.
Keyless replay reconstructs and validates both readiness profiles.

## Readiness is part of the scientific freeze

`thorn-provider-experiment/2` manifests freeze a `ProviderReadinessFreeze` containing:

- SHA-256 of the exact successful readiness evidence file;
- readiness run ID and timestamp;
- the `src/thorn` tree exercised by readiness;
- provider-adapter and provider-lock digests;
- both readiness transport-profile fingerprints; and
- a bounded freshness window (24 hours by default, at most seven days).

Scientific live execution verifies the exact evidence bytes, run/time identities,
source tree, adapter, lock, model, runtime, and profile fingerprints before creating a
live scientific provider. The readiness source tree must equal the manifest's frozen
production `src/thorn` tree. This prevents an arbitrarily old successful alias canary
or a canary from different provider-boundary code from authorizing a new measurement.

Readiness still does **not** authorize science. The scientific workflow separately
requires explicit scientific-run and pricing confirmations, and the manifest itself
must always say `paid_execution_authorized=false` so committed data cannot act as a
standing paid-run authorization.

No live readiness or scientific request is executed by this implementation PR.

## Failure-injection invariant matrix

The provider invariant suite, together with proof-review protocol tests, covers:

| Failure / change | Expected invariant |
|---|---|
| accepted structured response | one attempt, one response, known generation/usage where exposed; immediate exact v2 replay succeeds |
| pre-generation schema rejection | one attempt; typed HTTP evidence; zero generation unless provider proves otherwise |
| auth/permission error | one attempt; typed status/request-ID/error classification when exposed |
| rate limit | one attempt; retry metadata retained; no implicit SDK retry |
| provider 5xx | one attempt; typed transport evidence |
| network/connectivity error | one attempt; no invented HTTP metadata |
| timeout | one attempt; no implicit retry |
| exception containing a fake API secret | arbitrary exception/provider messages are absent from persisted evidence |
| empty output | response received; response-validation failure, not transport failure |
| malformed JSON | response received; response-validation failure with usage preserved |
| request-schema failure | response received; response-validation failure with response evidence |
| Thorn protocol-validator failure | quarantined structured response; forensic replay reproduces the same validator rejection |
| source-rescue initial/final turns | distinct identities and distinct readiness-covered transport profiles |
| non-default output cap through recorder | recorded contract is the exact dispatched contract; immediate replay uses the same cap |
| duplicate live execution | original accepted evidence immutable; conflicting result preserved and rejected |
| stale/tampered recording | replay fails closed |
| changed final wire request | execution fingerprint changes |
| changed validator semantics | execution fingerprint changes |
| changed dependency lock/runtime | execution fingerprint changes |
| exact accepted replay | no provider client/network/token use; v2 execution contract must match exactly |

## Paid workflow policy

There is one supported path for new paid scientific work:

```text
Provider readiness canary
    -> freeze successful readiness evidence in thorn-provider-experiment/2
    -> Provider experiment
```

The old generic `Live evaluation` workflow and the historical issue #101/#134 paid
workflows are retired and no longer receive the API secret. Their scripts/evidence
remain available for keyless historical reconstruction. This prevents a convenient
workflow bypass around readiness, freeze, budget, and immediate-replay guarantees.

Workflow-dispatch string inputs used by the supported workflows are first placed in
environment variables and then shell-quoted. They are not interpolated directly into
a secret-bearing `run:` script.

## Rules for future experiments

A provider-backed scientific experiment is not frozen until its manifest identifies:

1. the production source/runner revision and exact `src/thorn` tree;
2. every exact initial execution fingerprint, not only semantic envelopes;
3. the full provider dependency lock/runtime identity;
4. model identity policy;
5. request/output/token/request-count budgets and zero/explicit retry policy;
6. exact, fresh successful readiness evidence for the same production tree and all
   required provider transport profiles;
7. recording/replay directories and immutable artifact policy; and
8. a distinct scientific authorization at dispatch time.

The manifest may be committed after the production revision it names. The generic
runner verifies that the named revision resolves to the frozen `src/thorn` tree and
that the current checkout has the same tree, runner bytes, constraints, protocol,
prompt, runtime, and readiness identity. This avoids a self-referential manifest
commit without weakening the production freeze.

Issue-specific scripts remain only as historical reconstruction tools. New experiments
must use the shared readiness, execution-contract, recording/replay, budget, and
manifest primitives rather than cloning operational logic into another paid workflow.
