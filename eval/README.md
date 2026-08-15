# Thorn evaluation corpus

This directory contains small, self-contained regression cases for Thorn's Math IR, deterministic structural analysis, and semantic review.

The public corpus uses **synthetic mathematical examples** that isolate representative failure modes. It intentionally does not identify papers or authors from which a failure mode may have been motivated. Each `.tex` file has a matching `.json` expectation.

The corpus is organised as a **test-driven development ladder** plus an orthogonal **coverage matrix**. A case is added because it names a capability Thorn should possess, not because a particular model happened to complain about a paper.

## Evaluation layers

The same corpus specifies deliberately different capabilities:

```text
Math IR        deterministic extraction of argument structure
thorn analyze  deterministic structural diagnostics
thorn review   model-backed semantic mathematical review
```

Case metadata may contain:

```json
"modes": ["analyze", "review"]
```

Semantic cases default to both modes. A structural/IR fixture may use:

```json
"modes": ["analyze"]
```

so deterministic coverage can grow **without increasing the size or token cost of live model runs**.

Deterministic expectations live in `eval/analysis-expectations.json`. That manifest covers every analysis-enabled case exactly. An empty rule list is a real expectation: deterministic analysis must stay silent on that case at its current capability level.

Selected proof-support IR expectations live separately in `eval/support-expectations.json`. These test extracted claims, explicit support kinds, load-bearing structure, trailing binders, and cross-result dependency context without turning every suspicious IR fact into a diagnostic.

This distinction is intentional. A false theorem, invalid compactness step, hidden conjecture dependency, or quantifier error can be required semantic findings while simultaneously being required deterministic silence cases. The frontend represents structure; it does not pretend to prove the mathematics.

## Ladder

The numbered ladder under `cases/ladder/` increases the amount of mathematical context required:

- **L1 — surface consistency:** variable typos and mechanically visible source/label structure.
- **L2 — local algebra and notation:** local mathematical errors plus objective notation ambiguity.
- **L3 — hypotheses, boundaries, and local logic:** missing assumptions, converse errors, asymptotic specification, forgotten endpoints, empty or degenerate cases.
- **L4 — proof sufficiency, scope, and proof mechanics:** genuine gaps in true theorems, theorem/proof scope mismatch, invalid WLOG, induction coverage, existence/attainment, quotient well-definedness, and subsequence errors.
- **L5 — statement correctness and broader theorem misuse:** false/overstrong results, quantifier swaps, parameter-dependent null sets, finite/infinite-dimensional confusion, and local-to-global promotion.
- **L6 — cross-result and support structure:** downstream dependence on earlier arguments, proof-support structure, load-bearing prose, and propagation.
- **L7 — dependency structure:** circular proof dependencies across results, including indirect multi-hop cycles.
- **L8 — adversarial/comedy papers:** polished grand claims with deliberately elementary fatal errors.
- **L9 — hidden mathematical assumptions:** silently imported conjectures or foundational axioms.
- **L10 — semantic emptiness:** results that collapse to definitions or empty classes.

Level `0` is reserved for original smoke/regression cases that predate the ladder. Clean neighbours are essential: a reviewer that finds planted defects but invents problems in nearby valid proofs is not passing.

## Deterministic analysis policy

`thorn analyze` is judged against both planted structural defects and broad silence controls. The deterministic rule set should only grow when a mechanically justified premise has survived nearby clean controls.

This policy already rejected plausible-looking source-order/scope warnings: ordinary mathematical prose permits constructions such as a displayed formula followed by `for every $x\in X$`. Those facts remain useful in the IR without being promoted to warnings.

The rule is:

> **Do not weaken a deterministic expectation merely because a heuristic fires. Either the ground truth is wrong, or the heuristic is not ready to become a diagnostic.**

The first analyze-only tranche contains duplicate labels, ambiguous theorem references, missing internal references, explicit role conflicts, and nearby clean controls. Proof-support fixtures exercise richer IR while often remaining deterministic silence controls.

## Semantic review policy

The theorem statement and the actual logical reach of its proof should be compared explicitly. A proof that requires stronger hypotheses or establishes less than the theorem claims is a correctness failure. A proof that demonstrably works under weaker hypotheses or establishes a stronger conclusion is not a correctness failure; it may be reported only as an informational opportunity.

Scope surplus must be demonstrated by the supplied proof. Thorn should not propose speculative research generalizations merely because an argument appears reusable.

Objective readability findings must identify a concrete mathematical ambiguity. Thorn should not invent a house style; unusual notation that is clearly defined and consistently used is a clean case.

Semantic `thorn-eval` runs use the same normal local linguistic frontend as `thorn analyze` and `thorn ir`. This requires the local `en_core_web_sm` model but does not require a remote NLP service. `--structural-only` remains an explicit degraded/debug path for constrained environments and parser-neutral unit tests; it should not be used for the live/manual C2 IR or targeted comparison.

## Running the suite

Validate all fixtures and extraction without API calls:

```bash
thorn-eval eval/cases --validate-only
```

Run the complete deterministic analysis matrix with exact rule expectations:

```bash
thorn-eval eval/cases --analyze
```

The proof-support expectation manifest is exercised by the normal pytest suite (`tests/test_support_matrix.py`) against both supported parser backends.

Run only early review-enabled ladder cases while developing semantic capability:

```bash
thorn-eval eval/cases --model <model> --max-level 3
```

Run a controlled raw-vs-IR semantic context experiment:

```bash
thorn-eval eval/cases --review-context raw --model <model>
thorn-eval eval/cases --review-context ir --model <model>
```

Inspect targeted semantic-review selection without an API key or semantic provider call:

```bash
OPENAI_API_KEY="" thorn-eval eval/cases --targeted-preflight --case-filter missing_nonzero_hypothesis
```

The preflight prints each stable `SemanticReviewItem` identifier and its exact trigger relation identifiers/statuses, then emits a JSON-friendly summary. `would_make_semantic_request_count` is the number of item-driven requests that a targeted semantic run would make; `provider_request_count` is always zero in preflight. A zero-item selection is represented explicitly rather than treated as an error.

Run the live semantic regression suite:

```bash
export OPENAI_API_KEY=...
thorn-eval eval/cases --model <model>
```

Analyze-only cases are automatically excluded from live semantic review, so adding them does not increase paid model usage.

## Test-driven workflow

1. Add the smallest synthetic paper that exposes the missing capability and record its ground truth.
2. Add a nearby clean control whenever false-positive behavior is plausible.
3. Decide explicitly whether the case belongs to deterministic analysis, semantic review, or both.
4. Confirm fixture validation is deterministic and offline.
5. Run the relevant IR, analysis, or semantic expectation and observe the failure.
6. Improve extraction, IR, deterministic analysis, review context, prompts, or scoring until the case passes.
7. Re-run the full relevant matrix to catch regressions and false positives.

In short:

**Red: add bad paper -> Green: Thorn catches it at the appropriate layer -> Refactor: nearby clean papers remain clean.**

## Budget safety

Default CI is deliberately offline. It runs unit tests, fixture validation, the deterministic analysis matrix, proof-support IR expectations, linting, and type checking with `OPENAI_API_KEY` explicitly blank. Those checks must never make billable model calls.

The separate local-NLP contract workflow installs `en_core_web_sm` and exercises the production linguistic path, including the selected keyless C2 targeted preflight. It also keeps `OPENAI_API_KEY` blank. The GitHub `Live evaluation` workflow remains separate and manually triggered; it is not part of the preflight.

This is a regression suite, not an accuracy benchmark. Cases are deliberately small and known in advance. A later benchmark should contain held-out and blinded cases.

Exact provenance for research-derived audit cases should be kept outside this public repository.
