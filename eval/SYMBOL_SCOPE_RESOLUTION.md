# Symbol, scope, substitution and witness IR

Issue #62 adds a conservative identity-resolution layer above the typed formula and proof-obligation IR.

The pipeline remains:

```text
source-preserving Math IR
  -> graph-derived canonical Proof IR (#57)
  -> typed formula AST (#60)
  -> explicit proof obligations / typed proof-step candidates (#61)
  -> symbol and scope resolution (#62)
```

This layer does not change graph slicing, parse mathematical prose again, or turn Thorn into a proof kernel. It records which identities and proof operations Thorn can recover mechanically and leaves the rest explicit.

## Identity is not spelling

`IdentifierExpr(name="x")` is a syntactic AST node, not a global symbol identity. The same spelling can denote:

- a quantified binder;
- a shadowing inner binder;
- a source-level declaration;
- one of several same-named source declarations; or
- an unresolved symbol.

`SymbolResolutionIR` therefore keeps identity in side tables keyed by `ExpressionRef(owner_address, path)`. Core formula nodes remain immutable/value-like.

A lexical binder is exact because its scope is represented directly by the typed AST. Nested quantifiers create nested `ResolvedScope` and `SymbolDeclaration` entries, and occurrences resolve to the nearest matching binder declaration.

Source-level resolution is intentionally stricter. A same-spelling declaration is never enough to claim identity. If Thorn's source `SymbolTable` is supplied, an overlapping `SymbolUse` with an existing resolved symbol identifier can establish the identity. Without that source-use evidence, matching declarations remain ambiguity candidates even when only one same-spelling declaration happens to be present in the bounded review slice.

## Scope information

The layer records three scope origins:

- result root;
- source scopes recovered from Thorn's existing symbol table;
- lexical binder scopes recovered from typed expressions.

When the full source `SymbolTable` is available, source scope parentage and scope kinds are retained. When only the bounded semantic request is available, source scope IDs are retained but parentage remains unresolved rather than guessed.

## Types and domains

Recoverable source-symbol metadata is retained on declarations:

- role;
- arity;
- domain LaTeX;
- codomain LaTeX.

For quantified binders, a domain is represented by an `ExpressionRef` to the canonical AST domain node. The resolution layer does not duplicate or rewrite the domain as a new expression.

## Alpha-equivalence

`alpha_normalize_math_expr` canonicalizes bound names while leaving free identifiers untouched. This provides the issue-62 metamorphic contract that safe bound-variable renaming does not change canonical meaning.

It is intentionally only alpha normalization. It does not perform algebraic simplification, theorem instantiation, beta reduction, or type inference.

## Structural proof operations

The layer introduces three operation records, all expressed through canonical AST references.

### Universal instantiation

A `forall` proposition supporting a conclusion is recognized as an instantiation only when the quantified body matches the conclusion under one consistent replacement for the binder. The parameter, argument and conclusion are all `ExpressionRef` values.

An explicit `instantiate` / imported-result proof step that cannot be matched structurally is still represented, but its operation remains unresolved and has no invented argument.

### Existential witness introduction

When a supporting proposition is an exact instance of an existential body, Thorn records the binder, witness AST node and evidence proposition. If source wording says `witness` but the structure cannot identify one, the witness operation remains unresolved.

### Equality substitution

A confident substitution requires:

1. an existing #61 `rewrite_substitution` proof step;
2. an explicit equality premise;
3. a separate input premise; and
4. an exact tree replacement producing the conclusion.

The equality, replacement direction, input, output and replacement sites are all AST references. Rewriting underneath nested binders is deliberately left unresolved in this tranche because it requires declaration-aware capture analysis rather than lexical replacement.

Equation citation alone is still not treated as a rewrite. That conservative #61 boundary is preserved.

## Deliberate partiality

The following are expected unresolved/ambiguous cases, not parser failures:

- a free identifier with only same-spelling declaration candidates;
- source scope parentage when the complete `SymbolTable` is not supplied;
- multiple conflicting source-use identities in one canonical expression owner;
- substitution under nested binders;
- instantiation through nested binders where shadowing could matter;
- explicit witness/instantiate/rewrite wording without enough typed structure to identify the operation;
- type inference beyond already-recovered symbol metadata or binder domains.

These limits preserve the core rule: **do not manufacture identity or substitution semantics from spelling alone**.

## Provenance

Declarations, references, scopes and proof operations carry source/AST provenance. For typed expressions, the stable reference is the pair of canonical proof address plus AST path. Source declarations retain their Thorn `SourceSpan` and original symbol identifier.

No provider or model call is needed by this layer.
