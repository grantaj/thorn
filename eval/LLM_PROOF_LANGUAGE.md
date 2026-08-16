# Stable LLM-facing proof language

Issue #65 defines the deterministic delaboration of Thorn's canonical proof IR for an LLM semantic-review consumer.

This layer is deliberately **not** canonical proof semantics. The canonical stack remains:

```text
LaTeX
 -> source-preserving Math IR
 -> canonical typed Proof IR
 -> proof obligations
 -> symbol/type/scope resolution
 -> higher proof structure
 -> semantic transformations
```

The issue-65 layer consumes that structure and emits a compact, deterministic proof language. Parser traces, source coordinates, Pydantic shape, confidence bookkeeping, and other compiler internals stay out of the initial model packet.

## Frozen format

The selected initial format is `thorn-proof/1` and begins:

```text
THORN-PROOF 1
```

The compact syntax uses the existing short canonical proposition addresses (`T0`, `H1`, `R1`, `D1`, `C1`, ...). Mathematical expressions are rendered from the canonical typed AST with `render_math_expr`; they are not reconstructed from prose.

A typical result application looks like:

```text
R1 ∀x∈R.(P(x)⇒Q(x))
H1 P(a)
C1 Q(a) <- R1[x:=a],H1
DEP R1 thm:current>thm:lemma
```

The result reference, parameter mapping, input precondition, target proposition, and dependency path therefore remain explicit while implementation objects such as `SemanticTransformation` do not appear in the model language.

## Uncertainty and holes

The compact status markers are:

- no marker: structurally confident recovery;
- `~`: ambiguous recovery;
- `?`: unresolved recovery.

These markers describe Thorn's recovered structure. They do **not** certify mathematical validity.

Unresolved proof obligations are rendered explicitly:

```text
HOLE G2 C1: Q(a) | ctx R1,H1 | open @C1
```

A missing theorem-application precondition is also explicit rather than silently disappearing:

```text
C1 Q(a) <- R1[x:=a],?O1:P(a) ? @E1
NEED O1: P(a) | ctx R1,H1 @E1
```

`@C1` and `@E1` are source handles. They are included only where exact source may be needed to interpret unresolved or opaque content.

## Transformations

The projection renders the semantic operations established in issue #64 rather than generic prose-supported edges.

### Result application and specialization

```text
C1 Q(a) <- R1[x:=a],H1
```

Leading universal parameter mappings are written inside `[...]`. Discharged preconditions appear as the proposition addresses that satisfy them. Missing preconditions appear as `?O<n>:<formula>` and receive a separate `NEED` line.

### Equality rewriting

```text
C2 Q(b) <- C1,rewrite(H2:a→b)
```

The equality support proposition is distinct from the rewrite operation, and direction comes from the exact canonical AST references recovered in issue #62/#64.

### Definition use and unfolding

```text
C3 R(a) <- C2,unfold(D1)
```

`unfold` is emitted only for the mechanically justified definition-unfolding operation from issue #64. A mere prose cue such as `by definition` remains unresolved.

### Named properties

Named properties remain typed support without invented general property semantics, for example conceptually:

```text
C4 S(a) <- C3,property("by continuity") ? @E4
```

The unresolved marker is intentional when Thorn knows the referenced property but cannot mechanically validate the property-specific inference.

## Higher proof structure

Issue-63 control structure is retained with short local `F<n>` identifiers:

```text
FLOW F1 CASES -> C3 from H1 {case[H2]=>C1;case[H3]=>C2}
FLOW F2 INDUCTION -> T0 {base_case=>C4;inductive_step[C4]=>C5}
```

Nested structures can name a `parent=F<n>`. Subject, transformed-goal, and witness expressions are included when the canonical structure provides them.

The word `inferred` means the structural shape was recovered without a confident explicit manuscript assertion of the strategy. It is distinct from whether the recovered shape itself is structurally supported.

## Proof states

The model-facing packet includes the terminal goal and unresolved intermediate proof obligations. Discharged intermediate obligations are omitted because their supporting derivations are already visible on proposition lines.

```text
GOAL G0 T0: R(a) | ctx H1,C3 | open @T0
```

`structural` on a terminal goal means Thorn recovered a structural discharge candidate. It must not be read as a proof-validity certificate.

## Source-on-demand contract

The initial packet contains no source map or raw prose payload. Thorn retains a non-rendered `ProofLanguageSourceHandle` table keyed by the same canonical source addresses.

A reviewer may make **one** bounded rescue request:

```text
NEED_SOURCE P7,D3
```

The default maximum is eight unique addresses in that one request. Duplicate addresses are deduplicated while preserving request order. Unknown addresses, malformed commands, or a second rescue round are rejected.

The request is bound to the SHA-256 fingerprint of the exact `thorn-proof/1` initial packet. A request cannot be replayed against a different packet accidentally.

The response returns only the requested exact source, delimited by stable handles:

```text
THORN-SOURCE 1 <fingerprint>
SOURCE @P7
<exact source text>
END_SOURCE @P7
SOURCE @D3
<exact source text>
END_SOURCE @D3
```

If the handle refers to an imported result and Thorn has its result identity, the response may also include a `RESULT_ID` line before the exact source text.

All source/fallback characters must be counted in any later live token/cost evaluation. The rescue channel is not a free side channel.

## Determinism and replay

`LLMProofLanguage.fingerprint()` hashes the format version plus the exact initial rendering. The compact projection is deterministic over a fixed `SemanticTransformationIR`; source-map payloads do not affect the transmitted initial text.

The full Thorn-side packet can also be serialized canonically for fixtures/replay, but that JSON is not the LLM-facing language.

## Keyless candidate comparison

`ProofLanguageStyle` retains two deterministic renderings over the **same semantic IR**:

- `compact`: the frozen `thorn-proof/1` language;
- `explicit`: a more verbose keyword-heavy candidate used only as a keyless comparison baseline.

`scripts/measure_llm_proof_language.py` runs both over the full public corpus and reports:

- raw semantic-review characters;
- the earlier compact semantic-review characters;
- issue-65 compact proof-language characters;
- explicit-candidate characters;
- aggregate and median compression ratios;
- semantic inventory counts shared by both candidates;
- source-handle count; and
- `provider_requests: 0`.

The compact candidate is selected because both renderings are generated from exactly the same canonical semantic objects while the compact syntax removes repeated field labels and implementation vocabulary. This is a representation choice, not semantic compression.

## Relationship to proof-skeleton compression

Issues #49/#52 are a separate serialization/compression track. The proof skeleton and reversible dictionary codec test how small a representation can become while retaining source recoverability.

Issue #65 instead defines the stable semantic **machine interface** after the #60-#64 proof semantics exist. Reversible dictionaries, interning, batching, caching, or other transport optimizations may be applied later, but they must decode back to the same frozen proof-language packet and must not change its meaning.

## Non-goals

This tranche does not:

- change canonical Proof IR;
- make an LLM or provider part of elaboration;
- perform live/provider evaluation;
- infer mathematics from the compact text;
- expose raw AST JSON as the model interface;
- make named-property applications magically valid;
- allow unbounded source rescue;
- hide rescue/fallback token cost; or
- couple Thorn to Lean syntax or dependent type theory.
