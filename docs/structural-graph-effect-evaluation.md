# Structural graph-effect compiler evaluation

Status: frozen #215 research result, stacked on PR #214 / #213. No production semantic cutover is made by this tranche.

## Question

#212 established a deliberately small semantic target for proof dependency:

```text
G = (V, REQUIRE, bind, payload, visibility, status)

DECLARE(v; bind, payload, visibility, status)
REQUIRE(u, v)
```

with `Resolve`, `Visible`, `Direct`, and dependency-relevant `Status` as the primitive observations, `Closure` derived from `Direct`, and exact provenance/evidence maintained independently as `P`.

#213 showed that a generic local NLI model could not infer these effects safely and, independently, could not ground their exact arguments. #215 therefore tested a different hypothesis:

> Can a very small structural compiler over Thorn's existing normalized linguistic facts, typed math/reference placeholders, and exact source correspondence recover a useful subset of `DECLARE` / `REQUIRE` without recreating a sentence-template grammar?

The experiment is deliberately narrower than a production migration. Its primary purpose is to learn what the #212 calculus lets Thorn simplify and where the current handwritten path is conflating distinct semantic observations.

## Frozen experiment

The first semantic measurement used:

- Thorn branch: `issue-215-graph-effect-compiler`, stacked on #214 head `a7fe42e92351a30d925779d4d2154a9fdafc55f2`;
- GitHub Actions run: `32668846274`;
- checked-out PR merge identity: `3034697c2f2cac3e0193a2bf86920ffe92f38a92`;
- Python 3.11.16 on Ubuntu 24.04;
- spaCy 3.8.14;
- `en_core_web_sm` 3.8.0;
- no provider/model API calls;
- frozen artifact ID `9500797603`;
- artifact ZIP SHA-256 `f98ac93cdde66a814113fb2fc065b9790fe590f4ad5e2a34c482a68c57ebcd3a`;
- exact records checked in as `research/dependency-semantics/structural_effect_measurements.json`.

The semantic operator inventory was fixed before the first successful semantic measurement:

```text
introduction: assume, define, fix, let, set, suppose
naming:       call, mean, say, term
support verb: apply, follow, invoke, use
support noun: consequence
condition:    if, provided, when, whenever
hypothetical: could, might, would
```

These are intended as a deliberately tiny set of graph-semantic operator classes around dependency structure, not whole-sentence templates. No operators or synonyms were added after seeing the results below. In particular, the misses on `write`, joint/alternative support, ambient conventions, visibility retraction, and status were left untouched.

## Main result: reference resolution is not dependency authority

The audit found that current theorem-reference construction partly conflates two observations that #212 keeps separate:

```text
Resolve(reference) = T
```

and

```text
REQUIRE(current_result, T)
```

A uniquely resolved theorem reference tells Thorn which result the source mentions. It does not by itself establish that the presented proof uses that result as a direct prerequisite.

The #213 effect corpus makes the cost of this conflation unusually clear:

| Candidate rule | REQUIRE precision | REQUIRE recall | False positive REQUIREs | Exact prerequisite endpoints |
| --- | ---: | ---: | ---: | ---: |
| every resolved `THORNREF` implies `REQUIRE` | 0.368 | 1.000 | 12 | not a relation-grounding test |
| frozen structural support compiler | **1.000** | **0.714** | **0** | **5/7 overall; 5/5 recognized** |

The structural compiler recognized five of seven positive direct-support cases:

- direct `By` support;
- `follows from`;
- `using`;
- `applying`;
- `as a consequence of`.

It emitted no `REQUIRE` for the negative controls where the referenced result was merely mentioned, explicitly not used, hypothetical, attributed, historical, quoted, stronger than the proof actually used, or merely similar to the proof.

It deliberately missed the two pressure cases labelled joint and alternative support. Nothing was added after measurement to recover them.

This is not yet enough natural-paper evidence to change production semantics, but it is strong evidence that the future production boundary should preserve reference resolution as an input fact and establish `REQUIRE` separately.

## Declaration result

On the unchanged 36-case #160 declaration corpus the structural candidate produced:

- precision: **1.000**;
- recall: **0.571** (12 true positives, 9 false negatives);
- unsafe negative cases: **0 / 17**;
- lexical-challenge recall: **0.500**;
- exact source grounding on every matched declaration: **1.000**.

On the five `DECLARE` cases added by #213 it recognized four (**0.800 recall**) and retained exact payload grounding for those four. It deliberately missed the `write` construction rather than extending the frozen vocabulary after inspection.

This is a useful but secondary result. Post-#203 Thorn is already allowed to preserve declaration-like prose as exact non-authoritative review context instead of forcing it into canonical mathematical authority. Therefore lower declaration recall is acceptable unless natural evidence shows that a missed declaration changes a dependency observation that bounded review cannot faithfully recover.

## Explicit gaps retained

### Visibility and retraction

The first structural compiler does not infer textual visibility changes. Its exact visibility-grounding rate on the #213 pressure cases is **0.0**. Structural extent, workspace order, and ordinary shadowing remain separately well-founded production mechanisms, but text such as an explicit temporary scope or later retraction remains an open calculus/inference problem.

Do not add `throughout`, `until`, `no longer`, or similar phrases merely to make these heldouts pass. First establish the minimal visibility update semantics required by `Q`.

### Status

The prototype deliberately has no textual status updater. `InferenceStatus` in the linguistic/support layers is assurance confidence, not the dependency-capability `status(v)` label from #212. The `unproved` / `established` cases remain explicit gaps.

### Joint versus alternative support

Both pressure cases are missed by the frozen structural rule. Current `Q` asks which direct prerequisites the argument actually presented depends upon; it does not ask for minimal sufficient alternative proof sets. The cases should remain in the corpus, but this result does not justify richer Boolean edge algebra.

### Ambient conventions and other prose declarations

The #160 ambient cases were intentionally not recovered by the prototype. They remain exact source-addressable advisory context in current production. Natural-corpus evidence should determine whether a general structural `DECLARE` rule is needed before another ambient phrase family is introduced.

## Comparison with #213 NLI

The structural result and the #213 NLI result fail in different ways.

The NLI candidate attempted direct semantic classification of graph effects but produced poor precision/recall and no argument spans. The structural candidate is deliberately incomplete, but where it emits a relation it retains exact typed endpoints and source correspondence.

That is a much better fit to Thorn's assurance model:

> explicit unresolved evidence is preferable to a plausible effect label whose graph arguments or provenance are fabricated.

The result does **not** prove that the frozen operator inventory is the final language of mathematical prose. It shows that a small structural compiler is a credible hypothesis worth attacking with natural-paper evidence.

## Disposition

1. Keep the #212 `DECLARE` / `REQUIRE` calculus as the semantic specification.
2. Treat the remaining handwritten semantic layer as a compiler into fields of those operations, not as a taxonomy of mathematical English.
3. Preserve current structured-math authority, workspace/source eligibility, occurrence-aware resolution, exact provenance, and support corroboration where they directly establish graph fields.
4. Treat successful theorem/reference resolution as `Resolve`, not automatically as evidence for `Direct` / `REQUIRE`.
5. Do **not** make a production reference-to-`REQUIRE` cutover from the small synthetic corpus alone.
6. Carry the frozen structural compiler and audit into larger natural/private corpus testing, with particular attention to direct-result support.
7. Do not tune the frozen corpus by adding operator synonyms. A new natural case should first be classified as a missing generic linguistic fact, missing graph-field grounding, correct unresolved behavior, false authority, provenance failure, or calculus counterexample.
8. Keep visibility/retraction and status as explicit open gaps rather than patching them with phrases.

The evidence therefore supports **continue with a bounded structural compiler**, not a broad new prose parser and not an immediate production migration.
