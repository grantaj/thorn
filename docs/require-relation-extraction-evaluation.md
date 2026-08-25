# Focused REQUIRE relation-extraction evaluation

Issue #219 isolates the remaining semantic question after the natural-corpus
pressure test of the frozen handwritten compiler:

> given a known proof/result owner, an exact result-reference occurrence, and
> an independently resolved target, does the bounded prose express a direct
> prerequisite relation?

This research path deliberately does **not** ask a model to parse LaTeX,
discover canonical entities, resolve references, infer the current proof owner,
or mutate Thorn's dependency graph.

## Model-neutral boundary

`thorn.research.require_relations.RequireRelationQuery` supplies:

- the canonical owner identity;
- bounded local context and its exact source span;
- the exact typed reference occurrence and provenance;
- the independently resolved canonical target.

Candidate models return only non-authoritative relation scores tied back to the
supplied reference occurrence.

A score is evidence, not mathematical authority. The experiment evaluates a
fail-closed policy in which a sufficiently high score may propose `REQUIRE`;
all lower scores abstain. It never converts a low score into a canonical
`NON_REQUIRE` assertion.

## Public benchmark

`require_relation_cases.json` is synthetic/minimally authored public text. It
holds source parsing, workspace resolution, owner identity, endpoint identity,
and provenance fixed so the experiment measures relation semantics rather than
the rest of Thorn.

The benchmark contains 34 cases and 39 exact reference occurrences:

- 17 `REQUIRE` occurrences;
- 15 resolved `NON_REQUIRE` occurrences;
- 7 deliberately `UNRESOLVED` occurrences.

It includes:

- explicit and implicit direct support;
- operator-present and operator-absent positives;
- mentions, comparisons, attribution, reported use, quotation, hypothetical
  use, explicit non-use, and independent-proof negatives;
- ambiguous rhetorical/optional references;
- cross-sentence context;
- multiple references with mixed roles;
- joint and alternative support pressure.

Every reference occurrence has an exact synthetic source identity and character
span. No real-paper prose or provenance is used.

## GLiREL adapter

The first off-the-shelf candidate is GLiREL. GLiREL expects both ends of a
candidate relation to appear as supplied entities in the model token stream.
The adapter therefore adds a neutral `THORNOWNER:` sentinel before the source
context and supplies that sentinel plus all exact `THORNREFn` occurrences as
entities.

The owner sentinel is transport scaffolding only:

- it does not come from source evidence;
- it does not resolve anything;
- it does not add a support cue;
- it is never used as provenance;
- the original reference occurrence remains independently source-grounded.

The evaluated direction is:

```text
THORNOWNER --[candidate relation]--> THORNREFn
```

Reverse-direction scores are retained as a diagnostic rather than silently
accepted.

## Frozen public labels

The public benchmark freezes three relation-label phrasings:

1. `uses as a direct prerequisite`;
2. `depends on for this proof`;
3. `is required to establish the current result`.

All three are evaluated independently so a model's label-ranking competition
cannot change one label's score merely because another candidate wording is
present. Raw per-occurrence scores and threshold sweeps are retained.

## GLiREL measurement

The completed keyless run used:

- Thorn revision `00f58ef63b2a2a548b28b125930e4ae3087aa987`;
- `jackboyla/glirel-large-v0` revision
  `40a523e12a8432d6da364cf2a195a28755ff04d3`;
- GLiREL 1.2.1;
- PyTorch 2.6.0 CPU;
- workflow run `32815718381`;
- artifact `9551365367`;
- artifact ZIP SHA-256
  `587c32fc48a1ff7de9a4875895eea6244595dfe0f7955d90c920618484742491`;
- measurement JSON SHA-256
  `cae3a075abcd347712c93ab254aa6be8eb350a62357008766c3a2c75f3a74df2`.

All three labels preserved the supplied reference endpoint in 39/39
occurrences. This is necessary but is not counted as semantic success.

The most useful portion of the threshold sweep is:

| Relation label | Threshold | TP | FP | Precision | Recall | Ambiguous asserted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `uses as a direct prerequisite` | 0.10 | 14 | 10 | 0.583 | 0.824 | 6/7 |
| `uses as a direct prerequisite` | 0.20 | 4 | 4 | 0.500 | 0.235 | 0/7 |
| `depends on for this proof` | 0.10 | 14 | 12 | 0.538 | 0.824 | 7/7 |
| `depends on for this proof` | 0.20 | 7 | 2 | 0.778 | 0.412 | 1/7 |
| `is required to establish the current result` | 0.10 | 14 | 7 | 0.667 | 0.824 | 5/7 |
| `is required to establish the current result` | 0.20 | 3 | 0 | 1.000 | 0.176 | 0/7 |

At 0.30 every label abstains on every occurrence. The exact recorded summary is
`research/dependency-semantics/glirel_require_result.json`; the workflow
artifact retains the full per-occurrence scores and complete threshold sweeps.

The strongest public GLiREL configuration is:

```text
label = "is required to establish the current result"
threshold = 0.20
```

It proposes three of the 17 expected prerequisites and produces no false
`REQUIRE` on the 15 resolved-reference negatives or the seven deliberately
ambiguous occurrences. All three recovered references are operator-absent
positives: one ordinary support case and both references in a joint-support
case.

## GLiNER-RelEx comparator

The second candidate was evaluated only after the benchmark, three relation
labels, and GLiREL measurement were frozen. No private examples were inspected
or used for its configuration.

GLiNER-RelEx differs architecturally from GLiREL: its public inference API
jointly discovers entities and relations rather than accepting Thorn's entity
spans. Thorn therefore gives it credit only when a discovered entity's exact
character span equals the already-known `THORNOWNER` or `THORNREFn` sentinel.
This remapping is deliberately one-way: a model-discovered entity can match a
supplied identity, but can never replace or invent canonical Thorn identity.

The successful keyless measurement used:

- Thorn revision `f677b4d915ee1df78f480c38d0b53e2a87ba814f`;
- `knowledgator/gliner-relex-base-v1.0` revision
  `e6a880049a19c5cc222a7a479c32e84b0d8cdd9a`;
- GLiNER 0.2.28;
- workflow run `32832930044`;
- artifact `9557632070`;
- artifact ZIP SHA-256
  `d67e17cc617bb6c183d8cc17a52f5076b5ef897a98d76360ea28b0190735f986`;
- measurement JSON SHA-256
  `2b0d8701d448fa0cdcbdfb16f162dc74a6a2ec40af8dd73445dbe0a5ed71b3a0`.

The strict transport test succeeded: the candidate rediscovered the exact owner
and reference sentinel spans for 39/39 occurrences under every frozen label.
Semantic discrimination did not.

| Relation label | Threshold | TP | FP | Precision | Recall | Ambiguous asserted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `uses as a direct prerequisite` | 0.90 | 16 | 15 | 0.516 | 0.941 | 7/7 |
| `depends on for this proof` | 0.90 | 17 | 12 | 0.586 | 1.000 | 7/7 |
| `is required to establish the current result` | 0.80 | 16 | 10 | 0.615 | 0.941 | 7/7 |
| `is required to establish the current result` | 0.90 | 15 | 9 | 0.625 | 0.882 | 6/7 |

Lower thresholds are less selective. Thus GLiNER-RelEx has no useful
high-precision abstention regime on the frozen benchmark. Its exact entity
rediscovery is evidence that endpoint transport is not the problem; the failure
is relation semantics.

The measured model has 225,086,211 parameters, used about 6.36 GiB peak RSS on
CPU, and spent about 280.8 seconds in the three-label inference pass. The heavy
research workflow is manual-only after the recorded measurement. The exact
aggregate result is in
`research/dependency-semantics/gliner_relex_require_result.json`.

## Final public disposition

The independent comparator does not materially improve the precision/coverage
trade-off. GLiNER-RelEx is therefore not a private-qualification candidate.

The GLiREL configuration is now frozen for the untouched private holdout:

```text
model = jackboyla/glirel-large-v0
revision = 40a523e12a8432d6da364cf2a195a28755ff04d3
label = "is required to establish the current result"
threshold = 0.20
decision = score >= threshold proposes REQUIRE; otherwise abstain
```

The complete freeze, including entity direction, supplied-entity policy,
tokenization/context boundary, and prohibition on private tuning, is recorded
in `research/dependency-semantics/require_relation_selection.json`.

This is still **not production authority**. The next experiment is a holdout
generalization test only. The private corpus may measure whether this tiny
high-precision public regime survives natural mathematical prose, but it must
not change the model, label, threshold, context policy, directionality, entity
policy, or benchmark in response to private outcomes.

Fine-tuning, production graph mutation, `DECLARE`, and changes to the #212
calculus remain out of scope.
