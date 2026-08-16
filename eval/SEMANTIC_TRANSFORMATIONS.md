# Semantic transformation IR

Issue #64 adds the semantic-operation layer above Thorn's existing typed Proof IR.

The lower layers remain authoritative:

```text
source-preserving Math IR
  -> graph-derived canonical Proof IR (#57)
  -> typed expressions (#60)
  -> explicit obligations / proof-step edges (#61)
  -> symbol, scope, instantiation, substitution, witness resolution (#62)
  -> higher proof-control structure (#63)
  -> semantic transformations (#64)
```

This layer does not replace or rewrite those objects. It records what a proof step references and, separately, what transformation Thorn can mechanically recover from the typed structure.

## Reference is not application

A central #64 invariant is:

> Confidently identifying a referenced theorem, definition, equation, or property does not imply that the transformation performed with it is valid or even mechanically understood.

`SemanticSupportAtom` therefore represents the referenced support independently of `SemanticTransformation`.

A result reference can be confident while its application remains unresolved. This is important for common prose such as:

```text
By Lemma 4, the claim follows.
```

If Thorn cannot match Lemma 4's proposition to the target claim, the support atom still records the exact lemma reference and provenance, but the result application is unresolved.

The same rule applies to definitions, equality rewrites and named properties.

## Result application and specialization

For an imported result Thorn attempts a deliberately bounded typed reconstruction.

Leading universal quantifiers are treated as explicit parameters. Thorn matches the result body against the target AST and records each recoverable mapping as a `SemanticParameterBinding` using canonical `ExpressionRef` objects.

For example, from

```text
R1  forall x. P(x) => Q(x)
H1  P(a)
C1  Q(a)
```

an exact application can expose:

```text
support: R1
binding: x := C1.arguments[0]
precondition: P(a), satisfied by H1
target: C1
```

The mapping is structural; it is not stored as a rewritten source string.

A direct specialization such as

```text
forall x. Q(x)
    -> Q(a)
```

is represented separately as `RESULT_SPECIALIZATION`.

A non-quantified implication application such as

```text
P => Q
P
----
Q
```

uses the same application machinery without a parameter binding.

## Explicit application obligations

If a result conclusion matches the target but an implication antecedent is not available in the target's local proof context, Thorn creates a `SemanticApplicationObligation`.

This is the issue-64 form of a missing precondition. It records:

- the transformation that needs the precondition;
- the source theorem AST location from which the precondition came;
- the instantiated expected expression;
- the local proof context searched;
- any propositions that satisfy it; and
- discharged versus unresolved status.

The precondition is never silently discarded.

For

```text
R1  forall x. P(x) => Q(x)
C1  Q(a)
```

Thorn may recover `x := a`, but the application remains unresolved with an explicit expected `P(a)` obligation if no suitable premise is present.

## Equality rewriting

Issue #62 already records exact AST-level substitutions when it can identify:

- an equality;
- an input expression;
- the rewrite direction;
- the output expression; and
- exact replacement sites.

Issue #64 lifts those objects into explicit `EQUALITY_REWRITE` transformations and separates the equality itself into an `EQUALITY` support atom.

If the manuscript says `rewrite` but #62 cannot recover an exact equality-directed transformation, #64 keeps an unresolved rewrite transformation. The prose cue does not certify the rewrite.

## Definition use and unfolding

Definitions are represented as typed `DEFINITION` support atoms.

A definition use becomes `DEFINITION_UNFOLD` only when all of the following are mechanically recoverable:

1. the referenced definition is an exact equality;
2. an expression in the target's local context can serve as the input;
3. replacing one side of the definition equality with the other produces the target exactly; and
4. there is a unique recovered input/direction.

The transformation stores the input expression ref, definition-side refs and exact target replacement sites.

If those conditions are not met, Thorn records only `DEFINITION_USE` with unresolved or ambiguous transformation status. It does not guess an unfolding because the source says `by definition`.

This initial tranche intentionally does not attempt recursive normalization, beta reduction, arbitrary definitional equality or theorem-prover-style reduction.

## Named properties

An explicitly recognized property edge becomes a typed `NAMED_PROPERTY` support atom. Examples include source references to continuity, compactness or monotonicity.

The support atom records the property reference and exact source addresses, but the transformation remains unresolved unless a later semantic layer provides enough formal property semantics to justify it.

This is deliberate: the phrase `by continuity` is useful structured support information, but it is not by itself a mechanically checked inference rule.

## Dependency identity

Imported result support atoms preserve `referenced_result_identifier` from the canonical source tables.

They also carry a deterministic `dependency_path`. Without a project `DependencyGraph`, a direct application records the direct current-result to referenced-result pair. When a dependency graph is supplied, Thorn can recover a graph path while preserving the exact referenced result identity.

This means downstream consumers can distinguish the local transformation from the cross-result dependency that supplied it.

## Source provenance

Every transformation uses canonical AST references for mathematical source/target objects:

- support expression refs;
- target refs;
- parameter and argument refs;
- rewrite direction refs;
- replacement-site refs; and
- application-obligation template refs.

`source_addresses` retain exact Thorn source handles. Unresolved or ambiguous transformations additionally retain `opaque_source_addresses` so a later model-facing layer can request bounded source text instead of receiving broad manuscript context.

## Partiality and safety

The layer deliberately fails closed.

It does not:

- call an LLM or provider;
- infer theorem applications from prose alone;
- infer an equality rewrite merely because an equation is cited;
- claim a named property establishes an arbitrary target;
- perform nested-binder pattern matching when identity would be uncertain;
- silently discharge missing theorem preconditions;
- mutate the #60-#63 IR objects; or
- define the eventual compact LLM-facing language from #65.

`InferenceStatus.CONFIDENT` means that the transformation shape was recovered from exact structural evidence. It remains distinct from a proof-kernel judgement of mathematical validity.

## Initial bounded recognizers

The issue-64 tranche supports:

- exact direct use of an imported proposition;
- specialization of leading universal binders;
- one implication layer with an explicit precondition obligation;
- exact equality rewriting via the established #62 substitution operation;
- exact equality-style definition unfolding from local context;
- typed named-property support atoms with unresolved transformation semantics; and
- exact referenced-result identity / dependency paths.

More general rewriting, multi-stage theorem application, property-specific semantics and normalization should be added only when their evidence rules can remain equally explicit.

## Keyless contract

The regression suite is intentionally synthetic and public. It covers:

- universal theorem instantiation plus modus-ponens-style application;
- missing preconditions becoming unresolved obligations;
- direct universal specialization;
- mismatched theorem references failing closed;
- exact and unresolved rewrite cases;
- exact and unresolved definition use;
- named-property reference versus transformation certainty; and
- lower-layer immutability.

No provider/model call is needed for these contracts. `OPENAI_API_KEY` remains empty in CI.

## Boundary with issue #65

Issue #64 completes another canonical semantic layer. It should not decide how these objects are serialized for a model.

Issue #65 can project support atoms, bindings, preconditions and transformations into a compact proof language such as conceptually:

```text
R4 forall x. P(x)=>Q(x)
H1 P(a)
C2 Q(a) <- R4[x:=a], H1
```

The compact notation is a delaboration of the typed #64 structures, not their canonical representation.
