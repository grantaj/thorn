# Graph-derived canonical proof IR

Issue #57 changes the model-facing IR objective from **compressed proof prose** to a
**canonical mathematical proof language**.

The source-addressable `ProofSkeleton` remains a useful baseline, but it projects every
extracted proof claim and represents prose it does not inline as `~`. The canonical
proof IR instead asks the support/dependency graph which material belongs to the proof
before deciding how to serialize it.

## North star

```text
LaTeX manuscript
    -> rich Thorn Math IR
    -> result/dependency/support graph
    -> conservative backward proof slice
    -> canonical mathematical normalization
    -> canonical proof IR
```

The initial packet should contain only:

1. mathematical structure;
2. compact identifiers/references;
3. mathematical fragments whose support role is unresolved; or
4. irreducible prose that survives the recovered proof slice and cannot safely be
   converted to mathematical structure.

Prose is an escape hatch, not the representation.

## Three-way treatment of proof prose

The first implementation distinguishes three cases.

### 1. Disconnected pure prose

Pure prose outside the recovered core proof slice is deleted from the initial IR.
Its existence does not perturb canonical node numbering or graph structure.

A metamorphic test inserts an expository sentence before an otherwise identical proof
and requires byte-identical `render_initial()` output.

### 2. Math embedded in non-slice narration

If a claim is outside the recovered core slice but contains mathematical material,
Thorn does not call the narration load-bearing and does not discard the mathematics.
It emits only the normalized mathematical fragments as an unresolved-math node:

```text
U1:Z
```

The original sentence and provenance remain source-addressable locally.

For example, narration such as

```text
For orientation only, record the auxiliary quantity $Z$.
```

contributes `Z`, not the words `For orientation only ...`.

### 3. Irreducible load-bearing prose

If prose lies inside the recovered core proof slice and Thorn cannot safely normalize
it to mathematical structure, it is retained explicitly as an opaque proof node:

```text
P1:The limit clearly has full rank.
```

This is intentional. Replacing it by `~` would recreate the semantic bottleneck the
canonical IR is meant to avoid. The exact source and provenance are also retained in
the Thorn-side source map.

## What establishes the core proof slice

A generic NLP adjacency hypothesis is **not sufficient** to make arbitrary prose
load-bearing. In particular, an ambiguous, implicit `PRIOR_CLAIM` edge inferred only
from neighbouring sentences does not carry backward proof reachability.

The slice does retain structure supported by stronger evidence, including explicit or
confident support and typed mathematical relations such as result/equation references,
definitions, named properties and explicit reasons. Uncertainty on a retained relation
is preserved with `?` / `!`; typed ambiguity is not silently upgraded to confidence.

Mathematical material outside that core is preserved as `U<n>` rather than by keeping
its surrounding prose.

This distinction is important: the local linguistic frontend may suggest that adjacent
sentences *could* be related, but that alone should not cause an expository paragraph
to become part of the model-facing proof.

## Canonical vocabulary

The first tranche deliberately normalizes only mechanically safe constructions.

Exact TeX operator spellings map to mathematical symbols, including:

```text
\forall          -> ∀
\exists          -> ∃
\Rightarrow      -> ⇒
\Leftrightarrow  -> ⇔
\wedge / \land   -> ∧
\vee / \lor      -> ∨
\neg / \lnot     -> ¬
\in              -> ∈
\notin           -> ∉
\ne / \neq       -> ≠
\le / \leq       -> ≤
\ge / \geq       -> ≥
\subset          -> ⊂
\subseteq        -> ⊆
```

A small set of fully matched English mathematical templates is also canonicalized:

```text
for all / for every / for each -> ∀
there exists                    -> ∃
if ... then ...                 -> ⇒
iff / if and only if            -> ⇔
and / or / not                  -> ∧ / ∨ / ¬
is in / belongs to              -> ∈
equals / is not equal to        -> = / ≠
```

The matcher must consume the complete phrase. Partial matches fall back to prose rather
than guessing semantics.

Typed support vocabulary is represented by graph structure rather than narration.
For example, `therefore Q` and `hence Q` normalize to the same claim plus support edge,
and `By Lemma 3, Q` becomes a result-reference edge. The edge retains its original
confidence/ambiguity state.

## Source recovery

Every retained canonical node and edge has a local source address containing the exact
original text and provenance. Source-only markup such as `\label{...}` is excluded
from the model-facing atom but preserved in this source payload.

The canonical IR therefore permits aggressive removal of narration without pretending
that omitted source has ceased to exist.

## Keyless evidence

All measurements below use the normal local spaCy frontend with `OPENAI_API_KEY=""`.
No provider is constructed and no model/API call is made.

### Public 56-case corpus

On the current tranche:

| Representation | Characters | Raw / representation |
|---|---:|---:|
| raw theorem packets | 40,382 | 1.00x |
| source-addressable skeleton | 5,658 | 7.14x |
| canonical proof IR | 11,775 | 3.43x |

The canonical representation prunes 9 public claim nodes while preserving 144 opaque
nodes of all kinds (including result/dependency statements as well as proof prose).

The canonical packet being larger than the old skeleton is **not** presented as a
compression win. The old skeleton can replace arbitrary prose with `~`; the canonical
IR instead restores prose when the recovered proof says it is load-bearing. This
tranche is about establishing the stronger representation before serializing it more
aggressively.

### Anonymous exact-version real-paper corpus

The existing private harness measured the same 3 exact-version papers / 37 proved
results used by the earlier skeleton experiment and emitted aggregate counts only:

| Representation | Characters | Raw / representation |
|---|---:|---:|
| raw theorem packets | 225,884 | 1.00x |
| source-addressable skeleton | 40,099 | 5.63x |
| canonical proof IR | 46,204 | 4.89x |

The graph transformation is more informative than the byte total:

- **154 claims pruned** from the initial proof representation;
- **94 irreducible proof-prose nodes** remain inline, totalling 7,734 characters;
- **198 unresolved-math nodes** retain mathematical fragments without their narration,
  totalling 7,273 characters;
- 158 retained canonical support edges;
- 552 source-addressable canonical nodes/edges in total.

An earlier deliberately over-conservative slice retained 210 opaque proof-prose nodes.
Excluding generic ambiguous adjacency from proof reachability reduced that to 94 while
preserving math from non-slice claims as `U<n>` nodes.

These numbers show that the dependency graph is now doing semantic reduction rather
than merely annotating every sentence. They also show where the remaining work lies:
result/dependency statements and genuinely retained proof prose still need stronger
safe mathematical normalization.

## Strong invariants

Tests in `tests/test_canonical_proof_ir.py` require that:

1. inserting disconnected exposition leaves canonical proof IR unchanged;
2. non-slice narration containing math loses the narration but retains its math as
   source-addressed unresolved math;
3. `for all` and `for every` normalize identically;
4. `therefore` and `hence` induce the same canonical proof structure;
5. a typed lemma reference becomes a dependency edge, not repeated prose;
6. ambiguous load-bearing prose remains in the slice with its uncertainty and exact
   source recovery;
7. canonicalization does not mutate canonical Math IR / `SemanticReviewItem`.

## Next work

Do **not** return to generic substring compression yet.

The next leverage is to make the mathematical IR itself more complete:

- normalize theorem/result statements more structurally;
- recover quantifier/binder structure beyond the first safe templates;
- connect hypotheses, local constraints and definitions to claims precisely enough to
  slice unused context rather than including it conservatively;
- canonicalize common mathematical predicates and named properties;
- make terminal proof obligations explicit in the support graph rather than relying on
  proof-order fallbacks.

Once the canonical proof language is stable, the exact reversible coding from issue
#52 / PR #56 can be applied to this stronger representation. Compression then becomes
a serializer concern rather than a reason to throw away proof semantics.
