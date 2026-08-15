# Thorn evaluation corpus

This directory contains small, self-contained regression cases for Thorn's deterministic checker, mathematical IR, and semantic audit.

The public corpus uses **synthetic mathematical examples** that isolate representative failure modes. It intentionally does not identify papers or authors from which a failure mode may have been motivated. Each `.tex` file has a matching `.json` expectation.

The corpus is organised as a **test-driven development ladder** plus an orthogonal **coverage matrix**. The ladder roughly measures how much context/reasoning a case requires; the matrix records what kind of failure it is and what a correct diagnostic should mean. See [`docs/test-matrix.md`](../docs/test-matrix.md) for the full design.

A case is added because it names a capability Thorn should possess, not because a particular model happened to complain about a paper. Cases should stay small enough that the planted defect and the correct diagnosis are transparent to a human reader.

## Evaluation layers

The same corpus now specifies several deliberately different capabilities:

```text
Math IR       deterministic extraction of argument structure
thorn check   deterministic user-facing structural diagnostics
thorn review  model-backed semantic analysis
```

Case metadata may contain:

```json
"modes": ["check", "review"]
```

Existing semantic cases default to both modes. A structural/IR fixture may use:

```json
"modes": ["check"]
```

so deterministic coverage can grow **without increasing the size or token cost of future live model runs**.

Deterministic lint expectations live in `eval/check-expectations.json`. That manifest must cover every check-enabled case exactly. An empty rule list is a real expectation: the checker must stay silent on that case at its current capability level.

Selected proof-support IR expectations live separately in `eval/support-expectations.json`. These test extracted claims, explicit support kinds, load-bearing structure, trailing binders, and cross-result dependency context without turning every suspicious IR fact into a lint warning.

This means the corpus tests both sides of the offline/semantic boundary. A subtle false theorem may be a required semantic finding while simultaneously being a required deterministic silence case.

## Ladder

The numbered ladder under `cases/ladder/` increases the amount of mathematical context required:

- **L1 — surface consistency:** variable typos and mechanically visible source/label structure.
- **L2 — local algebra and notation:** local mathematical errors plus objective notation ambiguity.
- **L3 — hypotheses, boundaries, and local logic:** missing assumptions, converse errors, asymptotic specification, forgotten endpoints, empty or degenerate cases.
- **L4 — proof sufficiency, scope, and proof mechanics:** genuine gaps in true theorems, theorem/proof scope mismatch, demonstrated scope surplus, invalid WLOG, induction coverage, existence/attainment, quotient well-definedness, and subsequence errors.
- **L5 — statement correctness and broader theorem misuse:** false/overstrong results, quantifier swaps, parameter-dependent null sets, finite/infinite-dimensional confusion, and local-to-global promotion.
- **L6 — cross-result and support structure:** a theorem depends on a flawed lemma elsewhere in the paper, plus explicit proof claims/support, load-bearing prose, and downstream propagation.
- **L7 — dependency structure:** circular proof dependencies across results, including indirect multi-hop cycles.
- **L8 — adversarial/comedy papers:** polished grand claims with deliberately elementary fatal errors, such as a one-line proof of Fermat's Last Theorem.
- **L9 — hidden mathematical assumptions:** a proof silently imports an unproved conjecture or an unstated foundational axiom.
- **L10 — semantic emptiness:** a theorem is true only because its conclusion is built into a definition or its defining class is empty.

Level `0` is reserved for original smoke/regression cases that predate the ladder.

The ladder deliberately includes clean neighbours. A linter that finds every planted defect but invents problems in nearby valid proofs is not passing.

## Matrix metadata

New semantic fixtures should populate matrix fields when the classification is clear:

- `family`: correctness, specification, readability, or scholarship;
- `statement_truth`: true, false, vacuous, unknown, or not applicable;
- `proof_status`: valid, gap, invalid, circular, or not applicable;
- `locality`: line, proof, section, paper, or external;
- `fault_class`: a stable descriptive identifier;
- `detection_methods`: intended ways the defect can be exposed;
- `reader_consequence`: fatal, risky, clarity, opportunity, or not applicable;
- `deception_level`: obvious, plausible, or sneaky;
- `downstream_impact`: isolated, one result, or multiple results;
- `repairability`: trivial, local, statement, structural, or none;
- `scope_relation`, `hypothesis_relation`, and `conclusion_relation` where relevant.

These are ground truth for coverage analysis and future scoring. They are not included in model prompts.

## Deterministic matrix policy

`thorn check` must be judged against both planted structural defects and broad silence controls.

The #18 full-matrix audit was valuable precisely because it rejected plausible-looking rules. Initial source-order/scope warnings produced false positives on ordinary mathematical constructions such as a displayed formula followed by `for every $x\in X$`. Those rules were demoted to IR-only facts instead of weakening the expectations.

The rule is:

> **Do not weaken a deterministic expectation merely because a heuristic fires. Either the ground truth is wrong, or the heuristic is not ready to lint.**

The first check-only structural tranche includes planted cases for duplicate labels, ambiguous theorem references, missing internal references, and explicit role conflicts, plus nearby clean controls for equation labels and compatible callable roles.

The #19 proof-support tranche adds check-only cases for load-bearing sneaky prose with a downstream theorem dependency, repeated trailing binders, explicit theorem/equation/definition/property support, and non-load-bearing exposition. These cases deliberately remain silence controls for `thorn check`: the support graph may expose a suspicious unsupported load-bearing claim without yet having enough evidence to warn the user.

The support-IR expectation suite is run against both the regex and pylatexenc frontends. This makes proof/support extraction another parser-neutral Math-IR layer rather than an accident of the default parser.

## Theorem/proof scope policy

A proof that works only under stronger hypotheses or establishes less than the theorem claims is a correctness failure. A proof that demonstrably works under weaker hypotheses or establishes a stronger conclusion is not a correctness failure; it may be reported only as an informational `scope_surplus` opportunity.

Scope surplus must be demonstrated by the supplied proof. Thorn should not propose speculative research generalizations merely because an argument appears reusable.

## Objective readability, not invented style

The public suite may test notation/specification problems when they create a concrete mathematical ambiguity. It should not test whether an LLM prefers one notation, paragraph shape, or prose style over another.

Unusual notation that is explicitly defined and consistently used is a clean case. Style rules should only enter Thorn through an explicitly selected external style profile with a named authority.

## Hidden-assumption policy

An unproved conjecture and an unstated axiom are not the same defect. A proof that uses the Riemann hypothesis or ABC conjecture without marking the argument conditional has an `unproved_dependency`. A proof that explicitly claims to work in ZF and then invokes arbitrary Choice may have an `unstated_axiom`.

Likewise, `vacuous_truth` is reserved for cases where advertised content collapses transparently from the manuscript's own definitions; it is not a complaint that a theorem is easy.

## Running the suite

Validate all fixtures and extraction, including check-only fixtures, without API calls:

```bash
thorn-eval eval/cases --validate-only
```

Run the complete deterministic lint matrix with exact rule expectations:

```bash
thorn-eval eval/cases --check
```

The proof-support expectation manifest is exercised by the normal pytest suite (`tests/test_support_matrix.py`) against both supported parser backends.

Run only early review-enabled ladder cases while developing semantic capability:

```bash
thorn-eval eval/cases --model <model> --max-level 3
```

Run the live semantic regression suite:

```bash
export OPENAI_API_KEY=...
thorn-eval eval/cases --model <model>
```

Check-only cases are automatically excluded from live semantic review, so adding them does not increase paid model usage.

## Test-driven workflow

The intended development loop is:

1. Add the smallest synthetic paper that exposes the missing capability and record its ground truth.
2. Add a nearby clean control whenever false-positive behavior is plausible.
3. Decide explicitly whether the case belongs to `check`, `review`, or both.
4. Confirm fixture validation is deterministic and offline.
5. Run the relevant deterministic, IR, or semantic expectation and observe the failure.
6. Improve extraction, IR, deterministic analysis, context, prompts, or scoring until the case passes.
7. Re-run the full relevant matrix to catch regressions and false positives.

In short:

**Red: add bad paper -> Green: Thorn catches it -> Refactor: nearby clean papers remain clean.**

## Budget safety

Default CI is deliberately offline. It runs unit tests, fixture validation, the complete deterministic matrix, proof-support IR expectations, linting, and type checking with `OPENAI_API_KEY` explicitly blank. Those checks must never make billable model calls.

The GitHub `Live evaluation` workflow is intentionally separate and manually triggered. It is the only workflow that injects `OPENAI_API_KEY`. Check-only fixtures are excluded from that semantic run.

This is a regression suite, not an accuracy benchmark. Cases are deliberately small and known in advance. A later benchmark should contain held-out and blinded cases.

Exact provenance for research-derived audit cases should be kept outside this public repository.
