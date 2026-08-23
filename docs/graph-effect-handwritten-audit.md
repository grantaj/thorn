# Handwritten semantic rules against the proof-dependency calculus

Status: #215 audit, stacked on the exact #214 head. This is an ownership and inference audit, not a production cutover.

## Audit question

#212 deliberately narrowed Thorn's dependency semantics to the observations needed for proof dependency. The current falsifiable state model is

```text
G = (V, REQUIRE, bind, payload, visibility, status)
```

with construction operations

```text
DECLARE(v; bind, payload, visibility, status)
REQUIRE(u, v)
```

and `Closure` derived from `Direct`. Exact source/evidence remains the independent assurance projection `P`.

This gives a stronger audit criterion than asking whether a rule recognizes a familiar mathematical-prose category:

> A handwritten semantic rule belongs in the canonical path only when it helps establish a field of `DECLARE`, establishes a grounded `REQUIRE`, or implements the fixed resolution/visibility/status algebra needed by `Q`.

Everything else may still be useful source evidence, but it does not need to become canonical semantics.

## Current rule inventory

| Current mechanism | #212 role | Exact field/effect established | Evidence source | Audit disposition |
| --- | --- | --- | --- | --- |
| theorem-like environment extraction and labels | `DECLARE` | result node, optional `bind`, statement `payload` | parser-owned environment/label/source spans | keep; structural source fact plus mathematical node construction |
| `symbol_extract` explicit `:=` / `\\coloneqq` / mechanically defined equality operators | `DECLARE` | symbol `bind` + definitional `payload` | exact math syntax and source span | keep; direct mathematical grounding, not English recognition |
| `symbol_extract` map forms `f : A \\to B` | `DECLARE` | `bind` + domain/codomain payload | exact math syntax | keep; `project_context_source` mapping constraint is a derived payload projection |
| `symbol_extract` relation/quantifier forms | `DECLARE` | local `bind`, constraint/payload, structurally bounded visibility | exact math syntax + enclosing result/proof scope | keep conservatively; fail closed where candidate/extent is not unique |
| `IntroductionKind` (`let`, `for`, `define`, `set`, `quantifier`) | evidence for `DECLARE` | currently helps choose candidate parsing and visibility; the category itself is not in `Q` | local cue + structured math | retain only as internal extraction evidence; do not treat the category as canonical semantics |
| `_CUE_PATTERNS` (`let`, `for`, `define`, `set`) | evidence for `DECLARE` | licenses a structured-math introduction | eligible local source immediately around exact math | candidate for collapse into a tiny introduction-operator class; vocabulary must not grow by paraphrase |
| project explicit-definition parsing | `DECLARE` | project `bind` + payload | exact explicit definition operator | keep; strongest project-authority path |
| `project_context` alias bridge (`to mean`, `means`, `is defined as/to be`) | evidence for `DECLARE` | connects an already parsed infix binding to a second exact math payload | eligible projected text between exact math spans | bounded lexical-semantic residue; test structural replacement, otherwise keep small or demote |
| project convention tail (`in what follows`, `throughout`, `henceforth`, `from now on`) | `visibility` evidence on `DECLARE` | forward project visibility for an already structured constraint | exact eligible tail + workspace order | bounded lexical-semantic residue; no general phrase growth; explicit scope termination is currently missing |
| `structured_authority.enforce_structured_authority_boundary` | `DECLARE` authority/visibility gate | source eligibility, project capability, occurrence-aware visibility | frontend projection + resolved workspace facts | keep; this is Thorn assurance/visibility policy, not English interpretation |
| `SymbolTable.resolve` | `Resolve` | binding target / unresolved result under lexical and occurrence-aware project scope | canonical symbol state + workspace positions | keep; directly implements `Q1` |
| resolved `SymbolUse` inside a result/project declaration | `REQUIRE` | prerequisite identity | exact mathematical occurrence + resolved symbol identity | keep; use of a notation/definition changes meaning and therefore dependency |
| transitive symbol closure | derived `Closure` | none primitive | repeated canonical `REQUIRE` edges | keep only as derived selection/query logic, never infer a `Closure` label from text |
| theorem/reference label resolution in `latex.py` | `Resolve` | exact result target or ambiguous/missing reference | parser-owned reference macro + workspace occurrence consensus | keep as `Resolve`; **do not equate successful resolution with `REQUIRE`** |
| every resolved theorem reference currently copied into `DependencyGraph.direct_dependency_ids` | currently `REQUIRE` | direct prerequisite | reference occurrence only | **semantic conflation**: a resolved mention is not necessarily presented support; split resolution from prerequisite authority |
| proof-support reference cues (`by/from/using/apply/invoke`) | evidence for `REQUIRE` | support-role evidence around an already exact reference | eligible source + exact reference span | prototype as one small support-operator class over dependency structure; do not accumulate sentence templates |
| `linguistic_support` downgrade of cue-only reference/prior-claim edges | authority guard for `REQUIRE` | preserves ambiguity rather than inventing prerequisite authority | normalized dependency path + exact source | keep principle; parser attachment is evidence, not authority |
| `support_corroboration` explicit application + unique formula match | `REQUIRE` | dependent/prerequisite identity plus independent application evidence | exact cited result + asserted target + fully lowered formula match | keep; this is strong Thorn-owned mathematical corroboration |
| `By definition` support | candidate `REQUIRE` | relation evidence but no unique prerequisite node by itself | cue source span | demote unless a canonical definition node is independently resolved; the English category itself is not in `Q` |
| fixed named-property list (`compactness`, `continuity`, `linearity`, `monotonicity`, `convexity`) | no grounded `REQUIRE` by itself | only a prose support label | lexical match | remove/demote from canonical authority; it has no principled finite completion and no prerequisite identity |
| generic asserted support phrase retained `UNRESOLVED` | advisory candidate only | no canonical effect | exact source/evidence | keep as evidence if useful; unresolved text is not graph mutation |
| `Since ...` explicit-reason edge | candidate `REQUIRE` | support assertion but no canonical prerequisite identity | whole-construction regex | should not be canonical `REQUIRE` without independently grounded prerequisite; candidate for structural advisory evidence |
| conclusion cue -> previous claim (`therefore/hence/thus/consequently`) | candidate `REQUIRE` | possible prior-claim prerequisite | lexical cue + adjacency | keep non-authoritative unless structural/mathematical corroboration grounds the prerequisite; `SupportKind.PRIOR_CLAIM` is not a semantic primitive |
| trailing binder prose (`for every/all/each`) | `DECLARE` | local `bind` + local visibility | adjacent display/prose source | potentially graph-relevant, but current whole-construction regex should be tested against structural binder attachment |
| `SupportKind` taxonomy | evidence/debugging | none by itself | implementation classification | not part of `Q`; retain only where useful to construct/inspect grounded `REQUIRE` evidence |
| `InferenceStatus` on NLP/support evidence | assurance evidence | **not automatically `status(v)`** | parser/evidence confidence | keep separate from dependency-capability `Status`; do not launder confidence into semantic node status |

## Main semantic mismatch discovered by the audit

`Resolve` and `Direct` are separate primitive observations in #212, but current theorem-reference construction partially conflates them.

`latex.py` correctly performs occurrence-aware reference resolution. Once a theorem/reference label resolves uniquely, however, the resulting `DependencyEdge` is consumed directly by `DependencyGraph.direct_dependency_ids()`, and `snapshot_dependency_observations()` projects every such edge as a `SemanticRequirementObservation`.

Therefore the current path is conceptually:

```text
reference occurrence
    -> Resolve(reference) = theorem T
    -> REQUIRE(current_result, T)
```

The second implication is not valid in general. Source can uniquely identify a theorem while mentioning, contrasting, attributing, or explicitly declining to use it. #212 already proves why the distinction matters: two histories can expose exactly the same nodes and references while only one presented proof uses the prior result; `Direct` distinguishes them.

The support subsystem already contains the safer ingredients:

- typed/exact reference identity;
- dependency-parse attachment retained as ambiguous evidence;
- explicit support-role evidence;
- independent formula/application corroboration that can strengthen a relation only when a unique mathematical match exists.

The structural compiler experiment should therefore treat reference resolution as an input fact and infer `REQUIRE` separately. A production cutover should wait for evidence beyond the small synthetic corpus.

## What the calculus says Thorn does *not* need to understand

The following distinctions are not canonical merely because they are conventional mathematical language:

- definition versus notation versus convention versus assumption as prose labels;
- `let` versus `set` versus `define` when they establish the same binding/payload/visibility state;
- `by`, `using`, `from`, `applying`, or `therefore` as distinct support kinds when they establish the same direct prerequisite;
- rhetorical/pedagogical classifications with no effect on resolution, visibility, prerequisites, or dependency-relevant capability.

Those distinctions may remain useful debugging/evidence metadata outside semantic equality.

## Missing or weakly grounded fields

### 1. Explicit visibility termination/retraction

The current scope machinery handles structural extent, project order, forward visibility, and shadowing well. It does not provide a general text-grounded representation for a later statement such as

```text
From this point onward, the standing assumption X is no longer in force.
```

The #213 retraction heldout is therefore genuine calculus pressure. Do not add a phrase for it merely to pass the case. We first need to decide whether the fixed visibility algebra can express an end/retraction update cleanly under the two-operation construction language.

### 2. Status transition

Current `InferenceStatus` records confidence/partiality of recovered evidence. It is not the `status(v)` label from #212. Thorn has no general deterministic text grounding for statements such as “R remains unproved” or “R is now established”. This is another deliberate gap. Prefer deriving status from graph/support structure where possible before introducing any textual status updater.

### 3. Prose declaration payloads

Post-#203 production deliberately stopped promoting broad prose declarations into mathematical authority. Exact source statements remain available to bounded review. A future structural `DECLARE` compiler must independently ground both the binding and a substantive mathematical/opaque payload; recognizing a naming construction alone is insufficient.

### 4. Direct result support

As above, unique reference identity is well grounded, but actual support role is not uniformly grounded. This is the highest-value target for the structural prototype because it can remove false `Direct` authority without requiring general prose understanding.

### 5. Joint versus alternative support

The heldouts distinguish joint and alternative support, but current `Q` asks which prerequisites the presented argument depends upon, not for minimal sufficient alternative proof sets. Both may therefore project to the same set of `REQUIRE` edges today. Keep the cases as pressure; do not add Boolean edge semantics without a new observable query.

## Structural compiler hypothesis

The bounded alternative to both a phrase grammar and generic NLI is:

```text
normalized source / typed math+ref placeholders
        +
normalized dependency facts
        +
resolved canonical identities
        -> partial graph-effect frames
        -> authority/grounding gate
        -> DECLARE / REQUIRE or unresolved
```

The prototype should use a few *graph-semantic operator classes* only where syntax cannot determine context-change force. Rules should compose facts rather than encode whole sentences.

A useful success signal is not maximum recall. It is that a small fixed rule inventory provides materially better generalization while false authority remains low and every admitted operation argument has exact source grounding.

The stop signal is equally important: if each paraphrase requires another operator/synonym/construction, retain the smaller audited production layer and preserve the rest as advisory evidence.

## Large-corpus handoff

Natural-paper testing should attack this small target, not feed an open-ended phrase list. A newly observed failure should be classified as:

1. missing/incorrect generic source or linguistic fact;
2. missing grounding of a `DECLARE` field;
3. missing grounding of a `REQUIRE` endpoint/relation;
4. correct unresolved/no-effect behavior;
5. false authority;
6. provenance/occurrence failure; or
7. counterexample to the #212 graph calculus.

That classification is the main architectural payoff of the audit.