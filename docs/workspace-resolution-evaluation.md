# Workspace/project-resolution evaluation (#159)

## Architectural boundary first

`ProjectWorkspaceFacts` in `src/thorn/workspace.py` is the proposed Thorn-owned normalized boundary. It records only generic source/project facts: project root, expanded source occurrences, include sites and resolution state, label/reference locations, and diagnostics. A source **occurrence** has its own identity and ordinal, so repeated inclusion of one path is representable without collapsing provenance.

The boundary deliberately does not contain mathematical authority, declaration recognition, semantic scope, shadowing, dependency materiality, or Proof IR. Those remain Thorn decisions downstream. A backend may return `partial` for valid but unsupported/dynamic project structure, or `source_error` for malformed source; downstream code must not invent missing project facts.

## Fixture matrix and method

`eval/workspace_resolution/cases.json` is a public, declarative fixture corpus materialized by the keyless differential harness covering one-level/nested includes, parent/child declaration order, return-to-parent order, cross-include shadowing, repeated inclusion, cycles, missing files, cross-file references, fake syntax in comments/verbatim, macro-mediated structure, deliberately dynamic structure, and malformed input.

The harness runs each backend twice and hashes canonical output to check determinism. It records runtime as integration-cost evidence but does not use timing as a correctness criterion.

### Current Thorn baseline

The baseline calls the production `RegexLatexFrontend.parse_project` and normalizes its observable file/macro/diagnostic facts. The current frontend uses a path-level `seen` set and breadth-first pending queue. Therefore it discovers dependency files, but cannot itself represent repeated source occurrences or a true expanded occurrence stream. That is acceptable evidence for #159; this tranche does not repair it by adding another scanner.

### TexLab

The adapter is an LSP client, not copied TexLab internals. It opens the fixture workspace and obtains `.tex` dependency relationships from `textDocument/documentLink`, diagnostics from `publishDiagnostics`, and cross-file definition results from explicit fixture probes. It intentionally does not scan raw TeX to recover relationships TexLab does not expose.

TexLab is pinned to v5.26.0 in CI. Upstream is GPL-3.0 and distributed as a standalone server; runtime use therefore means a separate process and packaging a roughly tens-of-MB binary rather than importing a Python library. The process boundary is technically clean but material for installation and startup cost.

### LaTeXML

The adapter invokes LaTeXML as a separate process and records conversion success/failure, output digest, occurrence/order sentinels in the expanded XML, and whether source filenames survive in emitted XML. It does not reverse-engineer LaTeXML internals or treat converted XML as mathematical authority.

CI uses Ubuntu 24.04's LaTeXML 0.8.8 package. Upstream LaTeXML is public-domain software (with its license described as CC0-equivalent); licensing is therefore not the obstacle to runtime adoption. The practical cost is its Perl/XML/TeX dependency stack and conversion subprocess, so it is intentionally evaluated as a heavier high-fidelity oracle rather than assumed suitable for normal runtime.

## Responsibility/disposition matrix

This table is completed from the checked-in harness plus the CI evidence artifact produced by the PR.

| Responsibility | Current Thorn | TexLab | LaTeXML | Recommended ownership |
|---|---|---|---|---|
| Project root / dependency graph | partial, path-centric | evaluate LSP exposure | conversion-root only | normalized Thorn fact; external backend supplies evidence |
| Include site provenance | macro source span | document-link range | evaluate locator survival | Thorn normalized fact, never inferred downstream |
| Expanded occurrence order | not represented directly | evaluate ordered links/traversal suitability | expanded conversion is useful oracle | Thorn boundary owns representation; backend supplies facts |
| Repeated inclusion | collapsed by `seen` | evaluate repeated links | expansion oracle | occurrence identity is mandatory |
| Cycles / missing files | missing diagnostic; cycles collapse silently | evaluate diagnostics/links | evaluate fail/partial behavior | explicit partial diagnostic |
| Cross-file references | syntax facts only | definition/reference LSP is promising | resolved XML/reference oracle | generic reference facts only |
| Dynamic/macro project structure | unsafe to guess | evaluate explicit coverage | expansion oracle where supported | unresolved is valid result |
| Mathematical authority/scope | Thorn | **never** | **never** | Thorn only |

## Candidate role decision

The final role assignment is evidence-driven and should be read with the PR's `workspace-resolution-evidence` artifact:

- **TexLab:** candidate **optional backend / development-conformance oracle**, not yet production runtime substrate. Its LSP boundary is reproducible and already models workspace relationships and references, but #159 requires evidence that the externally accessible model preserves Thorn's required occurrence/order/provenance facts without Thorn reconstructing TexLab internals. GPL-3.0 and a persistent subprocess are also meaningful runtime-adoption costs.
- **LaTeXML:** **development/conformance oracle / benchmark reference**. It is valuable precisely where actual TeX expansion and macro state matter, but the heavyweight TeX/Perl/XML stack and conversion model are a poor default runtime shape for Thorn. If source locators or inclusion boundaries are not preserved adequately, use it only for behavioral oracle comparisons rather than normalized provenance.
- **Current Thorn workspace traversal:** compatibility baseline only. Do not grow it into a more complete TeX interpreter. Its repeated-inclusion/path-dedup limitation is a concrete reason the normalized boundary must be richer than `ParsedProject.files`.

No production workspace backend is changed by this evaluation. #160 and #161 remain separate tranches.
