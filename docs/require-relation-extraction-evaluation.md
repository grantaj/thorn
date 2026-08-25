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

All three are evaluated independently so GLiREL's label-ranking competition
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

### What the high-precision regime means

The strongest public configuration is currently:

```text
label = "is required to establish the current result"
threshold = 0.20
```

It proposes three of the 17 expected prerequisites and produces no false
`REQUIRE` on the 15 resolved-reference negatives or the seven deliberately
ambiguous occurrences. All three recovered references are operator-absent
positives: one ordinary support case and both references in a joint-support
case.

This is evidence that an off-the-shelf relation extractor can expose a small,
exactly grounded, high-precision subset without Thorn growing a handwritten
English grammar. It is not sufficient coverage for production authority.

## Runtime and dependency boundary

The measured model has 466,577,920 parameters. The CPU run loaded the model in
about 67.3 seconds, used about 4.1 GiB peak RSS, and spent about 57.3 seconds in
inference across the three independent label evaluations.

GLiREL remains a research-only dependency and is not added to Thorn's
`pyproject.toml`. The issue-specific workflow creates an isolated environment,
uses CPU inference, pins the GLiREL package and primary model revision, records
the resolved upstream model revisions, and uploads the full measurement JSON.
Ordinary Thorn installation and production semantics remain unchanged.

## Disposition after the first candidate

GLiREL is **not** promoted to production authority and is **not yet** taken to
the private natural-paper holdout. The zero-false-positive regime is credible
but covers only 3/17 expected prerequisites.

The next public tranche evaluates one independent off-the-shelf relation
extractor against the exact same benchmark and authority boundary. No benchmark
case, label, threshold, context policy, or private example is changed in
response to the GLiREL result. If no second candidate materially improves the
precision/coverage trade-off, the GLiREL configuration above is the candidate
to freeze before an untouched private holdout run.

Fine-tuning, production graph mutation, `DECLARE`, and changes to the #212
calculus remain out of scope.
