# Semantic-dependency conformance contract

## Purpose

This contract defines the mathematical dependency and source-reachability properties
that Thorn must preserve while LaTeX, workspace, linguistic, and graph substrates
change under issues #158-#161. It observes Thorn-owned state and behavior rather than
backend-native syntax trees, dependency parses, regex matches, private identifier
schemes, or module layout.

The executable contract starts in `tests/test_semantic_dependency_contract.py` and is
extended by the partiality, selector, and Local NLP contract tests. Its assertions
inspect:

- result-visible mathematical authority and exact declaration provenance;
- structured theorem/result dependencies and transitive semantic closure;
- canonical `thorn-proof/1` review context;
- exact bounded source handles where rescue is required;
- explicit ambiguity and capability state;
- explicit source/dependency partiality without invented authority or targets; and
- both current review selectors as projections of canonical Thorn state.

Passing this contract does not prove a theorem correct. It establishes that the
mathematical context Thorn claims to have recovered remains faithful, source-addressed,
and bounded before any model-backed review.

## Contract boundary

```text
ordinary LaTeX fixtures
        |
        v
advertised frontend / linguistic capabilities
        |
        v
Thorn Symbol IR + result dependency graph
        |
        v
review-context selection (policy, not authority)
        |
        v
canonical Proof IR -> thorn-proof/1 review context
        |
        +--> canonical initial representation, when sufficient
        `--> bounded exact NEED_SOURCE rescue, when required
```

Source and NLP machinery propose normalized facts or candidates. Thorn owns mathematical
authority, scope, dependency identity and materiality, ambiguity, provenance, transitive
semantic closure, and bounded review reachability. A selector may choose a bounded view
of those facts; it does not acquire a second authority graph by doing so.

Backend implementations may recover different intermediate evidence. They conform when
every capability they advertise satisfies the same Thorn-owned assertions. A reduced
configuration must omit a capability explicitly and the corresponding test must skip or
fail for that named reason; silently exercising a weaker path is not conformance.

## Stable Thorn-owned invariants

The contract is organized around these assurance properties:

1. At a result, an activated prose definition or ambient convention resolves to the
   mathematically authoritative declaration with exact source provenance. The contract
   does not constrain private symbol identifier spelling or require shadowed historical
   declarations to be discarded from internal state.
2. Authority follows mathematical use and scope, not textual proximity.
3. Ambient authority applies forward and does not leak backward.
4. Comments and verbatim-like source do not create authority.
5. Redefinition and include order select the declaration justified by project scope.
6. Semantic prerequisites remain transitively reachable and compose with structured
   theorem/result dependencies.
7. Ambiguous linguistic evidence remains a candidate and never becomes deterministic
   authority merely because a parser proposed it.
8. Review-relevant semantic context is available either as a semantically sufficient
   canonical initial representation or through an advertised exact source handle.
9. Every advertised semantic source handle resolves to exact manuscript text, and
   source rescue accepts only the finite advertised handle set.
10. `thorn-proof/1` remains a projection over canonical state, not a second semantic
    store or a whole-paper fallback.
11. Selector-visible results, dependencies, support relations, symbols, definitions,
    constraints, candidates, and source context must correspond to canonical Thorn-owned
    state. Selection may prune canonical state according to policy; it may not invent a
    dependency target, authority, source, ambiguity resolution, or shadow graph.
12. When a required source fact, project edge, or dependency is unavailable or
    ambiguous, Thorn must preserve that partiality explicitly or fail closed; it must
    not invent a result, child source, expanded project ordering, declaration,
    dependency target, or review source. Declaration-shaped prose without a substantive
    defining complement is partial evidence only and must not become an authoritative
    definition, constraint, or resolved semantic dependency.

These are fidelity, provenance, closure, ambiguity, and bounded-reachability guarantees.
They do **not** choose which current review selector should govern normal review.

The contract deliberately does not require authoritative prose to remain absent from the
initial packet. A future contract-equivalent projection may render semantically
sufficient canonical context directly. Conversely, if the initial representation is not
sufficient, exact relevant source must remain available through bounded closed-world
rescue. Review availability is therefore placement-neutral.

## Current review selectors

Thorn currently has two review-context policies. #162 characterizes both so later
architecture work can compare them without treating either policy as mathematical
authority.

### Result-level selection (`review_workflow` / `eval_review`)

The result-level path is called by `review_workflow` through the `eval_review` seam. For
a requested result it currently emits exactly one bounded item regardless of whether an
uncertainty trigger exists. It includes all claims and support relations belonging to
the selected result, result-visible symbol context, candidate evidence, and all resolved
direct structured dependencies of that result. Project-scope semantic declarations
selected by actual result use are closed transitively over declaration-to-declaration
uses before projection.

This path is wired into the canonical review workflow: its Thorn-owned review item feeds
the established semantic transformation / Proof IR path and ultimately `thorn-proof/1`.
Exact source rescue is therefore advertised by the canonical proof-language projection,
not by a selector-private source mechanism.

Observed policy, not a stable architecture choice:

- selection is result-wide rather than trigger-relative;
- escalation is decided by its caller, not by the selector itself;
- deterministic result context is included by default;
- all resolved direct structured dependencies are retained rather than trigger-pruned;
- ambiguous and unresolved support relations are preserved and listed as trigger
  identifiers, but their presence does not gate item creation;
- result-owned partial/candidate evidence may be present without becoming authority; and
- a no-trigger result still has a result-level review item available.

### Targeted uncertainty-triggered selection (`semantic_review`)

The targeted path emits items only for ambiguous or unresolved support relations. It
groups nearby uncertainty triggers into bounded local regions, carries confident support
relations only where they provide local structure, selects symbol/declaration context
relevant to those regions, and prunes structured dependencies to resolved canonical
result dependencies implicated by selected support labels. Selected project-scope
semantic declarations use the same transitive declaration closure as the result-level
path.

The targeted item carries Thorn-owned claims, relations, source spans, symbol state, and
dependency nodes directly. It does not advertise a separate NEED_SOURCE universe or
maintain a second dependency graph. Any later proof-language projection or rescue must
continue to derive from canonical Thorn state and exact provenance.

Observed policy, not a stable architecture choice:

- selection is uncertainty-triggered and trigger-relative;
- ambiguous/unresolved support relations are the escalation triggers;
- deterministic context is admitted only where it is structurally local to a trigger;
- claims, symbol context, and structured dependencies are pruned to the local region;
- unresolved support evidence remains unresolved even when a canonical structured
  dependency with the same label exists;
- ambiguous linguistic candidates can accompany a triggered item but cannot create one
  by themselves or become authority;
- nearby partial evidence may be exposed as exact non-authoritative context when it is
  attached to selected canonical evidence; and
- if there is no uncertainty trigger, no targeted item is emitted.

### Shared selector correspondence

`tests/test_semantic_dependency_selector_contract.py` exercises both selectors against
the same canonical project fixture. The shared assertions are intentionally phrased in
Thorn-owned terms:

- result and dependency identity correspond to the canonical dependency graph;
- selected structured dependencies lie inside canonical semantic reachability;
- selected support relations preserve canonical ambiguity/unresolved status and exact
  evidence provenance;
- selected symbols, definitions, constraints, and candidates are canonical Symbol IR
  objects rather than selector-owned copies of mathematical authority;
- structured dependencies and prose/symbol context compose in the same review item;
- nearby context must originate in exact evidence already attached to selected support;
- candidates remain non-authoritative after selection; and
- selection may prune canonical context but cannot invent source or dependency identity.

The result-level and targeted policies intentionally differ on trigger gating, context
breadth, pruning, direct dependency inclusion, and rescue advertisement. Those
differences are observations for a future selector-policy decision before #161, not
normative conclusions of #162.

## Configuration matrix

| Configuration | Project semantics | Linguistic candidates | Execution |
| --- | --- | --- | --- |
| Regex frontend, structural-only | Required | Not advertised | Ordinary CI |
| pylatexenc frontend, structural-only | Required | Not advertised | Ordinary CI |
| Regex frontend, deterministic NLP fixture | Required | Required | Ordinary CI |
| Regex frontend, real local spaCy (`en_core_web_sm`) | Required | Required | Mandatory Local NLP workflow |

Structural-only semantic declarations remain supported because the current explicit
prose recognizer is unconditional. Structural-only deliberately does not advertise the
linguistic-candidate capability; this is an explicit reduced-capability mode rather than
a silent fallback.

The real spaCy configuration remains isolated to `.github/workflows/nlp.yml`, which
installs `en_core_web_sm` locally and runs with `OPENAI_API_KEY` empty. Ordinary CI does
not gain a model download. `tests/test_semantic_dependency_local_nlp_contract.py` runs
the deterministic fixture and real spaCy adapter through the same normalized candidate
helper. The helper verifies that:

- `LinguisticFrontend.parse()` returns only Thorn-owned `LinguisticDocument` and
  `LinguisticToken` values at the adapter boundary;
- candidate evidence retains exact reversible source provenance;
- backend evidence is normalized into Thorn-owned candidate/evidence models;
- ambiguous linguistic evidence stays ambiguous and cannot become a definition,
  constraint, resolved dependency, or other mathematical authority merely because spaCy
  proposed it; and
- the serialized candidate boundary contains no spaCy-native objects.

This is conformance of the existing Local NLP adapter, not the prose-recognition
experiment in #160. The contract does not extend `_CALLED_RE`, `_SAID_TO_BE_RE`,
`_WE_SAY_RE`, `_BY_MEAN_RE`, `_AMBIENT_RE`, or any other hand-written English grammar.
Unsupported paraphrases remain future empirical work.

## Current fixture matrix

| Mathematical/source shape | Contract assertion |
| --- | --- |
| Held-out flag-complex predicate | Result-visible authority, exact provenance, review availability, closed world |
| Ambient Hausdorff convention between results | Forward application and no backward leakage |
| Comment, verbatim, and nearby historical prose | No false authority or reachability |
| Same-file and cross-file predicate redefinition | Source-order and include-order shadowing select justified authority |
| Parent/child include ordering variants | Authority respects project occurrence order in both directions |
| Recovered authoritative source projected to report navigation | Exact file, line range, excerpt, and file URI |
| Base-field convention, regular-matrix definition, and cited lemma | Transitive semantic closure composes with structured dependency |
| Local linguistic symbol introduction | Candidate remains ambiguous and non-authoritative |
| Real local spaCy linguistic introduction | Same Thorn-owned candidate contract and normalized adapter boundary |
| Result-level and targeted selector projections | Canonical authority/dependency correspondence; uncertainty preserved; policy differences explicit |
| Truncated theorem environment | Parse partiality explicit; no theorem/result invented |
| Missing included file | Exact missing-file provenance; unavailable source does not become guessed authority |
| Malformed/incomplete direct include | Exact project partiality; no guessed child or expansion order |
| Include-like text in comments/verbatim or unused macro definitions | No fabricated executed project boundary |
| Static non-ASCII/punctuated include target | No Thorn-owned ASCII filename grammar imposed |
| Missing structured result reference | Dependency remains missing; no target or review source invented |
| Duplicate structured result label | Dependency remains ambiguous; no arbitrary target selected |
| Truncated named declarations and ambient conventions | Exact available source preserved; no authority fabricated |

The source-rescue response bound remains enforced by the shared closed-world
proof-language contract in `tests/test_issue_88_closed_world_source_selection.py`. The
selectable universe may be larger, but one request is schema-bounded and an over-limit
response is rejected. #162 relies on that shared guarantee rather than freezing a second
copy of the current numeric limit.

## Explicit partiality boundary

Malformed theorem source is an unavailable source fact: the frontend reports normalized
parse partiality and Thorn must not synthesize a mathematical result. A backend may
retain a partial/error syntax node internally; #162 does not make that CST normative.

A missing include is explicit source/project unavailability with exact include-site
provenance. The stable contract is the normalized missing-file fact and the requirement
that unavailable source never becomes invented authority. The current failure mechanism
is not normative; #159 may replace it while preserving the same semantic consequences.

Missing and duplicate result references remain missing and ambiguous dependency edges
respectively, with no fabricated target and no fabricated referenced-result source in
review context. Parser disagreement is likewise observable rather than normalized away;
#162 constrains the Thorn-owned semantic consequences, not parser-native evidence.

The #167 guard extends this rule to incomplete prose declarations. A recognizer may
observe a declaration-shaped cue, but Thorn's authority layer must not promote it unless
substantive defining content is available. Exact partial source may later be exposed as
non-authoritative review evidence; that is selector policy, not mathematical authority.

The #169 guard applies the same fail-closed rule to direct project structure. Complete
static direct includes are project evidence; incomplete/mismatched/directly dynamic
include targets become normalized project partiality with exact provenance. Unsafe
children are not guessed into project order. Comment/verbatim include-shaped text is not
project evidence, and macro invocation semantics are deferred to #159 rather than
approximated by a Thorn-specific TeX expansion engine.

## Projection correspondence exposed by #162

The selector and Local NLP slices expose three correspondence rules worth making
explicit; no broader projection redesign is implied:

1. Selector-visible mathematical authority and dependency identity must correspond to
   canonical Symbol IR and dependency-graph state. A selector may filter but not resolve
   ambiguity or create a parallel semantic graph.
2. Ambiguity survives projection. Uncertain support or linguistic candidate evidence
   cannot become deterministic authority because it was selected, normalized by spaCy,
   or rendered for review.
3. Source navigation and rescue use canonical exact provenance. Where `thorn-proof/1`
   advertises a source address, the existing closed-world contract requires exact
   resolution; targeted selector context carries exact canonical spans rather than an
   independent source-address namespace.

These are the projection-correspondence assertions directly exposed by the final #162
slices. They do not prescribe future prompt shape, packet placement, selector policy, or
IR structure.

## Running the contract

The ordinary keyless semantic-dependency contract runs with:

```bash
pytest -q tests/test_semantic_dependency_contract.py \
  tests/test_semantic_dependency_partiality_contract.py \
  tests/test_semantic_dependency_project_partiality_contract.py \
  tests/test_semantic_dependency_selector_contract.py
```

The mandatory Local NLP workflow additionally installs its existing local spaCy model
and runs:

```bash
pytest -q tests/test_semantic_dependency_contract.py \
  tests/test_semantic_dependency_local_nlp_contract.py
```

No provider credentials, provider calls, readiness probes, paid evaluations, or
provider-backed model measurements are part of this contract.

## #162 completion boundary

The public conformance matrix now covers named prose authority, ambient scope,
scope/shadowing/include order, transitive closure, negative exposition,
comments/verbatim, ambiguity, exact provenance, bounded reachability, structured
result dependencies, source/project partiality, exact report/source navigation,
explicit reduced-capability modes, real Local NLP conformance, and characterization of
both current review selectors.

Accordingly there is no remaining #162 matrix. The future selector-policy decision is
architecture work after this conformance issue; #162 does not choose it. The empirical
backend evaluations in #158, #159, and #160 and eventual consolidation in #161 remain
separate work under #156.

## Non-goals

- proving mathematical correctness;
- recovering all implicit cultural mathematical knowledge;
- freezing parser- or NLP-native evidence paths;
- defining a Thorn-specific TeX filename grammar or macro-expansion engine;
- freezing private symbol identifier conventions or declaration storage multiplicity;
- freezing whether authoritative prose is initially rendered or source-rescued;
- choosing either current review selector as the future production policy;
- redesigning review prompts;
- extending hand-written prose grammar to unsupported paraphrases;
- exposing nearby or whole-paper prose as fallback context;
- introducing a second semantic IR; or
- using provider/model calls in the conformance tranche.
