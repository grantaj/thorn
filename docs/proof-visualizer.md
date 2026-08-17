# Proof argument visualiser

Thorn can render the mathematical argument it has already recovered as a self-contained interactive HTML graph:

```bash
thorn graph paper.tex
thorn graph paper.tex --output proof-graph.html --open
```

The default output is `paper.thorn-proof-graph.html`.

This command is keyless. It does not run semantic review, call a provider, or perform Lean formalisation.

## What the graph means

The visualiser is deliberately a view over Thorn's existing representations, not another proof representation.

At paper level it aggregates existing `ProofSupportGraph` `RESULT_REFERENCE` edges into theorem/lemma-level argument edges. A displayed arrow therefore means Thorn already recovered a referenced result as support for a claim in the dependent proof. Ordinary references — including references that merely occur in a theorem statement or proof prose without being recovered as support — are not promoted into argument topology.

Selecting a result shows its upstream argument dependencies and downstream dependents. Opening that result drills into the existing `ProofSupportGraph` for the proof unit:

- recovered claims are shown as claim nodes;
- existing claim-to-claim support edges form the internal topology;
- existing result-reference support edges appear as referenced-result nodes feeding the claim that cites them;
- ambiguous or unresolved support edges remain visibly distinct rather than being promoted to confident mathematical implications.

Other recovered support metadata such as definitions, equation references, named properties, and explicit reasons remains inspectable on the relevant claim, but does not automatically become peer topology in the graph.

## Presentation-only reduction

For readability the paper overview can suppress transitively redundant edges. This is reversible and affects only presentation. It never changes Thorn's underlying `ProofSupportGraph` or any other recovered IR.

Layout is also presentation-only. Cycles or mutually dependent recovered result relationships are displayed rather than silently rewritten into a DAG.

## Source navigation

Result and claim selections retain the exact existing source file/range. Where the browser permits local `file://` navigation, the visualiser exposes an `Open source file` link as a convenience; the visible `file:line` range remains the reliable provenance.

## Relationship to the review report

This first tranche is intentionally pre-review. It visualises recovered argument structure only.

The component is designed so the existing browsable report can later annotate the same result/claim identities with semantic-review findings, deterministic diagnostics, formalisation state, and dependency-aware review freshness. Those annotations must remain separate from proof-argument topology and must reuse their owning subsystems rather than adding visualiser-side validity logic.
