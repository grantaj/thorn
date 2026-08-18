# Issue #101 post-#128 semantic robustness experiment

## Status

**Frozen keylessly; not authorized for live execution by this document.**

This is a new experiment following the deterministic source-rescue repair in #128 / PR #129. It does not mutate or supersede the historical pre-repair manifest, proposal, recording, or C0 witness.

The historical experiment stopped after C0's initial response because Thorn expanded a valid two-handle model source request to 18 handles and rejected its own expansion. That outcome remains preserved in `LIVE_C0_PRE_REPAIR_RESULT.md`.

## Scientific question

With the source-rescue closure repaired, does Thorn's normal semantic-review path:

1. keep the matched clean control C0 clean;
2. surface the invariant uniformity defect in B0;
3. surface the same invariant defect when expressed through lemma indirection in A1;
4. characterize A2 consistently with its already-known representation/source-reachability limitation; and
5. surface the result-applicability defect in A3?

This run is intended to measure semantic-review behavior after the deterministic protocol boundary has been repaired. It is not a retry of the failed pre-repair batch under the old assurance state.

## Frozen assurance state

- Experiment ID: `issue-101-post-128`
- Manifest: `manifest_post128.json`
- Thorn assurance revision: `18c509f2d6414062a4da5311010c5346afd5b786`
- Frozen `src/thorn` tree: `02d9afdd478ae1ac30692907567237536b60cc66`
- Model alias: `gpt-5.6`
- Representation: `thorn-proof/1`
- Review protocol: `thorn-proof-review/2`
- Prompt: `proof_language_reviewer_v2`
- Cases: exactly C0, B0, A1, A2, A3

The manuscript bytes, source hashes, review targets, and initial provider-request fingerprints are intentionally unchanged from the historical manifest. The post-#128 freeze test reconstructs every initial request from the repaired assurance tree and requires those fingerprints to remain exact. This establishes that #128 changes the deterministic rescue handling rather than silently changing the initial semantic-review input.

## Frozen live bounds

A later authorized live execution must retain the existing bounded-provider discipline:

- at most 5 cases;
- at most 10 live provider requests total;
- one initial request plus at most one rescue request per case;
- aggregate input-token hard guard: 100,000;
- maximum output tokens per request: 4,096;
- maximum aggregate output allowance: 40,960;
- zero implicit SDK retries;
- record every accepted provider exchange;
- exact keyless replay immediately after the live batch;
- preserve reports and request/response evidence even if a later case stops the batch.

A later execution must stop before sending any request that would violate the frozen request or token ceilings.

## Preflight invariants

Before any new paid call:

1. `HEAD:src/thorn` must equal the frozen post-#128 source tree.
2. All five source SHA-256 values must match `manifest_post128.json`.
3. All five reconstructed initial provider requests must match their frozen fingerprints.
4. Those initial fingerprints must also equal the historical pre-repair fingerprints, demonstrating that the initial semantic inputs are unchanged.
5. The repaired C0 `T0,P3` source-selection shape must remain bounded by the eight-handle rescue contract under keyless regression tests.
6. Ordinary CI, Local NLP contract, and Lean contract must be green.
7. No historical #101 or #83 frozen evidence may be rewritten to make the new run fit.

## Live-run discipline

This proposal does **not** authorize a model call by itself. Once the freeze is merged and green, live execution requires a separate explicit authorization referring to this post-#128 experiment.

The temporary same-repository PR/CI pattern is acceptable for execution because it makes the paid job inspectable through ordinary PR workflow tooling. Any such branch must be scoped to this exact experiment, must not be merged, and must be removed or reset to `main` after its evidence has been preserved.

If the live run reveals another deterministic representation/protocol/report boundary before semantic adjudication, preserve the exact witness, stop adapting the manuscript, repair the earliest owning layer keylessly, and freeze a new experiment before any subsequent paid run.
