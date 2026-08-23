# Proof-dependency observational semantics

Status: research contract. This document proposes a semantic boundary and a falsifiable
replacement programme. It does **not** by itself change production authority or delete the
current semantic extraction path.

## Thesis

Thorn does not need a general semantics of mathematical prose. It needs exactly the semantic
state required to determine proof dependency.

> **Canonical Thorn semantics should retain exactly the distinctions that can change a
> proof-dependency observation, now or under some valid future continuation of the source.**

A distinction that cannot affect such an observation may still matter rhetorically,
pedagogically, stylistically, or as review evidence. It simply does not belong in the
canonical dependency semantics. Conversely, if a distinction can affect proof dependency but
cannot be represented, the semantic model is incomplete.

This gives two separate obligations:

1. **dependency semantics** — retain exactly dependency-observable distinctions;
2. **assurance decoration** — retain exact provenance/evidence for each represented semantic
   object or relation without making source coordinates part of mathematical equality.

## 1. Contextual equivalence on source histories

Let a **history** `h` be a valid normalized mathematical-source history after the source and
workspace layers have established their facts. Let `Sem(h)` denote whatever dependency
semantics Thorn assigns to that history.

Let `Q` be a finite family of dependency-relevant query forms. For a query `q` and history
`h`, write

```text
Obs(q, h)
```

for the dependency-relevant answer, including unresolved/ambiguous/partial outcomes where
they change dependency reasoning.

Current observations are not enough. A declaration can be unused when introduced but become
a prerequisite of a later theorem. Therefore let `C` range over valid future source
continuations and define:

```text
h1 ==Q h2
    iff
for every valid continuation C and every q in Q,
    Obs(q, h1 · C) = Obs(q, h2 · C).
```

This definition is intentionally on **source histories**, not on a presumed graph transition
`delta(graph, C)`. Writing such a transition already assumes that the proposed graph state is
sufficient to interpret every continuation, which is exactly what the research programme is
trying to establish.

If a fully abstract canonical representation `G` is found, then continuation processing on
canonical states becomes well-defined up to `==Q`:

```text
h1 ==Q h2
    iff
G(h1) = G(h2)             (up to canonical graph isomorphism)
```

The two directions are the familiar full-abstraction obligations:

- **preservation / adequacy**: `G` must not erase a distinction that a future dependency
  context can observe;
- **reflection / minimality**: `G` should not retain a semantic distinction that no future
  dependency context can observe.

This does not imply a finite state space. Mathematical payloads and projects are unbounded.
The finite thing sought is the **signature of dependency-relevant structure and queries**.

## 2. Dependency relevance

A proposed semantic distinction `r` earns a place in canonical state exactly when there are
two histories differing only in that distinction and some continuation/query that separates
them:

```text
RelevantQ(r)
    iff
there exist h_with_r, h_without_r, C, q such that
    Obs(q, h_with_r · C) != Obs(q, h_without_r · C).
```

Examples:

- `Define $x \star y$ to mean $x+y$.` is relevant because a later use of `\star` can gain or
  lose a canonical prerequisite.
- `Throughout, all groups are finite.` is relevant because later results may depend on the
  ambient finiteness premise without restating it.
- `By Lemma 4, ...` is relevant when Lemma 4 is actually presented as support for a claim.
- `This proof is elegant.` is not dependency-relevant unless Thorn deliberately adds a
  dependency query whose answer can depend on that judgement.

For borderline prose such as `The argument is similar to the previous proof`, the lexical
relation is not itself canonical. If the previous proof is being used as support, the
canonical effect is the prerequisite relation. If not, there is no dependency-semantic
effect. Ambiguity stays explicit.

## 3. Candidate semantic query family Q

`Q` is defined from Thorn's dependency obligations, not from current Python classes or a
vocabulary of mathematical speech acts.

### Q1. Resolution

```text
Resolve(occurrence, project-context)
    -> canonical target | unresolved | ambiguous
```

This covers notation/symbol/result identity only where identity can affect later dependency
behaviour.

### Q2. Visibility

```text
Visible(position, project-context)
    -> dependency-bearing facts/declarations in force
```

Project order, lexical/project scope, shadowing, and repeated inclusion are observable through
this query without making `let`, `throughout`, or `henceforth` primitive semantic acts.

### Q3. Direct prerequisites

```text
Direct(node) -> immediate canonical prerequisites
```

### Q4. Transitive prerequisites

```text
Closure(node) -> transitive canonical prerequisite set
```

### Q5. Dependency status / capability

```text
Status(query or graph element)
    -> resolved | given | established | ambiguous | partial | unsupported | source-error
```

The exact finite status set remains subject to minimization. A status survives only if some
future dependency observation distinguishes it. For example, an accepted premise and an
unsupported assertion cannot be collapsed if later review/closure semantics treats them
differently.

A query should be removed from `Q` when it is shown to be derivable from the others without
losing any supported dependency distinction.

## 4. Provenance/evidence P is separate from semantic equality

Exact provenance is mandatory for Thorn but must not define `==Q`. Otherwise two equivalent
paraphrases at different source offsets would automatically become different mathematics.

Let

```text
P : canonical node or relation -> exact source occurrence(s) + evidence
```

be the assurance decoration.

A replacement path must therefore satisfy two independent conditions:

```text
A ==Q B
```

for dependency semantics, and an exact correspondence between `P_A` and `P_B` for the
semantically matched graph elements.

Bounded review/source-rescue reachability is similarly an acceptance projection of semantic
state, provenance, and review policy. It must remain stable during migration, but it does not
make raw source coordinates part of the mathematical quotient.

## 5. Proposed minimal graph signature

The current falsifiable hypothesis is that canonical dependency semantics needs only a set of
dependency-bearing nodes plus a prerequisite relation:

```text
DependencyGraph = (V, REQUIRE)
REQUIRE subset of V x V
```

Equivalently, when constructing a graph from a complete history, the only structural
operations needed are:

```text
DECLARE(v)
REQUIRE(u, v)
```

`DECLARE` admits a future dependency target/fact. `REQUIRE(u, v)` says that `v` is a
prerequisite of `u` in the mathematics as presented.

These are a **representation basis**, not yet an incremental operational semantics. A future
continuation may cause the whole history to elaborate differently (for example by ending an
ambient convention). Full abstraction must be established before an implementation is
entitled to assume that every continuation can be processed by monotonically applying these
two operations to an existing graph.

### 5.1 Do not hide an ontology inside nodes

The proposal would be vacuous if a node could contain an arbitrary new semantic relation.
The node shape must be fixed and every field justified by `Q`.

The provisional core is:

```text
DependencyNode
    binding/reference key      optional; only if future resolution can observe it
    mathematical payload       structured expression/proposition or opaque payload
    dependency status          only distinctions observable through Q
    visibility description     only data required to answer Visible/Resolve
```

The only primitive semantic edge is `REQUIRE`.

Exact source spans, wording, parser evidence, confidence traces, and report handles belong in
`P`, not the semantic node.

Traditional labels such as `definition`, `assumption`, `notation`, `lemma`, `let`, or
`explicit reason` are not admitted merely because mathematicians use those words. Such a role
belongs in the core only if two otherwise identical histories can be separated by a future
proof-dependency context because of that role.

### 5.2 Surface forms as graph effects

The following table is explanatory, not an implementation dictionary:

| Source | Candidate canonical effect |
| --- | --- |
| `Set $q = 1$.` | declare a future-resolvable `q` fact/binding |
| `Define $x \star y$ to mean $x+y$.` | declare a future-resolvable `\star` fact/binding |
| `Let $G$ be a finite group.` | declare the dependency-bearing local context required by later claims |
| `Suppose $X$ is compact.` | declare a premise visible in the relevant scope |
| `Throughout, all rings are commutative.` | declare a forward-visible ambient premise |
| theorem/lemma statement | declare a result claim |
| local load-bearing proof claim | declare a claim that can itself have prerequisites |
| use of a prior definition/result/premise | add `REQUIRE(owner, prerequisite)` |
| purely rhetorical prose | no canonical graph effect |

### 5.3 Why node introduction is necessary

A history containing an unused but future-resolvable declaration and one without it can be
distinguished by appending a continuation that refers to it. A representation unable to
retain future dependency targets is therefore inadequate.

### 5.4 Why prerequisite edges are necessary

Two histories can expose the same set of declarations while one presented proof uses a prior
fact and another does not. `Direct(node)` separates them, so declaration availability alone
is insufficient.

## 6. Counterexample pressure on the minimal basis

`{DECLARE, REQUIRE}` is a hypothesis, not a result. The counterexample search has already
identified cases that must be treated carefully.

### Later scope changes and retractions

A continuation such as `From this point on we no longer assume compactness` can change the
future visibility of an earlier premise. This is why the formal equivalence above is defined
on `h · C` rather than by assuming monotone graph updates.

The two-operation basis survives only if the *final* graph for each history can encode the
resulting visibility using a fixed visibility description, without introducing an open-ended
semantic relation vocabulary. If not, visibility/scope needs an additional primitive.

### Alternative and joint support

A plain set of prerequisite edges records which material the presented argument depends on,
but it does not by itself distinguish Boolean support structure such as “either proof A or
proof B suffices” from “both A and B are needed”.

Current Thorn dependency/review queries concern presented prerequisite reachability rather
than minimal alternative proof sets, so this distinction is not currently in `Q`. If Thorn
later needs queries about alternative sufficient supports, either intermediate support nodes
must represent that structure without new edge semantics or the graph signature must grow.
That would be a legitimate calculus counterexample, not a reason to smuggle `OR` into an
arbitrary metadata field.

### Status changes

A later proof can change how an earlier claim is regarded. The preferred representation is
to make support itself graph structure and derive status where possible, rather than mutate a
surface-labelled `theorem`/`assumption` tag. Any irreducible status distinction must justify
itself through `Q`.

These cases are deliberate tests of completeness rather than corner cases to patch with prose
patterns.

## 7. Existing mathematics we can reuse

The proposal has strong precedents and should not be presented as a new foundational
semantics from scratch.

### Contextual equivalence and full abstraction

This is the closest standard formulation. In programming-language semantics, fragments are
contextually equivalent when no permitted context can distinguish their behaviour; a
semantics is fully abstract when equality in the semantic model coincides with contextual
observational equivalence.

For Thorn, the contexts are valid future manuscript continuations plus supported dependency
queries. This gives exactly the preservation/reflection criterion in Section 1.

### Dynamic semantics

Dynamic semantics treats discourse meaning as **context change potential**. That is a useful
analogy for source statements that establish later-visible mathematical context. Thorn's
abstraction is narrower: only changes that can affect proof dependency survive.

### Nerode-style future distinguishability

Myhill-Nerode supplies the useful pattern that histories should be identified by what future
continuations can distinguish. Thorn does not inherit the finite-automaton conclusion; its
state space is generally infinite.

### Behavioural equivalence / coalgebra

Coalgebraic and transition-system semantics provide general tools for identifying states by
observable future behaviour and are a natural mathematical language if we later make the
continuation dynamics explicit.

### Abstract interpretation

Informal mathematical discourse contains much more information than Thorn should preserve.
The dependency graph can be viewed as an abstraction that intentionally forgets information
while remaining sufficient for the dependency queries in `Q`.

### Lean elaboration

Lean separates extensible source syntax from a smaller elaborated core. Command elaboration
changes an environment, definitions add constants to it, and theorems are technically close
to definitions. The useful lesson for Thorn is architectural: rich surface forms elaborate
to a small core; surface command vocabulary should not determine the core ontology.

### OMDoc / MMT

OMDoc/MMT provide representation precedent for collapsing many document-level forms into
symbols/declarations plus structured mathematical objects and relations. MMT constants, for
example, can carry names, types, definitions, notations, roles, and aliases. Thorn's proposed
quotient is intentionally narrower: a distinction survives only if proof-dependency
observations can see it.

## 8. Consequence for natural-language analysis

The finite vocabulary must be the dependency semantics, **not an English dictionary**.
Production code must not regain architectures such as:

```text
if lemma in {define, mean, denote, call, ...}: emit DEFINITION
```

Dependency syntax alone is also insufficient: a dependency parser can expose argument
structure without determining whether a predicate expresses a dependency-relevant change.

A promising off-the-shelf direction is therefore semantic entailment over candidate graph
effects:

1. Tree-sitter and `LinguisticProjection` preserve exact source structure and typed math/ref
   placeholders.
2. `LinguisticFrontend` supplies general grammatical analysis and candidate arguments.
3. The finite graph signature constrains what effects may be proposed.
4. A general local semantic-inference/NLI component tests whether the source entails a
   proposed graph effect.
5. Thorn's authority gate admits a uniquely supported effect or preserves
   ambiguity/unsupported capability.

Semantic-role labelling or OpenIE remain possible evidence sources, but if they merely return
a lexical predicate that Thorn then maps through a hand-maintained `mean -> definition`
table, the architectural problem has only moved.

`research/dependency-semantics/run_nli_effect_screen.py` is a research-only feasibility
screen against the existing #160 adversarial corpus. It deliberately tests semantic-effect
classification before payload extraction and adds no production model dependency.

## 9. A/B and ablation contract

Let `A` be the current production path and `B` the replacement elaborator. Parity is not
internal-IR equality.

The semantic condition is contextual equivalence at `Q`; independently, exact evidence must
correspond through `P` and bounded review reachability must remain correct.

Every differential must be classified as one of:

1. semantic regression;
2. unsafe authority gain;
3. dependency-observationally equivalent representation change;
4. provenance/evidence regression;
5. intentional fail-closed improvement;
6. calculus counterexample.

The existing #162/#185 contracts already exercise no-backward-leakage, include-order
shadowing, repeated-occurrence disagreement, workspace partiality, dependency/review closure,
and exact provenance. The #203 `x \star y` ablation adds a useful continuation witness:
source evidence remains, but a later use loses its canonical dependency.

The current hand-written semantic layer may be ablated only when:

- the proposed graph signature has survived explicit counterexample search;
- relation inference uses general analysis rather than an expanding cue dictionary;
- accepted current cases are equivalent at semantic `Q`;
- current guesses that become unresolved are explicitly classified as intentional fail-closed
  changes;
- exact provenance/evidence remains intact through `P`;
- source/workspace partiality remains explicit;
- bounded review reachability remains correct;
- the normal path needs no provider/model API calls;
- superseded production machinery is deleted rather than retained as a shadow fallback.

## 10. Experimental sequence

1. Split the executable migration oracle into semantic `Q` and exact-provenance `P`
   projections.
2. Try to falsify the graph signature with synthetic/metamorphic continuation cases,
   especially scope termination, retraction, shadowing, aliases, ambient/local premises,
   cross-file order, repeated inclusion, support structure, and rhetorical controls.
3. Reuse the #160 adversarial corpus to evaluate at least one maintained off-the-shelf local
   semantic-inference path without lexical cue rules. Measure false authority first.
4. Build replacement path `B` beside current production `A`, with no production cutover.
5. Compare `A` and `B` at semantic `Q`, then compare `P` and bounded review reachability
   independently.
6. Extend the graph signature only for genuine dependency-observable counterexamples.
7. Cut over only after the evidence gate passes, then ablate the superseded parser-like
   semantic machinery.

## References

- Standard contextual-equivalence/full-abstraction literature in programming-language
  semantics; the key criterion is coincidence of contextual and denotational equivalence.
- Jeroen Groenendijk and Martin Stokhof, *Dynamic Predicate Logic*, Linguistics and
  Philosophy 14 (1991), and related work on dynamic semantics/context-change potential.
- John Myhill (1957) and Anil Nerode (1958), for the future-distinguishability pattern.
- J.J.M.M. Rutten, *Universal Coalgebra: A Theory of Systems*, Theoretical Computer Science
  249 (2000), 3-80.
- Patrick Cousot and Radhia Cousot, *Abstract Interpretation: A Unified Lattice Model for
  Static Analysis of Programs by Construction or Approximation of Fixpoints*, POPL 1977.
- Lean Language Reference, sections on elaboration, definitions, theorems, and source-file
  environments.
- Michael Kohlhase, OMDoc work on mathematical knowledge representation.
- Florian Rabe and Michael Kohlhase, MMT language/documentation, especially symbol
  declarations and theory structure.
