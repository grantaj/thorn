# Tree-sitter LaTeX packaging and production-default gate

This note records the packaging investigation for issue #183. It is deliberately
separate from the source-frontend evaluation: #158 established Tree-sitter as Thorn's
preferred source-structure substrate, while #183 asks whether the exact evaluated
runtime can be installed and supported as an ordinary production dependency.

## Supported identity under evaluation

The evaluated combination is:

- Python runtime: `tree-sitter==0.26.0`;
- grammar source: `latex-lsp/tree-sitter-latex` 0.6.0 at
  `fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9`;
- generation used by Thorn's reproducible CI lane: `tree-sitter-cli@0.24.7`;
- upstream grammar license: MIT.

The source revision is part of the contract. A package containing another 0.6.0
revision is not the parser that Thorn evaluated merely because the package version is
the same.

## Packaging candidates checked on 2026-08-23

### Upstream grammar repository

The evaluated source revision does not contain generated `src/parser.c`. Installing it
from source therefore still requires a Tree-sitter generator. The upstream 0.6.0 tag is
`7e0ecdc02926c7b9b2e0c76003d4fe7b0944f957`, not the evaluated revision, so replacing
the revision with the release tag would weaken the existing pin.

Upstream source and license:

- <https://github.com/latex-lsp/tree-sitter-latex>
- <https://github.com/latex-lsp/tree-sitter-latex/blob/fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9/LICENSE>

### `tree-sitter-language-pack`

`tree-sitter-language-pack` is the strongest conventional packaging candidate because
it publishes platform wheels and manages precompiled grammars. The latest version on
the public PyPI index checked for this issue, 1.13.5, does **not** package the evaluated
LaTeX source identity: its release source definition pins LaTeX to
`7e0ecdc02926c7b9b2e0c76003d4fe7b0944f957`.

The project's current unreleased source definition has since moved to
`fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9`, but depending on an unreleased moving
branch would replace one reproducibility problem with another. Thorn should reconsider
this route when a released package records the evaluated revision (or when Thorn
deliberately evaluates and pins a newer released revision).

Relevant source:

- <https://pypi.org/project/tree-sitter-language-pack/1.13.5/>
- <https://github.com/xberg-io/tree-sitter-language-pack/blob/55cb1d8b98bed6a604f53ab0c21dfbee600c7e0c/sources/language_definitions.json>

`tree-sitter-language-pack` is MIT licensed.

### Generated-source mirror

`Willie169/tree-sitter-latex` currently commits a generated `src/parser.c` and records
`fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9` in its `commit` file, so it is useful
independent evidence that the evaluated grammar can be generated without changing its
source semantics. It is not a production dependency for Thorn:

- it is not a released Python distribution on a public package index;
- its generation workflow uses `tree-sitter/setup-action@v2` rather than pinning the
  exact generator version used by Thorn's evaluation;
- its Python binding still returns the language pointer through `PyLong_FromVoidPtr`.

The last point matters with `tree-sitter==0.26.0`: modern generated Python bindings
return a `PyCapsule` named `tree_sitter.Language`, while the integer-language-handle
path is deprecated. Thorn will not suppress that warning and call the compatibility
question solved.

Mirror provenance:

- <https://github.com/Willie169/tree-sitter-latex>
- generated-mirror revision checked: `ab5121def07b340c2ecf382808efd3bb3cc6c702`;
- generated `src/parser.c` blob checked: `1ca6bd199796acb93cc265c24c2f00f76ca1235f`;
- the mirror and upstream grammar are MIT licensed.

A direct VCS/URL dependency on this mirror was rejected. Public Python indexes should
not accept direct references in uploaded distribution metadata, and making Thorn's
normal package depend on an unpublished Git checkout is not a frictionless production
install path.

### Thorn-owned vendoring or downloader

Copying the generated parser into Thorn, maintaining a patched grammar fork, or adding
a Thorn-specific grammar downloader would make the dependency problem look solved by
moving generic parser/distribution machinery into Thorn. #183 explicitly rules that
out. Generated parser logic must remain an external parser dependency or build artifact,
not become a second Thorn-owned LaTeX implementation.

## Runtime/default decision

The packaging gate is **not satisfied as of 2026-08-23**. `thorn-math[treesitter]`
therefore continues to install the supported Tree-sitter Python runtime only, and
`DEFAULT_FRONTEND_NAME` remains `"regex"`.

This is not a reversal of the source-substrate decision. Tree-sitter remains the
preferred source-structure backend and the dedicated CI lane continues to exercise the
exact grammar by generating it from the pinned source revision. The production default
stays on the compatibility frontend because there is no ordinary installable artifact
that simultaneously has:

1. the evaluated grammar source identity;
2. a reproducible generated-parser/build identity;
3. a modern non-deprecated Python language binding; and
4. public-package-compatible installation semantics.

The end-to-end blockers found after #161 (#185–#188) have been repaired. This issue also
identified a parser-lifecycle hazard independent of packaging: a module-level cached
default frontend would become a shared `tree_sitter.Parser` if the default changed.
Thorn now resolves the default frontend at each extraction call instead.

## Exit criteria for a future cutover

Reconsider the default when a conventional released artifact provides the exact
supported grammar identity (or after deliberately re-evaluating a newer released
identity), pins or records its generated-parser build provenance, and exposes the
modern capsule-based Python binding without compatibility warnings. At that point run
the complete #183 cutover gate unchanged: frontend/differential, source provenance,
semantic-dependency, workspace occurrence/partiality, Local NLP, Lean, clean-package
CLI, full pytest/Ruff/mypy, and zero provider/model calls.

No provider/model calls were used in this packaging investigation.
