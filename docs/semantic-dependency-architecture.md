# Semantic-dependency architecture

This document is the post-#161 architecture record for Thorn's semantic-dependency substrate. Historical evaluation details remain in the parser, workspace, prose-declaration, and conformance documents; this file describes the production ownership boundaries.

## Core rule

Generic source, workspace, and linguistic machinery may supply normalized facts or candidates. Thorn alone decides mathematical authority, scope, visibility, shadowing, dependency identity, materiality, ambiguity policy, transitive review closure, and canonical mathematical IR.

A lower layer may fail or report partiality. Thorn must not repair that uncertainty by inventing source structure, occurrence uniqueness, proof evidence, or mathematical authority.

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
             +--> proof claims + bounded support evidence
             |      eligible source only
             |      exact provenance + explicit uncertainty
             |
             v
        LinguisticFrontend
             |
             +--> grammatical support evidence
             |
             `--> ProseDeclarationInventory
                  non-authoritative declaration candidates
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

`latex.extract_project()` is the source-to-IR composition root. Backend-native Tree-sitter nodes, pylatexenc nodes, spaCy documents/tokens, TexLab LSP values, and LaTeXML XML never cross their adapters into canonical mathematical state.

## Source structure: `LatexFrontend`

`LatexFrontend` owns parser-neutral source facts only. `FrontendFile` exposes exact raw source, normalized macros/environments/math, `FrontendRegion` source roles, region completeness, and diagnostics. `DOCUMENT_TEXT` means syntactically eligible prose; it does not mean mathematical declaration, proof authority, or truth.

Semantic code consumes those facts through `source_projection.LinguisticProjection`. It no longer rescans raw TeX to rediscover comments, preamble/body boundaries, verbatim-like regions, or mathematical placeholders.

### Backend/default disposition

The actual runtime default is explicit and single-sourced in `thorn.frontends`:

```text
DEFAULT_FRONTEND_NAME = "regex"
```

Tree-sitter is the preferred source-structure substrate on the empirical evidence from #158 and the completed #162 contracts. That preference is an architecture disposition, not a second runtime setting. It is not the production default yet because the pinned `tree-sitter-latex` grammar still lacks a frictionless reproducible normal installation path. #183 owns that packaging/default-cutover gate.

Regex remains the compatibility default until that gate is satisfied. New LaTeX corner cases must not be used as a reason to grow the regex compatibility scanner. `pylatexenc` remains an independent parser/conformance backend.

## One reversible source-to-linguistic boundary

`build_linguistic_projection()` is the single production source-to-linguistic boundary. It consumes normalized source regions and produces an offset-preserving view with typed math/reference tokens and exact reverse provenance.

The boundary serves both declaration and proof-support semantics:

- parser-owned comments, preamble, non-document, verbatim, listing, minted and opaque regions are ineligible;
- partial region coverage fails closed;
- consumers can request contiguous eligible segments without recreating exclusion grammar;
- NLP-safe span projections derive from the same object and preserve exact source handles.

For proof-support extraction, excluded source is a hard claim boundary rather than whitespace that an eligible raw `Claim` may span across. Therefore excluded bytes cannot become claims, support edges, canonical Proof-IR nodes, or bounded source-rescue material.

The former `semantic_projection.py` path is retired; production semantics no longer has a second source-to-NLP representation.

## Workspace/project facts: `ProjectWorkspaceFacts`

`build_project_workspace_facts()` is the normalized source of expanded project occurrence/order facts. It exposes distinct `SourceOccurrence` identity, `IncludeSite` provenance, deterministic expanded order, and explicit resolution state. `ProjectPositionLookup` is the shared ordering/position consumer used by result ordering and semantic authority/scope.

Repeated inclusion is occurrence-sensitive even when physical file paths are equal. Missing children, cycles, malformed source, and unsupported/dynamic project structure remain explicit rather than guessed.

Structured result references consume occurrence-level workspace multiplicity before path-level dependency identity is allowed to collapse. One physical theorem or reference site is not evidence of project uniqueness. Repeated or partial occurrence state fails closed unless all relevant occurrences establish the same single target.

TexLab and LaTeXML retain their #159 roles as independent development evidence/oracles; neither decides mathematical scope or authority.

## Declaration candidates and Thorn-owned authority

`LinguisticFrontend` supplies normalized grammatical facts. The production declaration-candidate layer in `linguistic_declarations.py` implements the deliberately small #160 hybrid over Thorn-owned `LinguisticDocument`/`LinguisticToken` values. Its output is a `ProseDeclarationInventory` containing ambiguous, non-authoritative candidates with exact term/sentence/payload provenance and explicit `complete`, `reduced`, or `partial` capability.

No `LinguisticFrontend` means reduced prose-declaration capability. Structural-only mode does not silently restore the retired #125 phrase recognizer.

`project_semantic_context.py` is mathematical policy rather than a source or English parser. Authority promotion requires trustworthy source/workspace evidence, a complete candidate inventory, substantive defining content under #167, Thorn-owned visibility/shadowing at the exact project occurrence, and actual mathematical use/relevance.

Structured declaration recognition is likewise not authority by itself. The #185 boundary applies normalized source eligibility and occurrence-aware workspace visibility before structured Symbol-IR authority survives.

Candidate-shaped grammar is never sufficient by itself. Ambiguity remains explicit.

## Proof claims and support evidence

Proof-support IR is a frontend evidence layer, not canonical proof semantics. It consumes only source-role-eligible spans from `LinguisticProjection`. Local NLP receives typed span placeholders derived from that same projection and supplies parser-neutral grammatical evidence only.

Thorn deliberately retains a bounded support grammar for visible evidence semantics, including explicit application/reference cues, `by definition`, a small historical named-property family, explicit `since` reason structure, conclusion cues, and conservative trailing binders. These rules do not parse TeX structure and do not establish mathematical validity. Generic asserted support that cannot be identified remains `UNRESOLVED`; cue-only NLP-supported relations remain ambiguous/unresolved where semantics are not established.

The ownership split is strict:

- source eligibility/segmentation/projection -> `LatexFrontend` + `LinguisticProjection`;
- grammatical facts -> `LinguisticFrontend`;
- bounded visible support semantics -> Thorn support evidence policy;
- mathematical implication/truth -> canonical semantic review / Lean where supported.

## Dependency identity and closure

Structured result dependencies and prose/symbol semantic dependencies remain distinct canonical edge families but compose before review. Project declaration identities come from migrated authority state; declaration-to-declaration and result-to-declaration uses do not rediscover relationships from nearby source text.

There is one canonical project-symbol dependency closure implementation. Result and review ordering use workspace occurrence/order facts rather than private file walks or lexical path sorting.

The theorem/result IR remains path-level where safe. Repeated occurrence state may collapse only when occurrence-level evidence establishes the same answer; disagreement or unavailable workspace facts fail closed rather than choosing an arbitrary physical-file answer.

## Review selection

Normal Thorn review is result-level. A requested result has one canonical bounded result-level view whether or not deterministic extraction marked any support relation ambiguous or unresolved.

The uncertainty-focused selector remains only for explicit diagnostic/evaluation callers (`thorn-eval --targeted-preflight` and `--review-context targeted`). `ReviewTargetKind.RESULT` and `ReviewTargetKind.SUPPORT_RELATION` make that policy distinction explicit. Both views share canonical Symbol-IR materialization and semantic closure; the targeted view is not a second authority graph.

Provider adapters receive already-selected Thorn-owned requests. They do not traverse the project or decide review selection.

## Canonical downstream state

Symbol IR and canonical Proof IR remain the downstream semantic authority. Reports, source navigation, Lean projection, and `thorn-proof/1` derive from canonical state and exact provenance.

`thorn-proof/1` remains a bounded projection. Source rescue can request only exact handles Thorn advertised and does not become a whole-paper fallback or late source parser. Because proof-support source eligibility is enforced before canonical selection, excluded source cannot be advertised as rescue content.

## Partiality and failure policy

Thorn distinguishes:

- **valid and supported structure**: normalize and use it;
- **valid but unsupported/dynamic structure**: retain explicit partiality/unresolved capability;
- **malformed source**: fail closed with source-facing diagnostics;
- **ambiguous linguistic evidence**: retain a non-authoritative candidate;
- **incomplete declaration payload**: retain evidence where useful but do not promote authority;
- **incomplete source-role coverage**: do not manufacture proof/declaration evidence from unknown bytes;
- **uncertain occurrence uniqueness**: do not collapse to path-level authority/dependency identity.

The normal response to a new LaTeX or English corner case is therefore not “add a regex inside semantic review.” The owner is determined by the boundary that lacks the fact.

## Retained hand-written grammar and raw-source responsibilities

The architecture intentionally retains a small amount of handwritten logic. Every retained case has a bounded owner and justification:

| Responsibility | Location | Why retained |
| --- | --- | --- |
| Compatibility LaTeX scanner for macros, environments, comments, math and static includes | `frontends/regex.py` | Current compatibility backend while #183 packaging is unresolved. It must not grow to chase parser corner cases. |
| Source-region composition for non-Tree-sitter backends | `frontend_regions.py` | Normalizes already-extracted frontend spans into one backend-neutral eligibility contract. |
| Small Tree-sitter environment-name fallback and `verbatim*` classification | `frontends/tree_sitter.py` | Operates only on CST-owned spans/nodes when the pinned grammar omits a convenient classification. |
| Reversible source eligibility and typed span projection | `source_projection.py` | One shared adapter from normalized source facts to exact linguistic views; it does not infer mathematical meaning. |
| Bounded declaration anchors (`call`, `term`, `say`, `mean`) | `linguistic_declarations.py` | #160 showed broad dependency proposals had unacceptable false-candidate risk; the lexical guard bounds proposals without deciding authority. |
| Bounded ambient prefixes and negation/attribution guards | `linguistic_declarations.py` | Explicit document-scope grammar is not safely inferred from generic dependency structure alone. |
| Bounded proof-support cue grammar | `support_extract.py` | Records explicit author-presented support evidence over already-eligible source; ambiguous/general support remains unresolved and truth is not inferred. |
| Result/theorem environment names and reference macro family | `latex.py` | Thorn must identify its own mathematical result units and explicit result references from normalized frontend facts. |
| Frozen #125 phrase regex benchmark | `_frozen_declaration_benchmark.py` | Research-only reproduction of #160 evidence; not production authority. |

The retired five-family #125 phrase recognizer, bespoke generic singular/plural morphology, raw semantic comment/verbatim masking, duplicate semantic projection, private semantic include traversal, and selector-private closure are not production architecture.

## Ownership test for future changes

A new robustness failure should have one obvious owner:

- source/CST structure and source roles -> `LatexFrontend` / source backend;
- reversible semantic text projection -> `source_projection.LinguisticProjection`;
- expanded workspace occurrence/order -> `ProjectWorkspaceFacts`;
- grammatical variation -> `LinguisticFrontend` / candidate layer;
- visible proof-support evidence policy -> bounded support extractor;
- mathematical authority, scope, visibility, materiality -> Thorn semantic policy;
- dependency identity/closure/provenance -> canonical Thorn semantic state;
- normal vs diagnostic review breadth -> review projection policy;
- formal validity inside the supported subset -> Lean handoff.

If a proposed fix crosses those boundaries by rescanning raw TeX or rebuilding generic English grammar in a semantic/review layer, it should be rejected or moved to the correct substrate.
