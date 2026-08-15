# Thorn evaluation corpus

This directory contains small, self-contained regression cases for Thorn's semantic audit.

The public corpus uses **synthetic mathematical examples** that isolate representative logical failure
modes. It intentionally does not identify papers or authors from which a failure mode may have been
motivated. Each `.tex` file has a matching `.json` expectation.

The corpus is organised as a **test-driven development ladder** plus an orthogonal **coverage matrix**.
The ladder roughly measures how much context/reasoning a case requires; the matrix records what kind of
failure it is and what a correct diagnostic should mean. See
[`docs/test-matrix.md`](../docs/test-matrix.md) for the full design.

A case is added because it names a capability Thorn should possess, not because a particular model
happened to complain about a paper. Cases should stay small enough that the planted defect and the
correct diagnosis are transparent to a human reader.

## Ladder

The numbered ladder under `cases/ladder/` increases the amount of mathematical context required:

- **L1 — surface consistency:** a variable typo changes the mathematical argument.
- **L2 — local algebra and notation:** local mathematical errors plus objective notation ambiguity.
- **L3 — hypotheses, boundaries, and local logic:** missing assumptions, converse errors, asymptotic
  specification, forgotten endpoints, empty or degenerate cases.
- **L4 — proof sufficiency and proof mechanics:** genuine gaps in true theorems, invalid WLOG,
  induction coverage, existence/attainment, quotient well-definedness, and subsequence errors.
- **L5 — statement correctness and broader theorem misuse:** false/overstrong results, quantifier
  swaps, parameter-dependent null sets, finite/infinite-dimensional confusion, and local-to-global
  promotion.
- **L6 — cross-result dependency:** a theorem depends on a flawed lemma elsewhere in the paper,
  including the important case where the downstream theorem happens to be true but its stated proof is
  unsupported.
- **L7 — dependency structure:** circular proof dependencies across results, including indirect
  multi-hop cycles.
- **L8 — adversarial/comedy papers:** polished grand claims with deliberately elementary fatal errors,
  such as a one-line proof of Fermat's Last Theorem.
- **L9 — hidden mathematical assumptions:** a proof silently imports an unproved conjecture or an
  unstated foundational axiom. RH and ABC are tested as unproved dependencies; Choice is tested
  separately as an axiom, including a clean finite-choice neighbour.
- **L10 — semantic emptiness:** a theorem is true only because its conclusion is built into a definition
  or its defining class is empty.

Level `0` is reserved for the original smoke/regression cases that predate the ladder.

The ladder deliberately includes clean neighbours. A linter that finds every planted defect but invents
problems in nearby valid proofs is not passing.

## Matrix metadata

New fixtures should populate matrix fields when the classification is clear:

- `family`: correctness, specification, readability, or (eventually) scholarship;
- `statement_truth`: true, false, vacuous, unknown, or not applicable;
- `proof_status`: valid, gap, invalid, circular, or not applicable;
- `locality`: line, proof, section, paper, or external;
- `fault_class`: a stable descriptive identifier such as `invalid_wlog`;
- `detection_methods`: intended ways the defect can be exposed;
- `reader_consequence`: fatal, risky, or clarity;
- `deception_level`: obvious, plausible, or sneaky;
- `downstream_impact`: isolated, one result, or multiple results;
- `repairability`: trivial, local, statement, structural, or none.

These are ground truth for coverage analysis and future scoring. They are not included in model prompts.

The matrix is intentionally more important than the raw case count. In particular, it distinguishes
false theorems from true theorems with bad proofs and includes adversarial clean controls such as valid
WLOG arguments, well-defined quotient maps, finite choice in ZF, and explicitly defined nonstandard
notation.

## Objective readability, not invented style

The public suite may test notation/specification problems when they create a concrete mathematical
ambiguity. It should not test whether an LLM prefers one notation, paragraph shape, or prose style over
another.

Unusual notation that is explicitly defined and consistently used is a clean case.

Style rules should only enter Thorn through an explicitly selected external style profile with a named
authority (for example, a publisher or society guide), not through model taste.

## Hidden-assumption policy

An unproved conjecture and an unstated axiom are not the same defect. A proof that uses the Riemann
hypothesis or the ABC conjecture without marking the argument conditional has an
`unproved_dependency`. A proof that explicitly claims to work in ZF and then chooses an element from
every member of an arbitrary family may have an `unstated_axiom`. Thorn should not flag ordinary
classical use of Choice merely because a manuscript is written in the conventional ZFC setting.

Likewise, a theorem can be logically true and still deserve a semantic warning. `vacuous_truth` is
reserved for cases where the advertised content collapses transparently from the manuscript's own
definitions: the conclusion is the definition in disguise, or the defined class is inconsistent/empty.
It is not a general complaint that a theorem is easy.

## Existing smoke cases

- `threshold_squared` — a sign test on `a^2 - tau` is incorrectly treated as a threshold on `a - tau`.
- `quadratic_growth` — two-sided quadratic growth is incorrectly promoted to strong convexity and
  gradient smoothness.
- `convergence_mismatch` — continuity under decreasing convergence is invoked for a sequence known only
  to converge in `L^1`.

## Running the suite

Validate fixture parsing and dependency metadata without API calls:

```bash
thorn-eval eval/cases --validate-only
```

Run only the early ladder while developing a capability:

```bash
thorn-eval eval/cases --model <model> --max-level 3
```

Run the complete live semantic regression suite:

```bash
export OPENAI_API_KEY=...
thorn-eval eval/cases --model <model>
```

The command exits nonzero if a known defect is missed or if a clean control produces a surviving
diagnostic above the configured confidence threshold.

## Test-driven workflow

The intended development loop is:

1. Add the smallest synthetic paper that exposes the missing capability and record its ground truth.
2. Add a nearby clean control whenever false-positive behavior is plausible.
3. Confirm fixture validation is deterministic and offline.
4. Run the relevant ladder level and observe the semantic failure.
5. Improve extraction, context, prompts, scoring, or deterministic analysis until the case passes.
6. Re-run all lower levels and clean controls to catch regressions and false positives.

Do not weaken an expectation merely to accommodate a model response. If a case was badly specified,
make the mathematical ground truth clearer instead.

In short:

**Red: add bad paper -> Green: Thorn catches it -> Refactor: nearby clean papers remain clean.**

## Budget safety

Default CI is deliberately offline. It runs unit tests, deterministic mocked provider/integration tests,
fixture validation, linting, and type checking with `OPENAI_API_KEY` explicitly blank. Those checks must
never make billable model calls.

The GitHub `Live evaluation` workflow is intentionally separate and has only a manual
`workflow_dispatch` trigger. It is the only workflow that injects `OPENAI_API_KEY`. Live semantic
regression should remain an explicit human action rather than a pull-request or push check.

This is a regression suite, not an accuracy benchmark. Cases are deliberately small and known in
advance. A later benchmark should contain held-out and blinded cases.

Exact provenance for research-derived audit cases should be kept outside this public repository.
