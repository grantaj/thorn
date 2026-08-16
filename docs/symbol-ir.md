# Symbol, definition, and scope IR

This document records Thorn's frontend symbol evidence layer. It sits above the parser-neutral LaTeX frontend and below deterministic analysis and the canonical Proof IR elaboration programme.

```text
LaTeX frontend facts
        |
        v
symbol extraction pass
        |
        v
SymbolTable evidence
        |
        +--> thorn analyze
        +--> thorn ir
        |
        `-> Proof IR elaboration
              - canonical symbol identity
              - binder and lexical scope
              - type/domain information
              - substitution / instantiation / witnesses
```

Parser adapters do not decide mathematical meaning. The symbol extractor consumes normalized frontend facts and produces Thorn-owned evidence models.

The important architectural distinction is that `SymbolTable` is **not the final symbol semantics of canonical Proof IR**. It supplies declarations, uses, scopes, roles, constraints, and provenance from which a stronger elaboration layer can conservatively establish identity and binding.

## Scope hierarchy

For each theorem-like result, Thorn creates an explicit scope tree with project, result, statement, proof, and mechanically delimited local scopes. A theorem-statement introduction remains visible in its associated proof; proof-local declarations do not escape to other results. Exact syntactic binders can introduce nested local scopes.

The scope model supports lexical shadowing while keeping bindings from different results distinct.

This is necessary evidence for canonical scope resolution, but a frontend scope record is not by itself permission to merge mathematical objects. Issue #62 strengthens this boundary by making symbol identity and binding explicit in Proof IR.

## Conservative introductions

The extractor recognizes only high-confidence forms such as `Let $X$ be ...`, `Let $f:X\\to Y$ be ...`, quantified parameters, `Define ...`, `Set ...`, and explicit `\\forall` / `\\exists` binders.

Each extracted symbol retains exact source provenance, its containing result and lexical scope, introduction kind, and conservative role/arity information where syntactically established. Definitions and explicit constraints are separate linked IR records.

These records are observations about the manuscript. Later elaboration may establish a canonical binder, domain, type, theorem parameter, witness, or substitution target from them.

## Roles are evidence, not guesses

Role metadata is intentionally partial. If syntax does not establish a useful role, Thorn records `unknown`. It must not manufacture a type merely to make later analysis possible.

Likewise, conventional notation such as `\\sin`, `\\mathbb R`, operators, and formatting commands is not promoted to manuscript-defined symbols merely because it occurs in mathematics.

The Proof IR programme should strengthen type/domain information only when sufficient evidence exists. Unknown type is a legitimate state.

## Uses and frontend resolution

Frontend resolution is lexical and source-order aware: search the current scope, walk outward, prefer the nearest visible declaration, and do not resolve to a declaration that occurs later in the same source file.

This represents useful evidence such as unresolved use-before-introduction candidates, but representation is not automatically diagnosis. Ordinary mathematical prose admits trailing binders, implicit conventional notation, and repeated local names; `thorn analyze` reports only cases supported strongly enough to survive false-positive controls.

Canonical Proof IR imposes a stronger contract than this heuristic evidence layer:

- same-spelling symbols must never be merged solely by lexical identity;
- free and bound occurrences must remain distinguishable;
- shadowing and rebinding must preserve separate identities;
- unresolved identity must remain explicit;
- alpha-renaming of bound variables should not change canonical meaning;
- substitutions and instantiations should reference canonical expression nodes rather than rewritten strings.

These are elaboration responsibilities, not reasons to make the frontend extractor guess more aggressively.

## Substitution, instantiation, and witnesses

Issue #62 extends Proof IR beyond declarations and uses to represent mathematical operations involving identity and scope.

The target distinction is roughly:

```text
frontend evidence:
  theorem T has parameter x
  proof text mentions "apply T with x=a"

canonical Proof IR:
  instantiate(result=T, substitution={x := a})
```

and:

```text
frontend evidence:
  source says "choose y such that P(y)"

canonical Proof IR:
  witness_intro(symbol=y, obligation=P(y), provenance=...)
```

The exact source remains attached, but the operation should not remain encoded merely as prose once its mathematical meaning is safely recoverable.

## Deliberate limits

The frontend symbol layer does not by itself:

- scan arbitrary mathematical tokens and declare them undefined;
- infer semantic types from prose without evidence;
- treat every letter as a locally declared symbol;
- decide whether a definition is mathematically sensible;
- turn ambiguity or unresolved binding into a correctness claim;
- identify same-spelling variables across scopes;
- perform semantic substitution by rewriting strings.

These limits are intentional. They let later Proof IR elaboration become stronger without making the evidence layer overconfident.

## Backend neutrality

The symbol evidence is tested against both the compatibility regex frontend and the independent pylatexenc frontend. Shared fixtures require equivalent serialized `SymbolTable` values, including source provenance.

Parser choice may change how syntax is discovered, but backend-specific node types must never leak into Thorn's mathematical IR or downstream canonical Proof IR.

## Anti-regression rule

Do not evolve `SymbolTable` into an ad hoc substitute for canonical symbol semantics merely because a deterministic rule needs more data.

The frontend layer should remain conservative and provenance-rich. Stronger notions—canonical identity, binder equivalence, typed parameters, substitution, theorem instantiation, and witness provenance—belong in the Proof IR elaboration layer, where ambiguity can remain explicit and metamorphic invariants can be tested directly.
