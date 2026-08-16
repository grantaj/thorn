# Higher proof structure

Issue #63 adds an explicit proof-control layer above Thorn's typed formulas, proof obligations, and symbol/scope resolution.

The goal is not to prove that a strategy is mathematically valid. The goal is to stop forcing downstream consumers to reconstruct common proof-control shape from narration such as "consider two cases", "argue by contradiction", or "use induction".

The layer is implemented in `src/thorn/higher_proof_structure.py` and consumes `SymbolResolutionIR` from issue #62.

## Layering

The existing lower layers remain authoritative:

1. source-preserving Math IR owns manuscript truth and provenance;
2. graph-derived canonical Proof IR owns retained proof topology and prose pruning;
3. typed formula IR owns mathematical expression structure and explicit opacity;
4. proof-obligation IR owns propositions, local contexts, obligations, and candidate proof-step rules;
5. symbol-resolution IR owns symbol identity, binder scope, alpha-equivalence, instantiation, substitution, and witnesses;
6. higher proof structure adds control-flow shape only.

This tranche does not redesign the formula parser, canonical graph, result-application semantics, or the eventual LLM-facing proof language.

## Assertion and support are different facts

Every `ProofControlStructure` has two independent certainty fields:

- `assertion_status`: how strongly the source says that this strategy is being used;
- `support_status`: how strongly Thorn's existing typed structure supports the recovered control-flow shape.

For example, the sentence "Without loss of generality, assume x <= y" can establish that the author asserts a WLOG reduction. It does not establish that the reduction is valid. Thorn therefore records the WLOG structure and source handle while leaving its support unresolved unless stronger semantic evidence exists.

Likewise, exact structural evidence can expose a case split even if the prose never literally says "proof by cases". In that situation the support can be confident while the assertion remains unresolved.

Neither status is a mathematical-validity judgement.

## Explicit branches

`ProofBranch` records:

- its parent control structure;
- branch kind and optional label;
- proposition addresses participating in the branch;
- local assumptions represented by proposition addresses or canonical AST references;
- branch conclusion address / AST reference;
- assumptions discharged by the branch;
- witness/evidence references where relevant;
- source addresses; and
- structural recovery status.

AST references use issue #62 `ExpressionRef` objects. They never duplicate or reparse mathematical strings.

## Case splits

A case split can be mechanically supported when Thorn sees an exact structure such as:

- a disjunction `P ∨ Q`;
- one implication branch `P => R`;
- one implication branch `Q => R`; and
- a common branch conclusion `R`.

Each implication antecedent becomes an explicit discharged case assumption.

A source cue such as "split into cases" or a `Case ...` label can assert the strategy, but lexical evidence alone never makes the split mechanically supported. If the exhaustive branch shape cannot be recovered, the strategy remains source-addressed and unresolved.

## Contradiction

A contradiction structure is mechanically supported only by a bounded exact pattern:

- an existing issue #61 contradiction step;
- a target proposition `Q`;
- an explicit `not Q` proposition available in the retained proof state; and
- an explicit contradiction proposition such as `False` / bottom.

The negated target is recorded as a local assumption discharged by the contradiction branch.

A phrase such as "by contradiction" without this structural pattern records an asserted but unresolved contradiction strategy.

## Contraposition

For a goal `P => Q`, Thorn can recognize an exact transformed goal `not Q => not P` and expose it as a dedicated branch.

The support status remains ambiguous in this tranche. Thorn does not infer the ambient logical system or silently assume a classical equivalence where that matters. The source assertion and the structural transform therefore remain visible without overclaiming proof validity.

## Induction

For a universal goal `forall n, P(n)`, the initial induction recognizer can recover the bounded natural-number skeleton:

- base proposition `P(0)`;
- step proposition `forall k, P(k) => P(k + 1)` (or the corresponding unquantified step shape);
- induction parameter reference;
- base branch;
- inductive-step branch; and
- induction-hypothesis AST reference, marked as discharged by the step implication.

Nested binder shadowing is respected while constructing expected base/step expressions.

An induction cue without both exact base and step structure remains asserted but unresolved and retains its opaque source handle.

This is deliberately not a general induction theorem prover. Strong induction, structural induction over arbitrary datatypes, transfinite induction, and custom successor relations remain later extensions.

## WLOG / symmetry

Explicit `without loss of generality`, `WLOG`, and `by symmetry` cues create WLOG control structures.

They are not considered mechanically valid merely from the wording. If an existing named-property step is attached to the same source, the support may become ambiguous rather than unresolved, but issue #64 owns richer definition/rewrite/result/property application semantics.

The exact source remains available because the semantic reduction is not yet fully lowered.

## Local subproofs

A source-addressed implication written as an explicit local assumption block (for example, "Assume P. Therefore Q.") can be exposed as a local subproof branch with:

- assumption ref `P`;
- conclusion ref `Q`; and
- explicit discharge of the assumption by the implication.

Because the lower graph is still fundamentally flat, this tranche marks the recovered nested derivation as ambiguous rather than inventing an internal derivation that the source IR does not contain.

The branch structure is therefore useful to consumers while remaining loss-aware.

## Existential witness branches

Issue #62 already recovers exact witness operations when an existential conclusion is supported by a unique instantiated premise.

Issue #63 projects each such operation into an explicit witness branch with:

- existential conclusion;
- witness AST reference;
- evidence AST reference;
- operation address; and
- source provenance.

This does not redo witness matching; the issue #62 operation remains authoritative.

## Source addressability and opacity

Every recovered branch/control structure points back to canonical proof source addresses.

When Thorn recognizes a strategy but cannot lower its detailed semantics, `opaque_source_addresses` records the exact source that downstream consumers may need to inspect. Higher proof structure never replaces or mutates the lower source-preserving IR.

## Conservative non-goals

This tranche does not:

- validate arbitrary case exhaustiveness from prose;
- infer WLOG symmetry or quotient arguments;
- prove contradiction steps mathematically;
- assume a particular ambient logic for contraposition;
- reconstruct arbitrary nested proof blocks from indentation or typography alone;
- perform definition unfolding or general rewriting (#64);
- design the stable compact LLM proof language (#65); or
- invoke any provider/model.

## Regression contract

`tests/test_higher_proof_structure.py` checks:

- exact case branches and discharged case assumptions;
- lexical case cues failing closed;
- structural case recovery without pretending the strategy was explicitly asserted;
- contradiction assumption/discharge shape;
- contradiction wording alone remaining unresolved;
- contraposition remaining semantically ambiguous;
- induction base/step/IH recovery;
- incomplete induction remaining opaque and unresolved;
- WLOG cue conservatism;
- explicit local-subproof assumption discharge;
- witness-branch projection from issue #62;
- lower-IR immutability; and
- ordinary non-strategy prose creating no control structure.

All validation is intended to run with `OPENAI_API_KEY=""`.
