# Focused REQUIRE relation-extraction evaluation

Issue #219 isolates the remaining semantic question after the natural-corpus
pressure test of the frozen handwritten compiler:

> given a known proof/result owner, an exact result-reference occurrence, and
> an independently resolved target, does the bounded prose express a direct
> prerequisite relation?

This research path deliberately does **not** ask a model to parse LaTeX,
discover entities, resolve references, infer the current proof owner, or mutate
Thorn's dependency graph.

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

The benchmark includes:

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
THORNOWNER --[uses as a direct prerequisite]--> THORNREFn
```

Reverse-direction scores are retained as a diagnostic rather than silently
accepted.

## Configuration discipline

The public benchmark freezes three candidate relation-label phrasings:

1. `uses as a direct prerequisite`;
2. `depends on for this proof`;
3. `is required to establish the current result`.

The initial workflow evaluates the first label. Alternative phrasings can be
measured on this public benchmark, but label wording, threshold, directionality,
and context policy must be frozen before any private natural-corpus holdout is
examined.

The evaluator records raw per-occurrence scores and a threshold sweep rather
than selecting a single cutoff in advance.

## Reproducibility and dependency boundary

GLiREL remains a research-only dependency and is not added to Thorn's
`pyproject.toml`. The issue-specific workflow creates an isolated environment,
uses CPU inference, pins the GLiREL package and primary model revision, records
the resolved upstream model revisions, and uploads the full measurement JSON.

Ordinary Thorn installation and production semantics remain unchanged.

## Progression rule

Only an off-the-shelf configuration with a credible high-precision regime,
exact endpoint preservation, and low assertion rates on resolved-reference
negatives/ambiguous cases should progress to the frozen private natural-corpus
holdout.

If no candidate is close, #219 should stop with that evidence. Fine-tuning or a
new trained component would be a separate experiment with separately sourced
development data.
