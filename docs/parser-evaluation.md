# LaTeX frontend A/B evaluation

Issue #16 evaluates parser backends behind Thorn's source-preserving `LatexFrontend` contract. Parser choice is deliberately reversible: mathematical interpretation must not depend on backend-specific node classes.

## Backends

### `regex`

Thorn's compatibility frontend from #15. It is small, dependency-free, and intentionally pragmatic. It remains the default while this evaluation is in progress.

### `pylatexenc`

A second frontend backed by `pylatexenc.latexwalker.LatexWalker`.

For this experiment Thorn uses `pylatexenc==2.10`, the current stable 2.x release, behind an optional `thorn-math[pylatexenc]` dependency. The 3.x line remains pre-release on PyPI, so this experiment does not make a pre-release parser part of Thorn's normal installation.

The adapter uses pylatexenc for node/environment/math parsing and source positions. Thorn adds only normalization required by the frontend contract, such as known signatures for labels/references/newtheorem and conservative optional-argument handling for custom theorem-like environments.

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

A candidate backend must pass this suite before it can be considered interchangeable for Thorn's current mathematical analysis.

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

`current` remains an alias for the default backend.

## Evaluation dimensions

The final #16 disposition should record:

| Dimension | regex | pylatexenc |
| --- | --- | --- |
| Shared conformance | pending CI | pending CI |
| #12 graph compatibility | pending CI | pending CI |
| Source fidelity | pending CI | pending CI |
| Malformed-input recovery | pending CI | pending CI |
| Multi-file handling | pending CI | pending CI |
| Unknown macro policy | greedy brace groups | conservative without signature |
| Runtime dependency | none | optional pure-Python dependency |
| Adapter complexity | compatibility baseline | to measure from landed adapter |
| Incremental parsing | no | no (LatexWalker reparses file) |
| Performance | pending benchmark | pending benchmark |

## Default-backend decision rule

Do not change the default merely because a library parser sounds more sophisticated. A switch should require evidence that the candidate materially improves correctness/recovery/source fidelity without unacceptable packaging or performance cost.

Until the A/B evidence is complete, `regex` remains `current`.
