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
| `specification` | Is the mathematical claim unambiguous and does the stated theorem match the scope actually established? |
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
| reader consequence | `fatal`, `risky`, `clarity`, `opportunity`, `not_applicable` |
| deception level | `obvious`, `plausible`, `sneaky` |
| downstream impact | `isolated`, `one_result`, `multiple_results` |
| repairability | `trivial`, `local`, `statement`, `structural`, `none` |
| theorem/proof scope | `exact`, `proof_narrower`, `proof_stronger`, `incomparable`, `unknown` |
| hypothesis relation | `exact`, `proof_requires_more`, `theorem_has_surplus`, `unknown` |
| conclusion relation | `exact`, `proof_establishes_less`, `proof_establishes_more`, `incomparable`, `unknown` |

The most important dimensions are independent. In particular, Thorn must learn that theorem truth and
proof validity are not the same thing, and that theorem/proof scope is a separate question again.

We want all of these cells represented:

- false theorem, invalid proof;
- false theorem, superficially plausible proof;
- true theorem, invalid proof;
- true theorem, proof with a genuine gap;
- true theorem, valid proof that looks suspicious;
- true theorem whose supplied proof establishes a narrower result;
- true theorem whose supplied proof demonstrably establishes a stronger result;
- vacuous theorem that is logically true but mathematically empty;
- clean but unconventional mathematics that should not be normalized away.

False positives on clean and unusual cases are especially damaging. A linter that reflexively objects to
unusual mathematics is not useful to mathematicians.

## Theorem/proof scope

The theorem statement and the actual logical reach of its proof should be compared explicitly.
Suppose a theorem announces `H -> C`, while the supplied proof in fact establishes `H' -> C'`.
There are several materially different cases.

| Relation | Typical example | Thorn treatment |
| --- | --- | --- |
| exact | proof uses the stated hypotheses and reaches the stated conclusion | clean |
| proof narrower: stronger hypotheses | theorem says all real x; proof assumes x>0 | correctness error |
| proof narrower: weaker conclusion | theorem says an extremum is attained; proof shows only boundedness | correctness error |
| proof stronger: weaker hypotheses | theorem assumes x>=0; proof explicitly works for every real x | informational opportunity |
| proof stronger: stronger conclusion | theorem claims positivity; proof proves a quantitative lower bound | informational opportunity |
| incomparable | proof establishes a different property that does not imply the theorem | correctness error |

The direction matters. If the proof is narrower than the theorem, the stated result is unsupported even
when the theorem happens to be true. If the proof is stronger, there is no correctness defect. Thorn may
surface the surplus only as an informational authoring opportunity.

### Surplus hypotheses

A theorem may retain a hypothesis that the proof no longer needs after revisions. This can be useful to
flag, but only when the redundancy is demonstrated rather than guessed. Hypothesis-use tracing must
include definitions and dependencies. A hypothesis that is not mentioned syntactically in the final
proof paragraph may still be required by a cited lemma.

The suite therefore contains both:

- a theorem whose proof explicitly works without one of its stated hypotheses; and
- a clean theorem where a superficially unused hypothesis is required by a cited result.

### Stronger conclusions

Likewise, if the supplied proof explicitly derives a sharper inequality, stronger regularity property,
or otherwise stronger conclusion than the theorem states, Thorn may report that as information. The
proof must actually contain the stronger result; a plausible extension is not enough.

### No speculative generalization

"The proof proves more" is very different from "this argument looks as though it could be generalized."
Default Thorn should report only **demonstrated surplus scope**.

It should not propose a new parameter, weaker regularity class, larger ambient category, Banach-space
version, noncommutative analogue, or other research generalization merely because a proof pattern looks
reusable. Those are research suggestions, not lint diagnostics. A clean regression case deliberately
uses an argument that invites abstraction while proving exactly the theorem stated.

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

### Theorem/proof relationship

- proof requires stronger hypotheses than the theorem states;
- proof proves only a weaker conclusion;
- proof proves a related but incomparable statement;
- theorem contains a demonstrably surplus hypothesis;
- proof explicitly establishes a stronger conclusion;
- theorem statement changed during revision but proof still targets the old scope.

The first three are correctness failures. The next two are informational opportunities. The last can fall
in either class depending on the direction of the mismatch.

### Dependencies and foundations

- theorem depends on a false lemma;
- theorem depends transitively on a bad lemma;
- circular dependency, including multi-hop cycles;
- an unproved conjecture silently used as established;
- an unstated foundational axiom inconsistent with the paper's declared setting;
- a bad lemma that is present but irrelevant to an independently proved theorem.

### Material assumption gaps

`unstated` is not synonymous with `missing`. Material-assumption review uses a local stopping rule:
**would plausible alternatives to the unstated premise materially change proof validity, theorem meaning,
or claimed scope?** If not, Thorn should not surface the premise merely because a formal system would
require it explicitly. If yes, authoritative source context must adequately determine the intended
premise; otherwise the unresolved choice is a material assumption gap.

The test matrix distinguishes four cases that should not be collapsed:

| Assumption situation | Meaning | Thorn treatment |
| --- | --- | --- |
| explicit hidden dependency | a proof depends on an unstated external result, axiom, or premise whose use can be identified | review the dependency according to its mathematical status |
| harmless ambient/cultural background | expert-readable context settles the intended convention, or plausible alternatives do not affect this proof judgement | stay quiet; do not descend into foundational formalisation |
| materially ambiguous or missing ambient prerequisite | a load-bearing proof edge or claimed scope depends on a premise for which plausible alternatives change validity, meaning, or scope, and context does not settle the choice | surface the mathematical assumption gap without claiming the theorem is thereby proved false |
| formalisation-only assumption | Lean or another formal system needs an explicit type, structure, typeclass, topology, order, or similar witness, but human mathematical context already settles the relevant judgement | keep it a formalisation obligation, not a paper finding |

Materiality is local to the proof edge or claimed scope. Thorn must neither maintain a dictionary of
"safe" cultural assumptions nor silently select whichever stronger ambient structure makes an argument
or Lean export succeed. The public paired regressions live in
`eval/cases/ladder/09_material_assumption_gaps` and exercise geometry, algebra, foundational-looking
arithmetic, and dimension-sensitive functional analysis through the same context/scope/provenance rule.

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

For theorem/proof scope, useful clusters contain both directions: a narrower proof that is an error, a
stronger proof that is only informational, and a clean neighbour preventing speculative generalization
or naive unused-hypothesis detection.

The development loop remains:

**Red: add the case -> Green: Thorn catches exactly the intended issue -> Refactor: nearby controls stay clean.**

Expectations describe semantic ground truth rather than exact model prose. A live model does not pass
because it happened to complain; it passes because a surviving finding lands in an accepted category at
the required severity.

### Adaptive adversarial-author red-teaming

Adaptive white-box red-teaming is a separate assurance mode from ordinary fixture construction. It asks
whether an author who can inspect Thorn's source, prompts, canonical IR, source handles, dependency graph,
reports, and cache decisions can preserve one independently adjudicated mathematical defect while changing
only its presentation until the assurance boundary loses it.

These modes should not be collapsed:

| Mode | What is frozen | What changes | Primary question |
| --- | --- | --- | --- |
| paired clean/defect fixture | one small defect and nearby control | normally nothing after admission | does Thorn distinguish an already specified semantic contrast? |
| metamorphic test | mathematical semantics | a predetermined semantics-preserving transformation family | is behavior invariant under harmless rewrites? |
| natural-paper acceptance | real or realistically authored paper | normal corpus evolution, not outcome-adaptive attacks | does extraction/representation work on ordinary document shapes without excessive false positives? |
| frozen semantic-review evaluation | requests, schemas/protocols, expected categories, and usually provider records/replays | model/arm only as explicitly designed by the experiment | how does a fixed semantic-review treatment perform comparably over time? |
| adaptive adversarial-author red-team | one wrong mathematical invariant, independent adjudication, matched clean control, and attack journal | presentation changes iteratively after observing Thorn | where is the earliest assurance layer that a knowledgeable author can make lose the same defect? |

An adaptive attack is valid only while the known mathematical counterexample or missing premise still
applies. Adding the premise, weakening the theorem, removing the proof, or otherwise repairing the
mathematics invalidates the attack. Malformed LaTeX and parser denial-of-service cases belong to other
test classes rather than counting as mathematical evasions.

Every adaptive attempt should be journalled before the next mutation, including unsuccessful attacks.
The journal should record source hashes, parentage, the invariant defect and independent adjudication,
the attack hypothesis, deterministic/Proof-IR/dependency/source-handle observations, cache decision where
relevant, Lean/report behavior, the earliest failed boundary, and the outcome. A semantic cache reuse
decision after a relevant source/dependency change is itself a red-team outcome even if forced fresh
review would have detected the mathematics.

Keyless adaptive testing must not treat a fake reviewer response as mathematical evidence. Deterministic
representation, reachability, cache, replay, Lean, and report evidence can establish failures at those
layers; when faithful context reaches a live-model boundary and no exact replay exists, the semantic
outcome remains unresolved until a separately authorized frozen live experiment.

Public CI should contain only reproducible public methodology, representative/sanitized regressions, and
keyless checks. Unreleased adaptive variants may live in a private held-out corpus, but public CI must not
depend on private material. Issue #101's durable example lives under `eval/adversarial/issue_101`.

## Matrix metadata

A matrix-aware fixture may include fields like:

```json
{
  "family": "correctness",
  "statement_truth": "true",
  "proof_status": "gap",
  "locality": "proof",
  "fault_class": "proof_weaker_than_statement",
  "detection_methods": ["proof-goal comparison"],
  "reader_consequence": "fatal",
  "deception_level": "plausible",
  "downstream_impact": "one_result",
  "scope_relation": "proof_narrower",
  "hypothesis_relation": "exact",
  "conclusion_relation": "proof_establishes_less"
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
- Do we distinguish proof-narrower correctness failures from proof-stronger opportunities?
- Can we trace hypothesis use through dependencies before declaring a hypothesis surplus?
- Do we refuse speculative generalizations that the supplied proof does not actually establish?
- Do objective readability checks have clean unconventional controls?
- Can a dependency be flawed without tainting unrelated downstream results?
- Does every high-severity class have at least one adversarial clean neighbour?
- Do adaptive white-box attacks preserve one known-wrong mathematical invariant while probing representation, reachability, cache, semantic review, and report boundaries separately?

That is a much stronger specification than "we have N bad papers".
