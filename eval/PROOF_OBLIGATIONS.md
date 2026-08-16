# Explicit proof obligations and typed proof steps

Issue #61 adds a proof-state view above Thorn's canonical typed Proof IR.

The layer is deliberately conservative. It does not replace the source-preserving Math
IR, change the graph slice introduced by #57, or broaden the formula elaboration from
#60. It takes those two products as input and makes the proof-state questions explicit:

- what proposition is currently available;
- what role that proposition plays;
- what proposition is being derived;
- what local context was available at that point;
- what structural support the manuscript presents;
- what proof rule Thorn can name without guessing; and
- which obligations remain unresolved.

## Proposition roles

`ProofProposition` classifies canonical nodes as:

- `assumption` for hypotheses and local constraints;
- `goal` for the theorem conclusion;
- `derived` for understood proof claims;
- `imported_result` for referenced theorem/result dependencies;
- `definition` for definition dependencies; and
- `unresolved` for unresolved mathematical material or load-bearing opaque prose.

Every proposition retains a canonical source address. The exact source text and Thorn
span remain in the existing `CanonicalProofSource` side table.

## Obligations

A `ProofObligation` records:

- the proposition that is expected;
- its typed `MathExpr` when #60 could lower it;
- the lowering status (`full`, `partial`, or `opaque`);
- the local context available before that proof point;
- the smaller support context named by candidate proof steps;
- candidate discharging step addresses;
- source provenance; and
- whether it is the terminal theorem obligation.

`discharged` has a narrow structural meaning: Thorn recovered a confident structural
derivation candidate for sufficiently understood mathematical content. It is **not** a
claim that the inference is mathematically valid. Mathematical validation remains a
semantic-review responsibility.

Opaque content, unresolved mathematical nodes, ambiguous-only support, and missing
terminal justification remain `unresolved` even if surrounding prose sounds confident.

## Terminal theorem goal

The theorem conclusion is always represented by the terminal obligation `G0`.

The last proof proposition is connected to `G0` so downstream consumers never need to
infer how the narrated proof is supposed to terminate. When the final proposition's
typed expression is exactly equal to the theorem goal expression, Thorn records a
confident `exact` terminal step. Otherwise the terminal connection is retained with
`rule=unknown`, `status=unresolved`.

This is intentionally stricter than guessing that the final sentence proves the theorem.

## Proof-step rules

`ProofStepEdge` uses a small rule vocabulary:

- `unknown`;
- `exact`;
- `apply_result`;
- `implication_elimination`;
- `definition_use`;
- `rewrite_substitution`;
- `instantiate`;
- `witness_introduction`;
- `contradiction`; and
- `named_property_application`.

`unknown` is a normal first-class value, not an error.

A rule name is attached only when justified by one of three bounded evidence sources:

1. an already-typed canonical support-edge kind, such as a result reference or
   definition use;
2. exact #60 AST structure, currently including implication elimination when the
   antecedent is exactly present in local context and the target is exactly the
   consequent; or
3. narrow explicit wording in the existing support source, such as `rewrite`,
   `instantiate`, `witness`, or `contradiction`.

Equation references are not automatically called rewrites, prior-claim edges are not
automatically called implication elimination, and generic explicit reasons do not get a
rule name merely because they are confident.

## Local context

Global theorem context consists of hypotheses, local constraints, definitions, and
imported results. Each derived/unresolved proof proposition then sees that global context
plus preceding proof propositions in source-derived canonical order.

The terminal theorem obligation sees the global context plus all retained proof
propositions. Irrelevant prose pruned by #57 is not reintroduced to recreate sentence
order.

## Boundary with later work

This tranche does not perform symbol/type/scope resolution (#62), proof search, semantic
verification, LLM review, or LLM-facing delaboration (#65). It establishes the machine
interface those later stages can consume: explicit goals, local context, candidate proof
steps, rule certainty, and unresolved obligations.

All tests for this tranche are keyless and provider-free.
