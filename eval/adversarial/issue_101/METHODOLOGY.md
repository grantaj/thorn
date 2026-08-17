# Issue #101 adaptive red-team methodology

This directory is the durable public record for issue #101. It is an assurance investigation, not a collection of model-prompt tricks.

## Invariant

The defective family fixes one mathematical error before any adaptive work: the paper claims a single uniform index for the profiles `x^n` on `[0,1)`. For `epsilon=1/2`, every proposed integer `N` is defeated by `x_N=(3/4)^(1/N)`, since `x_N<1` but `x_N^N=3/4`. Every defective variant must remain false for this same reason.

The matched clean control fixes `0<rho<1` and works on `[0,rho]`. It was frozen with the baseline in commit `18bfa5e313f6de187af9da49b8cb430c442c0792` before the adaptive variants were added.

## What may change

An adversarial author may alter wording, notation, theorem/lemma decomposition, local conventions, source organization, and presentation of standard results. The author may not add the missing compactness/margin premise, weaken the theorem, remove the proof, or otherwise make the claimed uniform estimate true.

Malformed LaTeX, parser crashes, meaningless statements, and deliberate non-mathematical obfuscation do not count as attacks.

## Keyless evidence rule

No live provider response is treated as available in this tranche. A fake transport is used only to exercise review-state and cache transitions; its empty response is never evidence that mathematics is clean.

A keyless success therefore requires a deterministic assurance failure before model reasoning, such as:

- load-bearing source information lost by extraction or canonicalization;
- a dependency/scope edge that disappears;
- authoritative context that is neither rendered nor reachable by bounded `NEED_SOURCE`;
- unsafe semantic-cache reuse after a mathematically relevant source/dependency change;
- a report/visualization that conceals a concern already present upstream.

If a faithful packet reaches the model boundary, the keyless outcome is `ambiguous`, not `caught`: a fresh model response would be needed to adjudicate semantic reasoning.

## Earliest-boundary classification

The journal classifies the first failing layer, rather than adding a later heuristic:

1. source/extraction loss;
2. canonical representation loss;
3. dependency/scope/proof-structure loss;
4. rendering/model-packet salience loss;
5. source-reachability/rescue loss;
6. review-protocol/state loss;
7. semantic-cache under-invalidation;
8. model reasoning miss over faithful context;
9. Lean/formalisation boundary issue;
10. report/UX concealment.

A downstream symptom does not replace an earlier diagnosis. In particular, missing review context is not repaired by prompt wording or report decoration.

## Incremental-cache lane

The #10 cache is attacked separately from semantic reasoning. Starting from a cached review, the harness mutates:

- source wording that normalizes to the same `thorn-proof/1` packet;
- a relevant upstream proof while the target packet remains unchanged;
- dependency-edge identity/topology;
- nearby exposition intended to be irrelevant.

A `cache_hit_*`/reuse decision after one of the first three changes is a first-class red-team success. Conservative rechecks are recorded as robustness evidence (and, for genuinely irrelevant exposition, possible efficiency over-invalidation), not silently normalized away.

## Public/private discipline

Public Thorn contains the frozen baseline/control, several representative attacks, the observer, methodology, journal, and reduced regressions for understood failure classes. The private `grantaj/thorn-private` repository is used for unreleased adaptive shapes. Public CI never depends on private material.

## Reports and formalisation

The keyless observer builds the production browsable report and proof visualizer and verifies result identity survives those projections. Without a semantic finding it does not pretend to assess finding prose. Where an earlier layer loses the mathematical distinction, report inability to explain that distinction is recorded as a downstream consequence, not reclassified as a report-layer failure.

Lean status is recorded for every public case. `unsupported` is not evidence for or against the paper's mathematics; it identifies the current formalisation boundary only.
