# Focused REQUIRE relation-extraction evaluation

Issue #219 isolates the semantic question left after the natural-corpus pressure
test of Thorn's frozen handwritten graph-effect compiler:

> given a known proof/result owner, an exact result-reference occurrence, and
> an independently resolved target, does the bounded prose express a direct
> prerequisite relation?

The candidate model does **not** parse LaTeX, discover canonical entities,
resolve references, infer the current proof owner, or mutate Thorn's dependency
graph. A score is evidence, not mathematical authority. A sufficiently high
score may propose `REQUIRE`; every lower score is abstention, never canonical
`NON_REQUIRE`.

## Model-neutral boundary

`thorn.research.require_relations.RequireRelationQuery` supplies:

- the canonical owner identity;
- bounded local context and its exact source span;
- the exact typed reference occurrence and provenance;
- the independently resolved canonical target.

The public benchmark is synthetic/minimally authored text with parsing,
workspace resolution, owner identity, endpoint identity, and provenance held
fixed. It contains 34 cases and 39 exact reference occurrences:

- 17 `REQUIRE` occurrences;
- 15 resolved `NON_REQUIRE` occurrences;
- 7 deliberately `UNRESOLVED` occurrences.

It covers explicit and implicit direct support, operator-present and
operator-absent positives, mentions, comparisons, attribution, reported use,
quotation, hypothetical use, explicit non-use, ambiguous rhetorical references,
cross-sentence context, mixed multi-reference cases, and joint/alternative
support pressure. No real-paper prose or provenance is present.

## Frozen public relation labels

Both off-the-shelf candidates were measured with the same three public labels:

1. `uses as a direct prerequisite`;
2. `depends on for this proof`;
3. `is required to establish the current result`.

The labels are evaluated independently so one wording cannot affect another
through candidate-label competition. Exact endpoint preservation is measured
separately from semantic relation correctness.

## Candidate 1: GLiREL

The GLiREL adapter adds a neutral `THORNOWNER:` transport sentinel before the
source context and supplies that sentinel plus every exact `THORNREFn`
occurrence as model entities. The evaluated direction is:

```text
THORNOWNER --[candidate relation]--> THORNREFn
```

The completed keyless measurement used:

- Thorn revision `00f58ef63b2a2a548b28b125930e4ae3087aa987`;
- `jackboyla/glirel-large-v0` revision
  `40a523e12a8432d6da364cf2a195a28755ff04d3`;
- GLiREL 1.2.1 and PyTorch 2.6.0 CPU;
- workflow run `32815718381`;
- artifact `9551365367`;
- artifact ZIP SHA-256
  `587c32fc48a1ff7de9a4875895eea6244595dfe0f7955d90c920618484742491`;
- measurement JSON SHA-256
  `cae3a075abcd347712c93ab254aa6be8eb350a62357008766c3a2c75f3a74df2`.

All three labels preserved the supplied endpoint in 39/39 occurrences. The
useful portion of the threshold sweep was:

| Relation label | Threshold | TP | FP | Precision | Recall | Ambiguous asserted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `uses as a direct prerequisite` | 0.10 | 14 | 10 | 0.583 | 0.824 | 6/7 |
| `uses as a direct prerequisite` | 0.20 | 4 | 4 | 0.500 | 0.235 | 0/7 |
| `depends on for this proof` | 0.10 | 14 | 12 | 0.538 | 0.824 | 7/7 |
| `depends on for this proof` | 0.20 | 7 | 2 | 0.778 | 0.412 | 1/7 |
| `is required to establish the current result` | 0.10 | 14 | 7 | 0.667 | 0.824 | 5/7 |
| `is required to establish the current result` | 0.20 | 3 | 0 | 1.000 | 0.176 | 0/7 |

The strongest safety-first public configuration is therefore:

```text
label = "is required to establish the current result"
threshold = 0.20
```

It recovers three of 17 expected prerequisites with no false `REQUIRE` on the
15 resolved-reference negatives and no assertions on the seven deliberately
ambiguous occurrences. Those three recovered references are all
operator-absent positives, including both references in a joint-support case.

The measured model has 466,577,920 parameters, used about 4.1 GiB peak RSS on
CPU, and spent about 57.3 seconds in the three label evaluations after model
loading. Exact aggregate measurements are in
`research/dependency-semantics/glirel_require_result.json`.

## Candidate 2: GLiNER-RelEx

The second candidate uses `knowledgator/gliner-relex-large-v1.0`. Its current
RelEx inference API accepts supplied character `input_spans`, so the evaluator
passes the exact owner sentinel and exact reference spans instead of asking the
model to discover entity boundaries.

The completed keyless measurement used:

- Thorn revision `a92c0e039eddeae14edb819b1861b485cff4f5b0`;
- `knowledgator/gliner-relex-large-v1.0` requested revision `4aedc92`, resolved
  to `4aedc9226a5ac9e2f6b5ea3e91c1ee577c88a290`;
- GLiNER 0.2.28 and PyTorch 2.6.0 CPU;
- workflow run `32833062907`;
- artifact `9557596038`;
- artifact ZIP SHA-256
  `5d6d5e5b81e0187a1d09367b0fa2b9a3a4f88c22fcc8762f6fcfc85943dbfb19`;
- measurement JSON SHA-256
  `91c21d3ccfff87059310b4538339646aef0e5636dd0d7672af28af5498ec2890`.

The adapter boundary succeeds cleanly: every frozen label preserves all 39/39
supplied owner/reference endpoints and exposes all 39/39 exact owner-to-reference
relation candidates. The negative result is semantic rather than a provenance
or entity-boundary failure.

For the first two relation labels, scores are almost saturated for positives,
negatives, and ambiguous cases alike. Even at threshold 0.90 they retain all 17
true prerequisites while also asserting 15/15 or 14/15 resolved negatives and
7/7 ambiguous occurrences.

The third label is less saturated but still does not expose a useful safety
regime:

| Threshold | TP | FP | Precision | Recall | Ambiguous asserted |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.50 | 9 | 10 | 0.474 | 0.529 | 5/7 |
| 0.80 | 6 | 7 | 0.462 | 0.353 | 4/7 |
| 0.90 | 5 | 4 | 0.556 | 0.294 | 4/7 |

Examining every observed score cut-point, not only the predeclared sweep,
produces **no non-empty threshold** for any of the three labels that retains a
true `REQUIRE` while making both resolved-negative false assertions and
ambiguous assertions zero. The third label can eliminate resolved-negative
false positives only while it still asserts ambiguous cases.

The measured GLiNER-RelEx model has 466,576,896 parameters, used about 2.7 GiB
peak RSS on CPU, and spent about 127.5 seconds in inference across the three
label evaluations. Exact aggregate measurements are in
`research/dependency-semantics/gliner_relex_require_result.json`.

## Comparative disposition

The second candidate does not improve the false-authority/coverage frontier.
Under Thorn's safety-first policy, GLiREL is the clear public candidate because
it is the only measured extractor with a non-empty zero-false-authority
abstention regime.

The exact configuration is now frozen in
`research/dependency-semantics/require_relation_candidate_freeze.json` before
any private natural-corpus qualification:

```text
model = jackboyla/glirel-large-v0
revision = 40a523e12a8432d6da364cf2a195a28755ff04d3
label = "is required to establish the current result"
threshold = 0.20
decision = score >= threshold -> propose REQUIRE; otherwise abstain
```

This freeze is a research proposal boundary, not production authority. The next
experiment is an untouched private holdout qualification of this exact
configuration. The private corpus must not be used to change the model,
relation label, threshold, directionality, context policy, benchmark, or
positive/negative decomposition.

No production `DependencyGraph` semantics, #212 calculus, `DECLARE` behavior,
or mandatory Thorn runtime dependency changes as a result of this evaluation.
If the frozen GLiREL regime does not generalize privately, the evidence should
motivate a separate task-specific supervision/fine-tuning experiment rather
than another expansion of handwritten English rules or post-holdout tuning.
