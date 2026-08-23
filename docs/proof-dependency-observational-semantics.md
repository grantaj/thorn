# Proof-dependency observational semantics

Status: research contract. This document defines a proposed semantic boundary and an
experimental programme. It does **not** by itself change production authority or delete
existing extraction paths.

## Thesis

Thorn does not need a general semantics of mathematical prose. It needs exactly enough
semantic state to determine proof dependency.

The proposed principle is:

> **Canonical Thorn semantics contains exactly the distinctions that can change a
> proof-dependency observation, now or after some valid continuation of the source.**

This makes dependency relevance, rather than English phrasing or a hand-written taxonomy
of mathematical speech acts, the criterion for entering canonical semantic state.

A source relation that cannot change any dependency-relevant observation may still matter
rhetorically, pedagogically, stylistically, or as review evidence. It simply does not belong
in Thorn's canonical dependency semantics. Conversely, if a source distinction can change a
dependency observation but Thorn cannot represent it, the semantic state is incomplete.

There are therefore two deliberately separate correctness obligations:

1. **dependency semantics**: retain exactly the distinctions observable through proof
   dependency;
2. **assurance decoration**: preserve exact source provenance and evidence for each retained
   semantic object/relation without letting source coordinates create extra mathematical
   distinctions.

## 1. Formal setting

Let a **history** be a valid normalized source prefix after the source and workspace
boundaries have done their work. Let `S(h)` be the dependency-relevant semantic state after
history `h`.

Let `Q` be Thorn's finite family of dependency-relevant semantic query forms. For `q in Q`,
let

```text
O(q, S)
```

be the observable answer to query `q` in state `S`, including explicit unresolved,
ambiguous, partial, and source-error outcomes where those outcomes affect dependency
reasoning.

A first, insufficient equivalence would compare only current observations:

```text
S1 ~Q S2  iff  for every q in Q, O(q, S1) = O(q, S2).
```

That is too weak. A declaration may be unused at the point where it is introduced yet
change the dependency of a later theorem. Thorn therefore needs continuation-sensitive
observational equivalence.

Let `C` range over valid future normalized source continuations and let `delta*(S, C)` be
the state obtained by processing continuation `C` from `S`. Define

```text
S1 ==Q S2
    iff
for every valid continuation C and every q in Q,
    O(q, delta*(S1, C)) = O(q, delta*(S2, C)).
```

Equality includes dependency-relevant capability/failure outcomes. If one state yields a
unique resolved prerequisite and the other yields ambiguity, they are observably different.

This is a contextual/behavioural equivalence: two states are the same for Thorn exactly
when no future dependency-relevant context can distinguish them. The canonical semantic
state should be understood as the quotient induced by this equivalence, or as a practical
representation faithful to that quotient.

The target representation should be **fully abstract for proof-dependency observations**:

```text
source histories are contextually equivalent
    iff
their canonical dependency states are observationally equivalent.
```

The two directions give useful engineering obligations:

- **preservation / adequacy**: abstraction must not erase a distinction that some future
  dependency context can observe;
- **reflection / minimality**: abstraction should not retain a semantic distinction that no
  future dependency context can observe.

This does **not** imply that Thorn has finitely many states. Mathematical expressions,
source positions, and projects make the state space unbounded. The finite object we seek is
the **signature of dependency-relevant state changes and observations**.

## 2. Dependency relevance

For a proposed semantic fact or relation `r`, write `S + r` for a state that differs only by
retaining `r`. Then `r` is dependency-relevant exactly when there exist a state, a valid
continuation, and a dependency query that can distinguish its presence:

```text
RelevantQ(r)
    iff
there exist S, C, q such that
    O(q, delta*(S + r, C)) != O(q, delta*(S, C)).
```

This is the admission test for canonical semantics.

Examples:

- `Define $x \star y$ to mean $x+y$.` is relevant because a later occurrence of `\star`
  can resolve to a different canonical prerequisite.
- `Throughout, all groups are finite.` is relevant because a later result may depend on
  the ambient finiteness premise without repeating it.
- `By Lemma 4, ...` is relevant when it presents Lemma 4 as support for a claim.
- `This proof is elegant.` is not dependency-relevant unless Thorn deliberately defines a
  dependency query that depends on that judgement. It remains source prose/review evidence,
  not canonical dependency state.

This criterion handles borderline prose. `The argument is similar to the previous proof`
has no canonical effect if it is exposition; if the manuscript actually uses the previous
proof as support, the dependency effect is the prerequisite relation, not the lexical item
`similar`. Uncertainty about which reading is intended remains explicit uncertainty.

## 3. Semantic observables Q

`Q` is derived from the dependency questions Thorn must answer, not from current internal
classes or document vocabulary.

### Q1. Resolution

At a source occurrence and project-occurrence context:

```text
Resolve(occurrence) -> canonical target | unresolved | ambiguous
```

This includes symbol/notation identity and explicit result/reference identity where those
identities can change dependency closure.

### Q2. Visibility

At a source position/occurrence:

```text
Visible(position) -> dependency-bearing declarations/facts in force
```

This makes project order, lexical scope, forward visibility, shadowing, and repeated
inclusion observable without making `scope` a surface-language semantic act.

### Q3. Direct prerequisites

For a dependency-bearing claim/result/declaration:

```text
Direct(node) -> immediate canonical prerequisites
```

A prerequisite may be a prior result, an ambient/local premise, a definition/binding, or
another load-bearing claim. Those source categories need not be primitive graph operations.

### Q4. Transitive prerequisites

```text
Closure(node) -> transitive canonical prerequisite set
```

This is the fundamental proof-dependency closure observable.

### Q5. Dependency status / capability

```text
Status(query or graph element)
    -> resolved | given | established | ambiguous | partial | unsupported | source-error
```

The exact finite status lattice remains to be minimized. What matters is that a guessed
prerequisite is not equivalent to an explicit unresolved one, and an accepted premise is
not necessarily equivalent to an established result when that distinction changes what
later dependency reasoning may assume.

A query should remain in `Q` only if it cannot be derived from the others without losing a
supported dependency distinction.

## 4. Assurance observables are not semantic equality

Exact provenance is mandatory for Thorn but must **not** define `==Q`.

If raw source coordinates or surface wording were part of semantic equivalence, then two
mathematically equivalent paraphrases at different offsets would automatically be different
semantic states. That would make the quotient useless.

Instead let `P` be a provenance/evidence map decorating semantic graph elements:

```text
P : semantic node or relation -> exact source occurrence(s) + evidence
```

A correct implementation must satisfy both:

```text
A ==Q B
```

for dependency semantics, and

```text
P_A corresponds exactly to P_B
```

for source authority/provenance on the graph elements that are semantically matched.

Likewise bounded review/source-rescue reachability is a downstream acceptance projection of
semantic state plus provenance and review policy. It must remain stable during migration,
but it does not enlarge the mathematical quotient merely because two equivalent statements
occur at different source positions.

This semantic/evidence split is important: Thorn's assurance value depends on exact
provenance, but provenance is **proof-relevant decoration of the semantic quotient**, not an
extra mathematical relation.

## 5. Proposed minimal state-change calculus

### 5.1 Operational basis

For an append-only mathematical manuscript, the proposed primitive semantic mutations are
only:

```text
DECLARE(v, core)
REQUIRE(u, v)
```

`DECLARE` adds one future dependency target/fact to semantic state. `REQUIRE` adds a
prerequisite relation from an owner `u` to a dependency `v`.

At the graph level these are node addition and prerequisite-edge addition. Giving them
semantic names avoids mistaking a generic graph container for the proposed semantics.

This basis is deliberately smaller than current surface categories (`DEFINE`, `LET`, `FOR`,
`NAMED_PROPERTY`, `EXPLICIT_REASON`, and so on).

### 5.2 Do not hide an ontology in `core`

The two-operation proposal would be vacuous if `core` could contain arbitrary new semantic
relations. The allowed node core must itself be finite in shape and justified by `Q`.

The provisional node core is:

```text
DependencyNode
    identity / binding key     optional stable target for resolution
    mathematical payload       structured expression/proposition or opaque exact payload
    dependency status          finite status/capability value
    visibility domain          derived/normalized source-workspace domain
```

The semantic edge core is intentionally only:

```text
DependencyRequirement
    owner
    prerequisite
    dependency status          only if unresolved/ambiguous edges must be represented
```

Exact source occurrence, source text, parser evidence, confidence traces, and report handles
belong in the separate provenance/evidence decoration `P`, not in the semantic core.

A traditional role such as “definition”, “assumption”, “notation”, “lemma”, or “local proof
claim” is admitted to the core only if two otherwise identical states can be distinguished
by a future dependency query because of that role. Otherwise the role is derivable metadata
or a source/reporting classification.

### 5.3 Why DECLARE is necessary

A state containing a future-resolvable declaration and a state without it can be
distinguished by appending a continuation that refers to that declaration. Therefore a
representation that cannot add a future dependency target is incomplete.

### 5.4 Why REQUIRE is necessary

Two manuscripts can make exactly the same declarations available while one proof depends on
a prior fact and another does not. `Direct(node)` distinguishes them. Therefore availability
alone is insufficient; prerequisite relations are independently observable.

### 5.5 Why scope is not a primitive act

Thorn parses a whole project and has exact project order. Visibility can be a derived
predicate over a node's visibility domain and the normalized source/workspace occurrence.
Entering or leaving a scope need not destructively mutate the canonical graph. Shadowing
likewise adds a later declaration; it does not rewrite the earlier one.

If a valid manuscript construction is found whose future dependency behaviour cannot be
represented by visibility plus `DECLARE`/`REQUIRE`, that is a counterexample and must extend
the calculus before production cutover.

### 5.6 Surface forms compile to the basis

| Source form | Proposed dependency effect |
| --- | --- |
| `Set $q = 1$.` | `DECLARE(q-binding, payload=1, visibility=...)` |
| `Define $x \star y$ to mean $x+y$.` | `DECLARE(\star-binding, payload=x+y, visibility=...)` |
| `Let $G$ be a finite group.` | `DECLARE(G-context, payload=finite-group constraint, visibility=...)` |
| `Suppose $X$ is compact.` | `DECLARE(compact-X premise, status=given, visibility=...)` |
| `Throughout, all rings are commutative.` | `DECLARE(commutative-ring premise, status=given, visibility=...)` |
| theorem/lemma statement | `DECLARE(result claim, status=...)` |
| local load-bearing proof claim | `DECLARE(claim, status=...)` |
| use of `q`/`\star` in a result | `REQUIRE(result-or-claim, resolved binding)` |
| `By Lemma 4, ...` when used as support | `REQUIRE(current claim, Lemma 4)` |
| purely rhetorical prose | no canonical delta |

Every row also receives exact provenance through `P`. The table is explanatory only;
production inference must not implement it as an English phrase dictionary.

## 6. Completeness hypothesis

The research hypothesis is:

> For Thorn's dependency-observable semantics of an append-only mathematical manuscript,
> every canonical source effect is representable by adding a dependency-bearing node or a
> prerequisite relation, with visibility/status carried in a fixed finite node/edge shape
> and source authority carried separately by exact provenance decoration.

This is structural completeness of the update basis, **not** a claim that Thorn can recover
every such effect from unrestricted informal mathematics.

The recovery function may legitimately be partial:

```text
Elaborate(source evidence, current state)
    -> unique candidate delta
     | ambiguous candidate deltas
     | unresolved
     | unsupported capability
```

Completeness of the representation and completeness of natural-language understanding are
separate questions. Thorn should aim strongly for the former and remain explicit about the
limits of the latter.

## 7. Existing mathematics we can reuse

This proposal is not intended as a new foundational semantics invented from scratch. Several
established bodies of work supply the right mathematical language.

### Contextual equivalence and full abstraction

The closest standard formulation is contextual equivalence/full abstraction from
programming-language semantics. There, program fragments are observationally equivalent
when no permitted context can distinguish their behaviour; a denotational representation
is fully abstract when equality in the representation coincides with contextual
observational equivalence.

For Thorn, the context is a valid future manuscript continuation together with a supported
proof-dependency query. This gives the exact preservation/reflection criterion above.

### Dynamic semantics: meaning as context change

Dynamic semantics, especially the work of Groenendijk and Stokhof, treats the meaning of a
sentence as its **context change potential** rather than merely a static truth condition.
That is directly useful for Thorn: the relevant denotation of a source fragment is the
change it can make to dependency state.

The Thorn restriction is much stronger than general dynamic semantics: we intentionally
quotient away every context distinction that cannot affect proof dependency.

### Nerode-style future indistinguishability

The Myhill-Nerode construction identifies histories by whether any future continuation can
distinguish them. Thorn uses the same shape of equivalence, but not the finite-automaton
claim: our state space is generally infinite. The useful idea is that a minimal sufficient
state is determined by **future observational distinguishability**, which is exactly why an
unused definition still has to be retained.

### Behavioural equivalence and coalgebra

Transition-system and coalgebraic semantics provide a general notion of behavioural
equivalence/bisimulation: states are equivalent when their observations and future behaviour
cannot be distinguished. This is a natural mathematical home for `==Q` when Thorn's
transition system is not finite.

### Abstract interpretation

Cousot and Cousot's abstract interpretation gives a complementary perspective. Informal
mathematical discourse contains much more information than Thorn should represent. Canonical
dependency state is an abstraction that intentionally forgets information while preserving
its chosen dependency observables.

This suggests a useful correctness target: the abstraction should be dependency-sufficient
and as coarse as possible subject to that sufficiency. Explicit uncertainty must remain
visible rather than being hidden by an unsound approximation.

### Lean elaboration

Lean separates rich/extensible source syntax from a much smaller elaborated core and treats
command elaboration as effects on an environment. Definitions add constants to that
environment; theorems and definitions are technically close; Lean can also expose proof
axiom dependencies.

The lesson for Thorn is architectural rather than a proposal to formalize the manuscript in
Lean: rich source forms should elaborate into a small dependency-state core. Surface command
names should not determine that core ontology.

### OMDoc / MMT

OMDoc and MMT already show that mathematical knowledge representation benefits from
collapsing many document-level categories into declarations, constants, definitions,
assertions, theory inclusions, and relations. MMT constants in particular combine a name
with optional type, definition, notation, roles, and aliases.

Thorn's proposed quotient is deliberately narrower: a distinction survives only when it can
change dependency observations. OMDoc/MMT therefore provide useful representation precedent,
not the final Thorn ontology.

## 8. Consequence for natural-language analysis

The finite vocabulary must be the dependency calculus, **not an English dictionary**.
Production code should not regain architectures of the form:

```text
if lemma in {define, mean, denote, call, ...}: emit DEFINITION
```

Nor is dependency syntax alone enough: ordinary dependency parsing can expose argument
structure while leaving the semantic difference between `define A to mean B` and an
unrelated verb with similar syntax unresolved.

A promising off-the-shelf direction to evaluate is semantic entailment over candidate graph
deltas:

1. Tree-sitter and `LinguisticProjection` provide exact source structure and typed math/ref
   placeholders.
2. `LinguisticFrontend` provides generic grammatical analysis and candidate arguments.
3. The finite dependency calculus generates only graph effects Thorn knows how to represent.
4. A general local semantic inference/NLI component asks whether the source entails a
   candidate graph effect.
5. Thorn's authority gate decides whether that evidence is sufficient to enter canonical
   state; otherwise it remains ambiguous/unresolved.

This is an experimental direction, not a dependency decision. Small maintained NLI
cross-encoders make a local/keyless feasibility experiment possible. They must be compared
empirically with the existing spaCy-only substrate and current production behaviour before
any runtime dependency is adopted.

Semantic-role labelling or OpenIE are also plausible evidence sources, but by themselves
they normally return a lexical predicate and its arguments. If Thorn then maps predicates
such as `mean` or `define` to graph effects with a hand-maintained table, the architectural
problem has merely moved. They should therefore be evaluated only if they remove rather than
relocate lexical semantic policy.

## 9. A/B equivalence and evidence contract

Let `A` be the current production semantic path and `B` the proposed graph-delta elaborator.
Parity is **not** equality of internal IR objects.

The semantic differential condition is:

```text
A ==Q B
```

on cases where current behaviour is accepted as correct.

Separately, exact evidence/provenance and bounded review reachability must correspond under
the semantic matching. A semantic equivalence result cannot excuse lost or fabricated
source authority.

Every differential should be classified as one of:

1. **semantic regression**: `B` loses a dependency-relevant distinction;
2. **unsafe authority gain**: `B` creates a dependency not warranted by source evidence;
3. **observationally equivalent representation change**: internals differ but all semantic
   `Q` observations agree;
4. **provenance/evidence regression**: semantic graph matches but exact source authority does
   not;
5. **intentional fail-closed improvement**: `A` guessed and `B` exposes ambiguity/partiality;
6. **calculus counterexample**: a dependency-relevant distinction cannot be represented by
   the proposed basis.

The existing #162/#185 contracts already supply important observations: no backward leakage,
include-order shadowing, repeated-occurrence agreement/disagreement, workspace partiality,
and canonical dependency/review reachability, together with independent exact provenance
requirements. The #203 project-context ablation adds the useful `x \star y` continuation
case: source evidence can remain present while a later dependency loses its canonical target.

A dedicated A/B harness should compare semantic `Q` plus the independent provenance/evidence
map rather than compare private parser classes.

## 10. Ablation criterion

The existing hand-written semantic layer may be removed only when all of the following hold:

- the proposed calculus has survived explicit counterexample search;
- the new inference path uses general analysis rather than expanding an English cue
  dictionary;
- accepted current cases are `==Q` equivalent under A/B comparison;
- differences where current heuristics guessed are classified and intentionally fail closed;
- source/workspace partiality remains explicit;
- exact occurrence provenance and bounded review reachability remain intact as independent
  assurance obligations;
- no provider/model API calls are required for the normal local path;
- the superseded production mechanism is deleted rather than retained as a shadow fallback.

If the new path cannot meet those conditions, retain the old capability only as a documented
interim limitation rather than declaring the existing parser-like mechanism architecturally
correct.

## 11. Falsifiable next steps

1. Keep a backend-independent semantic `Q` snapshot and a separate exact-provenance snapshot
   over current canonical state.
2. Encode the minimal `DECLARE`/`REQUIRE` calculus as an experimental, non-authoritative
   graph-delta type with a closed attribute schema.
3. Build synthetic/metamorphic cases that try to falsify completeness of the two-operation
   basis, including scope endings, shadowing, aliases, ambient assumptions, local assumptions,
   cross-file order, repeated inclusion, explicit proof support, and rhetorical controls.
4. Reuse the #160 adversarial corpus to evaluate existing spaCy analysis plus at least one
   maintained off-the-shelf semantic inference path. Measure false authority first, not
   recall alone.
5. Implement `B` beside production `A` with no production cutover.
6. Differentially compare semantic `Q` and provenance/evidence separately, classify every
   difference, and extend the calculus only for genuine dependency-observable
   counterexamples.
7. Cut over only after the evidence gate passes, then ablate the superseded parser-like
   semantic machinery in the same tranche or immediately following deletion tranche.

## References

- Samson Abramsky and related work on observational equivalence/full abstraction; see the
  standard contextual-equivalence/full-abstraction literature in programming-language
  semantics.
- Jeroen Groenendijk and Martin Stokhof, *Dynamic Predicate Logic*, Linguistics and
  Philosophy 14 (1991), and related work on dynamic semantics/context change potential.
- Jeroen Groenendijk and Martin Stokhof, *Changing the Context: Dynamic Semantics and
  Discourse*.
- John Myhill (1957) and Anil Nerode (1958), the equivalence underlying the Myhill-Nerode
  theorem; used here only as the future-distinguishability pattern.
- J.J.M.M. Rutten, *Universal Coalgebra: A Theory of Systems*, Theoretical Computer Science
  249 (2000), 3-80.
- Patrick Cousot and Radhia Cousot, *Abstract Interpretation: A Unified Lattice Model for
  Static Analysis of Programs by Construction or Approximation of Fixpoints*, POPL 1977.
- Lean Language Reference, sections on elaboration, definitions, theorems, source-file
  environments, and axiom dependency tracking.
- Michael Kohlhase, *OMDoc -- An Open Markup Format for Mathematical Documents*, and the
  OMDoc mathematical-knowledge representation specifications.
- Florian Rabe and Michael Kohlhase, MMT language/documentation, especially symbol
  declarations and theory structure.
