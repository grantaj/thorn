# Symbol, definition, and scope IR

This document records the concrete symbol-layer contract introduced by issue #17. It sits above the parser-neutral LaTeX frontend and below deterministic analyses such as `thorn check`.

The important boundary is:

```text
LaTeX frontend facts
        |
        v
symbol extraction pass
        |
        v
SymbolTable IR
        |
        +--> deterministic analyses (#18)
        `--> later review-context distillation
```

Parser adapters do not decide mathematical meaning. The symbol extractor consumes only normalized frontend facts and produces Thorn-owned IR models.

## Scope hierarchy

For each theorem-like result, Thorn creates an explicit scope tree:

```text
project
  `-- result
       |-- statement
       `-- proof
            `-- local   (when mechanically delimited)
```

A theorem-statement introduction such as

```latex
Let $f:X\to Y$ be continuous.
```

is attached to the **result scope**, rather than only the statement scope. This is deliberate: hypotheses and objects introduced by the theorem statement must remain visible in its associated proof.

Objects introduced in a proof are attached to the **proof scope** and do not escape to other results. When Thorn has an exact syntactic boundary for a local binder, such as an explicit `\forall` or `\exists` inside one math span, it creates a nested **local scope** limited to that span.

The scope model supports lexical shadowing: a proof-local declaration can shadow a result-scope declaration, while a declaration in one result is not visible in another result.

## Conservative introductions

The first extraction tranche recognizes only high-confidence forms, including:

- `Let $X$ be ...`;
- `Let $f:X\to Y$ be ...`;
- `For $\epsilon>0$, ...`;
- `For $n\in\mathbb N$, ...`;
- `Define $g(x,y)=...`;
- `Set $A := ...`;
- explicit `\forall` and `\exists` binders.

Each extracted symbol retains:

- exact source offsets, lines, and columns;
- its introduction source span and original LaTeX;
- its containing result and lexical scope;
- the introduction kind;
- conservative role/arity information where syntactically established.

Definitions and explicit constraints are separate IR records linked back to the symbol they describe.

## Roles are evidence, not guesses

Role metadata is intentionally partial. Examples of strong evidence include:

```latex
$f:X\to Y$       % map, arity 1
$g(x,y)=...$      % function, arity 2
$\epsilon>0$      % scalar-like parameter
```

If the syntax does not establish a useful role, Thorn records `unknown`. It must not manufacture a type merely to make later checks possible.

Likewise, conventional notation such as `\sin`, `\mathbb R`, operators, and formatting commands is not promoted to manuscript-defined symbols merely because it occurs in mathematics.

## Uses and resolution

Issue #17 records uses of symbols that Thorn has already positively identified. Resolution is lexical and source-order aware:

1. search the current scope;
2. walk outward through parent scopes;
3. prefer the nearest visible declaration;
4. do not resolve to a declaration that occurs later in the same source file.

This already represents useful facts such as a use-before-introduction as an unresolved use, but **#17 does not emit a diagnostic for it**.

## Deliberate limits

This layer is representation, not mathematical judgment. In particular, #17 does not yet:

- scan arbitrary mathematical tokens and declare them undefined;
- diagnose redefinitions, scope errors, or arity mismatches;
- infer semantic types from prose;
- treat every letter in a formula as a locally declared symbol;
- decide whether a definition is mathematically sensible;
- parse implicit natural-language binders whose extent is unclear.

Those distinctions matter for false-positive control. Issue #18 can build deterministic checks over a stable symbol table without forcing the extraction layer to pretend it understands more than it does.

## Backend neutrality

The symbol IR is tested against both the compatibility regex frontend and the independent pylatexenc frontend. For the shared fixtures their complete serialized `SymbolTable` values must agree, including source provenance.

This is the same architectural rule used for the result dependency graph: parser choice may change how source syntax is discovered, but it must not leak backend-specific node types into Thorn's mathematical analysis.
