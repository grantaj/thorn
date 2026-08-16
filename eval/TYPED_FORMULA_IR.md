# Typed formula IR

Issue #60 adds the first typed-expression layer to Thorn's graph-derived canonical Proof IR.
This is a semantic-elaboration tranche, not a compression format and not an LLM prompt
language.

The intended layering is:

```text
LaTeX source
    -> source-preserving Thorn IR
    -> dependency/support analysis
    -> graph-derived canonical proof slice
    -> bounded typed-expression elaboration
    -> later proof obligations / typed proof edges (#61)
    -> later compact LLM-facing delaboration (#65)
```

The graph slice introduced by issue #57 remains authoritative for proof topology and prose
pruning. `build_canonical_typed_proof_ir` enriches that slice with mathematical expression
structure without changing node/edge selection. The legacy `atom` field and
`render_initial()` output remain available as compatibility/debug views; the expression tree
is the semantic payload when it is present.

## Expression core

`thorn.formula_ir` deliberately implements a small core rather than a speculative algebra
system. It currently distinguishes:

- identifiers and numeric literals;
- function application;
- generic unary/binary operator application for the bounded arithmetic syntax understood by
  the parser;
- equality, inequality, membership/non-membership, and subset relations;
- negation, conjunction, disjunction, implication, and iff;
- universal and existential quantification with structural binders and optional domains;
- tuples and simple finite set forms;
- `OpaqueExpr` for material Thorn cannot safely lower.

Expression models are frozen Pydantic value objects and form a discriminated, traversable
AST. `render_math_expr` is a deterministic diagnostic pretty-printer. It is intentionally not
an attempt to define the compact proof language reserved for issue #65.

## Partial elaboration

Partiality is represented explicitly. A statement such as

```text
for all x in R, <unsupported predicate>
```

can lower to a universal quantifier with a typed/domain-qualified binder and an opaque body.
The lowering result records `full`, `partial`, or `opaque` status. Thorn does not force a
complete parse simply to make a payload look formal.

Conservative boundaries are intentional. For example, chained comparisons such as
`x < y < z` remain opaque in this tranche instead of being guessed as nested binary
relations. Rich TeX constructs, set-builder syntax, multiple binders, subscripts/indexing,
sums/products/integrals, and broad mathematical English outside the small safe phrase set
also remain candidates for opaque fallback. Symbol/type/scope resolution is deliberately
left to issue #62.

## Canonical equivalence

The lowerer normalizes only surface equivalences it can account for mechanically. Tests cover
safe equivalences including:

- `for all`, `for every`, and `∀` binders;
- `if ... then`, `implies`, and `⇒`;
- English/symbolic forms of equality and inequality;
- membership/non-membership and subset relations;
- conjunction, disjunction, negation, and iff;
- supported LaTeX spellings such as `\\leq`, `\\neq`, `\\notin`, and `\\subseteq`.

The English phrase matcher requires the relevant top-level expression to match its bounded
shape. Unaccounted-for syntax is not silently discarded.

## Source correspondence

Exact source remains in the existing `CanonicalProofSource` side table. The typed layer adds
`ExpressionProvenance` records keyed by proof address plus a structural AST path. This keeps
parser/debug metadata out of the core expression nodes while allowing an expression or
subexpression to recover its source-addressed raw text and Thorn source span.

The source-preserving IR is not mutated or replaced. Normalization used for elaboration is a
one-way semantic view; exact raw source remains available separately.

## Keyless public-corpus measurement

Run:

```bash
OPENAI_API_KEY="" python scripts/measure_typed_formula_ir.py
```

The script structurally extracts every public synthetic evaluation case, builds the existing
result-level graph slice, adds typed expressions, and emits aggregate counts only. It reports
full/partial/opaque lowering status, node-kind coverage, AST node-category occurrence, prose
pruning, and unresolved-math counts. It does not construct a semantic provider, make a model
request, or print source excerpts.

This metric is about how much mathematical payload is available structurally to downstream
consumers. Character-count or token-count compression is intentionally not a success metric
for this tranche.
