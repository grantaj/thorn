# Workspace/project-resolution evaluation (#159)

## Architectural boundary first

`ProjectWorkspaceFacts` in `src/thorn/workspace.py` is the proposed Thorn-owned normalized boundary. It records only generic source/project facts: project root, expanded source occurrences, include sites and resolution state, label/reference locations, and diagnostics. A source **occurrence** has its own identity and ordinal, so repeated inclusion of one path is representable without collapsing provenance.

The boundary deliberately does not contain mathematical authority, declaration recognition, semantic scope, shadowing, dependency materiality, or Proof IR. Those remain Thorn decisions downstream. A backend may return `partial` for valid but unsupported/dynamic project structure, or `source_error` for malformed source; downstream code must not invent missing project facts.

This sits above the source-CST boundary established by #158. Tree-sitter remains the leading source-structure candidate; #159 does not replace or compete with that role.

## Fixture matrix and method

`eval/workspace_resolution/cases.json` is a public, declarative fixture corpus materialized by the keyless differential harness. It covers one-level and nested includes, parent/child declaration order, return-to-parent order, cross-include shadowing, repeated inclusion, cycles, missing files, cross-file references, fake syntax in comments/verbatim, static and dynamic macro-mediated structure, and malformed input.

The harness runs each backend twice and hashes canonical output after removing timing. CI evidence from commit `8d88635bebde440ebf5b63d15b44572ce34af04a`, workflow run `32426486532`, produced artifact `workspace-resolution-evidence` with digest `sha256:47b69122d8b312703ce507ab2701fcc0ae0ad79d8bae19f30461198debd37b2a`. All three backends were deterministic over the matrix after final-state LSP diagnostics were normalized.

The observed median cold-process/evaluation costs on the Ubuntu 24.04 CI runner were approximately 1.3 ms for current Thorn, 830 ms for a fresh TexLab process, and 757 ms for a fresh LaTeXML conversion. These measurements are integration-cost evidence only; a persistent TexLab server could amortize startup.

### Current Thorn baseline

The baseline runs `RegexLatexFrontend.parse_project` through the current production `normalize_project_structure` safety layer from #170, then records its observable source/project evidence. The current frontend still uses path-level `seen` identity and a pending-file queue. It therefore discovers reachable physical files but cannot represent two occurrences of the same file or a true expanded occurrence stream.

The #170 normalization does correctly fail closed for the tested malformed and macro-mediated direct-input cases by emitting `project_partiality`, and it prevents fake verbatim input syntax from becoming a reachable project file. The raw frontend macro evidence can still contain the fake macro occurrence; it is source syntax evidence, not a normalized project relationship. Missing static files produce an explicit `missing_file` diagnostic. Cycles are path-deduplicated without an explicit cycle diagnostic.

This tranche does not repair those limitations by growing another TeX/workspace scanner.

### TexLab v5.26.0

The adapter is an LSP client, not copied TexLab internals. It obtains `.tex` relationships from `textDocument/documentLink`, diagnostics from `publishDiagnostics`, and cross-file definition results from explicit probes.

Observed behavior:

- one-level and nested includes produced exact document-link source ranges and targets;
- repeated inclusion produced two distinct links at the two include sites, preserving include-site occurrence evidence even though LSP does not directly expose Thorn's expanded occurrence stream;
- the cycle fixture exposed all three graph edges but no cycle diagnostic;
- a missing target produced neither a document link nor a diagnostic, so absence cannot safely be interpreted as either "no include" or "missing include" without other source evidence;
- cross-file `\ref` definition lookup resolved to the defining file and line;
- fake `\input` syntax inside verbatim produced no document link, but a fake `\ref` inside verbatim still produced an `Undefined reference` diagnostic;
- the simple `\def`-mediated dynamic include resolved to `part.tex`, while the simple `\newcommand`-mediated static include did not, demonstrating inconsistent macro-mediated coverage at the public LSP boundary;
- malformed `\input{{part}` produced a syntax diagnostic but also a link to `part.tex`, so a Thorn adapter must fail closed on source-error state before trusting other workspace facts.

TexLab is GPL-3.0 and is distributed as a standalone server. Runtime use would therefore add a separate executable/process and distribution/licensing consideration rather than a normal Python import. The process boundary is technically clean and the tested evidence was deterministic.

### LaTeXML 0.8.8

The adapter invokes LaTeXML as a separate process and observes conversion success/failure, expanded-order sentinels, repeated marker counts, output digest, and whether source filenames survive in emitted XML. It does not reverse-engineer LaTeXML internals or infer missing provenance with a Thorn scanner.

Observed behavior:

- one-level, nested, parent/child, return-to-parent, and shadowing fixtures preserved the expected expanded textual order;
- repeated inclusion emitted the included marker twice;
- both tested macro-mediated includes expanded successfully, including the cases current Thorn marks partial and TexLab handles inconsistently;
- emitted XML contained none of the fixture source filenames under this invocation, so it does not provide the exact source-file/include-site provenance required by the normalized boundary;
- the cycle fixture did not terminate and was deterministically cut off by the harness's fixed five-second timeout;
- the missing-file fixture returned success and retained text before and after the missing include without an explicit error in the observed output;
- the malformed-input fixture also returned success rather than providing the fail-closed source error Thorn requires.

Upstream LaTeXML is public-domain software with its license described as CC0-equivalent. Licensing is not the obstacle; the practical costs are its Perl/XML/TeX dependency stack, conversion subprocess, provenance gap, and unsafe behavior for Thorn's cycle/missing/malformed requirements.

## Responsibility/disposition matrix

| Responsibility | Current Thorn | TexLab | LaTeXML | Recommended ownership |
|---|---|---|---|---|
| Project root | caller-selected root | workspace root is client-supplied | conversion root is caller-supplied | Thorn normalized fact |
| Include-site provenance | source macro spans; #170 filters traversal | strong: exact document-link ranges | insufficient in emitted XML | Thorn fact populated only from evidence with exact provenance |
| Expanded occurrence order | not represented | graph/site evidence, not direct expansion stream | strong behavioral oracle | Thorn boundary owns explicit occurrence stream |
| Repeated inclusion | physical file collapsed; sites remain visible as syntax | two distinct include-site links | expands twice | occurrence identity is mandatory; path identity is insufficient |
| Cycles | silently path-deduplicated | graph edges present; no cycle diagnostic | hangs until bounded timeout | explicit partial/cycle state required |
| Missing files | explicit `missing_file` | no link and no diagnostic | conversion succeeds silently in fixture | explicit partial/missing state required |
| Cross-file references | syntax facts only | strong definition result in fixture | expansion/reference behavior useful as oracle | generic reference facts only; authority remains Thorn |
| Macro-mediated structure | #170 explicitly partial | inconsistent across two simple forms | strong expansion oracle | unsupported structure must stay explicitly unresolved |
| Malformed source | #170 explicitly partial/fail-closed | diagnostic plus still-emitted link | conversion succeeds | source error dominates and invalidates dependent facts |
| Mathematical authority/scope | Thorn | **never** | **never** | Thorn only |

## Evidence-based disposition by role

**TexLab: optional backend candidate and development/conformance oracle; defer as default runtime substrate.** Its public LSP surface gives useful exact include-site ranges, repeated-site evidence, graph edges, and cross-file definition resolution, and was deterministic. But it does not by itself expose Thorn's required expanded occurrence stream, does not distinguish missing targets or cycles explicitly, has inconsistent macro-mediated coverage, and can emit usable-looking links alongside malformed-source diagnostics. A future adapter could normalize its evidence behind `ProjectWorkspaceFacts`, provided Thorn preserves explicit partial/source-error states and never reconstructs unsupported semantics with bespoke scanners. GPL-3.0, executable packaging, and process startup are additional runtime costs.

**LaTeXML: development/conformance oracle and benchmark/reference; reject as normal runtime or optional workspace backend for now.** It is the strongest tested oracle for actual TeX expansion order, repeated inclusion, and macro state, and its results were deterministic. However, the tested conversion path loses the exact source provenance Thorn requires, a cycle hangs, and missing/malformed inputs do not fail closed. Its heavier process/dependency stack reinforces the same conclusion. It is valuable for differential tests of expansion behavior, not as the source of canonical workspace provenance.

**Current Thorn workspace traversal: compatibility baseline only.** Preserve the #170 partiality guard while #159/#161 architecture evolves, but do not grow the path-centric traversal into a TeX interpreter. Its repeated-inclusion and cycle limitations are direct evidence for the richer occurrence-aware normalized boundary.

## Recommendation

Adopt `ProjectWorkspaceFacts` as the project/workspace contract to target in later consolidation, without selecting a production implementation in #159. Project structure/order and provenance belong in this boundary; mathematical authority, semantic scope, shadowing, materiality, and Proof IR remain downstream Thorn responsibilities.

Use TexLab as a promising optional evidence backend/conformance oracle where its LSP facts are explicit. Use LaTeXML as an expansion-behavior oracle. Continue to allow valid but unsupported dynamic structure to become explicit `partial`, and malformed source to become an author-facing fail-closed source error. Do not add bespoke scanners to fill gaps in either external candidate.

No production workspace backend is changed by this evaluation. #160 and #161 remain separate tranches.
