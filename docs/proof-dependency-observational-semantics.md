# Proof-dependency observational semantics

Status: research contract. This note follows the merged #211 production checkpoint and the
closure of #203. It defines the semantic target for later replacement work; it does **not**
change production mathematical authority or choose a new NLP/runtime dependency.

## Thesis

Thorn does not need a general semantics of mathematical prose. It needs exactly the semantic
state required to determine proof dependency.

> **Canonical Thorn semantics should retain exactly the distinctions that can change a
> proof-dependency observation, now or under some valid future continuation of the source.**

A distinction that cannot affect such an observation may still matter rhetorically,
pedagogically, stylistically, or as review evidence. It simply does not belong in canonical
dependency semantics. Conversely, if a distinction can affect proof dependency but cannot be
represented, the semantic model is incomplete.

Two correctness obligations are deliberately separate:

1. **dependency semantics** — retain exactly dependency-observable distinctions;
2. **assurance decoration** — preserve exact provenance/evidence for each retained semantic
   object or relation without making source coordinates part of mathematical equality.

## 1. Contextual equivalence on source histories

Let a history `h` be a valid normalized mathematical-source history after source and
workspace facts have been established.

Let `Q` be Thorn's finite family of dependency-relevant query forms. For a query `q` and
history `h`, write

```text
Obs(q, h)
```

for the dependency-relevant answer, including unresolved, ambiguous, partial, unsupported,
and source-error outcomes where those outcomes affect dependency reasoning.

Current observations alone are insufficient. An unused declaration may become a prerequisite
of a later theorem. Let `C` range over valid future source continuations and define

```text
h1 ==Q h2
    iff
for every valid continuation C and every q in Q,
    Obs(q, h1 · C) = Obs(q, h2 · C).
```

The definition is intentionally on **source histories**, not on a presumed transition
`delta(graph, C)`. Such a transition already assumes that the graph contains all information
needed to interpret every future continuation, which is what this programme is trying to
establish.

A canonical representation `G` is the target when it is fully abstract for these
observations:

```text
h1 ==Q h2
    iff
G(h1) = G(h2)             (up to canonical graph isomorphism)
```

This gives the usual two directions:

- **preservation / adequacy** — do not erase a distinction that a future dependency context
  can observe;
- **reflection / minimality** — do not retain a semantic distinction that no future
  dependency context can observe.

The state space need not be finite. Mathematical payloads and projects are unbounded. The
finite object sought is the **signature of dependency-relevant structure and observations**.

## 2. Dependency relevance

A proposed semantic distinction `r` belongs in canonical state exactly when some future
continuation and dependency query can observe it:

```text
RelevantQ(r)
    iff
there exist h_with_r, h_without_r, C, q such that
    Obs(q, h_with_r · C) != Obs(q, h_without_r · C).
```

Examples:

- `Define $x \star y$ to mean $x+y$.` is relevant because a later use of `\star` may gain or
  lose a canonical prerequisite.
- `Throughout, all groups are finite.` is relevant because a later result may depend on the
  ambient premise without restating it.
- `By Lemma 4, ...` is relevant when Lemma 4 is actually used as support.
- `This proof is elegant.` is not dependency-relevant unless Thorn deliberately introduces a
  dependency query whose answer can depend on that judgement.

For borderline prose such as `The argument is similar to the previous proof`, the word
`similar` is not itself canonical. If the previous proof is used as support, the canonical
effect is a prerequisite relation. Otherwise there is no dependency-semantic effect.
Ambiguity remains explicit.

## 3. Candidate semantic query family Q

`Q` is defined from Thorn's proof-dependency obligations, not from current Python classes or
a vocabulary of mathematical speech acts.

### Q1. Resolution

```text
Resolve(occurrence, project-context)
    -> canonical target | unresolved | ambiguous
```

This covers symbol, notation, and result identity only where identity can affect later
proof-dependency behaviour.

### Q2. Visibility

```text
Visible(position, project-context)
    -> dependency-bearing facts/declarations in force
```

Project order, scope, shadowing, and repeated inclusion are observable here without making
surface words such as `let`, `throughout`, or `henceforth` semantic primitives.

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

The exact finite status set remains subject to minimization. A status survives only when some
future dependency observation distinguishes it. A query should likewise be removed from `Q`
when it is derivable from the others without losing a supported dependency distinction.

## 4. Exact provenance/evidence P is not semantic equality

Exact provenance is mandatory for Thorn but must not define `==Q`. Otherwise two equivalent
paraphrases at different offsets would automatically become different mathematics.

Let

```text
P : canonical node or relation -> exact source occurrence(s) + evidence
```

be the assurance decoration.

A replacement path must satisfy both:

```text
A ==Q B
```

for dependency semantics, and an exact correspondence between `P_A` and `P_B` for semantically
matched graph elements.

The executable migration oracle in this tranche reflects that split physically:

```text
DependencyObservationSnapshot
    semantic   -> Q projection, with no raw source coordinates
    provenance -> P projection, with exact source occurrences
```

The semantic projection uses coordinate-free local graph keys. A source-relocation test
requires semantic `Q` to remain unchanged while provenance `P` changes.

Bounded review/source-rescue reachability is an acceptance projection of semantic state,
provenance, and review policy. It must remain stable during migration, but it does not make
raw source coordinates part of mathematical equality.

## 5. Proposed minimal graph signature

The current falsifiable hypothesis is that canonical dependency semantics needs only a set of
dependency-bearing nodes plus one prerequisite relation:

```text
DependencyGraph = (V, REQUIRE)
REQUIRE subset of V x V
```

Equivalently, when constructing a graph from a complete history, the structural basis is

```text
DECLARE(v)
REQUIRE(u, v)
```

`DECLARE` admits a future dependency target/fact. `REQUIRE(u, v)` records that `v` is a
prerequisite of `u` in the mathematics as presented.

These are a **representation basis**, not yet an incremental operational semantics. A future
continuation may change the correct elaboration of earlier material. Full abstraction must be
established before an implementation may assume every continuation can be processed by
monotonically mutating an existing graph.

### 5.1 Do not hide an ontology inside nodes

The proposal is vacuous if node metadata can contain arbitrary new semantic relations. Every
node field must be justified by `Q`.

The provisional core is only:

```text
DependencyNode
    binding/reference key      only if future resolution can observe it
    mathematical payload       structured expression/proposition or opaque payload
    dependency status          only distinctions observable through Q
    visibility description     only information required by Visible/Resolve
```

The only primitive semantic edge is `REQUIRE`.

Exact source spans, wording, parser evidence, confidence traces, and report handles belong in
`P`, not the semantic node.

Traditional labels such as `definition`, `assumption`, `notation`, `lemma`, `let`, or
`explicit reason` are not admitted merely because mathematicians use those categories. Such
a role belongs in the core only if a future proof-dependency context can distinguish it.

### 5.2 Surface forms are examples, not an implementation dictionary

| Source form | Candidate canonical effect |
| --- | --- |
| `Set $q = 1$.` | declare a future-resolvable `q` fact/binding |
| `Define $x \star y$ to mean $x+y$.` | declare a future-resolvable `\star` fact/binding |
| `Let $G$ be a finite group.` | declare dependency-bearing local context |
| `Suppose $X$ is compact.` | declare a visible premise |
| `Throughout, all rings are commutative.` | declare a forward-visible ambient premise |
| theorem/lemma statement | declare a result claim |
| local load-bearing proof claim | declare a claim that may itself have prerequisites |
| use of a prior definition/result/premise | add `REQUIRE(owner, prerequisite)` |
| purely rhetorical prose | no canonical graph effect |

The table explains the hypothesis. Production inference must not implement it as a phrase or
predicate dictionary.

### 5.3 Why both primitives are necessary

A history containing an unused but future-resolvable declaration can be distinguished from
one without it by appending a continuation that refers to the declaration. Some form of node
introduction is therefore necessary.

Two histories may expose the same declarations while the presented proof in one uses a prior
fact and the other does not. `Direct(node)` separates them. Availability alone is therefore
insufficient; prerequisite structure is independently observable.

## 6. Counterexample pressure

`{DECLARE, REQUIRE}` is a hypothesis, not a theorem. The following cases deliberately put
pressure on it.

### Scope changes and retractions

A continuation such as `From this point on we no longer assume compactness` can change future
visibility. The two-operation basis survives only if the final graph can represent this with
a fixed visibility description. Otherwise visibility/scope requires an additional primitive.

### Alternative and joint support

A plain prerequisite set does not distinguish `either A or B suffices` from `both A and B are
required`. Current Thorn queries concern the dependencies of the argument actually presented,
not minimal alternative proof sets, so this distinction is not currently in `Q`.

If a future product query requires alternative sufficient supports, the graph signature must
represent that structure, perhaps through intermediate support nodes. That would be a real
calculus counterexample, not permission to smuggle Boolean semantics into arbitrary metadata.

### Status changes

A later proof may change how an earlier claim is regarded. Prefer representing support as
graph structure and deriving status where possible. Any irreducible status distinction must
justify itself through `Q`.

These are tests of completeness, not prose corner cases to patch with recognizers.

## 7. Existing mathematics to reuse

This proposal is not presented as a new foundational semantics from scratch.

### Contextual equivalence and full abstraction

This is the closest standard formulation. Program fragments are contextually equivalent when
no permitted context can distinguish their behaviour; a semantics is fully abstract when its
equality coincides with contextual observational equivalence.

For Thorn, the permitted contexts are valid future manuscript continuations plus supported
proof-dependency queries.

### Dynamic semantics

Dynamic semantics treats discourse meaning as context change potential. Thorn uses a much
narrower abstraction: only context changes that can affect proof dependency survive.

### Nerode-style future distinguishability

Myhill-Nerode supplies the useful pattern that histories should be identified by what future
continuations can distinguish. Thorn does not inherit the finite-automaton conclusion; its
state space is generally infinite.

### Behavioural equivalence / coalgebra

Coalgebraic and transition-system semantics provide a general language for identifying
states by observable future behaviour if Thorn later formalizes continuation dynamics.

### Abstract interpretation

The dependency graph can be viewed as an abstraction of informal mathematical discourse that
intentionally forgets information while preserving the observables in `Q`.

### Lean elaboration

Lean separates rich/extensible source syntax from a much smaller elaborated core and changes
an environment through elaboration. The lesson for Thorn is architectural: rich surface forms
should elaborate to a small core; surface vocabulary should not determine the core ontology.

### OMDoc / MMT

OMDoc/MMT provide useful precedent for collapsing mathematical document forms into
symbols/declarations plus structured objects and relations. Thorn's proposed quotient is
narrower: a distinction survives only when proof-dependency observations can see it.

## 8. Consequence for natural-language analysis

The finite vocabulary must be the dependency semantics, **not an English dictionary**.
Production code must not regain architectures such as

```text
if lemma in {define, mean, denote, call, ...}: emit DEFINITION
```

Dependency syntax alone is also insufficient: a dependency parser can expose argument
structure without determining whether a predicate expresses a dependency-relevant change.

Possible mature semantic substrates include local entailment/NLI, semantic-role labeling,
OpenIE, AMR, or combinations with the existing spaCy analysis. None is selected here.

The key test is whether such a substrate can infer candidate graph effects and ground their
arguments **without** leaving Thorn to maintain a lexical predicate-to-effect dictionary.
External semantic analysis remains non-authoritative; Thorn still owns mathematical
authority, scope/visibility policy, ambiguity, graph identity, and provenance.

This empirical evaluation is intentionally split out to **issue #213**. #212 contains no
model experiment and makes no runtime-dependency decision.

## 9. A/B and ablation contract

Let `A` be the current production path after #211 and `B` a future replacement elaborator.
Parity is not private-IR equality.

The primary semantic condition is equivalence at `Q`. Independently, exact evidence must
correspond through `P`, and bounded review reachability must remain correct.

Every differential must be classified as one of:

1. semantic regression;
2. unsafe authority gain;
3. dependency-observationally equivalent representation change;
4. provenance/evidence regression;
5. intentional fail-closed improvement;
6. calculus counterexample.

The existing #162/#185 contracts exercise no-backward-leakage, include-order shadowing,
repeated-occurrence disagreement, workspace partiality, dependency/review closure, and exact
provenance. The #203/#211 `x \star y` ablation is an additional witness: source evidence
remains while a later occurrence loses its canonical dependency.

The current parser-like semantic machinery may be ablated only when:

- the graph signature has survived explicit counterexample search;
- relation inference uses general analysis rather than an expanding cue dictionary;
- accepted current cases are equivalent at semantic `Q`;
- intentional losses of unjustified certainty are explicitly classified;
- exact provenance/evidence remains correct through `P`;
- source/workspace partiality remains explicit;
- bounded review reachability remains correct;
- the normal path requires no provider/model API calls;
- superseded production machinery is deleted rather than retained as a shadow fallback.

## 10. Scope of this tranche and next work

This PR is complete when it establishes a reviewable semantic contract, not when it replaces
production inference.

Its deliverables are:

1. continuation-sensitive dependency observational equivalence on source histories;
2. the falsifiable `{DECLARE, REQUIRE}` minimal graph-signature hypothesis;
3. explicit counterexample pressure rather than assumed completeness;
4. the semantic `Q` versus exact-provenance `P` separation;
5. an executable migration oracle demonstrating that separation on the #211 alias case,
   project-order shadowing, repeated-occurrence fail-closed behaviour, and source relocation.

Follow-up #213 owns evaluation of off-the-shelf non-dictionary relation inference. A later
implementation tranche may build replacement path `B`, compare it against production `A` at
`Q` and `P`, and ablate the old recognizer only after that evidence gate passes.

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
