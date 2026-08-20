# Semantic-dependency conformance contract

## Purpose

This contract defines the mathematical dependency and source-reachability properties
that Thorn must preserve while LaTeX, workspace, linguistic, and graph substrates
change under issues #158-#161. It observes Thorn-owned state and behavior rather than
backend-native syntax trees, dependency parses, regex matches, private identifier
schemes, or module layout.

The executable contract starts in
`tests/test_semantic_dependency_contract.py`. Its fixtures are ordinary LaTeX projects
and its assertions inspect:

- result-visible mathematical authority and exact declaration provenance;
- structured theorem/result dependencies;
- canonical `thorn-proof/1` review context;
- exact bounded source handles where rescue is required;
- explicit ambiguity and capability state;
- explicit source/dependency partiality without invented authority or targets.

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
canonical Proof IR -> thorn-proof/1 review context
        |
        +--> canonical initial representation, when sufficient
        `--> bounded exact NEED_SOURCE rescue, when required
```

Backend implementations may recover different intermediate evidence. They conform
when every capability they advertise satisfies the same Thorn-owned assertions. A
reduced configuration must omit the capability explicitly and the corresponding test
must skip or fail for that named reason; silently exercising a weaker path is not
conformance.

## Stable invariants

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
11. When a required source fact, project edge, or dependency is unavailable or
    ambiguous, Thorn must preserve that partiality explicitly or fail closed; it must
    not invent a result, child source, expanded project ordering, declaration,
    dependency target, or review source. Declaration-shaped prose without a substantive
    defining complement is partial evidence only and must not become an authoritative
    definition, constraint, or resolved semantic dependency. Whether a selector exposes
    exact partial source as non-authoritative evidence is a separate review-policy
    question.

These properties concern fidelity, provenance, closure, and bounded reachability. They
do not decide which review-context selector should govern normal review.

The contract deliberately does **not** require authoritative prose to remain absent
from the initial packet. PR #155 currently keeps this prose behind source handles, but a
future contract-equivalent projection may render semantically sufficient canonical
context directly. Conversely, if the initial representation is not sufficient, the
exact source must remain available through the bounded closed-world rescue mechanism.

## Review-selector status

The production `review_workflow` currently uses result-level selection from
`eval_review`, while `semantic_review` provides targeted uncertainty-triggered
selection. Their materiality and escalation policies differ.

The conformance helper `assert_observed_result_context` deliberately names its current
result-level behavior as an observation. It accepts either canonical initial context or
bounded exact rescue and does not declare the current packet-placement choice
normative. Later #162 work must characterize targeted selection separately while
sharing the stable provenance, closure, and reachability assertions above. The
architecture decision gate must then choose the intended normal-review policy before
#161.

## Configuration matrix

The initial ordinary-CI matrix is:

| Configuration | Project semantics | Linguistic candidates | Execution |
| --- | --- | --- | --- |
| Regex frontend, structural-only | Required | Not advertised | Ordinary CI |
| pylatexenc frontend, structural-only | Required | Not advertised | Ordinary CI |
| Regex frontend, deterministic NLP fixture | Required | Required | Ordinary CI |

Structural-only semantic declarations are supported because the current explicit prose
recognizer is unconditional. Structural-only does not advertise linguistic candidates;
the executable matrix records that limitation as an intentional skip. Real spaCy
coverage remains in the mandatory Local NLP contract and must later consume the same
candidate assertions without exposing spaCy-native objects.

## Current fixture matrix

| Mathematical shape | Assertions | Frontends |
| --- | --- | --- |
| Held-out flag-complex predicate | Result-visible authority, exact provenance, review availability, closed world | Regex, pylatexenc |
| Ambient Hausdorff convention between results | Forward application and no backward leakage | Regex, pylatexenc |
| Comment, verbatim, and nearby historical prose | No false authority or reachability | Regex, pylatexenc |
| Cross-file predicate redefinition | Later included authority resolves at the result; earlier authority does not | Regex, pylatexenc |
| Same-file predicate redefinition | Later authority resolves at the result; shadowed source is not review-reachable | Regex, pylatexenc |
| Parent declaration before child include | Parent authority is visible to a theorem inside the child | Regex, pylatexenc |
| Child declaration before parent continuation | Child authority remains visible after returning to the parent | Regex, pylatexenc |
| Child redefinition followed by child and parent theorems | Child authority shadows the earlier parent declaration at both results | Regex, pylatexenc |
| Parent declaration after a child include | Later parent source does not leak backward into the child result | Regex, pylatexenc |
| Recovered authoritative source projected to report navigation | Canonical declaration provenance preserves exact file, line range, excerpt, and file URI | Regex, pylatexenc |
| Base-field convention, regular-matrix definition, and cited lemma | Transitive semantic closure composes with result dependency | Regex, pylatexenc |
| Local linguistic symbol introduction | Candidate remains ambiguous and non-authoritative | Deterministic NLP fixture; structural-only explicitly skipped |
| Truncated theorem environment | Parse partiality is explicit; no theorem/result is invented | Regex, pylatexenc |
| Missing included file | Exact `MISSING_FILE` include-site provenance; unavailable source does not become authority by guess | Regex, pylatexenc |
| Malformed/incomplete include | Exact normalized project-partiality provenance; no guessed child, expansion order, or later authority | Regex, pylatexenc |
| Include-like text in comments/verbatim | No child source or project edge is fabricated from literal source | Regex, pylatexenc |
| Include nested in custom macro structure | Explicit project partiality rather than macro-expansion guess | Regex, pylatexenc |
| Missing structured result reference | Dependency remains `MISSING`; no target or referenced review source is invented | Regex, pylatexenc |
| Duplicate structured result label | Dependency remains `AMBIGUOUS`; no arbitrary target or referenced review source is selected | Regex, pylatexenc |
| Truncated named declarations and ambient conventions | Exact available source is preserved; no definition, constraint, or resolved semantic dependency is invented; complete neighbouring declarations remain authoritative with exact provenance | Regex, pylatexenc |

The initial slice generalized the #125 seed beyond convergence vocabulary and made the
same semantic assertions reusable across both supported LaTeX frontends. The second
bounded slice extends the contract across source-occurrence order and report navigation
without asserting private identifier spelling, declaration storage multiplicity, or
whether authoritative prose is initially rendered versus source-rescued. The
report-navigation fixture derives navigation from canonical declaration provenance and
asserts review reachability separately, so it does not require a proof-language source
handle to exist.

The source-rescue response bound is already enforced by the shared closed-world
proof-language contract in
`tests/test_issue_88_closed_world_source_selection.py`: the selectable universe may be
larger, but one request is schema-bounded and an over-limit response is rejected. #162
therefore relies on that shared proof-language guarantee rather than freezing a second
copy of the current numeric limit. Its own fixtures continue to require that semantic
source handles belong to the finite advertised set and resolve to exact source.

## Explicit partiality boundary

The first partiality slice makes four already-supported failure modes part of the
backend-independent guardrail. A malformed theorem environment is a source fact that is
unavailable: the frontend must report normalized parse partiality and Thorn must not
synthesize a mathematical result from the malformed source. A frontend may still retain
a partial or error syntax node internally; #162 does not make that CST representation
normative.

A missing include is explicit source/project unavailability with exact include-site
provenance. The stable contract is the normalized `MISSING_FILE` fact and the requirement
that unavailable source never turns into invented mathematical authority. The current
extractor happens to fail closed with an exception, but neither `FileNotFoundError` nor
any particular exception/partial-project mechanism is normative. #159 may replace that
mechanism with a Thorn-owned partial project state while preserving the same source and
semantic consequences.

Missing and duplicate result references remain `MISSING` and `AMBIGUOUS` dependency
edges respectively, with no fabricated target and no fabricated referenced-result
source in review context.

Parser disagreement itself is also already observable rather than normalized away by
`tests/test_frontend_ab.py`; #162 relies on that source-fact boundary while asserting only
Thorn-owned semantic consequences.

The #167 tranche extends that boundary to incomplete prose declarations. A recognizer
may still observe a declaration-shaped cue, but Thorn's authority layer must not promote
it unless defining content is actually available. The exact source that was available
remains source provenance; it is not converted into a definition, ambient constraint,
or resolved semantic dependency by guess. The authority guard treats non-math macro-only or macro-leading
material conservatively as insufficient payload, so syntax such as labels or empty
formatting wrappers cannot manufacture authority or bridge into unrelated later prose. A future selector may still expose
the exact partial source as non-authoritative evidence; #162 deliberately leaves that
policy open. Complete neighbouring declarations continue to resolve normally. This rule
is vocabulary-independent and applies equally across the regex and pylatexenc structural
configurations.

The #169 tranche applies the same fail-closed rule to project structure. A complete
static `\\input`/`\\include` remains ordinary project evidence. An incomplete target,
mismatched group, dynamic/custom-macro include, or other include site whose expansion
cannot be determined safely becomes normalized `PROJECT_PARTIALITY` with exact available
source provenance. Files reached only through unsafe include-like evidence are excluded
from the normalized project, and extraction currently fails closed rather than allowing
later results to inherit guessed ordering or authority. Conversely, include-shaped text
that is demonstrably comment or closed verbatim content is not project evidence at all.
The current exception mechanism and the temporary normalization layer are not normative;
#159 may replace both with mature workspace/project-resolution tooling while preserving
these semantic consequences.

## Remaining #162 matrix

After the project-partiality tranche, remaining acceptance work is:

- targeted-selector characterization without choosing its production role;
- the real Local NLP configuration in its mandatory workflow;
- any additional projection-correspondence assertion exposed by those selector/NLP
  slices.

These are remaining acceptance work, not optional robustness ideas. #162 is complete
only when the public matrix covers them and the focused selector decision has enough
evidence to proceed.

## Running the contract

The keyless contract runs with:

```bash
pytest -q tests/test_semantic_dependency_contract.py \
  tests/test_semantic_dependency_partiality_contract.py \
  tests/test_semantic_dependency_project_partiality_contract.py
```

No provider credentials, provider calls, or model fixtures are permitted. Backend and
Local NLP lanes may add dependencies needed for their advertised capability, but the
asserted semantic vocabulary remains Thorn-owned.

## Non-goals

- proving mathematical correctness;
- recovering all implicit cultural mathematical knowledge;
- freezing parser- or NLP-native evidence paths;
- freezing private symbol identifier conventions or storage multiplicity;
- freezing whether authoritative prose is initially rendered or source-rescued;
- making both current review selectors normative;
- exposing nearby or whole-paper prose as fallback context;
- introducing a second semantic IR;
- using paid or model-backed tests.
