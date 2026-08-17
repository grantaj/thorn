# Thorn quickstart examples

These are small mathematical manuscripts for learning Thorn as a product. They are not evaluation fixtures and are not part of the frozen semantic-review corpus.

- `clean/paper.tex` is a short healthy argument with two supporting lemmas and a theorem. It is useful for a quiet keyless run, source navigation, the proof graph, and Thorn's current bounded Lean handoff.
- `structural-problem/paper.tex` contains an ordinary but broken internal mathematical reference. `thorn analyze` detects it deterministically as `TH103`, with no provider call.
- `mathematical-problem/paper.tex` contains a genuine proof defect that belongs to semantic review: it cancels a common factor without assuming that factor is nonzero. Model wording is nondeterministic; the stable expectation is that review should identify the missing nonzero hypothesis or the invalid division step.

Follow [`docs/quickstart.md`](../../docs/quickstart.md) from the repository root for the intended end-to-end walkthrough.
