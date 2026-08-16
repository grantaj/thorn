# Proof-language semantic-review handoff

Issue #78 closes the first provider handoff from canonical Proof IR to semantic
review without changing canonical Proof IR itself:

```text
LaTeX
  -> canonical Proof IR
  -> thorn-proof/1
  -> thorn-proof-review/1
  -> structured semantic-review transport
  -> optional one-round exact source rescue
  -> Thorn findings
```

`thorn-proof/1` remains a deterministic model-facing projection of canonical
Proof IR. The provider does not rebuild mathematical meaning from raw prose and
there is no second model-specific semantic IR.

## Provider-neutral review protocol

`ProofLanguageReviewRequest` owns the `LLMProofLanguage` packet and the source
rescue policy. A `ProofReviewTurnRequest` is the provider-independent transport
unit. `OpenAIProvider` only transports that turn through structured output; the
same turn type is used by recording and replay providers.

All issue-78 turns use protocol version `thorn-proof-review/1` and the same
versioned system prompt, `proof_language_reviewer_v1.md`. The structured model
response is one of two actions represented by one Pydantic schema:

- `review`: zero or more normal `CandidateFinding` values;
- `need_source`: a non-empty list of syntactically valid source handles and no
  findings.

The source request is therefore not recovered from free-form model text or a
regular expression at the provider boundary.

## One bounded `NEED_SOURCE` rescue

For arm C, the initial packet declares `SOURCE_RESCUE allowed-once`. If the
structured response requests source, Thorn converts the addresses to the
existing strict `NEED_SOURCE A1,B2` contract and applies all of these checks
before a second provider turn is possible:

1. every address must have been visibly advertised in the exact initial
   `thorn-proof/1` packet;
2. every address must exist in that packet's Thorn-held exact source map;
3. malformed addresses are rejected;
4. no more than the existing maximum of eight addresses can be requested;
5. only round 1 is supported;
6. the rescue is bound to the exact initial packet fingerprint.

The second turn contains only the exact requested Thorn-held source payloads.
It also carries the initial transcript and the structured source request so the
provider can continue the same review. `SOURCE_RESCUE exhausted` is explicit in
the second turn. A second `need_source` response fails closed; there is no
recursive rescue, arbitrary range query, source browsing, or whole-paper
fallback.

## Fingerprinting and replay

`ProviderRequestEnvelope` retains its legacy shape for existing attack,
defender, and semantic-review requests. Proof-review envelopes add explicit
protocol metadata: representation, stage, initial packet fingerprint, requested
addresses, and (for rescue) the complete two-turn transcript.

Consequently an exact request fingerprint changes when any of the following
material inputs change:

- model identifier;
- versioned system prompt;
- initial raw or `thorn-proof/1` payload;
- protocol or representation;
- structured response schema;
- source addresses requested;
- exact returned rescue source;
- prior structured source-request response.

Initial and rescue turns are recorded as separate exact exchanges. Existing raw
or legacy semantic-review recordings cannot satisfy a proof-review request, and
a changed proof packet produces a replay miss rather than stale reuse.

## Frozen A/B/C experiment

`eval/proof-review-challenge.json` freezes the public synthetic challenge set
before live outcomes. It is anchored to the post-PR-76 `main` revision and
contains 13 cases drawn from the existing public matrix rather than a new
outcome-tuned benchmark. It includes clean/defect pairs for missing
preconditions, upstream dependencies, load-bearing prose, notation/scope, and
well-definedness, plus harder quantifier-swap, weaker-proof, and hidden-RH cases.

The experiment arms are:

- **A — raw:** existing bounded theorem/proof packet, source rescue disabled;
- **B — Proof IR only:** exact `thorn-proof/1` packet, source rescue disabled;
- **C — Proof IR + rescue:** the same exact `thorn-proof/1` mathematical packet,
  with one bounded rescue permitted.

All three arms use the same model, system prompt, structured response schema,
fixture set, no-defender policy, and scoring contract. B and C differ only in
the minimal source-rescue protocol declaration. The primary comparison is A vs
C; B measures how self-sufficient the recovered Proof IR is when source cannot
be reopened.

A finding is not scored correct merely because its category matches fixture
metadata. Manual mathematical adjudication must confirm that the explanation
identifies the planted defect. The run output also records source rescue,
requested addresses, input and rescued-source sizes, token usage, request count,
request fingerprints, and cost when authoritative cost data is available.

## Keyless preparation

The complete initial A/B/C inventory is built without constructing a provider:

```bash
OPENAI_API_KEY="" python scripts/prepare_proof_review_experiment.py \
  --output /tmp/thorn-proof-review-inventory.json
```

This is the normal local-NLP path. `--structural-only` exists only as a debugging
and CI smoke fallback. The inventory reports the exact checkout revision, case
and packet counts, raw and Proof-IR payload character/byte totals, per-arm
request totals, advertised source-address count, prompt/schema hashes, all
initial fingerprints, and explicit `provider_requests = 0` / `live_requests =
0` counters.

## Separately authorized live run

Do not run the paid experiment as part of issue #78. After separate explicit
live-call authorization, use the frozen manifest and record every exchange:

```bash
python scripts/run_proof_review_experiment.py \
  --live \
  --record-dir /path/to/proof-review-recordings \
  --output /path/to/proof-review-results.json \
  --model gpt-5.6
```

The command requires the normal local NLP model and a separately configured
`OPENAI_API_KEY`. `--live` is mandatory and a live run also requires
`--record-dir`, so the script cannot accidentally turn a replay/preparation
invocation into a paid request.

Exact recordings can later be rerun keylessly:

```bash
OPENAI_API_KEY="" python scripts/run_proof_review_experiment.py \
  --replay-dir /path/to/proof-review-recordings \
  --output /tmp/proof-review-replay.json \
  --model gpt-5.6
```

The same protocol is intentionally usable by `thorn-private` later; no private
paper source, provenance, fixtures, or author-specific results are included in
the public challenge set.
