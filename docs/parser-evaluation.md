# LaTeX frontend evaluation and production disposition

Thorn keeps parser choice behind the source-preserving `LatexFrontend` contract.
Parser-native nodes are source evidence only: theorem/result identity, mathematical
authority, dependency identity, scope, ambiguity, and semantic closure remain
Thorn-owned.

This document records the #16 regex/pylatexenc comparison, the #158 Tree-sitter
evaluation, and the final #161 Slice G production/default decision.

## Current backend roles

| Backend | Current role | Default? |
| --- | --- | --- |
| `regex` | compatibility production frontend | **yes, for now** |
| `tree-sitter` | preferred source-structure backend and mandatory differential lane when installed | no; packaging blocker |
| `pylatexenc` | independent parser/conformance backend | no |

The runtime default is single-sourced through:

```text
DEFAULT_FRONTEND_NAME = regex
```

`current` resolves through `DEFAULT_FRONTEND_NAME`; `latex.extract_project()` uses the
same default selector rather than hard-coding a second choice. Tree-sitter's preferred
role is an evidence-backed architecture disposition documented here, not a second
runtime setting that could drift independently.

## Why Tree-sitter is preferred

The #158 evidence showed that `latex-lsp/tree-sitter-latex` can supply the generic
source structure Thorn wants behind `LatexFrontend`:

- exact macros, environments and math structure;
- normalized exact source provenance, including UTF-8 byte-to-character conversion;
- grammar-native comments and opaque/raw-code regions;
- conservative document-text eligibility;
- useful parse-error evidence without exposing parser-native nodes downstream;
- good conformance on ordinary mathematical LaTeX and the completed semantic-dependency
  contract.

The adapter also guards tolerant parser recovery where Thorn needs fail-closed source
facts. In particular, mismatched `\begin{...}` / `\end{...}` names are not promoted to
a valid `FrontendEnvironment` merely because the CST recovered a node.

The architecture does **not** require Tree-sitter to execute TeX, infer unknown macro
semantics, or repair malformed author input. Valid but unsupported structure may remain
partial; malformed structure may fail closed.

## Why Tree-sitter is not the default yet

The remaining blocker is installation/packaging, not semantic quality.

The evaluated grammar is `latex-lsp/tree-sitter-latex` 0.6.0 at revision
`fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9`. That revision does not contain generated
`src/parser.c`, so installing the exact evaluated grammar requires generating it first:

```text
git clone --filter=blob:none https://github.com/latex-lsp/tree-sitter-latex.git /tmp/tree-sitter-latex
git -C /tmp/tree-sitter-latex checkout fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9
(cd /tmp/tree-sitter-latex && npx --yes tree-sitter-cli@0.24.7 generate)
pip install /tmp/tree-sitter-latex
```

`thorn-math[treesitter]` currently installs `tree-sitter==0.26.0`, but it cannot by
itself install the exact generated grammar used by Thorn's conformance lane. The
0.6.0 grammar metadata also advertises an older Tree-sitter runtime range, while the
#158 evaluation intentionally exercised 0.26.0 and observed the binding's legacy
integer-language-handle deprecation warning.

A production-default switch must have a reproducible, pinned, ordinary installation
path that does not ask users to clone source and run Node code generation. Slice G
therefore keeps `regex` as the compatibility default and records a separate packaging
cutover as follow-up work.

This must not be misread as permission to improve the regex backend into a more complete
TeX parser. Tree-sitter remains the preferred destination.

## Normalized source contract

All serious backends are tested against parser-neutral Thorn facts rather than native
AST/CST shapes. The shared conformance surface covers:

- exact raw source and `SourceSpan` provenance;
- comments and escaped `%`;
- theorem/proof/custom and nested environments;
- inline/display math;
- labels and references;
- static `\input` / `\include` discovery and include-site provenance;
- malformed environment behavior without invented pairs;
- normalized source-region eligibility;
- dependency identity/reference context where frontend facts are sufficient.

Unknown macro-argument semantics are intentionally not normalized into a fictional
common answer. Backend disagreements are preserved as differential evidence.

Tree-sitter-specific tests additionally cover preamble/body separation, line/block
comments, `comment`, `verbatim`, `verbatim*`, `lstlisting`, `minted`, grammar-native
Asymptote/Python/Lua/Sage raw-code regions, fake include/reference syntax inside opaque
regions, UTF-8 provenance, and the no-native-node-leak invariant.

## Fail-closed distinctions

Conformance treats three classes differently:

1. **valid unusual LaTeX** — genuine robustness requirement;
2. **valid but unsupported/dynamic TeX** — explicit capability partiality is acceptable;
3. **malformed LaTeX** — author-facing source error is acceptable and preferable to
   heuristic repair.

For example, the historical malformed `\input{{chapter}` case is not a requirement to
recover the author's intended child. If the frontend cannot establish trustworthy
project structure, downstream authority must stop rather than reconstruct the command
with another Thorn scanner.

## Retained adapter-local handwritten logic

The Tree-sitter adapter contains two deliberately bounded source-role fallbacks:

- an environment-name expression applied only to a Tree-sitter-owned `begin` node when
  the grammar does not expose the convenient name field;
- `verbatim*` classification over an already CST-owned environment span because the
  pinned grammar parses it as a generic environment.

Neither fallback rescans the whole document or executes TeX. They are normalization of
parser-owned evidence, not a parallel parser.

The regex backend necessarily retains handwritten raw-source scanning because it is the
current compatibility frontend. That code is frozen as compatibility infrastructure in
architectural terms: new source corner cases should be addressed through the preferred
structured substrate or explicit capability limits, not by expanding the scanner.

## Workspace boundary above the parser

A source CST does not own expanded project occurrence semantics. `ProjectWorkspaceFacts`
now sits above every frontend and is the production owner of repeated occurrence
identity, include-site relationships, expanded order, and project partiality. TexLab and
LaTeXML remain independent workspace/deeper-expansion evidence as documented in
`workspace-resolution-evaluation.md`.

This separation is important: choosing Tree-sitter as the preferred source backend does
not turn it into Thorn's mathematical authority or a complete TeX workspace engine.

## Historical measurements

The final #158 review run reported:

| Backend | Parse median | Full extraction median | Installed parser bytes |
| --- | ---: | ---: | ---: |
| regex | 14.710 ms | 65.373 ms | none |
| pylatexenc | 32.452 ms | 64.793 ms | 1,143,296 |
| tree-sitter | 25.316 ms | 75.365 ms | 5,819,485 combined |

These small runtime differences were not architecturally decisive. Packaging was more
material: the pinned Tree-sitter grammar generation/build added roughly 50 seconds to
observed hosted-CI setup and required Node/tree-sitter-cli.

## Final #161 disposition

- Keep `LatexFrontend` as the sole parser boundary.
- Keep Tree-sitter as the preferred source-structure backend.
- Keep regex as the explicit compatibility default until exact grammar packaging is
  frictionless and reproducible.
- Keep pylatexenc as independent conformance evidence.
- Do not add raw-source compensation to make backends agree on unsupported semantics.
- Keep source/workspace partiality explicit and fail closed on malformed source.
- Re-run the full frontend, workspace, #162, Local NLP and Lean contracts before any
  later default switch.

The default decision is therefore settled for #161 without pretending the packaging
blocker has disappeared.
