# Semantic-dependency architecture

This document is the post-#161 architecture record for Thorn's semantic-dependency
substrate. It supersedes the pre-consolidation ownership audit originally written for
#157. Historical evaluation details remain in the parser, workspace, prose-declaration,
and conformance documents; this file describes the production boundaries after slices
A-F and the Slice G backend disposition.

## Core rule

Generic source, workspace, and linguistic machinery may supply normalized facts or
candidates. Thorn alone decides mathematical authority, scope, visibility, shadowing,
dependency identity, materiality, ambiguity policy, transitive review closure, and the
canonical mathematical IR.

A lower layer may fail or report partiality. Thorn must not repair that uncertainty by
inventing source structure or mathematical authority.

## Production pipeline

```text
LaTeX source
    |
    v
LatexFrontend
    |  normalized macros, environments, math, source regions,
    |  diagnostics, exact SourceSpan
    v
ParsedProject
    |
    +--> ProjectWorkspaceFacts
    |      occurrence identity, include sites, expanded order,
    |      labels/references, resolved/partial/source-error state
    |
    +--> ResultRegion / theorem-source facts
    |
    `--> reversible LinguisticProjection
             |
             v
        LinguisticFrontend
             |
             v
        ProseDeclarationInventory
        non-authoritative candidates + exact term/payload provenance
             |
             v
        Thorn mathematical authority policy
             |
        visibility / shadowing over ProjectPosition
             |
        semantic dependency identity + canonical closure
             v
        Symbol IR / canonical Proof IR
             |
        +----+----------------------+----------------+
        |                           |                |
        v                           v                v
      reports                    Lean          thorn-proof/1
                                                   |
                                           bounded source rescue
```

`latex.extract_project()` is the source-to-IR composition root. Backend-native
Tree-sitter nodes, pylatexenc nodes, spaCy documents/tokens, TexLab LSP values, and
LaTeXML XML never cross their adapters into canonical mathematical state.

## Source structure: `LatexFrontend`

`LatexFrontend` owns parser-neutral source facts only. `FrontendFile` exposes exact raw
source, normalized macros/environments/math, `FrontendRegion` source roles, region
completeness, and diagnostics. `DOCUMENT_TEXT` means syntactically eligible prose; it
does not mean mathematical declaration or authority.

Semantic code consumes those facts through reversible source projections. It no longer
rescans raw TeX to rediscover comments, preamble/body boundaries, verbatim-like regions,
or mathematical placeholders.

### Backend/default disposition

Slice G makes the distinction explicit in `thorn.frontends`:

- `DEFAULT_FRONTEND_NAME = "regex"`;
- `PREFERRED_FRONTEND_NAME = "tree-sitter"`.

Tree-sitter is the preferred source-structure substrate on the empirical evidence from
#158 and the completed #162 contracts. It is **not** the production default yet because
the pinned `tree-sitter-latex` grammar still lacks a frictionless reproducible normal
installation path: the evaluated revision requires source checkout, parser generation
with Node/tree-sitter-cli, and a local build. `thorn-math[treesitter]` therefore installs
the Python runtime but cannot by itself establish the exact evaluated grammar runtime.

That is a packaging blocker, not a parser-quality rejection. Regex remains the
compatibility default until a separately reviewed packaging/default cutover satisfies
the same frontend, workspace, semantic-dependency, Local NLP, and Lean contracts. New
LaTeX corner cases must not be used as a reason to grow the regex compatibility scanner.

`pylatexenc` remains an independent parser/conformance backend. Tree-sitter remains the
leading explicit backend and differential lane.

## Workspace/project facts: `ProjectWorkspaceFacts`

`build_project_workspace_facts()` is the production normalized source of expanded
project occurrence/order facts. It exposes distinct `SourceOccurrence` identity,
`IncludeSite` provenance, deterministic expanded order, and explicit resolution state.
`ProjectPositionLookup` is the shared ordering/position consumer used by result ordering
and semantic authority/scope.

Repeated inclusion is occurrence-sensitive even when physical file paths are equal.
Missing children, cycles, malformed source, and unsupported/dynamic project structure
remain explicit rather than guessed.

TexLab and LaTeXML retain their #159 roles as independent development evidence:

- TexLab: optional-backend candidate and conformance oracle, not the default runtime;
- LaTeXML: expansion/reference oracle, not a normal runtime backend.

Neither tool decides mathematical scope or authority.

## Reversible linguistic view and declaration candidates

`build_linguistic_projection()` consumes normalized source regions and replaces source
constructs such as math/reference material with typed, offset-reversible placeholders.
Every candidate can therefore map back to exact original LaTeX.

`LinguisticFrontend` supplies normalized grammatical facts. The production declaration
candidate layer in `linguistic_declarations.py` implements the deliberately small #160
hybrid over Thorn-owned `LinguisticDocument`/`LinguisticToken` values. Its output is a
`ProseDeclarationInventory` containing ambiguous, non-authoritative candidates with:

- declaration role (`definition` or `ambient`);
- exact term source;
- exact sentence source;
- exact proposed defining-payload source;
- normalized structural evidence and frontend identity;
- explicit `complete`, `reduced`, or `partial` capability.

No `LinguisticFrontend` means reduced prose-declaration capability. Structural-only mode
does not silently restore the retired #125 phrase recognizer.

## Thorn-owned authority and scope

`project_semantic_context.py` is now a mathematical-policy consumer rather than a source
parser or English parser. It consumes only normalized candidate, projection, workspace,
and result facts.

Authority promotion requires all of the following:

1. trustworthy source/project evidence;
2. a complete declaration-candidate inventory;
3. substantive defining content under the #167 fail-closed rule;
4. Thorn-owned visibility/shadowing at the exact project occurrence;
5. actual mathematical use/relevance before the declaration enters active semantic
   reachability.

Candidate-shaped grammar is never sufficient by itself. Ambiguity remains explicit.
Occurrence identity is retained in semantic declaration identity.

The current theorem/result IR is still path-level rather than occurrence-level. When a
physical result appears in repeated occurrences whose semantic contexts disagree, Thorn
fails closed instead of collapsing them to an arbitrary path-level answer. A safe
collapse is allowed only when all relevant occurrence contexts agree.

## Dependency identity and closure

Structured result dependencies and prose/symbol semantic dependencies remain distinct
canonical edge families but compose before review. Project declaration identities come
from the migrated authority state; declaration-to-declaration and result-to-declaration
uses do not rediscover relationships from nearby source text.

There is one canonical project-symbol dependency closure implementation. Result and
review ordering use the same workspace occurrence/order facts rather than private file
walks or lexical path sorting.

## Review selection

Normal Thorn review is result-level. A requested result has one canonical bounded
result-level view whether or not deterministic extraction marked any support relation
ambiguous or unresolved.

The uncertainty-focused selector remains only because it has an explicit supported
diagnostic/evaluation caller (`thorn-eval --targeted-preflight` and
`--review-context targeted`). `ReviewTargetKind.RESULT` and
`ReviewTargetKind.SUPPORT_RELATION` make that policy distinction explicit. Both views
share canonical Symbol-IR materialization and semantic closure; the targeted view is not
a second authority graph.

Provider adapters receive already-selected Thorn-owned requests. They do not traverse
the project or decide review selection.

## Canonical downstream state

Symbol IR and canonical Proof IR remain the downstream semantic authority. Reports,
source navigation, Lean projection, and `thorn-proof/1` derive from canonical state and
exact provenance.

`thorn-proof/1` remains a bounded projection. Source rescue can request only the exact
handles Thorn advertised and does not become a whole-paper fallback or a late source
parser.

## Partiality and failure policy

Thorn distinguishes:

- **valid and supported structure**: normalize and use it;
- **valid but unsupported/dynamic structure**: retain explicit partiality/unresolved
  capability;
- **malformed source**: fail closed with source-facing diagnostics;
- **ambiguous linguistic evidence**: retain a non-authoritative candidate;
- **incomplete declaration payload**: retain evidence where useful but do not promote
  authority.

The normal response to a new LaTeX or English corner case is therefore not “add a regex
inside semantic review.” The owner is determined by the boundary that lacks the fact.

## Retained hand-written grammar and raw-source responsibilities

The final #161 architecture intentionally retains a small amount of handwritten logic.
Every retained case has a bounded owner and justification:

| Responsibility | Location | Why retained |
| --- | --- | --- |
| Compatibility LaTeX scanner for macros, environments, comments, math and static includes | `frontends/regex.py` | Current production compatibility backend while Tree-sitter grammar packaging blocks a default cutover. It is not the preferred substrate and must not grow to chase parser corner cases. |
| Source-region composition for non-Tree-sitter backends | `frontend_regions.py` | Normalizes already-extracted frontend spans into one backend-neutral eligibility contract; it does not decide mathematical authority. |
| Small Tree-sitter environment-name fallback and `verbatim*` classification | `frontends/tree_sitter.py` | Operates only on CST-owned spans/nodes when the pinned grammar omits a convenient classification; it does not rescan whole source or infer TeX execution. |
| Bounded declaration anchors (`call`, `term`, `say`, `mean`) | `linguistic_declarations.py` | #160 showed broad dependency proposals had unacceptable false-candidate risk; a small lexical guard bounds grammatical proposals without deciding authority. |
| Bounded ambient prefixes and negation/attribution guards | `linguistic_declarations.py` | Explicit document-scope grammar is not safely inferred from generic dependency structure alone. Scope/authority still remain Thorn policy. |
| Result/theorem environment names and reference macro family | `latex.py` | Thorn must identify its own mathematical result units and explicit result references from normalized frontend facts; these are deliberate product semantics, not generic TeX parsing. |
| Frozen #125 phrase regex benchmark | `_frozen_declaration_benchmark.py` | Research-only reproduction of #160 evidence. It is not imported by production authority. |

The retired five-family #125 phrase recognizer, bespoke generic singular/plural term
morphology, raw semantic comment/verbatim masking, private semantic include traversal,
and selector-private closure are not production architecture.

## Ownership test for future changes

A new robustness failure should have one obvious owner:

- source/CST structure -> `LatexFrontend` / source backend;
- expanded workspace occurrence/order -> `ProjectWorkspaceFacts`;
- grammatical variation -> `LinguisticFrontend` / declaration-candidate layer;
- mathematical authority, scope, visibility, materiality -> Thorn semantic policy;
- dependency identity/closure/provenance -> canonical Thorn semantic state;
- normal vs diagnostic review breadth -> review projection policy;
- formal validity inside the supported subset -> Lean handoff.

If a proposed fix crosses those boundaries by rescanning raw TeX or rebuilding English
grammar in a semantic/review layer, it should be rejected or moved to the correct
substrate rather than accepted as a local convenience.
