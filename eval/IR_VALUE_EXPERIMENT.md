# Does compact Math IR help semantic review?

Issue #47 is a pre-registered experiment about the value of Thorn's structural prior.
The compact renderer introduced by #43 / PR #46 is frozen for this experiment: cases or
rendering should not be tuned in response to model outcomes.

## Question

The previous six-case experiment established that compact Math IR can be much smaller
than both the old full-IR serialization and the raw review packet while preserving the
six mathematical decisions in that sample. It did not establish *why* compact IR worked.

Three possibilities matter:

1. the Math IR structure genuinely helps a model reason about a proof;
2. compact IR is mainly useful semantic compression;
3. the structural prior removes information a sufficiently capable model would have used.

The third possibility is especially important as models improve. Thorn should not force a
model to reason only inside a lossy parser interpretation unless that restriction earns its
keep.

## A prompt confound in the older evaluator comparison

The existing `thorn-eval --review-context raw|ir` modes are useful engineering paths, but
they are not a clean causal comparison of representations. `raw` uses the attack-provider
path and attacker system prompt, while `ir` uses the semantic-review provider path and
semantic-reviewer system prompt.

Issue #47 therefore uses dedicated experiment envelopes. Every arm has exactly the same:

- semantic-reviewer system prompt;
- model identifier;
- provider contract and request kind;
- structured-output schema;
- confidence/scoring policy in a future live run;
- no defender.

Only the user-visible mathematical context changes.

## Frozen representation arms

### A — `raw`

The selected raw `TheoremUnit` packet, rendered by the existing raw theorem renderer.

### B — `compact_ir`

The compact result-level `SemanticReviewItem` projection from Math IR.

### C — `raw_plus_compact`

Both A and B in the same request. This is intentionally somewhat redundant: the point is
to give the model Thorn's structure as optional scaffolding without making that structure
an information bottleneck.

If C beats A while B loses to A, that is evidence for keeping IR as an assistive structural
prior rather than replacing the source packet.

## Pre-registered challenge set

`eval/ir-value-challenge.json` freezes 16 existing public synthetic fixtures before any
A/B/C outcomes are observed.

Six clean/defect pairs cover:

- cancellation and missing hypotheses;
- quotient well-definedness;
- valid versus invalid WLOG reasoning;
- clean versus broken result dependencies;
- expository versus load-bearing sneaky prose;
- unusual-but-clear versus genuinely colliding notation.

Four harder unpaired defects cover:

- quantifier order;
- the Rolle proof gap;
- a hidden Riemann-hypothesis dependency;
- a proof that establishes only a weaker statement than claimed.

The challenge set must not be changed merely to improve a model or representation score.
A future experiment may add a separately pre-registered holdout set instead.

## Keyless inventory

The preparation step constructs the exact request envelopes without constructing a semantic
provider or reading an API key:

```bash
OPENAI_API_KEY="" python scripts/prepare_ir_value_experiment.py
```

Normal preparation uses Thorn's local spaCy frontend, matching normal Math IR construction.
`--structural-only` is available only as a debugging/degraded path.

The JSON inventory reports, for every case and arm:

- exact model-facing user-content character count;
- exact UTF-8 byte count;
- the request fingerprint used by Thorn's record/replay boundary.

It also records one system-prompt SHA-256 and verifies that all cases and arms share it.
`provider_requests` and `live_requests` are both zero.

The preflight deliberately does **not** estimate token count from characters. Exact token
usage is provider/model specific and will be recorded from actual provider usage only if a
live run is separately authorized.

## Later live protocol — not authorized by this preparation tranche

A full A/B/C run is exactly:

```text
16 cases × 3 representation arms = 48 model requests
```

When explicitly authorized, the run should:

- use one fixed model and model version where available;
- use the same semantic-review prompt and response schema for all arms;
- disable the defender;
- keep the compact renderer and challenge manifest frozen;
- randomize or otherwise avoid systematic arm-order effects where practical;
- record every successful exchange through Thorn's exact record/replay provider;
- report request count, input/output/total tokens, latency, and exact configuration;
- score mathematical decisions separately from Thorn taxonomy labels.

The Rolle case is a known reason for the last point: a model may identify the mathematical
failure correctly while choosing a different defensible finding category.

## Interpretation

The primary question is mathematical decision quality, followed by false positives and
cost:

```text
compact IR > raw
    structural prior is adding semantic value

compact IR ≈ raw, materially cheaper
    IR is useful primarily as semantic compression

raw + compact IR > raw, but compact IR < raw
    IR helps as scaffolding but is too lossy as the sole representation

raw >= compact IR and raw >= raw + compact IR
    the structural prior is not earning enough; direct token compression becomes the
    next hypothesis to test
```

A future fourth arm may compare a non-IR compressed-raw packet. That control is intentionally
out of scope until this A/B/C question has been answered.
