# Semantic-dependency architecture

This document records Thorn's current semantic-dependency ownership boundary after the source/workspace consolidation and the #203 ablation programme. Historical evaluation details remain in the issue-specific research material; this file describes production architecture.

## Core rule

Generic source, workspace, and linguistic tooling may supply normalized observations. Thorn owns the mathematical decisions built on those observations: authority, scope, visibility, shadowing, dependency identity, materiality, ambiguity policy, transitive review closure, exact provenance, and canonical mathematical IR.

A lower layer may fail or report partiality. Thorn must not repair that uncertainty by inventing source structure, occurrence uniqueness, proof evidence, or mathematical authority.

## Production pipeline

```text
LaTeX source
    |
    v
Tree-sitter LatexFrontend
    |  normalized macros, environments, math, source regions,
    |  diagnostics, exact SourceSpan
    v
ParsedProject
    |
    +--> ProjectWorkspaceFacts
    |      occurrence identity, include sites, expanded order,
    |      labels/references, resolved/partial/source-error state
    |
    +--> ResultRegion / theorem and proof source facts
    |
    +--> Symbol IR + bounded support evidence
    |
    `--> reversible LinguisticProjection
             |
             v
        optional LinguisticFrontend
             |  source-mapped grammatical observations only
             v
        LinguisticStatementInventory
             |
             +--> advisory retrieval
             `--> bounded support uncertainty

Thorn mathematical authority / scope / visibility / shadowing
    |
    v
semantic dependency identity + canonical closure
    |
    v
canonical Proof IR
    |
    +--> reports
    +--> Lean
    `--> thorn-proof/1 + bounded source rescue
```

`latex.extract_project()` is the source-to-IR composition root. Backend-native Tree-sitter nodes, spaCy documents/tokens, TexLab values, and LaTeXML XML never cross their adapters into canonical mathematical state.

## Source structure

`LatexFrontend` owns parser-neutral source facts only. `FrontendFile` exposes exact raw source, normalized macros/environments/math, source roles, region completeness, and diagnostics. `DOCUMENT_TEXT` means syntactically eligible prose; it does not mean mathematical declaration, proof authority, or truth.

Tree-sitter is the production default. The exact grammar/runtime identities are package-controlled and covered by the frontend conformance and clean-install gates. The regex and pylatexenc frontends remain independent compatibility/conformance backends; new LaTeX corner cases are not a reason to grow a second production parser in semantic code.

Semantic consumers use `source_projection.LinguisticProjection` when they need a reversible text view. It preserves exact source offsets and typed math/reference placeholders and excludes comments, preamble/non-document material, verbatim-like content, and other ineligible regions. Incomplete source-role coverage fails closed.

## Workspace/project facts

`ProjectWorkspaceFacts` is the normalized source of expanded project occurrence and order. It exposes distinct `SourceOccurrence` identity, include-site provenance, deterministic expanded order, and explicit resolution state. `ProjectPositionLookup` is the shared ordering/visibility substrate.

Repeated inclusion remains occurrence-sensitive even when physical paths are equal. Missing children, cycles, malformed source, and unsupported or dynamic project structure stay explicit rather than being guessed. Path-level authority or dependency identity may collapse repeated occurrences only when the occurrence-level evidence establishes the same single answer.

TexLab and LaTeXML retain their roles as independent development evidence/oracles. Neither decides mathematical scope or authority.

## Mathematical authority

Thorn no longer has a generic prose-to-mathematics promotion pipeline. The former production prose-declaration interpretation machinery was removed in #204-#207, and generic linguistic symbol interpretation was removed in #210. Local NLP therefore cannot create a mathematical symbol, definition, dependency, scope rule, or canonical proof fact merely because a dependency parser finds declaration-shaped English.

Project-scope mathematical authority is intentionally narrower and remains Thorn-owned.

### Formula-derived project declarations

`symbol_extract.py` recognizes explicit mathematical definitions such as `q := 1` or `q \coloneqq 1` from normalized math/source facts. These do not depend on English cues or Local NLP.

### Bounded explicit project conventions

`project_context.py` retains a small authority policy for author-level declarations that cannot be recovered from formula shape alone. Its current accepted forms are deliberately bounded:

- `Set` or `Define` with an explicit mathematical definition operator;
- `Let` with an explicit definition operator, or an explicit typed-map declaration with the bounded `be` form;
- `For` mathematical constraints only when followed by an explicit project-convention tail such as `in what follows`, `throughout`, `henceforth`, or `from now on`;
- explicit infix definitions of the form `Define $x \star y$ to mean $x+y$`.

This layer is not a general English parser. It reuses Thorn's mathematical symbol grammar, requires complete eligible source projection and a resolved workspace, excludes result-local material, and records occurrence-aware project positions, exact provenance, uses, shadowing, and dependency identities.

#185 established that this policy participates in real cross-file semantics: project declarations resolve later uses, respect include order, shadow correctly, fail closed under repeated-occurrence disagreement, and preserve exact review provenance.

#203 then ablated the less-obvious infix `to mean` bridge in isolation. In that experiment, workspace facts, exact source-mapped linguistic statements, and an explicit `q := 1` control were unchanged. What disappeared was the canonical `\star` project definition and its later resolved use. That is a material mathematical-identity loss, so the bridge and the surrounding bounded `project_context.py` authority responsibility are retained. The evidence argues against replacing this layer with broader generic NLP just as strongly as it argues against deleting it.

## Local NLP boundary

Local NLP provides source-mapped grammatical observations, not mathematical authority. `collect_project_linguistic_statements()` records exact statements, scope and normalized segmentation. Advisory retrieval may rank those already-source-mapped statements for review, but ranking does not promote them into definitions, symbols, dependencies or proof facts.

The local frontend may also contribute bounded grammatical evidence when Thorn classifies already-identified proof-support structure. Such evidence remains explicit uncertainty. Parser-native vocabulary must not shape canonical Proof IR or Lean output, and uncertainty cannot be laundered into confidence by later rendering.

With no linguistic frontend, structured LaTeX/result, workspace, symbol and dependency semantics continue to work. Source-mapped linguistic statements and linguistic uncertainty are simply unavailable; there is no fallback handwritten English parser.

## Proof support and dependency closure

Proof-support IR is an evidence layer, not canonical proof truth. It consumes only source-role-eligible spans and may record explicit application/reference cues, `by definition`, bounded named-property structure, explicit `since` reasons, conclusion cues, and conservative trailing binders. Generic asserted support that cannot be identified remains unresolved.

Structured result dependencies, project-symbol dependencies and bounded support evidence compose before review. Dependency identity, occurrence-aware visibility and transitive closure are Thorn-owned canonical state; downstream review code does not rediscover them from nearby prose.

## Canonical downstream state

Symbol IR and canonical Proof IR are the downstream semantic authority. Reports, source navigation, Lean projection and `thorn-proof/1` derive from canonical state and exact provenance.

`thorn-proof/1` is a bounded projection. Source rescue can request only exact handles Thorn advertised; it is not a whole-paper fallback or a late source parser.

## Partiality and failure policy

Thorn distinguishes:

- **valid and supported structure**: normalize and use it;
- **valid but unsupported/dynamic structure**: retain explicit partiality or unresolved capability;
- **malformed source**: fail closed with source-facing diagnostics;
- **ambiguous linguistic evidence**: retain it only as non-authoritative evidence;
- **incomplete source-role coverage**: do not manufacture proof/declaration evidence from unknown bytes;
- **uncertain occurrence uniqueness**: do not collapse to path-level authority or dependency identity.

The normal response to a new LaTeX or English corner case is therefore not to add a regex inside semantic review. The owner is determined by the boundary that lacks the fact.

## Retained handwritten responsibilities

The remaining handwritten logic has a bounded owner and evidence-backed purpose:

| Responsibility | Location | Why retained |
| --- | --- | --- |
| Tree-sitter source normalization and small CST classification fallbacks | `frontends/tree_sitter.py` | Adapts the packaged grammar into Thorn's parser-neutral source contract; does not infer mathematics. |
| Compatibility/conformance source backends | `frontends/regex.py`, `frontends/pylatexenc.py` | Independent comparison and reduced-backend coverage; not a second semantic parser. |
| Reversible source eligibility and typed projection | `source_projection.py` | One exact bridge from normalized source facts to linguistic views; no mathematical interpretation. |
| Explicit project mathematical conventions | `project_context.py` | #185 and #203 show real scope, identity, shadowing, provenance and definition responsibilities that disappear under ablation. |
| Formula-derived symbol extraction | `symbol_extract.py` | Thorn-owned mathematical syntax/authority over normalized math facts. |
| Bounded proof-support cue policy | support extraction | Records explicit author-presented support evidence; ambiguous/general support remains unresolved and truth is not inferred. |
| Result/theorem units and explicit reference families | source/result extraction | Thorn must identify its own mathematical result units and explicit references from normalized frontend facts. |
| Frozen historical prose recognizer | `_frozen_declaration_benchmark.py` | Research-only reproduction of earlier evidence; not production authority. |

The retired production prose-declaration interpreter, generic linguistic symbol interpreter, duplicate semantic projection, private semantic include traversal, and selector-private closure are not production architecture.

## Ownership test for future changes

A new robustness failure should have one obvious owner:

- source/CST structure and source roles -> `LatexFrontend` / source backend;
- reversible semantic text projection -> `source_projection.LinguisticProjection`;
- expanded workspace occurrence/order -> `ProjectWorkspaceFacts`;
- grammatical variation -> `LinguisticFrontend` observations only;
- explicit project mathematical convention -> bounded `project_context.py` authority;
- visible proof-support evidence -> bounded support extractor;
- mathematical authority, scope, visibility and materiality -> Thorn semantic policy;
- dependency identity, closure and provenance -> canonical Thorn semantic state;
- formal validity inside the supported subset -> Lean handoff.

If a proposed fix crosses those boundaries by rescanning raw TeX or rebuilding generic English grammar in a semantic/review layer, it should be rejected or moved to the correct substrate.
