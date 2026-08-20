# Semantic-dependency architecture audit

This document is the architecture and ownership audit required by issue #157. It
describes the post-#155 tree at `4024b55`, identifies the generic substrate that is
currently reconstructed inside semantic analysis, and defines the boundaries that the
#158-#160 evaluations must test.

It does not select Tree-sitter, TexLab, LaTeXML, or a dependency-based declaration
recognizer. Those choices remain empirical. It also does not authorize a production
backend change or a broad refactor.

## Executive finding

Thorn already has the right high-level boundaries:

- `LatexFrontend` normalizes parser output and exact source spans;
- `LinguisticFrontend` normalizes local grammatical evidence;
- Symbol IR records declarations, uses, scopes, definitions, constraints, and
  uncertainty;
- canonical Proof IR is the semantic source of truth for downstream projections;
- `thorn-proof/1` advertises a bounded, closed set of exact source handles.

The principal architectural problem is that two generic facts are not first-class in
those boundaries:

1. which exact source regions are eligible document prose; and
2. where a source point occurs in expanded project order.

`project_semantic_context.py` consequently reconstructs both facts while also
recognizing declaration grammar, resolving visibility and shadowing, deciding
mathematical authority, and closing semantic dependencies. Generic reconstruction and
Thorn-specific policy are therefore coupled in one 800-line module.

The current behavior is valuable and should remain the regression baseline. The
target is to preserve its mathematical semantics while moving generic source,
workspace, and grammatical evidence behind explicit Thorn-owned contracts.

## Current pipeline

```text
LaTeX files
    |
    v
LatexFrontend.parse_project()
    |  FrontendFile, macro, environment, math, SourceSpan, diagnostics
    v
latex.extract_project()
    |-- theorem/proof units and ResultRegion
    |-- structural result DependencyGraph
    |-- ProofSupportGraph
    |      |-- structural explicit/cue extraction
    |      |-- optional NLP candidates during extraction
    |      `-- optional NLP uncertainty pass over cue-only edges
    `-- SymbolTable
           |-- symbol_extract: result/local declarations and uses
           |-- project_context: explicit mathematical project declarations
           |-- project_context_source: authoritative source sentence expansion
           |-- project_semantic_context: unconditional prose definitions/conventions
           `-- linguistic_symbols: optional ambiguous grammatical candidates
    |
    v
ExtractedProject
    |-- semantic_review.build_review_context()
    |      targeted uncertainty-bearing support items
    `-- eval_review.build_result_review_context()
           result-level context used by normal thorn review and controlled evaluation
    |
    |  both select claims, relations, symbols, definitions, constraints,
    |  candidates, and dependencies; both close selected project semantics
    v
canonical Proof IR -> typed Proof IR -> ProofObligationIR
    -> SymbolResolutionIR -> higher proof structure -> SemanticTransformationIR
    |-- Lean projection
    |-- reports and visualisation
    `-- thorn-proof/1
            |
            `-- one bounded NEED_SOURCE turn over advertised exact handles
```

`latex.extract_project()` is the composition root for the source-to-IR path. Parser
and NLP objects do not escape their adapters, which is an important invariant to
retain.

## Responsibility inventory

| Responsibility | Current owner(s) | Classification | Target owner |
| --- | --- | --- | --- |
| Exact offsets, lines, and columns | Both frontend adapters; repeated helpers in symbol, support, linguistic, and project-context modules | Generic source infrastructure | One normalized source-span utility or frontend-supplied spans |
| Macro, environment, and math structure | `frontends/regex.py`, `frontends/pylatexenc.py` | Generic TeX/source infrastructure | `LatexFrontend` backend |
| Comment handling | Regex frontend scanning; `project_semantic_context._semantic_view` | Generic TeX/source infrastructure | Frontend/CST-derived eligible-region facts |
| Verbatim/listing/comment exclusion | `project_semantic_context._semantic_view`, based on frontend environments | Generic TeX/source infrastructure | Frontend/CST-derived eligible-region facts |
| Preamble/document-body eligibility | `project_semantic_context._semantic_view` | Generic TeX/source infrastructure | Frontend/CST-derived eligible-region facts |
| Sentence/prose segmentation | `support_extract`, `project_context_source`, `project_semantic_context`; spaCy supplies sentence identity only after projection | Generic linguistic/source infrastructure | Reversible semantic projection plus normalized linguistic evidence, with a structural fallback contract |
| Project file discovery | Both frontend adapters | Generic workspace infrastructure | Shared workspace adapter or normalized frontend project loader |
| Expanded include order | `project_semantic_context._document_order` | Generic workspace infrastructure | Thorn-owned normalized project-order facts backed or checked by evaluated tooling |
| Result/dependency ordering | `latex.extract_project` sorts units by file path and line; `DependencyGraph` treats insertion order as project order | Generic project ordering consumed by Thorn graphs | Normalized project positions shared by extraction and semantic resolution |
| Include cycles, repeats, and missing files | Frontend adapters use a `seen` set and missing-file diagnostics; semantic ordering has separate active/visited logic | Generic workspace infrastructure | One project/workspace boundary with explicit partiality |
| Label/reference syntax | Frontend facts plus `latex.extract_project` | Generic source structure followed by Thorn dependency identity | Syntax from frontend; dependency semantics remain Thorn-owned |
| Theorem/result identity and edges | `latex.extract_project`, `dependencies.py` | Thorn mathematical interpretation | Thorn |
| Generic graph traversal and SCC | `DependencyGraph`; local closure loops elsewhere | Generic graph infrastructure | Shared utilities or a mature graph library only where it reduces code without changing edge semantics |
| Mathematical symbol grammar | `symbol_extract.py`, reused privately by `project_context.py` | Thorn mathematical interpretation over generic syntax | Thorn, behind public internal contracts rather than private cross-module imports |
| Ordinary grammatical analysis | `SpacyLinguisticFrontend`; proof-support extraction and uncertainty refinement; linguistic symbol candidates; phrase/regex grammar in support, symbol, and semantic-context modules | Generic linguistic infrastructure | `LinguisticFrontend` and normalized candidate evidence where evaluations support it |
| Prose declaration candidates | `project_semantic_context._declarations` directly creates authoritative inputs | Mixed generic grammar and Thorn authority | Candidate recognition below; authority policy above |
| Term morphology and phrase matching | `project_semantic_context` | Generic linguistic/name mechanics | Linguistic evidence or a deliberately small documented fallback |
| Mathematical authority | `project_context`, `project_semantic_context` | Thorn mathematical interpretation | One explicit Thorn authority policy |
| Result/statement/proof/local scopes | `symbol_extract`, `SymbolTable` | Thorn mathematical interpretation | Thorn Symbol IR |
| Cross-file visibility and shadowing | `project_semantic_context` combines document order with term matching; `SymbolTable` handles lexical scope and same-file forward visibility | Thorn mathematical scope over generic project facts | Thorn resolver consuming normalized project positions |
| Binder and expression resolution | `symbol_resolution_ir.py` | Thorn mathematical interpretation | Thorn |
| Ambiguity and partiality | evidence models, candidates, support edges, Symbol Resolution IR | Thorn assurance policy | Thorn |
| Semantic dependency closure | `project_semantic_context._reachable_declarations`; `semantic_review._close_project_symbol_dependencies`, privately reused by `eval_review` | Thorn mathematical/assurance policy | One explicit closure contract over canonical dependency identities |
| Review-context selection/materiality | Targeted selection in `semantic_review.py`; result-level normal-review selection in `eval_review.py` | Thorn assurance/review policy | Shared selection primitives with explicit targeted and result-level policies |
| Canonical Proof-IR lowering | canonical and typed Proof-IR modules | Thorn mathematical/assurance policy | Thorn |
| Advertised source handles | `llm_proof_language.py`, derived from semantic IR sources | Thorn assurance/review policy | Thorn |
| Closed-world rescue limits | `proof_language_review.py` | Thorn assurance/review policy | Thorn |
| Report/source navigation | `report.py` and report HTML | Thorn product assurance over exact provenance | Thorn |

## Detailed findings

### Source structure

`LatexFrontend` exposes raw files, macros, environments, math, diagnostics, and exact
spans. It does not expose comments, text/math regions, document-body regions, or an
eligibility classification for prose. This is why semantic code must rescan raw TeX.

There are several overlapping implementations:

- `frontends/regex.py` skips comments independently while scanning macros and math;
- `project_semantic_context._semantic_view` rescans escaped `%`, masks comments,
  excludes a local list of verbatim-like environments, and masks the main preamble;
- `support_extract._sentence_spans` segments proof prose with its own expression;
- `project_context_source` expands an introduction to a sentence using another
  boundary expression;
- `project_semantic_context._sentence_bounds` implements paragraph, punctuation, and
  math-aware sentence bounds again;
- source-span construction and line/column calculation are repeated in both frontend
  adapters and at least four downstream modules.

Exact offsets are generally preserved because masking is length-preserving and
`SourceSpan` is used throughout. The guarantee is nevertheless procedural and
duplicated. A new source consumer can bypass it by calculating a span locally.

The frontend should supply normalized source-region facts sufficient to answer:

- is this exact range eligible document prose, math, configuration, comment, or
  literal/verbatim text;
- what exact source span produced it;
- is the classification complete, partial, or affected by a parse error.

The frontend must not decide whether eligible prose is mathematically authoritative.

### Project and workspace structure

Both frontend adapters duplicate breadth-first file discovery, include argument
normalization, `.tex` suffix handling, missing-file diagnostics, and repeated-file
suppression. Their `ParsedProject.files` order is load order, not expanded document
order.

`project_semantic_context._document_order` therefore performs a second include walk
over selected source points. It models insertion at include locations and prevents
cycles, but a global `visited` set means repeated inclusion is represented once rather
than as multiple expanded occurrences. Missing, ambiguous, or macro-generated include
structure is not expressible as partial project-order evidence.

No first-class project position currently identifies an occurrence in expanded order.
The semantic resolver receives a dictionary of integer ranks calculated for one call.
That fact cannot be reused by labels, other scope resolvers, reports, or differential
tests.

There is also a separate downstream ordering rule: `latex.extract_project()` sorts
theorem units by source file path and line rather than expanded project position.
`DependencyGraph._node_order()` then treats that insertion order as stable project
order when returning direct and transitive dependencies and cyclic components. A
project-order consolidation that rewires only prose semantic resolution would
therefore leave result/dependency ordering on a different source of truth.

The target workspace boundary should expose normalized, provenance-bearing facts such
as:

- main/root file identity;
- include relationship and exact source location;
- source occurrence or project position in expanded order;
- repeated occurrence identity;
- missing, cyclic, ambiguous, and unresolved state.

Those are source/workspace facts. Whether a declaration at one position is
mathematically authoritative or visible to a theorem at another remains Thorn policy.

### Linguistic structure

The existing `LinguisticFrontend` is a sound adapter boundary. `SpacyLinguisticFrontend`
immediately converts spaCy tokens to Thorn-owned tokens, and dependency evidence is
kept lexical-free where contracts require it. Existing support and symbol paths also
preserve ambiguous or unresolved candidates rather than promoting parser output to
truth.

The current production orchestration has four distinct NLP-related paths:

1. `extract_proof_support_graph()` optionally parses projected proof prose to attach
   reference, adjacency, and qualifier candidates;
2. `apply_linguistic_uncertainty()` performs a subsequent pass that downgrades
   cue-only confident edges when normalized dependency evidence cannot justify them;
3. `add_linguistic_symbol_candidates()` optionally proposes ambiguous local symbol
   introductions after deterministic symbol extraction;
4. `add_project_semantic_context()` always runs first and recognizes authoritative
   prose definitions and conventions without `LinguisticFrontend` evidence.

The fourth path is the #160 comparison target. The first three are existing consumers
whose candidate, provenance, and degraded-mode behavior must remain intact; they are
not automatically replaced by a declaration recognizer.

The #125 prose-declaration path does not use that boundary. It currently owns:

- five declaration-form expressions;
- sentence detection around a match;
- style-wrapper removal;
- singular/plural morphology;
- term-use expression construction;
- lexical matching between declarations and uses.

This code correctly avoids a mathematical vocabulary list, but it remains a bespoke
English recognizer. More importantly, `_declarations` produces inputs that are later
made authoritative without an intermediate normalized candidate/ambiguity contract.

#160 should compare three strategies over the same reversible semantic projection:
the frozen #125 recognizer, dependency-based candidate recognition, and a small hybrid.
All must output Thorn-owned candidates with role, term span, sentence span, evidence,
provenance, and ambiguity. A separate policy must decide authority.

`--structural-only` is a deliberate product mode, not an accidental absence of spaCy.
Its capability must remain explicit. If authoritative prose declarations require real
NLP after consolidation, structural-only must report the reduced capability rather
than fabricate equivalence.

### Name, scope, and graph structure

Several scope mechanisms are legitimate but their boundaries are not obvious:

- `SymbolTable` owns the project/result/statement/proof/local scope tree and resolves
  visible symbols through parent chains and same-file forward offsets;
- `project_context` separately maps source uses into the most specific result scope;
- `project_semantic_context` separately maps term uses to result scopes and resolves
  cross-file shadowing with its private document-order ranks;
- `SymbolResolutionIR` projects relevant source scopes and adds expression/binder
  scopes for mathematical elaboration.

The last item is not simple duplication: proof-expression binders belong in
`SymbolResolutionIR`. The architectural drift is the absence of a common source/project
position supplied to the earlier resolvers. `SymbolTable.visible_symbols()` cannot
express cross-file expanded order, while the prose-semantic resolver cannot reuse the
scope resolver.

Similarly, `DependencyGraph` owns meaningful result-dependency edge types, while its
depth-first traversal and strongly connected component implementation are generic.
Small generic algorithms are not a problem by themselves. They become a problem when
multiple semantic layers implement closure with different implicit edge rules. Thorn
must continue to own which edges exist and which closures are assurance-relevant.

### Semantic dependency and authority

Thorn's distinctive value appears in these decisions:

- a source statement is a mathematical definition, convention, assumption, or
  exposition;
- a declaration is authoritative with a stated certainty;
- scope and project order make it visible at a result;
- later authority shadows earlier authority only in justified scope;
- a use is materially dependent on that authority;
- transitive semantic prerequisites must be closed before a one-shot review;
- irrelevant nearby prose must remain unavailable.

Those decisions are currently spread across `project_context`,
`project_semantic_context`, `SymbolTable`, `semantic_review`, and `eval_review`. The
code has the correct conservative instincts but no named service or public internal
contract for the policy.

`project_semantic_context` is the highest-risk hotspot because it performs every stage
from source eligibility through closure. `project_context` also imports private parser
helpers from `symbol_extract`, which makes the intended reuse implicit and fragile.

Review-context selection is independently duplicated. `semantic_review` builds
targeted items around uncertainty-bearing trigger edges and filters context by relevant
spans. `eval_review` builds one result-level item, selects all result claims and direct
dependencies, and applies a different symbol-context rule. Normal `thorn review` uses
the latter through `review_workflow`, despite its historical `eval_review` module name
and evaluation-seam docstring. `eval_review` privately imports
`_close_project_symbol_dependencies` from `semantic_review`, so closure is shared but
selection policy is not. This is both an ownership ambiguity and a consolidation risk.

The target should make the stages observable:

```text
eligible source facts
        + normalized project positions
        + normalized linguistic candidates
                          |
                          v
             Thorn authority decision
                          |
                          v
             Thorn visibility/shadowing
                          |
                          v
        Thorn semantic dependency identities
                          |
                          v
        material/transitive closure for review
```

These may be internal models and services around the existing Symbol IR. They must not
become a second semantic IR.

### Proof IR and bounded reachability

The downstream assurance boundary is comparatively well separated after context
selection:

- `semantic_review` and `eval_review` select different bounded views and both close
  selected project declarations before Proof-IR construction;
- canonical Proof IR is graph-derived and provenance-bearing;
- `thorn-proof/1` is a deterministic projection, not a second store;
- its source handles are derived from canonical source entries;
- the review protocol enumerates the exact allowed handle set and caps a rescue
  response at eight handles;
- unadvertised addresses and paths are rejected without source disclosure.

Consolidation should preserve this boundary rather than moving source discovery into
the review protocol. #162 should test it from authoritative source span through report
navigation and `NEED_SOURCE` response.

## Architectural drift and hotspots

| Hotspot | Risk | Required disposition |
| --- | --- | --- |
| `project_semantic_context.py` | Generic scanning, NLP, workspace order, mathematical policy, and closure change together | Split only after #158-#160 evidence and #162 coverage |
| Frontend adapter project walks | Duplicate behavior and no occurrence-level expanded order | Evaluate a shared workspace boundary under #159 |
| Missing eligible-prose frontend fact | Every semantic consumer can invent exclusions | Extend the parser-neutral contract under #158 if evidence supports it |
| Multiple sentence segmenters | Different authoritative spans and source handles for the same prose | Establish one reversible segmentation/evidence contract |
| Repeated local span builders | Provenance invariants rely on copied arithmetic | Centralize span construction or consume backend spans |
| `project_context` private imports from `symbol_extract` | Hidden coupling makes ownership unclear | Expose a deliberate internal mathematical-declaration contract |
| Phrase grammar directly feeding authority | Parser disagreement cannot remain ambiguity | Introduce normalized semantic-declaration candidates under #160 |
| Project order represented as transient integer ranks | Repeated includes and uncertainty cannot be represented | Add a provenance-bearing project-position fact model under #159/#161 |
| Units sorted by file path while dependency graphs call node order project order | Project order can diverge between prose semantics and structured dependencies | Make result/dependency ordering consume the #159 project-position contract |
| Two project semantic closure stages | Edge semantics and termination contract are implicit | Specify one backend-independent closure invariant in #162 |
| `semantic_review` and `eval_review` context selectors | Normal and targeted review select materially different context through duplicated code; normal review uses the module named as an evaluation seam | Name both policies explicitly, share selection primitives, and cover both under #162 before consolidation |
| Structural-only behavior | A backend change could silently weaken or overclaim capability | Add explicit capability assertions in #162 |

## Target layering

```text
LaTeX backend / source CST
    |
    | Thorn-normalized syntax, eligible regions, exact provenance, partiality
    v
Project/workspace boundary
    |
    | Thorn-normalized include relationships, occurrences, expanded positions
    +-------------------------------+
    |                               |
    v                               v
Reversible semantic projection   theorem/result/source facts
    |
    v
LinguisticFrontend
    |
    | normalized candidates and ambiguity
    +-------------------------------+
                                    v
                     Thorn mathematical authority policy
                                    |
                     Thorn scope, visibility, shadowing
                                    |
                     Thorn dependency identity and closure
                                    v
                       Symbol IR / canonical Proof IR
                                    |
                 +------------------+------------------+
                 v                  v                  v
               Lean             reports          thorn-proof/1
                                                       |
                                              bounded source rescue
```

The contracts between layers are Thorn-owned even when their facts come from external
components. No backend-native node, LSP object, or spaCy object may cross an adapter.

## Evaluation seams and candidate roles

### #158 source/CST evaluation

Evaluate Tree-sitter behind `LatexFrontend`. The evaluation should determine whether
the normalized frontend contract can reliably add eligible source-region facts,
comment/verbatim exclusions, document boundaries, include locations, malformed-state
partiality, and exact spans.

Possible dispositions are runtime/default candidate, optional backend, differential
oracle, benchmark/reference, or reject/defer. Tree-sitter must not recognize
mathematical declarations.

### #159 workspace evaluation

Evaluate TexLab and LaTeXML against a Thorn-owned project-order fixture contract. A
tool may be valuable as an oracle even if its process, packaging, licensing, or source
locator behavior makes it unsuitable at runtime.

The deliverable must assign a role per responsibility rather than one role per tool.
For example, root discovery and reference structure may have a different disposition
from true TeX expansion.

### #160 linguistic evaluation

Evaluate declaration-candidate recognition through `LinguisticFrontend` over a shared
source-preserving projection and adversarial corpus. The production recommendation may
be replace, hybridize, retain, or defer. False project-scope authority is more damaging
than missed low-confidence recall and must be measured separately.

### Generic name and graph infrastructure

Do not add a new dependency merely to replace a short deterministic traversal. During
#161, extract or adopt generic utilities only where doing so removes actual duplicated
mechanics, improves partiality, or makes the semantic edge policy clearer. Mathematical
identity, edge kinds, materiality, and closure selection remain Thorn-owned.

## Non-negotiable behavioral evidence

| Contract | Existing evidence to preserve |
| --- | --- |
| Parser-neutral syntax and exact provenance | `test_frontend_conformance.py`, `test_frontend_ab.py`, `test_frontend_adapter_boundary.py` |
| Frontend disagreement remains visible | unknown-macro and injected-frontend tests |
| Symbol scope and anti-guessing | `test_symbol_ir.py`, `test_symbol_resolution_ir.py`, scope regression tests |
| NLP objects stay behind the adapter | `test_linguistic_frontend.py` |
| Ambiguity remains non-authoritative | linguistic ambiguity, binder, and symbol candidate tests |
| Reversible math/reference projection | `test_semantic_projection.py` |
| Prose definition reachability | #125 prose-definition and semantic-context tests |
| Ambient forward scope and no backward application | #125 review-fidelity tests |
| Comment and verbatim exclusion | #125 review-fidelity tests |
| Cross-file order and shadowing | #125 review-fidelity tests |
| Transitive semantic closure | #125 review-fidelity tests |
| Irrelevant nearby prose stays pruned | #125 semantic-context tests |
| Exact report navigation | #125 semantic-context report test |
| Closed-world rescue | issue #88 and #125 reachability tests |
| Structured dependencies compose with semantic context | dependency, Proof-IR fidelity, and #125 tests |
| Normal result review and targeted semantic selection remain intentional | review-workflow, semantic-review, eval-preflight, and semantic-review-provider tests |
| `thorn-proof/1` remains a projection | Proof-language, transformation, and review-contract tests |

#162 should centralize these properties into smaller semantic assertions rather than
only preserving issue-specific end-to-end tests.

## Sequencing recommendation

1. Land this audit without production changes.
2. Start #162's fixture matrix and assertion helpers so all later evaluations target
   the same Thorn-owned promises.
3. Run #158-#160 as separate evaluation changes. They may proceed in parallel, but
   each must consume the audit boundaries and report an explicit disposition.
4. Publish the architecture decision gate combining their evidence.
5. Begin #161 only after the relevant #162 contract is executable.
6. Consolidate source facts, project facts, candidates, authority, and closure in
   bounded changes, removing superseded paths only after consumers are rewired.
7. Re-establish full keyless CI and Local NLP contract coverage before any deferred
   paid semantic-review experiment.

## What Thorn deliberately continues to own

After consolidation, Thorn should still implement the code that answers questions no
generic parser, workspace engine, NLP parser, graph library, or theorem prover can
answer for it:

- Which recovered source statements carry mathematical authority?
- Which authority is visible, shadowed, ambiguous, or unresolved at this result?
- Which semantic relationships are load-bearing for the result or proof step?
- Which transitive prerequisites must be represented or source-reachable for bounded
  review?
- Which uncertainty must remain explicit rather than being guessed away?
- How does every conclusion retain an exact, auditable path to manuscript evidence?
- What does Thorn promise to human, AI-review, report, and Lean consumers, and where
  does that assurance stop?

That is Thorn's value-add. The #158-#161 work should make it smaller, more explicit,
and more thoroughly guarded, not delegate it.
