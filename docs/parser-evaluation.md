# LaTeX frontend A/B evaluation

Issue #16 evaluates parser backends behind Thorn's source-preserving `LatexFrontend` contract. Parser choice is deliberately reversible: mathematical interpretation must not depend on backend-specific node classes.

## Backends

### `regex`

Thorn's compatibility frontend from #15. It is small, dependency-free, and intentionally pragmatic. It remains the default after this evaluation.

### `pylatexenc`

A second frontend backed by `pylatexenc.latexwalker.LatexWalker`. Thorn uses `pylatexenc==2.10` behind the optional `thorn-math[pylatexenc]` dependency. The adapter uses pylatexenc for node/environment/math parsing and source positions, then normalizes the results into Thorn-owned frontend types.

## Normative conformance

Both backends run through the same `tests/test_frontend_conformance.py` suite. The shared contract includes theorem/proof association, labels and references, project traversal, math spans, nested environments, comments/escaping, malformed-environment diagnostics, exact source provenance, and the result dependency graph.

`tests/test_frontend_ab.py` additionally compares complete extracted units and serialized dependency structure on representative projects. Parser replacement must never silently change Thorn's Math IR.

## Malformed-input recovery

The first A/B CI run exposed a useful difference. Given an unclosed `proof` environment, pylatexenc's tolerant recovery may return an environment node whose apparent span extends to a later closing environment even though no matching `\\end{proof}` exists.

That behavior can be useful for general document recovery but is too permissive for Thorn provenance. Thorn accepts recovered environment nodes only when the raw source actually contains the matching closing token; the parse diagnostic is retained.

This is a good example of why Thorn owns the frontend contract rather than exposing parser-native nodes directly.

## Explicit disagreement policy

Parser differences must not be silently normalized away when LaTeX surface syntax does not determine a unique interpretation. An unknown macro followed by a brace group is one such case: without a macro definition, the source alone does not establish whether the group is an argument or subsequent document content.

`tests/test_frontend_ab.py` freezes acknowledged disagreements rather than forcing one parser to imitate the other. Later symbol/macro analysis can resolve cases where the manuscript supplies additional evidence.

## Development selection

The parser can be selected explicitly while inspecting the recovered IR:

```text
thorn ir paper.tex --frontend=regex
thorn ir paper.tex --frontend=pylatexenc
```

or while exercising deterministic structural analysis:

```text
thorn analyze paper.tex --frontend=regex
thorn analyze paper.tex --frontend=pylatexenc
```

`current` remains an alias for the default backend (`regex`).

## Evaluation results

CI run 31875577724 used a generated two-file project containing 40 lemma/theorem pairs, 11,332 source bytes, and 20 timed iterations after warm-up.

| Dimension | regex | pylatexenc |
| --- | --- | --- |
| Shared conformance | pass | pass |
| dependency graph compatibility | pass | pass; exact A/B snapshot match |
| Source fidelity | pass | pass |
| Malformed-input recovery | conservative pairing | strict error + tolerant recovery filtered by Thorn |
| Multi-file handling | pass | pass |
| Unknown macro policy | consumes following brace group | conservative without known signature |
| Runtime dependency | none | optional `pylatexenc==2.10` |
| Incremental parsing | no | no; current adapter reparses each file |
| Median parser time | 21.066 ms | 56.146 ms |
| Median full extraction time | 57.347 ms | 77.784 ms |

On this fixture pylatexenc parsing was 2.665x the regex parser time, while complete Thorn extraction was 1.356x the regex path. Absolute full-extraction latency remained below 80 ms for both backends on the synthetic project.

## Disposition

**Keep `regex` as the `current` default and retain pylatexenc as an independent optional A/B backend.**

The important result is architectural: a genuinely independent parser can reproduce Thorn's normative frontend contract and Math IR without changing downstream analysis code. The default can be reconsidered later if a broader corpus shows a material structural/recovery advantage.
