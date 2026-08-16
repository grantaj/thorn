# Deterministic analysis

`thorn analyze` runs Thorn's deterministic structural analyses over the Math IR recovered from a LaTeX project.

```bash
thorn analyze paper.tex
```

This mode is local and makes no model/API calls. The normal frontend includes local spaCy dependency parsing, but parser-derived relations are evidence in the IR rather than mathematical truth. Ambiguous or unresolved parser candidates do not become diagnostics merely because the parser proposed them.

For debugging or constrained environments:

```bash
thorn analyze paper.tex --structural-only
```

A clean analysis means only that none of the implemented structural rules fired. It does **not** imply that a theorem or proof is mathematically correct.

## Architectural role

Deterministic analysis is a useful consumer of Thorn's recovered mathematical structure, but it is **not the architectural north star**.

The wider architecture is:

```text
ordinary mathematical LaTeX
    -> source-preserving Math IR
         |--> thorn analyze
         |
         `-> partial mathematical elaboration
                -> canonical typed / partial Proof IR
                     |--> systematic LLM review
                     |--> deterministic proof tooling
                     `--> Lean / formal proof handoff
```

The canonical Proof IR is now a substantial implemented layer, not merely a future direction. It includes typed formulas, proof obligations and typed edges, symbol/type/scope resolution, higher proof structure, semantic transformations and the stable `thorn-proof/1` projection. The two primary consumer handoffs are tracked separately in #78 (production Proof-IR-backed LLM review) and #77 (bounded Lean export).

This means local checkability must not determine what mathematics Thorn chooses to represent.

If Thorn can safely identify that a step is a theorem application, substitution, witness introduction, rewrite, case split or proof obligation, that structure belongs in Proof IR even when `thorn analyze` cannot decide whether the operation is mathematically valid.

Conversely, an unresolved inference or ambiguous binding may be valuable IR state without justifying a warning.

This is a deliberate guard against returning to the abandoned `thorn check` idea through implementation convenience.

## Current deterministic diagnostics

| Rule | Finding | Default severity |
| --- | --- | --- |
| `TH101` | duplicate theorem/result label | error |
| `TH102` | ambiguous theorem/result reference | error |
| `TH103` | missing internal LaTeX reference | error |
| `TH104` | circular theorem/result dependency | error |
| `TH113` | incompatible explicit roles for the same symbol in one scope | warning |

`TH113` is deliberately narrow: incompatible roles must be established by explicit introductions in the same recovered lexical scope. Map/function roles are treated as compatible callable evidence.

## IR facts are broader than diagnostics

The frontend Math IR and downstream Proof IR record facts and uncertainty that are useful even when they do not establish a user-facing defect. Examples include unresolved uses, source ordering, lexical scope, ambiguity-bearing candidates, explicit proof obligations, partially lowered expressions, unknown inference rules, recovered theorem applications and source-addressed opaque steps.

Those are not automatically warnings.

For example, ordinary mathematical prose permits trailing binders:

```latex
\[
  m \le f(x) \le M
\]
for every $x\in[0,1]$.
```

A source-order heuristic that warns on every apparent use-before-introduction is therefore too noisy. Thorn keeps uncertain structure in the IR so later elaboration and other consumers can use it, while deterministic analysis reports only facts supported strongly enough to justify a diagnostic.

Similarly, a canonical Proof IR edge with an unresolved rule or open precondition is useful because it exposes exactly what remains unknown. Its presence does not itself prove that the author made an error.

## Inspecting the frontend IR

The current `thorn ir` command exposes the rich frontend Math IR:

```bash
thorn ir paper.tex
thorn ir paper.tex --format json > thorn-ir.json
```

The JSON form contains the extracted project, theorem/result units, dependency graph, symbol table and proof-support graph with source provenance.

The canonical typed / partial Proof IR is a stronger downstream layer built from that evidence. It should not be conflated with the current CLI serialization merely because both are called IR internally.

For the canonical architecture see [`mathematical-ir.md`](mathematical-ir.md). For the project-level contract see [`positioning.md`](positioning.md).

## False-positive boundary

Deterministic analysis deliberately does not:

- infer deep mathematical types from notation without evidence;
- decide whether a nontrivial implication is mathematically valid;
- treat every unresolved symbol or parser ambiguity as a defect;
- infer proof correctness from local grammatical structure;
- treat an explicit unresolved proof obligation as automatically erroneous;
- treat prose style such as `clearly` or `obviously` as a mathematical error.

False theorems, missing hypotheses, quantifier errors, invalid limiting arguments, hidden conjecture dependencies and similar mathematical faults generally require substantive semantic reasoning unless a formal backend can establish them mechanically for the relevant subset.

The important distinction is that Thorn should still **represent** as much relevant structure as it can. Failure of deterministic diagnosis is not failure of the IR.

## Relationship to LLM review

LLM review can consume richer structure than `thorn analyze` is allowed to turn into findings.

Issue #20 established IR-assisted review contexts and controlled raw/IR/targeted evaluation paths. The subsequent Proof-IR work provides a stronger machine interface: `thorn-proof/1` renders explicit propositions, obligations, dependencies, transformations, uncertainty and stable source handles from canonical semantics.

Issue #78 tracks the remaining production integration. Until that is complete, the current `thorn review` command still uses the existing semantic-review request path; the frozen `thorn-proof/1` representation should not be described as the normal provider input yet.

The model is a downstream mathematical reviewer, not a hidden part of deterministic IR construction and not a formal verifier.

## Relationship to Lean / formal checking

A formal proof assistant can provide a stronger assurance regime for the subset of Proof IR translated into kernel-checkable terms.

Issue #77 tracks the first bounded Lean handoff. Export must start from canonical Proof IR, translate only mechanically justified structure, preserve source correspondence and leave explicit holes/goals for unsupported mathematics.

That does not turn `thorn analyze` into a theorem prover and does not require all Thorn input to become formal. The same source-derived Proof IR may contain formally exportable fragments beside unresolved or opaque informal steps.

## Exit status

`thorn analyze` uses `--fail-on`:

- `error` (default): non-zero for error findings;
- `warning`: non-zero for warning or error findings;
- `never`: always zero for findings.

Parser/project-read failures return status 2. A missing local spaCy model is reported as a local-frontend error and suggests `--structural-only` as the explicit reduced fallback.

JSON diagnostic output is available with:

```bash
thorn analyze paper.tex --format json
```
