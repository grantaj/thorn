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
| `TH113` | incompatible explicit roles for the same symbol in one scope | warning |

`TH113` is deliberately narrow: it requires incompatible roles to be established by explicit introductions in the same recovered lexical scope. Map/function roles are treated as compatible callable evidence.

## Binding facts are not yet diagnostics

The symbol IR records useful facts such as unresolved uses, source ordering, and lexical scope. The first #18 implementation initially promoted two of those facts directly to warnings:

- `TH111` — a known symbol appears before a later explicit introduction;
- `TH112` — a same-named explicit declaration exists outside the use's recovered lexical scope.

Running `thorn check` over the complete public synthetic matrix showed that those premises are not sufficient for a user-facing diagnostic. In particular, ordinary mathematical prose permits **trailing binders** such as

```latex
\[
  m \le f(x) \le M
\]
for every $x\in[0,1]$.
```

and freely reuses locally bound names. A source-order or same-name scope relationship therefore does not establish that the author used the wrong binding.

The IR continues to retain those facts because they may become useful once Thorn has a richer prose/argument structure, but `thorn check` stays silent on them for now. This is an intentional example of the distinction between **representing a suspicious fact** and having enough evidence to **lint it**.

## Full-matrix specification

Every check-enabled public synthetic case has an explicit deterministic expectation in:

```text
eval/check-expectations.json
```

Run the deterministic matrix with:

```bash
thorn-eval eval/cases --check
```

The manifest must cover every check-enabled case exactly. An empty rule list is meaningful: it says the current deterministic checker is expected to stay silent on that paper even when the paper contains a semantic mathematical defect.

The matrix now contains **52 check-enabled cases**:

- the original 46 semantic/review cases, which double as broad false-positive controls for `thorn check`;
- six additional **check-only** cases that exercise the surviving structural rule families end to end without adding future model cost.

The check-only tranche includes:

- duplicate theorem labels → `TH101`;
- a reference to a duplicated theorem label → `TH101` + `TH102`;
- a missing internal theorem reference → `TH103`;
- explicit same-scope scalar/map role conflict → `TH113`;
- an existing equation label as a clean non-result-reference control;
- compatible map/function introductions as a clean callable-role control.

The two existing L7 circular-dependency papers exercise `TH104`.

Case metadata has a `modes` field. Existing cases default to both `check` and `review`; structural fixtures can declare `"modes": ["check"]`. As a result, the deterministic matrix can grow without silently increasing paid semantic-review runs. The live review suite remains at 46 cases.

This is important to Thorn's capability boundary. A false theorem, invalid compactness step, hidden conjecture dependency, or quantifier error should not acquire a structural warning merely because the offline checker cannot understand it.

Default CI runs the complete 52-case deterministic matrix with `OPENAI_API_KEY` blank.

## False-positive boundary

This initial pass deliberately does **not**:

- treat every mathematical token as a user-defined symbol;
- complain about conventional notation merely because it lacks a local declaration;
- infer binding scope from source order alone;
- equate a repeated symbol name with identity of mathematical binding;
- infer deep mathematical types from notation;
- infer function arity from arbitrary expressions;
- decide whether a nontrivial implication is mathematically valid;
- treat prose style such as `clearly` or `obviously` as a defect.

Broad undefined-symbol detection, binding/scope diagnostics, more aggressive redefinition checks, and arity diagnostics should be added only with planted failures plus nearby clean controls demonstrating acceptable noise.

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
