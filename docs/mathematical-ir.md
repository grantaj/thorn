# Thorn mathematical IR architecture

## Purpose

Thorn's deterministic layer is a **mathematical document frontend**, not an offline mathematical correctness checker. Its main job is to recover a compact, source-preserving representation that later analyses and reviewers can consume.

The core pipeline is:

```text
LaTeX project
    |
    v
source-preserving LaTeX frontend
    |
    v
Thorn Math IR
    |-- theorem/result units and dependencies
    |-- symbols, definitions, roles, and scopes
    |-- claims and explicit support relationships
    |-- ambiguity/evidence
    `-- exact provenance back to source
    |
    +--> thorn analyze
    |       deterministic structural diagnostics
    |
    +--> thorn ir
    |       inspect/export the representation
    |
    `--> thorn review
            semantic mathematical judgment
```

The result-level dependency graph introduced in #12 is the first layer of this IR. The symbol, linguistic, and proof-support work extends the same Thorn-owned representation.

## Architectural rule: separate parsing from mathematical interpretation

A parser backend should answer syntactic questions such as which files form the project, where environments and macro calls occur, and what exact source spans produced them. It should not decide that a sentence is mathematically true, that an implication follows, or that a proof is valid.

Those concepts belong above the parser boundary:

```text
parser-specific syntax
        |
        v
frontend-neutral source model
        |
        v
Thorn Math IR
        |
        +--> structural analysis
        `--> semantic review
```

Nothing in the mathematical IR or analysis layers should depend directly on parser-specific node classes.

## Frontend abstraction

Thorn owns a replaceable LaTeX frontend contract. During development, backend selection remains explicit enough to support A/B testing:

```text
thorn analyze paper.tex --frontend=current
thorn analyze paper.tex --frontend=pylatexenc
```

A backend change that alters recovered result units, references, dependencies, or source provenance is not automatically wrong, but the difference must be testable and explained.

## Mathematical IR

### Results and dependencies

The result layer represents theorem-like units, proof association, labels, references, direct/reverse/transitive dependencies, ambiguous dependencies, cycles, and exact source provenance.

### Symbols, definitions, and scopes

The symbol layer conservatively records explicitly introduced mathematical objects, uses, roles, constraints, and scopes. Unknown or ambiguous structure should remain unknown or ambiguous rather than being forced into a confident interpretation.

Conventional mathematical notation must not generate noise merely because it lacks a local declaration.

### Claims and support

The proof-support layer records explicit and sufficiently well-supported relationships such as citations to earlier results, named definitions/properties, and prose assertions that later steps depend on.

A support edge can exist without Thorn knowing whether it is mathematically valid. This is a central design boundary:

> **The frontend represents argument structure; semantic review judges mathematically nontrivial validity.**

### Load-bearing prose

Mathematical assertions do not cease to matter because they are written in prose. The IR should retain load-bearing assertions regardless of whether they appear in displayed mathematics or prose, while avoiding irrelevant expository text where possible.

## Provenance is mandatory

Every IR object derived from source must retain enough information to return to the manuscript location: file, range/offsets, line information where practical, and raw source or stable access to it.

This supports precise diagnostics, browsable reports, review prompts containing original wording, revision-aware caching, parser comparisons, and future safe autofix.

Normalization must never destroy the route back to original source.

## Deterministic analysis

`thorn analyze` consumes the Math IR and reports only mechanically justified findings. Current examples include duplicate/conflicting labels, ambiguous or broken result dependencies, dependency cycles, and incompatible explicit symbol roles.

The presence of rich IR does **not** imply that every suspicious IR fact should become a diagnostic. In particular, parser ambiguity, unresolved uses, missing explicit support, or unusual notation may be evidence for later review without establishing a user-facing defect.

A deterministic diagnostic must never claim that a nontrivial mathematical implication is false merely because Thorn cannot establish it.

## Semantic review

The semantic reviewer should increasingly consume IR-derived context rather than rediscovering project structure from raw LaTeX.

A review packet can contain a bounded result statement, definitions/symbols in scope, dependencies, proof claims/support, uncertainty evidence, and the exact raw source spans needed to resolve wording.

This is the purpose of the IR-assisted review work in issue #20. The current raw-`TheoremUnit` path remains useful as an A/B baseline while IR-based review is evaluated; it is not the architectural endpoint.

## First-class IR output

The representation is inspectable independently of either diagnostics or semantic review:

```bash
thorn ir paper.tex
thorn ir paper.tex --format json > thorn-ir.json
```

This matters because semantic review is only one possible consumer. Other future consumers can include dependency visualisation, document navigation, specialised local models, report generation, and bounded formalisation/proof-assistant backends.

## Design invariants

1. **Parser backends are replaceable.** Mathematical analysis never depends directly on parser-specific node classes.
2. **Parser differences are testable.** Backends run through the same conformance expectations.
3. **Provenance is never discarded.** Derived mathematical objects point back to source.
4. **Unknown is preferable to guessed.** The IR may be partial or explicitly ambiguous.
5. **Deterministic analysis does not masquerade as proof verification.** Structural facts and mathematical validity are different things.
6. **Prose can be mathematical.** Load-bearing prose belongs in the argument representation.
7. **One IR serves multiple consumers.** Analysis, semantic review, and future tooling share the same extracted structure.
8. **False-positive control is a feature.** Deterministic diagnostics require planted failures and nearby clean controls.
9. **Architecture permits A/B testing.** Parser and semantic-review strategies can be compared on the same corpus before becoming defaults.

## What success looks like

A mature Thorn run should look less like "send a paper to a model" and more like a compiler/static-analysis toolchain:

```text
LaTeX
  -> source-preserving parse
  -> Thorn Math IR
  -> structural diagnostics
  -> dependency-aware semantic review
  -> source-linked findings/report
```

The difficult mathematical judgment remains semantic unless and until a bounded obligation is handed to a formal backend. The deterministic frontend is valuable because it gives every downstream consumer a stable mathematical representation, not because it can certify the paper offline.
