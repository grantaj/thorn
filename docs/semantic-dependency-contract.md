# Semantic-dependency conformance contract

## Purpose

This contract protects Thorn-owned semantic behavior while source, workspace,
linguistic, and review implementations evolve. It observes normalized Thorn state and
canonical projections rather than backend-native CST nodes, NLP objects, regex matches,
private identifier spelling, or module layout.

The executable contract lives primarily in:

- `tests/test_semantic_dependency_contract.py`;
- `tests/test_semantic_dependency_partiality_contract.py`;
- `tests/test_semantic_dependency_project_partiality_contract.py`;
- `tests/test_semantic_dependency_selector_contract.py`;
- `tests/test_semantic_dependency_local_nlp_contract.py`;
- occurrence/authority and review-selection regressions added during #161.

Passing this contract does not prove a theorem correct. It establishes that the
mathematical context Thorn claims to have recovered is source-faithful, appropriately
partial, occurrence-aware where required, and bounded before model review.

## Current contract boundary

```text
ordinary LaTeX fixtures
        |
        v
LatexFrontend -> normalized source regions/provenance
        |
        v
ProjectWorkspaceFacts -> occurrence/order/partiality
        |
        +----------------------+
        |                      |
        v                      v
result/source facts       reversible LinguisticProjection
                               |
                               v
                         LinguisticFrontend
                               |
                               v
                     non-authoritative candidates
                               |
        +----------------------+
        v
Thorn authority / scope / shadowing
        |
        v
canonical semantic dependency identities + closure
        |
        v
Symbol IR / canonical Proof IR
        |
        +--> normal result-level review -> thorn-proof/1
        `--> explicit targeted diagnostic/evaluation projection
```

Source and NLP machinery propose facts or candidates. Thorn owns mathematical authority,
scope, dependency identity/materiality, ambiguity policy, transitive semantic closure,
exact provenance, and bounded review reachability.

## Configuration capabilities

The executable harness advertises capabilities explicitly:

- `PROJECT_SEMANTICS` — normalized project/workspace/source facts are available;
- `PROSE_AUTHORITY` — an NLP-capable declaration candidate path is available and Thorn
  may promote qualifying prose candidates through its own authority policy;
- `LINGUISTIC_CANDIDATES` — normalized local linguistic candidate evidence is available.

The ordinary structural configurations (regex and pylatexenc) advertise project
semantics but **not** prose authority. `PROSE_AUTHORITY_CONFIGURATIONS` add the
deterministic test `DeclarationContractFrontend`. The Local NLP workflow exercises the
same Thorn-owned contracts with the real local spaCy frontend. When Tree-sitter and its
pinned grammar are installed, the Tree-sitter contract lane exercises the corresponding
parser-neutral semantic contract.

A configuration that lacks a capability must say so explicitly. It must not silently
exercise a weaker path and claim equivalence.

### Structural-only is deliberately reduced

With no `LinguisticFrontend`, `ProseDeclarationInventory` is `REDUCED`. Structured
results, references, workspace facts and other deterministic semantics continue to
operate, but prose declaration authority is unavailable. The old unconditional #125
phrase recognizer is not a fallback.

This is a post-#161 invariant.

## Stable Thorn-owned invariants

The conformance matrix protects these properties:

1. **Authority is use- and scope-dependent.** Declaration-shaped syntax alone is not
   authority.
2. **Exact provenance survives.** Activated definitions/conventions retain exact source
   spans and review/source-navigation reachability.
3. **Ambient authority is forward-only.** It does not leak backward through project
   order.
4. **Comments and opaque/verbatim source are not eligible authority.** Source-role facts
   come from the frontend/projection boundary, not semantic rescanning.
5. **Project order is occurrence-aware.** Include order and redefinition/shadowing use
   normalized `ProjectPosition` facts.
6. **Repeated inclusion cannot be collapsed unsafely.** If repeated occurrences of a
   path-level result see different authority, the current path-level result IR fails
   closed rather than guessing one target.
7. **Structured and prose dependencies compose.** Transitive semantic prerequisites
   remain reachable alongside theorem/result dependencies.
8. **Ambiguous linguistic evidence stays non-authoritative.** Parser confidence is not
   mathematical authority.
9. **Incomplete declaration payloads fail closed.** A recognized declaration cue without
   substantive defining content cannot become a definition/constraint or resolved
   semantic dependency.
10. **Missing/ambiguous result references do not acquire fabricated targets.** Exact
    dependency resolution state survives projection.
11. **Workspace partiality is explicit.** Missing, cyclic, malformed, or unsupported
    dynamic project structure cannot become invented expanded order or source.
12. **Canonical review context is bounded.** `thorn-proof/1` is a projection over
    canonical state and source rescue accepts only advertised exact handles.
13. **Selection cannot create authority.** A review projection may prune canonical
    state, but may not invent a dependency, declaration, source, ambiguity resolution,
    or shadow relation.

## Production prose authority

The production declaration recognizer is the bounded #160 hybrid in
`linguistic_declarations.py`, operating on Thorn-owned normalized linguistic tokens.
Its candidates carry exact term, sentence and payload provenance and begin ambiguous.

Thorn's authority policy separately requires complete source/workspace/candidate facts,
substantive payload, valid occurrence-specific visibility/shadowing, and actual use
before active semantic authority is emitted.

The retired #125 phrase templates are frozen only in
`_frozen_declaration_benchmark.py` for research reproduction. Contract tests must not
reintroduce them as a production authority path merely to make structural-only fixtures
pass.

## Project/workspace semantics

`ProjectWorkspaceFacts` is the canonical production boundary for expanded project
occurrence/order facts. The contract exercises:

- parent/child and return-to-parent ordering;
- declarations before/after includes;
- cross-file redefinition and shadowing;
- repeated inclusion;
- missing files;
- cycles and project partiality;
- malformed/incomplete direct include syntax;
- fake include-like syntax in comments/verbatim;
- unusual static include targets without a Thorn-owned ASCII filename grammar.

Downstream semantic code consumes normalized positions. It does not maintain a separate
include walk.

## Review projection policy after Slice F

The selector decision is now settled.

### Normal review: result-level

`review_workflow` uses the canonical result-level projection from
`build_result_review_context()`. A requested result has exactly one bounded review item
whether or not deterministic extraction marked any support relation ambiguous or
unresolved.

A result-level item may contain uncertainty, but uncertainty did **not** cause the item
to exist. `ReviewTargetKind.RESULT` records that policy explicitly.

The result-level view contains canonical result claims/support, result-visible symbol and
declaration context, candidate evidence where relevant, canonical direct structured
dependencies, and transitive project semantic closure required for interpretation.

### Targeted diagnostic/evaluation view

`build_review_context()` retains uncertainty-triggered selection only for explicit
`thorn-eval --targeted-preflight` and `--review-context targeted` use. Its
`ReviewTargetKind.SUPPORT_RELATION` items are trigger-relative diagnostic/evaluation
projections.

This path is not the normal review policy, does not gate `review_workflow`, does not own
mathematical authority, and does not maintain a second semantic graph. Result-level and
targeted projections share canonical Symbol-IR materialization and dependency closure.

The full and compact renderers distinguish “uncertainty present in this result” from
“uncertainty caused this targeted diagnostic view.”

## Source reachability and bounded rescue

Review-relevant semantic context must be available either directly in canonical
`thorn-proof/1` state or through exact source handles advertised from canonical
provenance. The rescue protocol is closed-world: unadvertised addresses are rejected and
request size is bounded by the shared proof-language contract.

Selectors and providers do not create independent source namespaces. Report navigation
and rescue resolve back to canonical exact spans.

## Backend neutrality

The contract does not require regex, pylatexenc and Tree-sitter to have identical native
parse trees or to make up answers where syntax is genuinely ambiguous. It requires each
advertised capability to satisfy the same Thorn-owned outcome.

Important distinctions:

- unusual but valid source is a robustness requirement;
- valid but unsupported/dynamic source may produce explicit partiality;
- malformed source may fail closed;
- parser disagreement is preserved as evidence rather than normalized through a second
  Thorn parser.

Tree-sitter is the preferred source backend, while regex remains the compatibility
default until the pinned grammar has a reproducible ordinary installation path. That
default decision does not weaken the semantic contract.

## Representative fixture matrix

| Shape | Required outcome |
| --- | --- |
| Named prose definition | exact candidate provenance; authority only with NLP capability + Thorn promotion |
| Ambient convention | forward application, no backward leakage |
| Comment/verbatim declaration lookalike | no authority |
| Same-file/cross-file redefinition | occurrence/order-aware shadowing |
| Parent/child include variants | correct normalized project position |
| Repeated child under one declaration | safe agreement may collapse to path-level result |
| Repeated child across redefinition | disagreement fails closed |
| Transitive prose declaration chain + cited lemma | one canonical semantic closure composing with structured dependency |
| Local/real-spaCy linguistic introduction | candidate remains non-authoritative |
| Truncated named declaration | candidate may exist; no authority without substantive payload |
| Missing include / malformed direct include | explicit partial/source error; no guessed child/order |
| Missing/duplicate result reference | missing/ambiguous edge; no fabricated target |
| Result-level review with no uncertainty | result review item still exists |
| Targeted preflight with uncertainty | explicit support-relation diagnostic item |
| Report/source rescue | exact file/span/text and closed-world handle set |

## Running the keyless contract

Ordinary semantic-dependency coverage is included in the normal pytest suite and can be
focused with:

```bash
pytest -q tests/test_semantic_dependency_contract.py \
  tests/test_semantic_dependency_partiality_contract.py \
  tests/test_semantic_dependency_project_partiality_contract.py \
  tests/test_semantic_dependency_selector_contract.py \
  tests/test_issue_161_occurrence_authority.py \
  tests/test_issue_161_review_selection.py
```

The Local NLP workflow additionally installs the local English model and runs the real
adapter contract. Tree-sitter CI installs/builds the pinned grammar and runs the same
parser-neutral semantic-dependency surface. Lean CI checks the downstream formal handoff.

No provider credentials or model calls belong to this conformance programme.

## Non-goals

This contract does not:

- prove mathematical correctness;
- infer every cultural mathematical assumption;
- freeze parser-native or NLP-native evidence paths;
- define a Thorn TeX expansion engine;
- require universal acceptance of dynamic TeX projects;
- freeze private symbol identifier spelling;
- make ambiguous linguistic proposals authoritative;
- permit whole-paper review fallback;
- introduce a second semantic IR;
- authorize provider/model calls.

The contract's job is narrower: preserve faithful, occurrence-aware, provenance-bearing,
explicitly partial mathematical context while implementation substrates evolve.
