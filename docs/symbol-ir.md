# Symbol, definition, and scope IR

This document records the symbol-layer contract introduced by issue #17. It sits above the parser-neutral LaTeX frontend and below deterministic analysis and semantic-review context distillation.

```text
LaTeX frontend facts
        |
        v
symbol extraction pass
        |
        v
SymbolTable IR
        |
        +--> thorn analyze
        +--> thorn ir
        `--> semantic review context
```

Parser adapters do not decide mathematical meaning. The symbol extractor consumes normalized frontend facts and produces Thorn-owned IR models.

## Scope hierarchy

For each theorem-like result, Thorn creates an explicit scope tree with project, result, statement, proof, and mechanically delimited local scopes. A theorem-statement introduction remains visible in its associated proof; proof-local declarations do not escape to other results. Exact syntactic binders can introduce nested local scopes.

The scope model supports lexical shadowing while keeping bindings from different results distinct.

## Conservative introductions

The extractor recognizes only high-confidence forms such as `Let $X$ be ...`, `Let $f:X\\to Y$ be ...`, quantified parameters, `Define ...`, `Set ...`, and explicit `\\forall` / `\\exists` binders.

Each extracted symbol retains exact source provenance, its containing result and lexical scope, introduction kind, and conservative role/arity information where syntactically established. Definitions and explicit constraints are separate linked IR records.

## Roles are evidence, not guesses

Role metadata is intentionally partial. If syntax does not establish a useful role, Thorn records `unknown`. It must not manufacture a type merely to make later analysis possible.

Likewise, conventional notation such as `\\sin`, `\\mathbb R`, operators, and formatting commands is not promoted to manuscript-defined symbols merely because it occurs in mathematics.

## Uses and resolution

Resolution is lexical and source-order aware: search the current scope, walk outward, prefer the nearest visible declaration, and do not resolve to a declaration that occurs later in the same source file.

This represents facts such as unresolved use-before-introduction candidates, but representation is not automatically diagnosis. Ordinary mathematical prose admits trailing binders and repeated local names; `thorn analyze` reports only cases supported strongly enough to survive false-positive controls.

## Deliberate limits

The symbol layer does not by itself:

- scan arbitrary mathematical tokens and declare them undefined;
- infer semantic types from prose;
- treat every letter as a locally declared symbol;
- decide whether a definition is mathematically sensible;
- turn ambiguity or unresolved binding into a correctness claim.

These boundaries let semantic review use richer evidence without forcing deterministic analysis to pretend it understands more than it does.

## Backend neutrality

The symbol IR is tested against both the compatibility regex frontend and the independent pylatexenc frontend. Shared fixtures require equivalent serialized `SymbolTable` values, including source provenance.

Parser choice may change how syntax is discovered, but backend-specific node types must never leak into Thorn's mathematical IR or downstream analysis.
