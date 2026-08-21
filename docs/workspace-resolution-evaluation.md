# Workspace/project-resolution evaluation and production disposition

This document records the #159 workspace-tooling evaluation and the production outcome
of #161. The evaluation compared current Thorn behavior with TexLab and LaTeXML; the
consolidation then made Thorn's normalized `ProjectWorkspaceFacts` boundary the
production source of project occurrence/order facts.

## Production boundary after #161

`ProjectWorkspaceFacts` in `src/thorn/workspace.py` is no longer merely a proposed
contract. `latex.extract_project()` builds it for every parsed project and downstream
semantic/result ordering consumes it through `ProjectPositionLookup`.

The boundary contains generic source/project facts only:

- caller-selected main/root file;
- expanded `SourceOccurrence` records with distinct occurrence identity and ordinal;
- `IncludeSite` identity, parent occurrence, exact source provenance, written and
  resolved target where available, resolution state, and child occurrence;
- normalized label/reference source facts;
- explicit `resolved`, `partial`, or `source_error` state and diagnostics.

It deliberately excludes mathematical authority, declaration recognition, semantic
scope, shadowing, dependency materiality, transitive semantic closure, and Proof IR.
Those remain Thorn decisions downstream.

## Why occurrence identity matters

A physical path is not a project occurrence. If the same file is included twice, its
source statements appear at two different positions in the expanded document and may
therefore see different mathematical authority.

The production workspace builder preserves those occurrences separately. Result
ordering and prose visibility/shadowing consume the same normalized project-position
facts instead of maintaining private include walks or lexical path ordering.

The current theorem/result IR is still path-level. When repeated appearances of the
same physical result would resolve to different semantic contexts, Thorn deliberately
fails closed rather than selecting one occurrence arbitrarily. A path-level result may
collapse repeated occurrences only when their relevant semantic contexts agree.

## Partiality and failure

Workspace resolution does not attempt complete TeX execution.

- complete static project structure is resolved;
- missing included files remain explicit missing/partial evidence with exact include
  provenance;
- include cycles remain explicit rather than disappearing through path deduplication;
- valid but unsupported or macro-generated/dynamic structure may remain `partial`;
- malformed source may become `source_error` and invalidate dependent project facts.

Downstream mathematical authority must not infer project order through a gap in this
boundary. Explicit loss of capability is safer than invented source order.

## #159 fixture matrix

The public differential matrix under `eval/workspace_resolution/` covers:

- one-level and nested includes;
- declaration before/after includes;
- parent declaration with theorem in child;
- child declaration followed by theorem after return to parent;
- redefinition/shadowing across include boundaries;
- repeated inclusion;
- include cycles;
- missing include;
- cross-file labels/references;
- fake syntax in comments/verbatim;
- static and macro-mediated project forms;
- malformed editing-state input.

The evaluation ran each backend twice and compared canonical evidence for
reproducibility. It was entirely keyless.

## Candidate dispositions

### TexLab

**Role: optional-backend candidate and development/conformance oracle; not the default
runtime substrate.**

Useful observed evidence included exact document-link ranges/targets for ordinary
includes, distinct links for repeated include sites, complete graph edges for the cycle
fixture, and cross-file `\ref` definition lookup.

The public LSP surface did not itself provide Thorn's required expanded occurrence
stream, explicit missing-target state, or cycle diagnostics. Macro-mediated coverage was
inconsistent across simple fixtures, and malformed source could produce both a syntax
diagnostic and a usable-looking link. A Thorn adapter would therefore still have to
normalize those facts behind `ProjectWorkspaceFacts` and let source-error state dominate.
TexLab also adds a standalone GPL-3.0 process/distribution boundary. The #159 fresh
process measurement was roughly 830 ms median.

### LaTeXML

**Role: development/conformance oracle and benchmark/reference; not a normal runtime or
optional workspace backend.**

LaTeXML gave useful expansion-order evidence, including nested order, repeated
inclusion, and both tested macro-mediated cases. Under the evaluated invocation,
however, emitted XML did not retain the exact source-file/include-site provenance Thorn
requires; the cycle case ran until the bounded timeout; missing and malformed fixtures
converted successfully rather than producing Thorn's fail-closed state. The process and
Perl/XML/TeX stack are also comparatively heavy. The #159 simple conversion measurement
was roughly 757 ms median.

### Frontend static traversal

Each `LatexFrontend` may discover physical files and static include syntax needed to
construct a parsed project. That discovery is **not** the semantic source of expanded
project order. `ProjectWorkspaceFacts` owns occurrence expansion and resolution state.
The regex frontend's path-level `seen` traversal is therefore a compatibility loader,
not an architecture to extend into TeX execution.

## Responsibility matrix after consolidation

| Responsibility | Production owner |
| --- | --- |
| Physical source syntax / include macro provenance | `LatexFrontend` |
| Expanded occurrence identity and order | `ProjectWorkspaceFacts` |
| Include-site resolution/partiality | `ProjectWorkspaceFacts` |
| Result ordering by project position | `ProjectPositionLookup` consumer in extraction |
| Mathematical declaration authority | Thorn semantic authority policy |
| Forward visibility and shadowing | Thorn policy over `ProjectPosition` |
| Semantic dependency identity/closure | canonical Thorn semantic state |
| TexLab/LaTeXML comparison | development/evaluation harness only |

## Raw-source responsibility inventory

No separate workspace raw-TeX scanner is retained in the semantic layer. Static include
syntax comes from normalized frontend macros. The workspace builder orchestrates those
facts into occurrences; it does not rescan the manuscript or expand arbitrary TeX
macros.

The regex compatibility frontend still scans raw source to produce its normalized macro
facts. That responsibility belongs to the frontend and is retained only because regex
remains the compatibility default pending Tree-sitter grammar packaging. It must not be
expanded in workspace or semantic code to recover unsupported dynamic structure.

## Final #161 disposition

- `ProjectWorkspaceFacts` is the authoritative production boundary for project
  occurrence/order facts.
- Repeated inclusions preserve distinct occurrence identity.
- Result ordering and semantic scope consume the same normalized positions.
- Dynamic/unsupported project relationships remain explicit partiality rather than
  guessed TeX execution.
- TexLab remains optional/oracle evidence; LaTeXML remains expansion/reference evidence.
- Neither external workspace tool becomes mathematical authority.
- No project-order reconstruction belongs inside semantic review.

A future richer workspace backend can replace how these normalized facts are supplied
without changing Thorn's mathematical policy or canonical IR.
