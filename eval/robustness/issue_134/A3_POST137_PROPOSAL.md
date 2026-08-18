# A3 post-#137 pre-#125 continuation

This is a new, separately frozen continuation of issue #134 for **A3 only**.

The original post-#132/pre-#125 batch produced accepted live semantic-review measurements for A1 and A2. A3 stopped before a usable semantic outcome because the provider-facing structured-output contract admitted an action/state combination that Thorn rejected only after the provider response had completed. Issue #137 repaired that general schema/transport defect keylessly.

The #137 repair intentionally changes the provider-visible request contract. Therefore the original A3 request fingerprint is historical evidence and must not be silently replaced in the original freeze. This continuation freezes a new A3 request on the repaired assurance tree while leaving A1 and A2 untouched.

## Scientific question

With the A3 manuscript and mathematical target unchanged, and with the general #137 transport repair in place, does production `thorn-proof/1` + `thorn-proof-review/2` semantic review identify that a correct result is being applied outside its hypotheses/domain?

The observation is intended to distinguish the result-applicability reasoning/salience boundary from transport/protocol defects. It is not a new adaptive manuscript search and it does not weaken the independent reason to implement #125 after the pre-#125 baseline is complete.

## Frozen continuity

- A1: preserve the accepted pre-#137 live measurement; **do not resample**.
- A2: preserve the accepted pre-#137 live measurement and the independently established pre-#125 representation/reachability defect; **do not resample**.
- A3: same frozen manuscript, source hash, theorem target and variation family as the original issue #134 freeze.
- The original A3 initial request fingerprint remains recorded as the predecessor fingerprint.
- The new initial request fingerprint is frozen only after reconstruction on the post-#137 `src/thorn` assurance tree.
- No issue #125 implementation belongs to this tranche.

## Keyless freeze

The freeze must verify, without constructing a provider:

- exact Thorn assurance revision and `src/thorn` tree identity;
- exact A3 source SHA-256;
- unchanged path, target and variation family relative to the original issue #134 manifest;
- model `gpt-5.6`;
- representation `thorn-proof/1`;
- protocol `thorn-proof-review/2`;
- prompt version and prompt bytes;
- one bounded source-rescue turn with at most eight addresses;
- zero implicit provider retries;
- at most two provider requests total;
- 4096 output tokens per request and 8192 aggregate output tokens;
- a hard 40000 aggregate input-token ceiling with a conservative pre-request guard;
- exact reconstructed post-#137 initial request fingerprint.

The candidate fingerprint is computed keylessly first. Once recorded in the manifest, the same preflight must require exact equality. Any later `src/thorn` or request-contract drift stops this experiment and requires another explicitly named freeze rather than mutation of this one.

## Live discipline

This proposal and its merge **do not authorize a paid call**. A live run requires a separate explicit authorization after the frozen keyless preflight is green and official provider pricing has been checked at that time.

If later authorized, the run is limited to A3 only:

1. one initial request;
2. at most one bounded exact source-rescue request if requested by the reviewer;
3. exact recording of every completed provider exchange and usage;
4. immediate keyless replay of the accepted exchange(s);
5. HTML review report preservation;
6. independent mathematical adjudication and earliest-boundary classification;
7. abort rather than widening limits, changing the manuscript, resampling A1/A2, or modifying the protocol after seeing output.

A completed provider response that Thorn rejects locally is still preserved as failure evidence under the #137 accounting contract and is not silently discarded or retried.

## Interpretation

A successful A3 semantic diagnosis would be evidence that the repaired production review boundary can catch this result-applicability defect with faithful represented context. A miss would be classified at the earliest demonstrated boundary rather than patched at a later layer. Either outcome completes the intended pre-#125 A3 observation.

After that observation is preserved, issue #125 may proceed under a separately frozen post-repair experiment for A2 plus an independent held-out prose-definition/ambient-convention case.
