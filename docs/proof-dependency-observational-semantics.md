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

A source relation that cannot change any dependency-relevant observation is still allowed
to matter rhetorically, pedagogically, stylistically, or as review evidence. It simply does
not belong in Thorn's canonical dependency semantics. Conversely, if a source distinction
can change a dependency observation but Thorn cannot represent it, the semantic state is
incomplete.

## 1. Formal setting

Let a **history** be a valid normalized source prefix after the source and workspace
boundaries have done their work. Let `S(h)` be the dependency-relevant semantic state after
history `h`.

Let `Q` be Thorn's finite family of dependency-relevant query forms, specified below. For
`q in Q`, let

```text
O(q, S)
```

be the observable answer to query `q` in state `S`, including explicit unresolved,
ambiguous, partial, and source-error outcomes where applicable.

A first, insufficient equivalence would compare only current observations:

```text
S1 ~Q S2  iff  for every q in Q, O(q, S1) = O(q, S2).
```

That is too weak. A declaration may be unused at the point where it is introduced yet
change the dependency of a later theorem. Thorn therefore needs continuation-sensitive
behavioural equivalence.

Let `C` range over valid future normalized source continuations and let `delta*(S, C)` be
the state obtained by processing continuation `C` from `S`. Define

```text
S1 ==Q S2
    iff
for every valid continuation C and every q in Q,
    O(q, delta*(S1, C)) = O(q, delta*(S2, C)).
```

Equality here includes capability/failure outcomes. If one state yields a unique resolved
dependency and the other yields ambiguity, they are observably different.

This is a Nerode-style / behavioural equivalence: two states are the same for Thorn exactly
when no future dependency-relevant experiment can distinguish them. The canonical semantic
state should be understood as the quotient induced by this equivalence, or as a practical
representation faithful to that quotient.

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
  the ambient finiteness assumption without repeating it.
- `By Lemma 4, ...` is relevant when it presents Lemma 4 as support for a claim.
- `This proof is elegant.` is not dependency-relevant unless some future Thorn query is
  deliberately defined to depend on that judgement. It remains source prose, not canonical
  dependency state.

This criterion also handles borderline prose. `The argument is similar to the previous
proof` has no canonical effect if it is exposition; if the manuscript is using the previous
proof as support, the dependency effect is the support relation, not the word `similar`.
Uncertainty about which reading is intended remains explicit uncertainty.

## 3. The observable query family Q

The first proposed `Q` is derived from current Thorn product and assurance behaviour rather
than from current internal classes. The precise encodings may change; these observable
questions must not silently disappear during an implementation rewrite.

### Q1. Resolution

At a source occurrence and project occurrence context:

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

The prerequisite may be a prior result, an ambient/local assumption, a definition or
binding, or another load-bearing claim. Those source categories need not be primitive graph
operations.

### Q4. Transitive prerequisites

```text
Closure(node) -> transitive canonical prerequisite set
```

This is the core review/dependency closure observable.

### Q5. Authority/support state

```text
Status(node or relation) -> accepted/given/established/ambiguous/unresolved/... 
```

The exact finite status vocabulary remains a separate design question, but uncertainty and
the difference between a manuscript premise and established support are observable because
they change review and fail-closed behaviour.

### Q6. Exact provenance and occurrence identity

```text
Provenance(node or relation) -> exact source occurrence(s)
```

Provenance is an attribute of the dependency graph rather than extra mathematical content,
but it is part of Thorn's assurance semantics. Two graphs with the same topology but
different source authority are not equivalent for Thorn.

### Q7. Capability / partiality

```text
Capability(query context) -> resolved | partial | ambiguous | source error | unsupported
```

A guessed dependency is not observationally equivalent to an explicit unresolved one.

### Q8. Bounded review reachability

```text
ReviewClosure(result) -> exact bounded material exposed for review/source rescue
```

This should ultimately be derivable from Q1-Q7 plus review policy. It is nevertheless kept
as an acceptance observable while the representation is being changed so that apparently
internal refactors cannot silently broaden or narrow what a reviewer sees.

A query should be removed from `Q` only after showing that it is derivable from the others
and that no supported Thorn behaviour distinguishes it.

## 4. Proposed minimal state-change calculus

### 4.1 Operational basis

For an append-only mathematical manuscript, the proposed primitive semantic mutations are
only:

```text
DECLARE(v, attributes)
REQUIRE(u, v, attributes)
```

`DECLARE` adds one dependency-bearing declaration/fact to semantic state. `REQUIRE` adds a
prerequisite relation from an owner `u` to a dependency `v`.

At the graph level these are simply node addition and dependency-edge addition. Giving them
semantic names avoids mistaking a generic graph data structure for the proposed semantics.

This basis is deliberately smaller than the current surface categories (`DEFINE`, `LET`,
`FOR`, `NAMED_PROPERTY`, `EXPLICIT_REASON`, and so on).

### 4.2 Minimal declaration attributes

The following are proposed as observable attributes, not as English speech acts:

- stable canonical identity/reference key where one exists;
- mathematical payload, which may be structured or explicitly opaque;
- authority/support state;
- visibility domain over exact project/source occurrences;
- exact provenance and occurrence identity;
- capability/ambiguity state when the declaration is not canonical authority.

A declaration may represent a binding/notation, an assumption, an established result, or a
local proof claim without requiring those surface descriptions to be primitive mutations.
Whether some node-role distinction is genuinely primitive is to be decided by the query
minimality test, not by traditional document terminology.

### 4.3 Why DECLARE is necessary

A state containing a future-resolvable declaration and a state without it can be
distinguished by appending a continuation that refers to that declaration. Therefore a
representation that cannot add a future dependency target is incomplete.

### 4.4 Why REQUIRE is necessary

Two manuscripts can make exactly the same declarations available while one proof depends on
a prior fact and another does not. A direct-dependency query distinguishes them. Therefore
availability alone is insufficient; prerequisite relations are independently observable.

### 4.5 Why scope is not a primitive act

Thorn parses a whole project and has exact project order. Visibility can therefore be a
derived predicate over declaration provenance, lexical/project scope facts, and source
position. Entering or leaving a scope need not destructively mutate the canonical graph.
Shadowing likewise adds a later declaration; it does not rewrite the earlier one.

If a valid manuscript construction is found whose dependency behaviour cannot be represented
by visibility metadata plus `DECLARE`/`REQUIRE`, that is a counterexample to this proposal
and must extend the calculus before production cutover.

### 4.6 Surface forms compile to the basis

| Source form | Proposed dependency effect |
| --- | --- |
| `Set $q = 1$.` | `DECLARE(q-binding, payload=1, visibility=...)` |
| `Define $x \star y$ to mean $x+y$.` | `DECLARE(\star-binding, payload=x+y, visibility=...)` |
| `Let $G$ be a finite group.` | `DECLARE(G-context, payload=finite-group constraint, visibility=...)` |
| `Suppose $X$ is compact.` | `DECLARE(compact-X premise, authority=given, visibility=...)` |
| `Throughout, all rings are commutative.` | `DECLARE(commutative-ring premise, authority=given, visibility=...)` |
| theorem/lemma statement | `DECLARE(result claim, authority/status=...)` |
| local load-bearing proof claim | `DECLARE(claim, authority/status=...)` |
| use of `q`/`\star` in a result | `REQUIRE(result-or-claim, resolved binding, provenance=use)` |
| `By Lemma 4, ...` when used as support | `REQUIRE(current claim, Lemma 4, provenance=source relation)` |
| purely rhetorical prose | no canonical delta |

The table is explanatory only. Production inference must not implement it as a dictionary of
English phrases.

## 5. Completeness hypothesis

The research hypothesis is:

> For Thorn's dependency-observable semantics of an append-only mathematical manuscript,
> every canonical source effect is representable by adding a dependency-bearing declaration
> or adding a prerequisite relation, with scope/authority/provenance carried as graph
> attributes and visibility derived from source/project order.

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

## 6. Existing mathematics we can reuse

This proposal is not intended as a new foundational semantics invented from scratch. Several
established bodies of work supply the right mathematical language.

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
equivalence/bisimulation: states are equivalent when their observations and future
behaviour cannot be distinguished. This is a more direct general mathematical home for the
`==Q` relation when Thorn's transition system is not finite.

### Abstract interpretation

Cousot and Cousot's abstract interpretation gives a second useful perspective. Informal
mathematical discourse contains far more information than Thorn should represent. The
canonical dependency state is an abstraction that intentionally forgets information while
preserving the observables in `Q`.

This suggests a useful correctness target: the abstraction should be dependency-sufficient
and as coarse as possible subject to that sufficiency. Thorn's explicit uncertainty policy
must remain visible rather than being hidden by an unsound approximation.

### Lean elaboration

Lean separates rich/extensible source syntax from a much smaller elaborated core and treats
command elaboration as effects on an environment. Definitions add constants to that
environment; theorems and definitions are technically close; Lean also tracks proof
dependencies such as axioms used by proofs.

The lesson for Thorn is architectural rather than a proposal to formalize the manuscript in
Lean: rich source forms should elaborate into a small dependency-state core. Surface command
names should not determine the core ontology.

### OMDoc / MMT

OMDoc and MMT already show that mathematical knowledge representation benefits from
collapsing many document-level categories into declarations, constants, definitions,
assertions, theory inclusions, and relations. MMT constants in particular combine a name
with optional type, definition, notation, roles, and aliases.

Thorn's proposed quotient is deliberately narrower: a distinction survives only when it can
change dependency observations. OMDoc/MMT therefore provide useful representation precedent,
not the final Thorn ontology.

## 7. Consequence for natural-language analysis

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
   candidate effect such as `MATH_1 denotes MATH_2` or `this claim requires RESULT_1`.
5. Thorn's authority gate decides whether that evidence is sufficient to enter canonical
   state; otherwise it remains ambiguous/unresolved.

This is an experimental direction, not a dependency decision. Hugging Face Transformers
supports local NLI-based zero-shot entailment, including relatively small NLI models, so an
off-the-shelf/keyless experiment is feasible. It must be compared empirically with the
existing spaCy-only substrate and current production behaviour before any runtime dependency
is adopted.

Semantic-role labelling or OpenIE are also plausible evidence sources, but by themselves
they normally return a lexical predicate and its arguments. If Thorn then maps predicates
such as `mean` or `define` to graph effects with a hand-maintained table, the architectural
problem has merely moved. They should therefore be evaluated only if they remove rather than
relocate lexical semantic policy.

## 8. A/B equivalence contract

Let `A` be the current production semantic path and `B` the proposed graph-delta elaborator.
Parity is **not** equality of internal IR objects. The primary differential condition is
behavioural equivalence at `Q`:

```text
A ==Q B
```

on cases where current behaviour is accepted as correct.

Every differential should be classified as one of:

1. **semantic regression**: `B` loses a dependency-relevant distinction;
2. **unsafe authority gain**: `B` creates a dependency not warranted by source evidence;
3. **observationally equivalent representation change**: internals differ but all `Q`
   observations agree;
4. **intentional fail-closed improvement**: `A` guessed and `B` exposes ambiguity/partiality;
5. **calculus counterexample**: a dependency-relevant distinction cannot be represented by
   the proposed basis.

The existing #162/#185 contracts already supply important observations: no backward leakage,
include-order shadowing, repeated-occurrence agreement/disagreement, exact provenance,
workspace partiality, and canonical review reachability. The #203 project-context ablation
adds the useful `x \star y` continuation case: source and linguistic evidence can remain
unchanged while a later dependency loses its canonical target.

A dedicated A/B harness should snapshot `Q` rather than compare private parser classes.

## 9. Ablation criterion

The existing hand-written semantic layer may be removed only when all of the following hold:

- the proposed calculus has survived explicit counterexample search;
- the new inference path uses general analysis rather than expanding an English cue
  dictionary;
- accepted current cases are `==Q` equivalent under A/B comparison;
- differences where current heuristics guessed are classified and intentionally fail closed;
- source/workspace partiality remains explicit;
- exact occurrence provenance and bounded review reachability remain intact;
- no provider/model API calls are required for the normal local path;
- the superseded production mechanism is deleted rather than retained as a shadow fallback.

If the new path cannot meet those conditions, retain the old capability only as a documented
interim limitation rather than declaring the existing parser-like mechanism architecturally
correct.

## 10. Falsifiable next steps

1. Implement a backend-independent `Q` snapshot over current canonical state.
2. Encode the minimal `DECLARE`/`REQUIRE` calculus as an experimental, non-authoritative
   graph-delta type.
3. Build synthetic/metamorphic cases that try to falsify completeness of the two-operation
   basis, including scope endings, shadowing, aliases, ambient assumptions, local assumptions,
   cross-file order, repeated inclusion, explicit proof support, and rhetorical controls.
4. Evaluate existing spaCy analysis plus at least one maintained off-the-shelf semantic
   inference path against those candidate deltas. Measure false authority first, not recall
   alone.
5. Implement `B` beside production `A` with no production cutover.
6. Differentially compare `Q`, classify every difference, and extend the calculus only for
   genuine dependency-observable counterexamples.
7. Cut over only after the evidence gate passes, then ablate the superseded parser-like
   semantic machinery in the same tranche or immediately following deletion tranche.

## References

- Jeroen Groenendijk and Martin Stokhof, *Dynamic Predicate Logic*, Linguistics and
  Philosophy 14 (1991), and related work on dynamic semantics/context change potential.
- Jeroen Groenendijk and Martin Stokhof, *Changing the Context: Dynamic Semantics and
  Discourse*.
- John Myhill (1957) and Anil Nerode (1958), the equivalence underlying the
  Myhill-Nerode theorem; used here only as the future-distinguishability pattern.
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
