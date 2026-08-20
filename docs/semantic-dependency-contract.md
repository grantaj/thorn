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
- explicit ambiguity and capability state.

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

## Initial fixture matrix

| Mathematical shape | Assertions | Frontends |
| --- | --- | --- |
| Held-out flag-complex predicate | Result-visible authority, exact provenance, review availability, closed world | Regex, pylatexenc |
| Ambient Hausdorff convention between results | Forward application and no backward leakage | Regex, pylatexenc |
| Comment, verbatim, and nearby historical prose | No false authority or reachability | Regex, pylatexenc |
| Cross-file predicate redefinition | Later included authority resolves at the result; earlier authority does not | Regex, pylatexenc |
| Base-field convention, regular-matrix definition, and cited lemma | Transitive semantic closure composes with result dependency | Regex, pylatexenc |
| Local linguistic symbol introduction | Candidate remains ambiguous and non-authoritative | Deterministic NLP fixture; structural-only explicitly skipped |

This first slice generalizes the #125 seed beyond convergence vocabulary and makes the
same semantic assertions reusable across both supported LaTeX frontends.

## Remaining #162 matrix

The next bounded slice must add:

- same-file redefinition and the remaining parent/child include-order shapes;
- malformed or incomplete source with explicit partiality rather than invented facts;
- exact report-navigation assertions over recovered semantic sources;
- targeted-selector characterization without choosing its production role;
- the real Local NLP configuration in its mandatory workflow;
- explicit source-address limit and projection-correspondence assertions where existing
  proof-language tests are not already sufficient.

These are remaining acceptance work, not optional robustness ideas. #162 is complete
only when the public matrix covers them and the focused selector decision has enough
evidence to proceed.

## Running the contract

The initial keyless contract runs with:

```bash
pytest -q tests/test_semantic_dependency_contract.py
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
