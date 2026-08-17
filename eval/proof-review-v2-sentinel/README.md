# Post-#90 proof-review v2 sentinel

This directory is a deliberately tiny, separately frozen paid-evaluation gate for
the post-#83 structural sequence (#87, #88, #89, #90).

It is **not** an extension of `eval/proof-review-challenge.json`. That historical
manifest remains the archived v1 experiment.

The sentinel contains one matched pair:

- `clean.tex`: the theorem claims existence and the proof gives an explicit witness;
- `defect.tex`: the same paper/proof instead claims uniqueness, which the proof does
  not establish and which is false because both square-root signs satisfy the
  project-level relation.

Both papers intentionally place the relation definition outside the theorem so
that the live C arm can exercise authoritative project context, closed-world
source selection, carried review state, and goal-versus-supported-conclusion
review without requiring source rescue merely to pass.

The three initial arms remain:

1. `raw` — bounded raw theorem/proof source, no rescue;
2. `proof_ir` — exact `thorn-proof/1`, no rescue;
3. `proof_ir_rescue` — the same Proof-IR packet with at most one bounded exact
   source-rescue turn.

Two cases therefore mean six initial model calls and at most two rescue calls:
**eight live calls maximum**. OpenAI SDK retries remain disabled and each
proof-review request retains the existing 4096-token output cap.

## Freeze discipline

`manifest.json` records the post-#95 main revision, model, protocol, prompt
version, scoring rules, request ceiling, and—once frozen—the exact prompt hash,
fixture/metadata hashes, and all six initial request fingerprints/schema hashes.

Before a live run, execute the normal local-NLP preflight:

```bash
OPENAI_API_KEY="" python scripts/prepare_proof_review_sentinel.py \
  --output /tmp/proof-review-v2-sentinel.json
```

A frozen manifest must verify all six request contracts keylessly before
`scripts/run_proof_review_sentinel.py --live` will construct the provider.

Do not tune fixtures, prompt, scoring, model, output cap or retry policy after the
first successful semantic review response. A request rejected by the API before
semantic review because the structured-output contract itself is invalid is a
transport/preflight defect, not a mathematical outcome. Such a defect may be
repaired only through a general protocol fix, followed by a complete keyless
refreeze of every changed request contract before another live attempt.

## Pre-semantic transport repair

The first live transport attempt never produced a model response. OpenAI rejected
the no-rescue response schema with HTTP 400 because Pydantic encoded mechanically
empty `tuple[()]` fields as arrays with `maxItems: 0` but no `items` schema.

The repair is provider-independent and preserves the existing closed-world
semantics: every mechanically empty response array now retains its actual item
type plus `maxItems: 0`. The only representable value is still the empty array,
but the generated JSON Schema is valid for strict structured-output transport.
The sentinel fixtures, prompt, model and scoring were not changed. Because the
response schema participates in request fingerprinting, all six initial request
contracts must be refrozen after this repair before any second live attempt.
