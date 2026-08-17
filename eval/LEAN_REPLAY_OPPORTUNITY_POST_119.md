# Lean replay opportunity after explicit-citation recovery

Issues: #115, #119

## Purpose

Issue #115 froze a small public normal-local-NLP inventory and found the clean
quickstart final theorem at class **E**: Thorn had already recovered the exact
result applications, target propositions, `x := 2` binding, and discharged
application precondition, but the cited-result support edges had been downgraded
to `ambiguous` before the canonical Lean handoff.

Issue #119 repairs that owning recovery boundary. This note records the required
rerun of the same public inventory rather than rewriting the historical #115
report after the fact.

## Reproduction

The Local NLP contract runs, keylessly:

```bash
python scripts/measure_lean_replay_opportunity.py \
  --thorn-revision "$(git rev-parse HEAD)" \
  --output /tmp/lean-replay-opportunity.json
```

The first post-#119 workflow rerun completed successfully on the PR merge revision
`dc0184bad9419874c4f28b03f1dddd3a46b28dcd`, over #119 branch head
`969265c92506d08f5b5705178b45f26bc0323b65` stacked on the #118 evaluation
branch. The run made no provider/model calls. Subsequent #119 commits at the time
of this note are documentation and a static-typing-only rename; CI reruns the same
normal-path contract.

## Mechanical change in the frozen public inventory

The decisive public case changes exactly as intended.

### `quickstart_transfer` / `thm:main`

Before #119:

- two `result_application` transformations existed but were `ambiguous`;
- the second application had a confident `x := 2` binding and a discharged
  `E(2)` precondition;
- whole-result Lean replay was blocked by ambiguous canonical support.

After #119:

- both result support atoms are `confident`;
- both `result_application` transformations are `confident`;
- the second application still records one application obligation, with the
  expected proposition present and status `discharged`;
- its universal parameter binding remains confident;
- `opaque_source_address_count` is zero for both applications;
- whole-result Lean status is `complete`;
- `contains_sorry` is false;
- `is_mechanically_checkable` is true.

The separate Lean contract exercises the same quickstart through the **normal
local-NLP path**, without `--structural-only`, requires a complete hole-free
artifact, and the pinned Lean executable accepts it.

### Missing-precondition calibration

The paired theorem-application fixture remains deliberately non-checkable:

- the cited result support is confident;
- the result application is identified;
- its universal binding is confident;
- the expected application precondition is present as an obligation;
- `satisfied_by_count` is zero;
- the obligation and transformation remain `unresolved`;
- whole-result Lean status is `partial`;
- the recorded reason is `missing_result_precondition`;
- generated Lean contains `sorry` and is not classified mechanically checked.

This is important: #119 strengthens **which result the author is explicitly using
here**. It does not manufacture a premise or convert application identification
into validity.

## A/B/C/D/E effect

In the six ordinary public #115 cases, only the quickstart final theorem changes
classification:

| case | #115 | after #119 | reason |
| --- | --- | --- | --- |
| quickstart `lem:even-two` | D | D | internal proof remains outside current mechanical recovery |
| quickstart `lem:even-square` | D | D | witness/algebra proof remains outside current mechanical recovery |
| quickstart `thm:main` | **E** | **A** | explicit cited-result uses are now confidently corroborated and replay complete |
| quickstart cancellation defect | E | E | exact cancellation/division operation is still not recovered |
| square bound | D | D | no exact algebra/rewrite transformation recovered |
| monotone limit | D | D | substantive epsilon/infimum reasoning remains informal |

Thus the public ordinary lane changes from `A=0, B=0, C=0, D=4, E=2` to:

```text
A=1, B=0, C=0, D=4, E=1
```

The six private #115 classifications were not rerun by this public PR. If their
historical classifications are simply carried forward unchanged, the combined
12-case table becomes `A=1, B=0, C=0, D=4, E=7`; that combined number is a derived
comparison, not a fresh private-corpus measurement.

The #115 disposition therefore remains **NARROW**, but its key hypothesis now has
a real ordinary-product example: a mechanically closed local proof island can be
recovered and independently replayed inside a manuscript whose cited lemmas'
internal proofs remain informal/unsupported.

## Architectural result

The repair exposed a useful boundary that was previously split across the
pipeline.

A result citation has at least two different questions:

1. **support-role recovery:** is the author actually consuming this cited result
   at this proof point, rather than mentioning it expositionally?
2. **operation validity/checkability:** does the recovered application have the
   required bindings, premises, scope, and formal lowering needed for independent
   replay?

Local NLP alone cannot safely answer (1), because a reference can be expository.
Formula matching alone cannot safely answer it either, because matching
mathematics may be discussed without being consumed. #119 therefore combines
independent evidence at the **proof-support recovery boundary**, after linguistic
uncertainty and exact dependency resolution but before proof graphs, targeted
semantic review, canonical Proof IR consumers, or Lean see the relation.

Confidence is strengthened only when all of the following agree mechanically:

- the source has an asserted application/support role, not merely a nearby cue;
- the reference resolves to one exact result identity;
- cited result and asserted consequence lower fully;
- exactly one target fragment matches the cited result application shape;
- universal parameters are uniquely fixed;
- any explicit equality binding in the sentence agrees with the inferred binding.

An implication precondition is deliberately *not* discharged at this boundary.
It is carried forward as a separate downstream proof obligation.

### Simplification exposed by the boundary

The formula-shape part of result application is now isolated as a deterministic,
consumer-independent primitive rather than being conceptually owned by Lean.
That is the useful simplification: support recovery can ask whether an application
shape is corroborated without importing Lean semantics or proof-obligation
policy.

The later semantic-transformation layer still independently constructs the
canonical operation and checks local preconditions. Keeping those two facts
separate is intentional: #119 should not turn “we know what result the author
claims to use” into “the application is valid”. A future refactor may share more
of the pure formula-matching implementation to remove duplicated tree-walking,
but it should preserve this evidence/validation separation and should not make
support confidence depend on a Lean-specific representation.

## Negative controls

The #119 regression set additionally establishes that confidence is not promoted
when:

- a `By Lemma ...` sentence cites a result whose conclusion cannot instantiate to
  the claimed target;
- the source explicitly states a binding that contradicts the binding forced by
  the target;
- an expository sentence contains matching mathematics and even an unrelated
  leading `Using` cue, but does not grammatically assert the reference as the
  support for that target.

These controls run through the local-linguistic path. The existing 70-case spaCy
contract, full pytest suite, ruff, and normal CLI regressions remain part of the
acceptance surface.
