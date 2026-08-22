# LaTeX frontend evaluation and production disposition

Thorn keeps parser choice behind the source-preserving `LatexFrontend` contract.
Parser-native nodes are source evidence only: theorem/result identity, mathematical
authority, dependency identity, scope, ambiguity, and semantic closure remain
Thorn-owned.

This document records the #16 regex/pylatexenc comparison, the #158 Tree-sitter
evaluation, the #161 architectural disposition, and the #183 production cutover.

## Current backend roles

| Backend | Current role | Default? |
| --- | --- | --- |
| `tree-sitter` | production source-structure frontend and mandatory conformance lane | **yes** |
| `regex` | compatibility and differential backend; frozen as parser infrastructure | no |
| `pylatexenc` | independent parser/conformance backend | no |

The runtime choice is single-sourced through:

```text
DEFAULT_FRONTEND_NAME = tree-sitter
```

`current` resolves through `DEFAULT_FRONTEND_NAME`; `latex.extract_project()` asks for a
fresh default frontend at each extraction rather than caching a shared mutable parser.
That lifecycle rule was established by #195 before the default changed.

## Why Tree-sitter is the production backend

The #158 evidence showed that `latex-lsp/tree-sitter-latex` supplies the generic source
structure Thorn wants behind `LatexFrontend`:

- exact macros, environments and math structure;
- normalized exact source provenance, including UTF-8 byte-to-character conversion;
- grammar-native comments and opaque/raw-code regions;
- conservative document-text eligibility;
- useful parse-error evidence without exposing parser-native nodes downstream;
- strong conformance on ordinary mathematical LaTeX and the completed
  semantic-dependency contract.

The adapter guards tolerant parser recovery where Thorn needs fail-closed source facts.
For example, mismatched `\begin{...}` / `\end{...}` names are not promoted to a valid
`FrontendEnvironment` merely because the CST recovered a node.

The architecture does **not** require Tree-sitter to execute TeX, infer unknown macro
semantics, or repair malformed author input. Valid but unsupported structure may remain
partial; malformed structure may fail closed.

## Packaged identity and #183 cutover

The historical #158 grammar pin was
`fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9`. It remained non-default because installing
that exact generated grammar required a source clone plus Node-based generation.

Issue #183 clarified the actual invariant: Thorn must ship an exact grammar identity
that has passed the evidence gate; the first evaluated revision is not immutable.
The conventionally released candidate was therefore evaluated independently before the
default changed.

The production identity is now:

- `tree-sitter==0.26.0`;
- `tree-sitter-language-pack==1.14.3`;
- language-pack v1.14.3 release tag commit
  `df3bcc39862da6972032d7537d49b782a50a25bb`;
- packaged LaTeX grammar revision
  `7e0ecdc02926c7b9b2e0c76003d4fe7b0944f957`.

The exact packaging/provenance evidence is recorded in
[`tree-sitter-packaging.md`](tree-sitter-packaging.md).

The released package exposes modern `get_language("latex")` and `get_parser("latex")`
APIs. Thorn uses `get_parser` directly and runs the API with Python deprecation warnings
as errors in CI, removing the legacy integer-language-handle problem rather than hiding
it.

Because Tree-sitter is the production default, its runtime and grammar bundle are core
Thorn dependencies. A plain install is therefore sufficient; users do not clone a
grammar repository, run Node, or select a special backend extra.

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
- `verbatim*` classification over an already CST-owned environment span when the grammar
  represents it generically.

Neither fallback rescans the whole document or executes TeX. They normalize parser-owned
evidence rather than forming a parallel parser.

The regex backend necessarily retains handwritten raw-source scanning because it is a
compatibility backend. That code is frozen in architectural terms: new source corner
cases should be addressed through the structured substrate or explicit capability
limits, not by expanding the scanner.

## Workspace boundary above the parser

A source CST does not own expanded project occurrence semantics. `ProjectWorkspaceFacts`
sits above every frontend and owns repeated occurrence identity, include-site
relationships, expanded order, and project partiality. TexLab and LaTeXML remain
independent workspace/deeper-expansion evidence as documented in
`workspace-resolution-evaluation.md`.

Choosing Tree-sitter as the production source backend therefore does not turn it into
Thorn's mathematical authority or a complete TeX workspace engine.

## Evidence behind the cutover

Before changing the default, PR #196 evaluated the released grammar while keeping the
old runtime default. Candidate commit `9b9df9de581e98e87305e925ad58eb3ac540ffcf`
passed the warning-free packaged-runtime check, 26 frontend/differential/source-projection
tests, and the completed Tree-sitter semantic-dependency contract (64 passed, 1 skipped,
1 xfailed), together with Ruff and mypy. The same candidate also passed the Local NLP
and Lean workflows. No material regression against the previously evaluated grammar was
found.

The representative #183 measurement reported:

| Backend | Parse median | Full extraction median |
| --- | ---: | ---: |
| regex | 14.430 ms | 65.685 ms |
| pylatexenc | 22.844 ms | 54.480 ms |
| tree-sitter | 19.923 ms | 70.691 ms |

These small runtime differences are not architecturally decisive. The decisive change
from #161 is that the preferred structured backend now has a conventional released,
pinned, warning-free installation path that has passed Thorn's gate.

## Production disposition

- Keep `LatexFrontend` as the sole parser boundary.
- Use the exact released Tree-sitter identity recorded above as the production default.
- Keep regex as compatibility/differential evidence, not a parser-development target.
- Keep pylatexenc as independent conformance evidence.
- Do not add raw-source compensation to make backends agree on unsupported semantics.
- Keep source/workspace partiality explicit and fail closed on malformed source.
- Keep `ProjectWorkspaceFacts` above the CST boundary.
- Re-run frontend/provenance, workspace, #162, Local NLP, Lean, clean-install CLI, full
  pytest, Ruff, and mypy whenever the production grammar/default identity changes.
