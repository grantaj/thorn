# LaTeX frontend evaluation

Thorn keeps parser choice behind the source-preserving `LatexFrontend` contract. Parser-native nodes must never become mathematical authority: frontends recover source facts and exact provenance, while theorem/result authority, dependency identity, scope, ambiguity, and semantic closure remain Thorn-owned.

This document records the earlier regex/pylatexenc A/B work (#16) and the Tree-sitter LaTeX evaluation in #158.

## Backends

### `regex`

Thorn's compatibility frontend. It is small, dependency-free, and intentionally pragmatic. It remains the `current` default.

### `pylatexenc`

An independent frontend backed by `pylatexenc.latexwalker.LatexWalker`, installed through `thorn-math[pylatexenc]`. The adapter normalizes pylatexenc nodes immediately to Thorn-owned frontend models.

### `tree-sitter` (experimental)

`TreeSitterLatexFrontend` uses the `latex-lsp/tree-sitter-latex` 0.6.0 grammar behind the same parser-neutral boundary. It is deliberately optional and does **not** change `current`.

The Python runtime is available through the `treesitter` extra:

```text
pip install 'thorn-math[treesitter]'
```

The grammar is not declared as a normal Thorn dependency in this tranche. The evaluated grammar revision is pinned explicitly for development/CI:

```text
pip install 'tree-sitter-latex @ git+https://github.com/latex-lsp/tree-sitter-latex.git@fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9'
```

This split is intentional evidence, not a migration plan. The grammar's own 0.6.0 metadata leaves its `core` extra on `tree-sitter~=0.21`, while this evaluation exercises current `tree-sitter==0.26.0`. Thorn therefore tests the grammar binding and runtime explicitly rather than importing the grammar's stale optional runtime constraint.

## Normative conformance

When the optional Tree-sitter packages are installed, `tests/test_frontend_conformance.py` runs the same contract against all three backends. It covers:

- exact raw source and source spans;
- comments and escaped `%`;
- theorem/proof/custom environments and nested environments;
- inline/display math;
- labels and references;
- `\\input` / `\\include` traversal and include-site diagnostics;
- malformed environment recovery without invented pairs;
- dependency graph identity, reference context, ambiguity, and provenance.

`tests/test_tree_sitter_frontend.py` adds #125/#162-derived source-level cases for preamble/body separation, `comment`, `verbatim`, `verbatim*`, `lstlisting`, and `minted` regions, fake includes/labels inside opaque regions, UTF-8 provenance, and the requirement that no Tree-sitter `Node` escapes the adapter.

The normal CI job continues to run the full keyless suite. A dedicated Tree-sitter job installs the pinned optional grammar and reruns frontend conformance plus the completed #162 semantic-dependency contracts. No provider/model call is made.

## Source/provenance observations

### Byte offsets need normalization

Tree-sitter positions are UTF-8 byte offsets/byte columns; Thorn's `SourceSpan` offsets are Python-string character offsets. The adapter therefore translates every parser boundary before exposing it. A Unicode regression (`αβ café` before a label) freezes this requirement. Directly copying Tree-sitter points into Thorn provenance would be wrong for non-ASCII manuscripts.

### Malformed environments require a Thorn guard

`tree-sitter-latex`'s generic environment grammar structurally accepts a `begin` and an `end` node without asserting that their environment names agree. That recovery behavior is useful for editor parsing but is too permissive for Thorn authority/provenance. The adapter validates names, emits an explicit parse diagnostic on disagreement, and never promotes the mismatched pair to `FrontendEnvironment`.

This is the same design principle established by the pylatexenc evaluation: tolerant parser recovery is evidence, not authority.

### Generic macro arguments remain ambiguous

The grammar models `generic_command` with zero or more curly groups. An optional bracket after an unknown command is therefore normally a sibling rather than part of that command. The adapter performs a narrowly bounded group recovery starting only at a Tree-sitter-recognized command boundary so existing source-fidelity conformance remains available without reintroducing a second whole-document scanner.

For an unknown command followed by a mandatory brace group, regex and Tree-sitter consume the group while pylatexenc conservatively leaves it as following content. `tests/test_frontend_ab.py` records that disagreement explicitly. Parser choice does not settle unknown macro semantics.

### Opaque environments must suppress inner source facts

Dedicated grammar nodes correctly make `comment`, `verbatim`, `lstlisting`, and `minted` contents opaque. `verbatim*` is not given a dedicated grammar node by the evaluated grammar, so Thorn applies a small source-role classification to the Tree-sitter-recovered environment boundary and suppresses nested macros before project traversal. This prevents a literal `\\input{...}` in verbatim-like material from becoming a project dependency.

The remaining limitation is custom verbatim-like environments: without package/macro semantics, neither a generic CST nor Thorn can know that an arbitrary custom environment changes tokenization. Such cases must remain explicit uncertainty rather than inferred mathematical source.

## Normalized document regions

#158 adds parser-neutral `FrontendRegion` / `FrontendRegionKind` facts as an experimental contract extension. The Tree-sitter adapter exposes:

- `PREAMBLE`;
- `DOCUMENT_TEXT` (plain body text after conservatively subtracting recognized commands, math, comments, and opaque regions);
- `COMMENT`, `VERBATIM`, `LISTING`, `MINTED`, and `MATH` exclusions.

`DOCUMENT_TEXT` means *syntactically eligible document prose*, not a declaration and not mathematical authority. No downstream semantic consumer is switched to these regions in #158.

**Boundary recommendation:** keep this normalized region concept. It is a meaningful generic source responsibility that a structured frontend can own, and it gives later semantic code a route away from repeated raw masking/scanning. Consolidating existing consumers onto it belongs to #161, not this tranche.

## Measurements

`scripts/measure_tree_sitter_frontend.py` builds the same deterministic two-file synthetic project for all three frontends, warms each path, and records median parser/full-extraction time plus installed distribution bytes. The dedicated CI job prints and retains the measurement JSON. Final measured values and the resulting disposition are recorded in the #158 PR/issue evidence after the first green evaluation run.

The packaging comparison is already qualitatively material: regex adds no parser package, pylatexenc is a pure-Python optional package, while Tree-sitter requires both the compiled Tree-sitter runtime and a separately built language binding. The grammar's current distribution/runtime constraint story is weaker than the ordinary PyPI-wheel path used by Thorn's existing optional backend.

## Earlier regex/pylatexenc result

The #16 CI run used a generated two-file project containing 40 lemma/theorem pairs, 11,332 source bytes, and 20 timed iterations after warm-up.

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

## #158 disposition

Pending the pinned Tree-sitter CI measurement and full contract run, **do not change the production/default frontend**. The evidence so far supports Tree-sitter as a serious structured-source candidate and differential oracle, but packaging friction, custom tokenization limits, and measured cost must be included before choosing between `optional backend`, `development/differential oracle`, or a stronger default-candidate disposition.
