# Proof-dependency observational semantics

Status: research contract. This note follows merged #211 and the closure of #203. It defines
the semantic target for later replacement work; it does **not** change production authority,
choose an NLP/model dependency, or cut over the current semantic path.

## Thesis

Thorn does not need a general semantics of mathematical prose. It needs the semantic state
required to determine proof dependency.

> **Canonical Thorn semantics should retain exactly the distinctions that can change a
> proof-dependency observation, now or under some valid future continuation of the source.**

This is intentionally narrower than “understand the mathematics”. A distinction may matter
rhetorically, pedagogically, stylistically, or as source evidence while still disappearing
from canonical dependency semantics. Conversely, if a distinction can change proof dependency
and the canonical state cannot represent it, the state model is incomplete.

The proposal has two independent obligations:

1. **dependency semantics `Q`** — preserve exactly dependency-observable distinctions;
2. **assurance provenance `P`** — preserve the source evidence for each represented node,
   resolution, and prerequisite relation without making source coordinates mathematical
   identity.

## 1. Contextual equivalence on source histories

Let a history `h` be normalized mathematical source after the source and workspace layers have
established their facts. Let `Q` be the family of dependency-relevant query forms.

For a query `q` and history `h`, write

```text
Obs(q, h)
```

for the dependency-relevant answer, including unresolved, ambiguous, partial, unsupported, and
source-error outcomes where those outcomes alter dependency reasoning.

Current answers are not sufficient. A declaration can be unused now and become a prerequisite
of a theorem appended later. Let `C` range over valid future manuscript continuations and
define contextual equivalence by

```text
h1 ==Q h2
    iff
for every valid continuation C and every q in Q,
    Obs(q, h1 · C) = Obs(q, h2 · C).
```

The definition is deliberately on source histories, not on a presumed transition
`delta(graph, C)`. Writing that transition already assumes the proposed graph contains all
information needed to interpret every continuation, which is exactly what this programme is
trying to establish.

A canonical representation `G` is the target when it is fully abstract for these observations:

```text
h1 ==Q h2
    iff
G(h1) = G(h2)             up to canonical graph isomorphism
```

This gives the usual two directions:

- **preservation / adequacy** — do not erase a distinction that some future dependency context
  can observe;
- **reflection / minimality** — do not retain a semantic distinction that no future dependency
  context can observe.

The state space is not expected to be finite. Mathematical payloads and manuscripts are
unbounded. What should be finite is the **signature of dependency-relevant structure and query
forms**.

## 2. Dependency relevance

A candidate semantic distinction `r` belongs in canonical state only if some continuation and
dependency query can observe it:

```text
RelevantQ(r)
    iff
there exist h_with_r, h_without_r, C, q such that
    Obs(q, h_with_r · C) != Obs(q, h_without_r · C).
```

Examples:

- `Define $x \star y$ to mean $x+y$.` is relevant because a later use of `\star` can gain or
  lose a prerequisite.
- `Throughout, all groups are finite.` is relevant because a later theorem may depend on the
  ambient premise without repeating it.
- `By Lemma 4, ...` is relevant when Lemma 4 is actually presented as support.
- `This proof is elegant.` is not dependency-relevant unless Thorn deliberately introduces a
  dependency query whose answer depends on that judgement.

For a borderline sentence such as `The argument is similar to the previous proof`, `similar`
is not itself a canonical relation. If the previous proof is used as support, the dependency
effect is a prerequisite edge. If it is only exposition, there is no dependency-semantic
effect. Ambiguity remains explicit.

## 3. Primitive query family Q

`Q` is defined from Thorn's proof-dependency obligations, not from current Python classes and
not from a vocabulary of mathematical speech acts.

### Q1. Resolution

```text
Resolve(occurrence, context)
    -> canonical target | unresolved | ambiguous
```

This covers result, symbol, and notation identity only where the identity can change later
dependency behaviour.

### Q2. Visibility

```text
Visible(context)
    -> dependency-bearing nodes currently in force
```

Project order, scope, shadowing, and repeated inclusion are observable through this query
without making surface words such as `let`, `throughout`, or `henceforth` semantic primitives.

### Q3. Direct prerequisites

```text
Direct(node)
    -> immediate prerequisite nodes | unresolved prerequisite references
```

This is the primitive graph-dependency query.

### Q4. Capability/status

```text
Status(query or graph element)
    -> finite dependency-relevant capability state
```

The exact status algebra remains subject to minimization. A status survives only if a future
dependency observation can distinguish it.

### Derived observations

Transitive closure is intentionally **not** a primitive member of `Q`:

```text
Closure(node) = transitive closure of Direct
```

Review reachability is also not semantic equality. It is an acceptance projection computed
from dependency semantics, provenance, and review policy.

Any proposed query should be removed when it is derivable from the remaining query family
without losing a supported dependency distinction.

## 4. Provenance/evidence P is separate from semantic equality

Exact provenance is mandatory for Thorn, but raw source coordinates must not define `==Q`.
Otherwise moving equivalent mathematics by two blank lines would create different
mathematics.

Let

```text
P : semantic node/resolution/relation -> source occurrence(s) + evidence
```

be the assurance decoration.

A replacement path must therefore satisfy two different conditions:

```text
A ==Q B
```

for dependency semantics, and a faithful correspondence between `P_A` and `P_B` for
semantically matched nodes, resolutions, and prerequisite relations.

This distinction matters particularly for edges. Recovering the correct `REQUIRE(u, v)` from
the wrong sentence is a provenance failure even when the graph topology is identical.

The executable migration oracle in this tranche reflects the split physically:

```text
DependencyObservationSnapshot
    semantic   -> bounded Q projection
    provenance -> P projection
```

The semantic projection contains no source offsets, source filenames, parser roles, or review
selection. `P` records source evidence separately.

Where current canonical IR exposes a full `SourceSpan`, `P` preserves offsets and columns.
Where an existing result-reference edge exposes only `SourceRange`, `P` preserves that
line-granular evidence plus workspace occurrence IDs rather than pretending greater precision.
A replacement must not degrade the available provenance and should improve it where the
canonical substrate later becomes more precise.

## 5. Minimal labelled-graph hypothesis

The earlier shorthand

```text
DependencyGraph = (V, REQUIRE)
```

was too terse: `Resolve`, `Visible`, and `Status` cannot be answered by an unlabelled graph.

The actual falsifiable hypothesis is a **small labelled directed graph**

```text
G = (V, REQUIRE, bind, payload, visibility, status)
```

where:

- `V` is the set of dependency-bearing nodes;
- `REQUIRE ⊆ V × V` is the only primitive semantic edge;
- `bind(v)` is an optional finite-namespace reference/binding key;
- `payload(v)` is the mathematical expression/proposition carried by the node;
- `visibility(v)` is the fixed visibility information needed by `Resolve` and `Visible`;
- `status(v)` is only the finite capability state that cannot be derived from graph structure.

In construction language the structural operations are still

```text
DECLARE(v; bind, payload, visibility, status)
REQUIRE(u, v)
```

but `DECLARE` introduces a **labelled** node. The labels are part of the proposed finite
signature; they are not an unrestricted metadata dictionary.

### 5.1 No hidden ontology

The proposal would be vacuous if `payload`, `visibility`, or `status` could contain arbitrary
new semantic relations.

The restrictions are:

```text
bind
    finite reference namespace + mathematical binding key

payload
    structured mathematical expression/proposition
    or an explicitly opaque mathematical payload

visibility
    fixed scope/precedence data sufficient for Resolve/Visible
    never raw English or an open-ended semantic tag map

status
    finite dependency-capability distinctions justified by Q
```

Source wording, parser evidence, confidence traces, report handles, and source coordinates
belong in `P` or other non-semantic layers.

Traditional labels such as `definition`, `assumption`, `notation`, `lemma`, `let`, and
`explicit reason` are not admitted merely because mathematicians use those categories. A
distinction survives only when a future proof-dependency context can observe it.

### 5.2 Surface forms are examples, not an inference dictionary

| Source form | Candidate graph effect |
| --- | --- |
| `Set $q = 1$.` | declare a future-resolvable mathematical node |
| `Define $x \star y$ to mean $x+y$.` | declare a future-resolvable node |
| `Let $G$ be a finite group.` | declare dependency-bearing local context |
| `Suppose $X$ is compact.` | declare a visible premise |
| `Throughout, all rings are commutative.` | declare a forward-visible premise |
| theorem/lemma statement | declare a result node |
| local load-bearing proof claim | declare a claim node |
| use of a prior result/definition/premise | add `REQUIRE(owner, prerequisite)` |
| purely rhetorical prose | no canonical graph effect |

This table explains the target semantics. Production inference must not implement it as a
phrase or predicate dictionary.

### 5.3 Why both structural primitives are necessary

An unused declaration is still necessary state: append a continuation that refers to it and a
history with the declaration becomes distinguishable from one without it.

Prerequisite edges are independently necessary: two histories can expose the same nodes while
the presented proof in one uses a prior fact and the other does not. `Direct(node)` separates
them.

## 6. Visibility and source order

Source coordinates are not mathematical identity, but **relative semantic precedence can be
observable**.

For example:

```text
Set q = 1.
Set q = 2.
```

and the reversed order need not be equivalent because a later `q` can resolve differently.

By contrast, swapping two independent labelled theorem blocks whose local bindings never
interact should not change `Q`.

The bounded executable projection therefore derives symbol identity from:

```text
visibility owner
+ binding
+ mathematical payload
+ shadow rank within that binding/visibility owner
```

The shadow rank depends on order only inside a resolution domain where shadowing can be
observed. It does not use physical filename or offset as identity. Independent scopes can move
without changing semantic `Q`; their provenance `P` changes.

This is a canonicalization strategy for the current migration oracle, not a proof that this is
the final representation of `visibility`.

## 7. Counterexample pressure on the minimal signature

`{DECLARE, REQUIRE}` plus the fixed node labels above is a hypothesis, not a theorem.

### Scope termination and retraction

A continuation such as

```text
From this point on we no longer assume compactness.
```

changes future visibility. The proposed signature survives only if the fixed `visibility`
algebra can represent the distinction without an open-ended relation vocabulary. Otherwise
scope change is a genuine missing primitive.

### Alternative and joint support

A plain prerequisite set does not distinguish

```text
either A or B suffices
```

from

```text
both A and B are required.
```

Current Thorn queries ask for dependencies of the argument actually presented, not minimal
alternative sufficient proof sets. Therefore this Boolean support distinction is not
currently in `Q`.

If Thorn later needs such a query, the graph may need intermediate support nodes or a richer
edge algebra. That would be a legitimate calculus counterexample, not permission to hide
`OR` in arbitrary metadata.

### Status changes

A later proof may change how an earlier claim is regarded. Prefer deriving status from support
structure where possible. Any irreducible status distinction must justify itself through `Q`.

### Binding without dependency consequence

A linguistic distinction that changes neither resolution, visibility, direct prerequisites,
nor capability under any continuation is outside canonical dependency semantics even when it
is meaningful English.

## 8. Existing mathematics to reuse

This proposal is not presented as a new foundational semantics from scratch.

### Contextual equivalence and full abstraction

This is the closest standard formulation. Program fragments are contextually equivalent when
no permitted context can distinguish their behaviour; a semantics is fully abstract when its
equality coincides with contextual observational equivalence.

For Thorn, the permitted contexts are valid future manuscript continuations and the
proof-dependency observations in `Q`.

### Dynamic semantics

Dynamic semantics treats discourse meaning as context-change potential. Thorn uses a narrower
abstraction: only context changes that can alter proof dependency survive.

### Nerode-style future distinguishability

Myhill-Nerode supplies the useful pattern that histories should be identified by what future
continuations can distinguish. Thorn does not inherit the finite-automaton conclusion; its
semantic state is generally infinite.

### Behavioural equivalence / coalgebra

Coalgebraic and transition-system semantics provide a general language for identifying states
by observable future behaviour if Thorn later formalizes continuation dynamics.

### Abstract interpretation

The dependency graph can be viewed as an abstraction of informal mathematical discourse that
intentionally forgets information while preserving the observations in `Q`.

### Lean elaboration

Lean separates rich source syntax from a smaller elaborated core and updates an environment
through elaboration. The useful lesson for Thorn is architectural: rich surface forms should
elaborate to a small core; surface vocabulary should not determine the core ontology.

### OMDoc / MMT

OMDoc/MMT provide useful precedent for collapsing mathematical document forms into
symbols/declarations plus structured objects and relations. Thorn's proposed quotient is
narrower: a distinction survives only when proof-dependency observations can see it.

## 9. Executable migration oracle

`thorn.dependency_observations` is intentionally a **bounded witness projection**, not a claim
that the Python models in this PR are the final fully abstract representation.

It projects current canonical state into:

```text
semantic.nodes
semantic.resolutions
semantic.requirements

provenance.nodes
provenance.resolutions
provenance.requirements
```

The semantic side deliberately excludes:

- `SymbolRole`;
- parser introduction/cue categories;
- `ScopeKind` labels as output semantics;
- raw source coordinates;
- review-context selection;
- review-trigger identifiers;
- transitive closure.

The projection keeps only current mathematical payload, normalized binding identity,
dependency-relevant visibility/precedence, resolution state, direct prerequisite relations,
and workspace capability.

The tests require that it:

- detects the #211 `x \star y` alias ablation at semantic `Q`;
- retains an unaffected formula-derived control and its provenance;
- records provenance for prerequisite relations themselves;
- treats pure source relocation as a `P` change, not a `Q` change;
- treats reordering independent scopes as semantically irrelevant;
- preserves project-order shadowing where order is observable;
- preserves repeated-occurrence disagreement as fail-closed unresolved resolution;
- agrees on the bounded semantic projection between the production Tree-sitter frontend and
  the regex compatibility frontend for the conformance witness.

A later replacement is compared through this boundary only for the observations it actually
projects. The formal `Q` above remains the specification; if the implementation witness is
missing a required query, the oracle must grow rather than redefining the semantics.

## 10. Consequence for natural-language analysis

The finite vocabulary must be the graph semantics, **not an English dictionary**.

Production code must not regain architectures such as

```text
if lemma in {define, mean, denote, call, ...}:
    emit DEFINITION
```

Dependency syntax alone is also insufficient: it can expose grammatical argument structure
without determining whether the sentence expresses a dependency-relevant state change.

Possible mature semantic substrates include local entailment/NLI, semantic-role labelling,
OpenIE, AMR, or combinations with the existing spaCy analysis. None is selected here.

The test is whether such a substrate can infer candidate `DECLARE`/`REQUIRE` effects and
ground their arguments without leaving Thorn to maintain a lexical predicate-to-effect
dictionary. External semantic analysis remains non-authoritative. Thorn still owns authority,
visibility/shadowing policy, ambiguity, graph identity, and provenance.

That empirical evaluation is intentionally split into issue #213.

## 11. A/B and ablation contract

Let:

```text
A = production after #211
B = future replacement elaborator
```

Parity is not private-IR equality.

A production replacement must satisfy:

- equivalence at the supported semantic observations in `Q`;
- faithful provenance/evidence correspondence through `P`;
- unchanged bounded review/source-rescue reachability as an acceptance projection;
- explicit classification of intentional fail-closed improvements;
- no provider/model API requirement for the normal path;
- deletion, not shadow retention, of superseded parser-like machinery after cutover.

Every differential must be classified as one of:

1. semantic regression;
2. unsafe authority gain;
3. dependency-observationally equivalent representation change;
4. provenance/evidence regression;
5. intentional fail-closed improvement;
6. calculus counterexample.

If a replacement exposes an implementation distinction that the old path happened to retain
but no query in `Q` can observe, that is **not** a parity failure.

If a source case changes a dependency observation but cannot be represented by the labelled
graph signature, that **is** a calculus counterexample and the signature must be revised before
cutover.

## 12. Scope of this tranche

This PR is complete when it establishes a reviewable semantic contract and executable bounded
migration witness. It intentionally does **not**:

- implement replacement relation inference;
- select a transformer/NLI/SRL/OpenIE/AMR dependency;
- remove `project_context.py`;
- add English cue vocabulary;
- claim the minimal signature is proven complete;
- perform provider/model API calls.

Follow-up #213 owns inference evaluation. A later implementation tranche can build path `B`,
compare it with `A` at `Q` and `P`, and ablate the current recognizer only after that evidence
gate passes.

## References

- Standard contextual-equivalence and full-abstraction literature in programming-language
  semantics.
- Jeroen Groenendijk and Martin Stokhof, *Dynamic Predicate Logic*, Linguistics and Philosophy
  14 (1991).
- John Myhill (1957) and Anil Nerode (1958), for the future-distinguishability pattern.
- J. J. M. M. Rutten, *Universal Coalgebra: A Theory of Systems*, Theoretical Computer Science
  249 (2000), 3–80.
- Patrick Cousot and Radhia Cousot, *Abstract Interpretation: A Unified Lattice Model for
  Static Analysis of Programs by Construction or Approximation of Fixpoints*, POPL 1977.
- Lean Language Reference, sections on elaboration, definitions, theorems, and environments.
- Michael Kohlhase, OMDoc work on mathematical knowledge representation.
- Florian Rabe and Michael Kohlhase, MMT language/documentation on declarations and theories.
