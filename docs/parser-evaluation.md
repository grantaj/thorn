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

The `treesitter` extra installs only the Python runtime used by the evaluation:

```text
pip install 'thorn-math[treesitter]'
```

The evaluated grammar revision is `fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9`. That source revision does not contain generated `src/parser.c`, so a direct `pip install` from its Git repository does not build. The reproducible CI evaluation instead generates the parser first:

```text
git clone --filter=blob:none https://github.com/latex-lsp/tree-sitter-latex.git /tmp/tree-sitter-latex
git -C /tmp/tree-sitter-latex checkout fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9
(cd /tmp/tree-sitter-latex && npx --yes tree-sitter-cli@0.24.7 generate)
pip install /tmp/tree-sitter-latex
```

This is evaluation/build evidence, not a proposed normal-user installation path. The grammar's 0.6.0 metadata also leaves its `core` extra on `tree-sitter~=0.21`, while this evaluation exercises `tree-sitter==0.26.0`. With 0.26.0 the binding additionally emits a deprecation warning because the grammar exposes the legacy integer language handle. The runtime works, but the packaging/API compatibility story is materially less mature than Thorn's existing optional pylatexenc path.

## Normative conformance

When the optional Tree-sitter packages are installed, `tests/test_frontend_conformance.py` runs the same parser-neutral contract against all three backends. It covers:

- exact raw source and source spans;
- comments and escaped `%`;
- theorem/proof/custom environments and nested environments;
- inline/display math;
- labels and references;
- `\\input` / `\\include` traversal and include-site diagnostics;
- malformed environment recovery without invented pairs;
- dependency graph identity, reference context, ambiguity, and provenance.

`tests/test_tree_sitter_frontend.py` adds #125/#162-derived source-level cases for preamble/body separation, `comment`, `verbatim`, `verbatim*`, `lstlisting`, and `minted` regions, fake includes/labels inside opaque regions, UTF-8 provenance, and the requirement that no Tree-sitter `Node` escapes the adapter.

The pinned evaluation run produced:

- frontend/differential conformance: **26 passed**;
- completed #162 semantic-dependency contract: **64 passed, 1 skipped, 1 strict xfail**;
- ordinary Thorn CI: fully green, including the normal test suite, Ruff and mypy;
- Lean contract: green;
- Local NLP contract: green;
- provider/model requests: **0**.

The strict xfail is deliberately part of the evaluation evidence rather than a compatibility workaround. For malformed direct source `\\input{{chapter}`, the evaluated grammar loses the command identity inside an undifferentiated parse `ERROR`. The #162 project-partiality contract requires Thorn to know that this is an indeterminate project boundary. Recovering that fact in the adapter would require rescanning the raw LaTeX for an include command, exactly the parallel-parser pattern #158 prohibits.

This is therefore a **genuine assurance blocker for default/production use of this backend**, not a request to add a Thorn regex special case. The xfail is strict so an upstream grammar improvement that restores enough structure becomes visible immediately.

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

`scripts/measure_tree_sitter_frontend.py` builds one deterministic two-file project containing 40 lemma/theorem pairs, 7,231 source bytes, warms each backend, and records the median of 20 parse and full-extraction iterations.

| Backend | Parse median | Full extraction median | Installed parser bytes |
| --- | ---: | ---: | ---: |
| regex | 14.735 ms | 66.823 ms | none |
| pylatexenc | 33.956 ms | 66.425 ms | 1,143,296 |
| tree-sitter | 24.957 ms | 77.956 ms | 5,819,485 combined |

The Tree-sitter installed total is 2,078,154 bytes for `tree-sitter` plus 3,741,331 bytes for the generated `tree-sitter-latex` distribution. It parses this fixture faster than pylatexenc but slower than regex, and its current full-extraction path is the slowest of the three. None of these differences is large enough to be the deciding architectural factor.

Packaging is more consequential. In the observed hosted CI run, cloning/generating/building the pinned grammar took roughly 55 seconds before tests could start, and requires a Node/tree-sitter-cli generation step. That is an observation of the current build path rather than a stable runtime benchmark, but it reinforces that this is not yet a frictionless normal-install dependency.

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

**Disposition: retain Tree-sitter as an experimental development/differential oracle and source-structure prototype; do not promote it to Thorn's default or production assurance frontend.**

The positive evidence is substantial: conventional mathematical LaTeX conformance is strong, provenance normalizes exactly, opaque/comment/math regions are materially cleaner than repeated raw scanning, and parser-neutral `FrontendRegion` facts look like the right long-term ownership boundary.

The negative evidence is also decisive for this tranche: at least one completed #162 project-partiality case loses the syntactic identity required to fail closed at the project boundary; repairing that in Thorn would recreate generic LaTeX scanning. The grammar also currently requires a generated-source build path and exposes a stale Tree-sitter runtime/API compatibility story.

Accordingly:

1. keep the adapter, corpus, differential lane, measurement script, and normalized-region experiment as useful architectural evidence;
2. keep `current` as `regex`;
3. do **not** add bespoke source scanning to make Tree-sitter satisfy the malformed-include case;
4. revisit production candidacy only if the upstream grammar preserves enough error structure, or a later generic source-partiality design can fail closed without identifying constructs by rescanning raw LaTeX;
5. use the `FrontendRegion` result as input to #161 substrate consolidation, without pre-empting #159 project/workspace evaluation.
