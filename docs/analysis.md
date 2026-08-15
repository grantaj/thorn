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

The symbol and proof-support IR records useful facts such as unresolved uses, source ordering, lexical scope, and ambiguity-bearing linguistic candidates. Those are not automatically warnings.

For example, ordinary mathematical prose permits trailing binders:

```latex
\[
  m \le f(x) \le M
\]
for every $x\in[0,1]$.
```

A source-order heuristic that warns on every apparent use-before-introduction is therefore too noisy. Thorn keeps uncertain structure in the IR so semantic review can use it, while deterministic analysis only reports facts supported strongly enough to justify a user-facing diagnostic.

This is the intended separation:

```text
LaTeX
  -> Thorn Math IR
       -> deterministic structural analysis
       `-> semantic mathematical review
```

## Inspecting the IR

The IR is a first-class output:

```bash
thorn ir paper.tex
thorn ir paper.tex --format json > thorn-ir.json
```

The JSON form contains the extracted project, theorem/result units, dependency graph, symbol table, and proof-support graph with source provenance.

## False-positive boundary

Deterministic analysis deliberately does not:

- infer deep mathematical types from notation;
- decide whether a nontrivial implication is mathematically valid;
- treat every unresolved symbol or parser ambiguity as a defect;
- infer proof correctness from local grammatical structure;
- treat prose style such as `clearly` or `obviously` as a mathematical error.

False theorems, missing hypotheses, quantifier errors, invalid limiting arguments, hidden conjecture dependencies, and similar mathematical faults are semantic-review problems unless a separate formal backend can establish them mechanically.

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
