# Thorn test matrix

Thorn's public evaluation corpus is not intended to be a bag of entertaining mistakes or a leaderboard
for whichever model happens to be configured today. It is a test-driven specification of what a useful
mathematical linter should notice, what it should leave alone, and how precisely it should describe the
difference.

The existing L1--L10 ladder remains useful as a rough measure of how much context or reasoning a case
requires. It is not, however, a coverage model. Mathematical faults are multidimensional. Two cases at
the same ladder level can exercise completely different capabilities, while the same logical error can
appear as a one-line mistake or as a paper-wide dependency failure.

For coverage, Thorn therefore uses an orthogonal **test matrix**.

## Diagnostic families

The matrix starts with four families.

| Family | Question |
| --- | --- |
| `correctness` | Is the stated mathematics supported by the supplied argument and assumptions? |
| `specification` | Is the mathematical claim unambiguous and sufficiently specified to have a stable meaning? |
| `readability` | Is there an objective notation or presentation problem that materially impedes mathematical interpretation? |
| `scholarship` | Do citations, attribution, and novelty claims match external evidence? |

`scholarship` is deliberately future-facing. It requires retrieval and external evidence and should not
be conflated with an offline correctness pass.

`readability` is also deliberately narrow. Thorn should not become a generic prose critic. A readability
finding must identify a concrete mathematical ambiguity or cognitive hazard: for example, the same
symbol having two simultaneous meanings, a convention that changes mid-proof, or an unresolved
reference with more than one plausible antecedent.

## Style is not model taste

Thorn should not invent a house style.

A nonstandard symbol, dense proof, unusual naming convention, or terse exposition is not a defect merely
because a model would have written it differently. If an author defines unusual notation clearly and
uses it consistently, the corresponding test should pass.

Style lint may eventually be supported through explicitly selected, externally sourced profiles such as
a publisher or society style guide. Such a rule should record its authority and provenance. Without such
an authority, Thorn should stay silent.

This is analogous to a programming linter enforcing an adopted language or project convention rather
than treating the model's prose preferences as a specification.

## Orthogonal dimensions

Each matrix-aware fixture can record the following dimensions. They are ground truth for coverage and
future scoring; they are not hints passed to the model.

| Dimension | Representative values |
| --- | --- |
| family | `correctness`, `specification`, `readability`, `scholarship` |
| statement truth | `true`, `false`, `vacuous`, `unknown`, `not_applicable` |
| proof status | `valid`, `gap`, `invalid`, `circular`, `not_applicable` |
| locality | `line`, `proof`, `section`, `paper`, `external` |
| fault class | free stable identifier such as `quantifier_swap` or `invalid_wlog` |
| detection method | counterexample, dependency tracing, type/domain check, scaling, theorem-hypothesis check, etc. |
| reader consequence | `fatal`, `risky`, `clarity` |
| deception level | `obvious`, `plausible`, `sneaky` |
| downstream impact | `isolated`, `one_result`, `multiple_results` |
| repairability | `trivial`, `local`, `statement`, `structural`, `none` |

The most important dimensions are independent. In particular, Thorn must learn that theorem truth and
proof validity are not the same thing.

We want all of these cells represented:

- false theorem, invalid proof;
- false theorem, superficially plausible proof;
- true theorem, invalid proof;
- true theorem, proof with a genuine gap;
- true theorem, valid proof that looks suspicious;
- vacuous theorem that is logically true but mathematically empty;
- clean but unconventional mathematics that should not be normalized away.

False positives on the last two clean categories are especially damaging. A linter that reflexively
objects to unusual mathematics is not useful to mathematicians.

## Fault classes

The following list is a coverage map, not a claim that every item needs its own diagnostic code.

### Logic and quantifiers

- converse or inverse implication errors;
- necessary/sufficient confusion;
- incorrect negation;
- quantifier-order swaps;
- witness reuse (`forall x exists y` silently becoming `exists y forall x`);
- non-exhaustive case splits;
- invalid "without loss of generality";
- contradiction arguments that assume more than the negation of the claim.

### Induction and recursive arguments

- missing or wrong base cases;
- an induction step with the wrong stride;
- using the induction hypothesis at the case being proved;
- strong induction with a circular hypothesis;
- recursive definitions without a well-founded decrease;
- missing limit stages in transfinite induction.

### Existence, uniqueness, and well-definedness

- treating an infimum as an attained minimum;
- defining an inverse before the required bijectivity is known;
- quotient constructions that depend on the representative;
- existence proved but uniqueness claimed;
- uniqueness only up to equivalence but literal uniqueness stated;
- locally defined pieces that do not agree on overlaps.

### Domains, types, and structures

- applying a map outside its domain;
- composing incompatible source and target spaces;
- assuming a subgroup is normal, a subset is measurable, or an operator is bounded without support;
- using finite-dimensional facts in infinite-dimensional settings;
- confusing an element with an equivalence class, set, or subspace.

### Algebra, order, and scaling

- sign errors and illegal cancellation;
- reversing an inequality with an unknown-sign multiplier;
- unjustified roots or logarithms;
- wrong monotonicity or convexity direction;
- equality-case mistakes;
- constants with impossible scaling or units.

### Boundary and degenerate cases

- zero, empty, singleton, scalar, or one-dimensional cases;
- singular matrices or repeated eigenvalues;
- equality cases;
- disconnected or noncompact domains;
- characteristic-dependent failures.

Cheap adversarial examples such as zero, identity, constant functions, and one-point spaces should be
treated as first-class detection strategies.

### Limits and interchange

- interchanging limits, integrals, derivatives, or infinite sums without hypotheses;
- pointwise versus uniform convergence confusion;
- weak versus strong convergence confusion;
- a convergent subsequence silently promoted to convergence of the whole sequence;
- invalid diagonal arguments;
- compactness invoked outside its domain.

### Measure and probability

- "almost everywhere" promoted to "everywhere";
- parameter-dependent null sets treated as one common null set;
- uncountable unions of null sets treated as null;
- pairwise independence used as mutual independence;
- zero covariance used as independence;
- Fubini/Tonelli used without the relevant assumptions.

### Algebraic, topological, and geometric structure

- commutativity assumed in a noncommutative setting;
- quotient by a non-normal subgroup or non-ideal;
- diagonalizability or simultaneous diagonalization silently assumed;
- continuous bijection promoted to homeomorphism without the missing hypotheses;
- local inverse/local minimum/local trivialization promoted to a global one;
- connected and path-connected confused.

### Counting, optimization, and computation

- ordered/unordered counting mistakes or ignored automorphisms;
- local optimum claimed global without convexity;
- stationary point claimed a minimum;
- optimizer assumed to exist from boundedness alone;
- finite numerical verification extrapolated to a universal theorem;
- floating-point evidence treated as exact proof;
- code verifying a subtly different proposition from the manuscript.

### Dependencies and foundations

- theorem depends on a false lemma;
- theorem depends transitively on a bad lemma;
- circular dependency, including multi-hop cycles;
- an unproved conjecture silently used as established;
- an unstated foundational axiom inconsistent with the paper's declared setting;
- a bad lemma that is present but irrelevant to an independently proved theorem.

### Semantic emptiness

- a theorem merely restates a definition;
- hypotheses define an empty class;
- a conclusion follows only because an object was defined to have that property.

These are warnings about mathematical content, not claims that the theorem is false.

### Mathematical specification and readability

- the same symbol has two simultaneous meanings;
- notation changes meaning across a proof without an explicit scope change;
- asymptotic notation does not state the varying parameter or required uniformity;
- "the norm", "the topology", or "the measure" is ambiguous when several are active;
- a symbol is used before it is defined in a way that changes mathematical interpretation;
- an internal reference has several plausible mathematical antecedents.

Again, nonstandard notation by itself is a clean case.

## Test construction

Every new capability should preferably be introduced as a small pair or cluster:

1. the smallest synthetic manuscript exhibiting the fault;
2. a nearby clean control that uses similar surface language;
3. when useful, a second case that changes theorem truth while preserving the proof fault.

Examples include invalid versus valid uses of "without loss of generality", a quotient map that is and is
not representative-independent, or arbitrary versus finite choice in ZF.

The development loop remains:

**Red: add the case -> Green: Thorn catches exactly the intended issue -> Refactor: nearby controls stay clean.**

Expectations describe semantic ground truth rather than exact model prose. A live model does not pass
because it happened to complain; it passes because a surviving finding lands in an accepted category at
the required severity.

## Matrix metadata

A matrix-aware fixture may include fields like:

```json
{
  "family": "correctness",
  "statement_truth": "true",
  "proof_status": "invalid",
  "locality": "proof",
  "fault_class": "invalid_wlog",
  "detection_methods": ["symmetry check", "counterexample"],
  "reader_consequence": "fatal",
  "deception_level": "plausible",
  "downstream_impact": "one_result"
}
```

Not every legacy fixture needs to be backfilled immediately. New cases should populate these fields when
the classification is clear.

## What coverage means

The goal is not to maximize the raw number of fixtures. Coverage improves when we fill genuinely
different cells of the matrix and add controls that constrain false positives.

A mature Thorn suite should be able to answer questions such as:

- Do we test true theorems with invalid proofs, not only false theorems?
- Do we have paper-wide and external failures, not only local algebra?
- Are quantifier, induction, well-definedness, limit, and local/global errors represented?
- Do objective readability checks have clean unconventional controls?
- Can a dependency be flawed without tainting unrelated downstream results?
- Does every high-severity class have at least one adversarial clean neighbour?

That is a much stronger specification than "we have N bad papers".
