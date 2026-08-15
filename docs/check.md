# `thorn check`

`thorn check` is Thorn's deterministic, zero-inference analysis mode.

```bash
thorn check paper.tex
```

It consumes the same project-level mathematical IR used by later semantic review, but it does not import or invoke model-backed audit/provider code. No `OPENAI_API_KEY` is required.

A clean `thorn check` run means only that none of the implemented **structural** rules fired. It is not a proof certificate and does not imply that a theorem or proof is mathematically correct.

## Initial deterministic rules

The issue #18 tranche intentionally contains only checks supported by strong structural evidence:

| Rule | Finding | Default severity |
| --- | --- | --- |
| `TH101` | duplicate theorem/result label | error |
| `TH102` | ambiguous theorem/result reference | error |
| `TH103` | missing internal LaTeX reference | error |
| `TH104` | circular theorem/result dependency | error |
| `TH111` | known symbol used before its later explicit introduction | warning |
| `TH112` | known symbol used outside its explicit lexical scope | warning |
| `TH113` | incompatible explicit roles for the same symbol in one scope | warning |

These findings report structural facts. For example, `TH112` says that Thorn can see an explicit declaration but that declaration is unavailable under the mechanically recovered scope tree; it does not claim that no implicit mathematical convention could repair the manuscript.

## False-positive boundary

This initial pass deliberately does **not**:

- treat every mathematical token as a user-defined symbol;
- complain about conventional notation merely because it lacks a local declaration;
- infer deep mathematical types from notation;
- infer function arity from arbitrary expressions;
- decide whether a nontrivial implication is mathematically valid;
- treat prose style such as `clearly` or `obviously` as a defect.

Broad undefined-symbol detection, more aggressive redefinition checks, and arity diagnostics should be added only with planted failures plus nearby clean controls demonstrating acceptable noise.

## `check` versus `review`

The CLI capability boundary is explicit:

```text
thorn check paper.tex     deterministic structural analysis; no model calls
thorn review paper.tex    model-backed adversarial mathematical review
```

For compatibility, the historical form

```bash
thorn paper.tex
```

continues to mean `thorn review paper.tex`.

Both modes share LaTeX extraction and mathematical IR. The intended long-term pipeline is:

```text
LaTeX
  -> source-preserving frontend
  -> result graph + symbol/scope IR
  -> thorn check
  -> later proof/support IR
  -> selective thorn review
```

## Exit status

`thorn check` uses the existing `--fail-on` policy:

- `error` (default): non-zero for error findings;
- `warning`: non-zero for warning or error findings;
- `never`: always zero for findings.

Parser/project-read failures still return status 2.

JSON output is available with:

```bash
thorn check paper.tex --format json
```

and includes `"mode": "check"` plus the deterministic findings.
