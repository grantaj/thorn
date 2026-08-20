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

This is evaluation/build evidence, not a proposed normal-user installation path. Thorn deliberately evaluated `tree-sitter==0.26.0`; the grammar's 0.6.0 metadata advertises an older `tree-sitter~=0.21` core extra. With Thorn's selected 0.26.0 runtime, the binding emits a deprecation warning because the grammar exposes an integer language handle. That warning is an observation about this evaluated runtime/binding combination: this tranche did **not** establish that the grammar's advertised 0.21 runtime range is unsuitable or that the mismatch is an upstream defect. The generated-source build path remains independent packaging evidence against making this a frictionless default dependency today.

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

Unknown-macro argument semantics are deliberately **not** part of that shared contract: without a macro signature, surface syntax does not determine whether adjacent groups belong to the command. Those disagreements are preserved in `tests/test_frontend_ab.py` instead of being normalized into a fictional common answer.

`tests/test_tree_sitter_frontend.py` adds #125/#162-derived source-level cases for preamble/body separation, line and block comments, `comment`, `verbatim`, `verbatim*`, `lstlisting`, `minted`, every native Asymptote/Python/Lua/Sage raw-code environment in the pinned grammar, fake includes/labels inside opaque regions, UTF-8 provenance, and the requirement that no Tree-sitter `Node` escapes the adapter.

The review-followup evaluation run produced:

- frontend/differential conformance: **27 passed**;
- completed #162 semantic-dependency contract: **64 passed, 1 skipped, 1 strict xfail**;
- ordinary Thorn test suite: **597 passed, 8 skipped**;
- Ruff: green;
- Tree-sitter-lane mypy: green;
- Lean contract and Local NLP contract: green on the review-fix head;
- provider/model requests: **0**.

The strict xfail is deliberately part of the evaluation evidence rather than a compatibility workaround. For malformed direct source `\\input{{chapter}`, the evaluated grammar loses the command identity inside an undifferentiated parse `ERROR`. Recovering that command identity in the adapter would require rescanning raw LaTeX, exactly the parallel-parser pattern #158 prohibits.

This malformed-input case is **not evidence against Tree-sitter's production candidacy by itself**. Thorn is expected to be robust to unusual but valid LaTeX; it is not expected to repair invalid LaTeX or infer what an author probably intended. The appropriate assurance behavior for structurally invalid input is generic fail-closed partiality: if the frontend cannot establish reliable source or project structure, Thorn should stop analysis that depends on that structure and report the source problem for the author to correct.

Accordingly, future conformance should distinguish three cases:

- **valid but unusual syntax:** a real robustness requirement; systematic failures count against the backend;
- **valid but unsupported syntax or TeX dynamics:** an explicit capability limit to investigate with mature tooling or represent as unresolved/unsupported;
- **invalid or malformed syntax:** an input error that Thorn may reject rather than repair heuristically.

None of these cases justifies growing a parallel Thorn LaTeX parser to guess missing structure.

## Source/provenance observations

### Byte offsets need normalization

Tree-sitter positions are UTF-8 byte offsets/byte columns; Thorn's `SourceSpan` offsets are Python-string character offsets. The adapter therefore translates every parser boundary before exposing it. A Unicode regression (`αβ café` before a label) freezes this requirement. Directly copying Tree-sitter points into Thorn provenance would be wrong for non-ASCII manuscripts.

### Malformed environments require a Thorn guard

`tree-sitter-latex`'s generic environment grammar structurally accepts a `begin` and an `end` node without asserting that their environment names agree. That recovery behavior is useful for editor parsing but is too permissive for Thorn authority/provenance. The adapter validates names, emits an explicit parse diagnostic on disagreement, and never promotes the mismatched pair to `FrontendEnvironment`.

This is the same design principle established by the pylatexenc evaluation: tolerant parser recovery is evidence, not authority.

### Generic macro arguments remain ambiguous

The grammar models `generic_command` with zero or more curly groups. The adapter now exposes **only groups owned by that CST node**. It does not inspect sibling raw source to recover additional `[...]` or `{...}` arguments.

That makes two useful disagreements explicit:

- for unknown `\\mystery{payload}`, regex and Tree-sitter consume the mandatory curly group while pylatexenc leaves it as following content;
- for unknown `\\mystery[alpha]{payload}`, regex and pylatexenc associate both groups with the command, while the pinned Tree-sitter grammar ends `generic_command` at `\\mystery`; the bracket and following group remain siblings.

`tests/test_frontend_ab.py` records both cases. This is intentional evidence: parser choice does not settle unknown macro semantics, and #158 does not justify building a second group parser inside Thorn to make the backends agree.

### Opaque environments must suppress inner source facts

The pinned grammar has dedicated trivia/raw-code nodes beyond the familiar `comment`, `verbatim`, `lstlisting`, and `minted` cases. The adapter therefore fails closed over **all native opaque/trivia node types in that grammar revision**, including:

- `block_comment` (`\\iffalse ... \\fi`) as `COMMENT`;
- `asy` and `asydef`;
- `pycode`;
- `luacode` / `luacode*`;
- `sagesilent` and `sageblock`.

These raw/code environments map to a generic `OPAQUE` source role rather than growing a new Thorn enum for every package. Their full CST-owned spans are subtracted from eligible document prose, and macros found inside those spans are suppressed before include/project traversal. The regression corpus exercises every one of these native environment names.

`verbatim*` is the one small classification fallback in this tranche because the pinned grammar parses it structurally as a generic environment rather than a dedicated trivia node. Thorn classifies the already Tree-sitter-owned environment span as `OPAQUE`; it does not rescan source to find its boundary.

The remaining limitation is custom verbatim-like environments: without package/macro semantics, neither a generic CST nor Thorn can know that an arbitrary custom environment changes tokenization. Such cases must remain explicit uncertainty rather than inferred mathematical source.

## Normalized document regions

#158 adds parser-neutral `FrontendRegion` / `FrontendRegionKind` facts as an experimental contract extension. The Tree-sitter adapter exposes:

- `PREAMBLE`;
- `DOCUMENT_TEXT` (plain body text after conservatively subtracting recognized commands, math, comments, and opaque/trivia regions);
- `COMMENT`, `VERBATIM`, `LISTING`, `MINTED`, `OPAQUE`, and `MATH` exclusions.

`DOCUMENT_TEXT` means *syntactically eligible document prose*, not a declaration and not mathematical authority. No downstream semantic consumer is switched to these regions in #158.

The review-driven corpus verifies that declaration-looking text in line comments, `\\iffalse` block comments, the common literal environments, and every native Asymptote/Python/Lua/Sage raw-code environment in the pinned grammar is not exposed as `DOCUMENT_TEXT`.

**Boundary recommendation:** keep this normalized region concept. It is a meaningful generic source responsibility that a structured frontend can own, and it gives later semantic code a route away from repeated raw masking/scanning. Consolidating existing consumers onto it belongs to #161, not this tranche.

## Measurements

`scripts/measure_tree_sitter_frontend.py` builds one deterministic two-file project containing 40 lemma/theorem pairs, 7,231 source bytes, warms each backend, and records the median of 20 parse and full-extraction iterations.

The review-followup run measured:

| Backend | Parse median | Full extraction median | Installed parser bytes |
| --- | ---: | ---: | ---: |
| regex | 14.710 ms | 65.373 ms | none |
| pylatexenc | 32.452 ms | 64.793 ms | 1,143,296 |
| tree-sitter | 25.316 ms | 75.365 ms | 5,819,485 combined |

The Tree-sitter installed total is 2,078,154 bytes for `tree-sitter` plus 3,741,331 bytes for the generated `tree-sitter-latex` distribution. It parses this fixture faster than pylatexenc but slower than regex, and its current full-extraction path is the slowest of the three. None of these differences is large enough to be the deciding architectural factor.

Packaging is more consequential. In observed hosted CI runs, cloning/generating/building the pinned grammar takes roughly 50 seconds before tests can start and requires a Node/tree-sitter-cli generation step. That is an observation of the current build path rather than a stable runtime benchmark, but it reinforces that this is not yet a frictionless normal-install dependency.

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

**Disposition: Tree-sitter is the preferred structural-source substrate candidate for Thorn. Keep it optional until the generic fail-closed partiality boundary and packaging path are mature enough for a production-default switch; do not relegate it merely because it rejects malformed or unsupported source.**

The positive evidence is strong: conventional mathematical LaTeX conformance is good, exact provenance normalizes correctly, grammar-native opaque/comment/math regions can be excluded without repeated whole-document raw scanning, and parser-neutral `FrontendRegion` facts provide the right direction for moving generic source eligibility below Thorn's mathematical semantics.

The evaluation does **not** require Tree-sitter to recover author intent from malformed LaTeX. In particular, the malformed `\\input{{chapter}` case should be treated as an author-correctable structural input error, provided Thorn can fail closed generically rather than deriving guessed project order. It is not a reason to preserve or extend a bespoke Thorn parser.

Production candidacy should instead be judged on:

1. robustness across unusual but valid mathematical LaTeX;
2. exact provenance and conservative source-role recovery;
3. explicit failure/partiality for structurally indeterminate input;
4. a workable packaging/runtime path;
5. evidence from #159 about project/workspace facts that lie beyond a source CST.

Accordingly:

1. keep the Tree-sitter adapter, corpus, differential lane, measurement script, and normalized-region contract as architectural building blocks;
2. keep `current` as `regex` for now because #158 was an evaluation tranche, not a migration PR;
3. carry Tree-sitter forward into #161 as the leading source-structure substrate candidate rather than an oracle-only backend;
4. use #159 to determine how project/workspace ordering and valid dynamic TeX structure should be supplied or marked unresolved;
5. fail closed on malformed source and report it to the author; do not add Thorn-specific parsing to repair or guess invalid input;
6. treat valid-but-unsupported syntax as a capability boundary to improve or document, not as malformed input and not as justification for heuristic repair.
