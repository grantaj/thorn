# Tree-sitter LaTeX packaging and production identity

Issue #183 removes the last installation blocker identified by #158/#161. The rule is
not that Thorn must retain the first grammar revision it evaluated. The rule is that the
production frontend must use an exact, reproducible grammar identity that has passed
Thorn's evidence gate.

## Supported production identity

The supported combination is:

- Python runtime: `tree-sitter==0.26.0`;
- released grammar bundle: `tree-sitter-language-pack==1.14.3`;
- language-pack release tag commit:
  `df3bcc39862da6972032d7537d49b782a50a25bb`;
- LaTeX grammar source: `latex-lsp/tree-sitter-latex` at
  `7e0ecdc02926c7b9b2e0c76003d4fe7b0944f957`.

The mapping is not inferred from the LaTeX grammar's version number. The
`tree-sitter-language-pack` v1.14.3 source definition explicitly pins its `latex`
language to that exact upstream revision. Thorn records all four identities in
`thorn.frontends.tree_sitter_identity`, pins the two installed distributions in
`pyproject.toml`, and checks the installed versions in CI.

Both `tree-sitter-language-pack` and `latex-lsp/tree-sitter-latex` are MIT licensed.
The grammar remains external generated parser machinery; Thorn does not vendor or fork
its parser implementation.

Relevant upstream provenance:

- <https://github.com/xberg-io/tree-sitter-language-pack/tree/v1.14.3>
- <https://github.com/xberg-io/tree-sitter-language-pack/blob/v1.14.3/sources/language_definitions.json>
- <https://github.com/latex-lsp/tree-sitter-latex/tree/7e0ecdc02926c7b9b2e0c76003d4fe7b0944f957>

## Why the historical pin moved

The #158 evaluation used
`fa8df448fc2c0192a8c2f8cfc97de53cb2b4ecb9`. That revision was pinned because it was
the exact revision Thorn had tested, not because it was intended to be immutable.
It lacked a frictionless released Python installation path and required CI to clone the
grammar, run a pinned Node Tree-sitter generator, and install the generated local
package.

PR #195 correctly refused to substitute a differently packaged grammar without evidence.
After #195, issue #183 was reopened with the clarified invariant: a different released
revision may become the supported pin only after passing the same Thorn conformance gate.

`tree-sitter-language-pack==1.14.3` still packages LaTeX revision `7e0ecdc...`. PR #196
therefore evaluated that released grammar as a genuinely different candidate rather than
assuming equivalence with `fa8df448...`.

## Candidate evidence

The isolated candidate commit `9b9df9de581e98e87305e925ad58eb3ac540ffcf`
changed only the grammar/runtime loading and packaging seam; the Thorn normalization
logic below `_load_parser()` was unchanged and `DEFAULT_FRONTEND_NAME` remained `regex`.
That made failures attributable to the packaged grammar/runtime path rather than to a
simultaneous default cutover.

On GitHub Actions run `32599835472`, the released candidate passed:

- ordinary wheel installation of `tree-sitter==0.26.0` and
  `tree-sitter-language-pack==1.14.3`;
- the parser API under `DeprecationWarning`-as-error;
- frontend/differential/source-projection conformance: 26 passed;
- completed Tree-sitter semantic-dependency contract: 64 passed, 1 skipped, 1 xfailed;
- focused Ruff;
- mypy over all 78 source files.

The same candidate commit also passed the Local NLP and Lean workflows. No material
regression relative to the previously evaluated revision was found, so the issue's
stop-before-bespoke-machinery condition did not apply.

The measured 40-pair, 7,231-byte synthetic fixture gave a Tree-sitter parse median of
19.923 ms and full extraction median of 70.691 ms over 20 iterations. The installed
`tree-sitter` distribution occupied 2,078,154 bytes and the language pack 5,825,300
bytes on that Linux runner. These measurements are operational evidence, not acceptance
thresholds.

## Runtime/deprecation resolution

Thorn no longer converts `tree_sitter_latex.language()` through the legacy integer
language-handle path. The adapter uses the released bundle's
`get_parser("latex") -> tree_sitter.Parser` API directly. CI also exercises
`get_language("latex")` and `get_parser("latex")` with Python deprecation warnings
promoted to errors.

This resolves the binding deprecation rather than suppressing its warning. No Thorn
compatibility shim, grammar downloader, generated-source mirror, or patched parser is
needed.

## Production/default decision

Tree-sitter is now the production source frontend:

```text
DEFAULT_FRONTEND_NAME = tree-sitter
```

Because a production default must exist after a plain installation, `tree-sitter` and
`tree-sitter-language-pack` are core Thorn dependencies rather than optional runtime
requirements. The historical `treesitter` extra name remains as an empty compatibility
extra so existing `thorn-math[treesitter]` install commands continue to work without
selecting a different dependency set.

The regex frontend remains available for compatibility and differential evidence. This
cutover is not permission to grow the regex scanner, move workspace ownership into the
CST, or move mathematical authority/scope into Tree-sitter.

## Production evidence gate

The default-cutover contract is deliberately broader than the parser unit tests. CI must
keep the following green on the packaged production identity:

1. frontend/differential and source-region/provenance conformance;
2. the completed semantic-dependency/#162 contracts;
3. workspace occurrence/order/partiality evaluation;
4. Local NLP contract;
5. Lean contract;
6. a clean built-wheel installation with no Tree-sitter extra, followed by ordinary CLI
   use of the default frontend;
7. full pytest, Ruff and mypy;
8. zero provider/model calls.

The workspace workflow's path filters include frontend/default and dependency changes so
a future parser/default change cannot silently skip that gate.

## Architectural boundary

Tree-sitter supplies generic source structure only. Parser-native objects remain inside
`thorn.frontends.tree_sitter`; downstream code receives Thorn-owned `LatexFrontend`
models and exact normalized `SourceSpan` data. `ProjectWorkspaceFacts` remains above the
source-CST boundary and owns repeated occurrence identity, include relationships,
expanded order, and project partiality. Thorn continues to own mathematical authority,
scope, ambiguity, semantic dependency identity, closure, and review/formalisation IR.

Valid but unsupported dynamic source may remain explicitly unresolved. Malformed source
may fail closed. Thorn does not add raw-source scanners to make the released grammar
pretend to execute TeX.

No provider/model calls were used in the #183 packaging or cutover evaluation.
