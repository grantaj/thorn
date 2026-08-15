# LaTeX frontend A/B evaluation

Issue #16 evaluates parser backends behind Thorn's source-preserving `LatexFrontend` contract. Parser choice is deliberately reversible: mathematical interpretation must not depend on backend-specific node classes.

## Backends

### `regex`

Thorn's compatibility frontend from #15. It is small, dependency-free, and intentionally pragmatic. It remains the default after this evaluation.

### `pylatexenc`

A second frontend backed by `pylatexenc.latexwalker.LatexWalker`.

For this experiment Thorn uses `pylatexenc==2.10` behind an optional `thorn-math[pylatexenc]` dependency. The adapter uses pylatexenc for node/environment/math parsing and source positions. Thorn adds normalization required by the frontend contract, including known signatures for labels/references/newtheorem and conservative optional-argument handling for custom environments.

## Normative conformance

Both backends run through the same `tests/test_frontend_conformance.py` suite. These are facts Thorn considers part of the frontend contract rather than parser preferences:

- theorem-like/custom environments and theorem/proof association;
- labels/references and duplicate-label ambiguity;
- `input` / `include` project traversal and missing-file provenance;
- inline/display math spans;
- nested environments;
- comments and escaped control symbols;
- optional/mandatory arguments where the signature is known or structurally explicit;
- malformed-environment diagnostics;
- exact source offsets, lines, and columns;
- result dependency graph behavior from #12.

Both backends pass the shared conformance suite. `tests/test_frontend_ab.py` additionally compares complete extracted units and the serialized #12 dependency graph for a representative result-dependency project; they match exactly.

## Malformed-input recovery finding

The first A/B CI run exposed a meaningful recovery difference. Given an unclosed `proof` environment, pylatexenc's strict parser correctly reports an error, but its tolerant recovery may return an environment node whose apparent span extends to a later closing environment even though no `\\end{proof}` occurs in the source.

That behavior is useful for general document recovery but is too permissive for Thorn provenance: Thorn must not invent a closed proof span. The pylatexenc adapter therefore accepts recovered environment nodes only when the node's raw source actually contains its matching closing token. The parse diagnostic is retained. A regression test freezes this contract.

This is a good example of why Thorn owns the frontend contract rather than exposing parser-native nodes directly.

## Explicit disagreement policy

Parser differences must not be silently normalized away when LaTeX surface syntax does not determine a unique interpretation.

The first recorded disagreement is an unknown macro followed only by a brace group:

```latex
\mystery{payload}
```

Without a macro definition, the source alone does not establish whether `{payload}` is an argument or merely the next group of document content. The compatibility regex backend historically consumes the group as an argument. `pylatexenc` conservatively treats an unknown macro as taking no arguments.

`tests/test_frontend_ab.py` freezes this as an *acknowledged disagreement*. It is not a reason to force either parser to imitate the other. Later symbol/macro analysis can resolve such cases when the manuscript supplies a definition.

## Development selection

The parser can be selected explicitly during development:

```text
thorn paper.tex --dry-run --frontend=regex
thorn paper.tex --dry-run --frontend=pylatexenc
```

`current` remains an alias for the default backend (`regex`).

## Evaluation results

CI run 31875577724 used a generated two-file project containing 40 lemma/theorem pairs (80 result environments plus proofs), 11,332 source bytes, and 20 timed iterations after warm-up.

| Dimension | regex | pylatexenc |
| --- | --- | --- |
| Shared conformance | pass | pass |
| #12 graph compatibility | pass | pass; exact A/B snapshot match |
| Source fidelity | pass | pass |
| Malformed-input recovery | conservative pairing; reports malformed structure | strict error + tolerant recovery; Thorn filters synthetic closures |
| Multi-file handling | pass | pass |
| Unknown macro policy | consumes following brace group | conservative without known signature |
| Runtime dependency | none | optional `pylatexenc==2.10` |
| Incremental parsing | no | no; current adapter reparses each file |
| Median parser time | 21.066 ms | 56.146 ms |
| Median full extraction time | 57.347 ms | 77.784 ms |

On this fixture pylatexenc parsing is 2.665x the regex parser time, while complete Thorn extraction is 1.356x the regex path. The absolute full-extraction median remains below 80 ms for both backends on this synthetic project, so parser speed is not currently a practical blocker.

The stable pylatexenc package also adds installation complexity compared with the zero-dependency compatibility parser. For that reason it remains optional rather than becoming a core Thorn dependency in this change.

## Disposition

**Keep `regex` as the `current` default and retain pylatexenc as an independent optional A/B backend.**

This recommendation is based on the observed tradeoffs rather than parser preference:

1. The abstraction is validated: a genuinely independent parser can reproduce Thorn's normative frontend contract and #12 mathematical structure without changing analysis code.
2. Pylatexenc provides a useful independent interpretation and stronger parser machinery, especially for future experiments with richer LaTeX structure.
3. It does not currently produce a material correctness improvement on Thorn's conformance corpus that justifies changing user-visible behavior.
4. It has additional dependency/install cost and is slower, although the absolute latency is small.
5. Macro signatures remain an important source of unavoidable ambiguity for either backend; #17's symbol/definition work is a better place to add manuscript-derived knowledge than hard-code increasingly speculative parser behavior.

The default can be reconsidered later without architectural upheaval. Good triggers would be evidence from a broader corpus that one backend materially improves structural correctness/recovery, a mature parser release with better packaging, or later IR layers that benefit substantially from richer parser-native structure.
