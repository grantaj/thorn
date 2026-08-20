# Semantic-dependency substrate programme plan

This document records the execution plan for issues #156-#162. It is a programme
plan, not the architecture audit required by #157 and not the conformance contract
required by #162. Findings from those issues may refine implementation details, but
the sequencing and decision gates below should remain stable unless new evidence
justifies changing them.

## Progress

| Phase | Status | Evidence or next gate |
| --- | --- | --- |
| Phase 0: baseline | Complete | 530 tests passed and 1 skipped, with one cache-sensitive test run separately from a clean working directory; ruff and mypy passed |
| #157 ownership audit | Ready for review | Adversarial review findings addressed in `docs/semantic-dependency-architecture.md` on `issue-157-semantic-dependency-audit` |
| #162 conformance contract | Not started | Next PR-sized chunk after #157 review/landing |
| #158 Tree-sitter evaluation | Not started | Requires #157 boundary and evaluation dependency approval |
| #159 workspace evaluation | Not started | Requires #157 boundary and external-tool approval |
| #160 linguistic evaluation | Not started | Requires #157 boundary and #125 baseline freeze |
| Architecture decision gate | Blocked by evidence | Requires dispositions from #157-#160 and executable #162 coverage |
| #161 consolidation | Blocked by design | Must not begin before the decision gate |

Baseline notes for the current #157 chunk:

- branch: `issue-157-semantic-dependency-audit`;
- source baseline: post-#155 `main` at `4024b55`;
- focused frontend, linguistic, #125, Proof-IR fidelity, and closed-world rescue suite:
  53 passed;
- full suite excluding one local-cache-sensitive CLI test: 529 passed, 1 skipped,
  1 deselected; the deselected test passed separately from a clean working directory;
- the provider freeze builder passed separately after installing the repository's
  pinned provider runtime;
- `ruff check .` and `mypy src` passed;
- no provider/model calls were made.

The initially deselected CLI test reused an existing `.thorn/cache` entry instead of
invoking its injected fake provider. It passed when run from a clean working directory,
confirming local test-state contamination rather than a semantic-dependency failure.
CI starts from a clean checkout and remains the authoritative full-suite result.

Adversarial review of the first chunk identified and corrected three audit gaps:

- the production `eval_review`/`review_workflow` path and its duplicated context
  selection relative to targeted `semantic_review`;
- lexical file/line unit ordering consumed as project order by `DependencyGraph`;
- the four distinct NLP-related production paths, including the unconditional #125
  prose recognizer.

## Objective

Re-ground Thorn's semantic-dependency substrate so that mature components own generic
LaTeX, workspace, linguistic, name-resolution, and graph mechanics where evidence
supports doing so, while Thorn continues to own:

- mathematical dependency identity and relevance;
- mathematical authority, scope, and shadowing semantics;
- ambiguity, partiality, and uncertainty policy;
- exact provenance in Symbol IR and canonical Proof IR;
- the distinction between load-bearing context and exposition;
- bounded closed-world source reachability;
- semantic-review and Lean assurance boundaries.

No production backend should change during the evaluation phase. No provider or paid
model calls are part of this programme.

## Programme dependency graph

```text
#157 ownership audit ------------------+
                                       +--> decision gate --> #161 consolidation
#158 Tree-sitter evaluation -----------+
#159 workspace tooling evaluation -----+
#160 linguistic evaluation ------------+
#162 conformance contract ------------------------------------^
```

#158-#160 may perform bounded implementation and evaluation work in parallel once the
current contracts are understood. Their final dispositions depend on #157. #162 begins
early and becomes the invariant gate for #161.

## Phase 0: establish the baseline

Start from the post-#155 `main` tree.

1. Create a feature branch for #157.
2. Establish the development environment with `uv`.
3. Run the full keyless test suite, `ruff check .`, and `mypy src`.
4. Record focused baseline results for:
   - frontend conformance and parser A/B tests;
   - linguistic frontend and ambiguity tests;
   - Symbol IR and symbol-resolution tests;
   - canonical Proof-IR and source-correspondence tests;
   - bounded source-rescue tests;
   - all #125 semantic-context regressions.
5. Record the supported backend/capability matrix, including the intentionally reduced
   guarantees of `--structural-only`.

The post-#125 paid semantic-review evaluation remains deferred until the programme has
settled the production substrate.

## Phase 1: deliver the #157 ownership audit

Add `docs/semantic-dependency-architecture.md` as an analytical deliverable. Do not
perform a broad refactor in this phase.

The document must contain:

- a current pipeline and call-flow diagram;
- a responsibility table naming the current code owner, duplicate implementations,
  desired ownership class, and preserving regressions;
- classification of each responsibility as generic source, workspace, linguistic,
  name/scope/graph, Thorn mathematical interpretation, or Thorn assurance policy;
- high-risk custom parsing and resolution hotspots;
- proposed adapter boundaries for #158-#160;
- a target layering that does not preselect an external tool;
- positive statements of what remains Thorn-owned;
- sequencing recommendations for the remaining programme.

The audit must examine at least the files named by #157. Initial hotspots already
requiring evidence include:

- source eligibility in `project_semantic_context.py`, the frontend adapters, and
  symbol masking;
- sentence discovery in `project_semantic_context.py`, `project_context_source.py`,
  and `support_extract.py`;
- include traversal in the frontend adapters and semantic-context document ordering;
- phrase grammar and lexical morphology below the existing `LinguisticFrontend`;
- visibility and shadowing across `SymbolTable`, semantic-context resolution, and
  `SymbolResolutionIR`.

## Phase 2: establish the #162 semantic-dependency contract

Build the backend-independent contract before replacing production machinery.

1. Add a compact public semantic-dependency fixture matrix.
2. Add assertion helpers over existing Thorn-owned Symbol IR, canonical Proof IR, and
   advertised source handles.
3. Parameterize the contract by frontend/NLP capability, not backend-native objects.
4. Cover:
   - named prose definitions;
   - explicit ambient conventions and forward-only application;
   - same-file and cross-file shadowing;
   - transitive semantic closure;
   - comments, verbatim/listing regions, and irrelevant exposition;
   - ambiguous and malformed source outcomes;
   - exact source provenance and report navigation;
   - composition with structured theorem/result dependencies;
   - bounded closed-world review reachability.
5. Require reduced-capability configurations to advertise and test their limitation
   explicitly instead of silently passing a weaker contract.
6. Run structural assertions in ordinary CI and real-NLP assertions in the Local NLP
   contract.

Do not introduce a second semantic IR. The contract observes canonical Thorn state and
the `thorn-proof/1` projection.

## Phase 3: run the empirical evaluations

Each evaluation is a separate bounded change with fixtures, a reproducible harness,
measurements, a written failure analysis, and an explicit disposition. None changes
production defaults.

### #158: Tree-sitter LaTeX

- Implement an optional adapter behind `LatexFrontend`.
- Extend frontend conformance for eligible document text, comments/verbatim regions,
  document boundaries, include locations, malformed input, and exact provenance.
- Compare regex, pylatexenc, and Tree-sitter behavior and runtime.
- Verify that no Tree-sitter object crosses the adapter boundary.
- Classify Tree-sitter as a default candidate, optional backend, conformance oracle,
  benchmark/reference, or reject/defer.

### #159: workspace/project resolution

- Define the normalized project-order facts Thorn actually needs without embedding
  mathematical authority decisions in them.
- Build fixtures for nested, repeated, cyclic, missing, malformed, and macro-influenced
  includes, plus cross-file labels and declaration/redefinition ordering.
- Compare current Thorn behavior with TexLab and LaTeXML on concrete fixtures.
- Record licensing, packaging, process, performance, provenance, and reproducibility
  costs.
- Assign each tool a role per responsibility: runtime substrate, optional backend,
  development oracle, benchmark/reference, or reject/defer.

### #160: prose semantic declarations

- Freeze the #125 recognizer as the benchmark baseline.
- Define Thorn-owned semantic-declaration candidate/evidence types with exact source
  provenance and ambiguity status.
- Compare the current recognizer, a dependency-parser recognizer through
  `LinguisticFrontend`, and a deliberately small hybrid.
- Use paraphrase, lexical-substitution, inline-math, cross-file, adversarial, and
  expository controls.
- Measure intended-candidate recall, false-authority rate, lexical dependence,
  provenance fidelity, Local NLP stability, and Thorn-specific grammar complexity.
- Record a disposition: replace, hybridize, retain, or defer.

## Phase 4: enforce the architecture decision gate

Do not begin #161 until #157-#160 have produced explicit dispositions and the relevant
parts of #162 are executable.

Publish one consolidated decision record specifying:

- the authoritative owner of eligible document text/source regions;
- the authoritative owner of project order and workspace relationships;
- the selected linguistic candidate-recognition strategy;
- each external tool's runtime, optional, oracle, reference, or rejected role;
- capability behavior for structural-only mode;
- conformance and benchmark evidence supporting each choice;
- superseded code expected to be removed.

A negative evaluation is valid. Retaining a Thorn implementation is acceptable when
the evidence and its bounded contract are documented.

## Phase 5: implement #161 in bounded changes

Split consolidation so that every intermediate tree remains reviewable and testable.

1. Introduce the selected normalized source and project fact contracts.
2. Rewire semantic declaration recognition to consume eligible prose and normalized
   linguistic candidates.
3. Centralize Thorn-owned mathematical authority, project visibility, shadowing,
   ambiguity, and dependency-closure policy.
4. Rewire Symbol IR, canonical Proof IR, advertised source handles, and
   `thorn-proof/1` to the consolidated path.
5. Remove superseded source masking, sentence scanning, include-order reconstruction,
   morphology, and duplicate scope machinery.
6. Update architecture, mathematical-IR, Proof-IR, local-NLP, and trust-boundary
   documentation.

Compatibility adapters may be temporary. A temporary second semantic store is not
acceptable. The #162 contract must remain green after every step.

## Phase 6: final validation

The completed programme must pass:

- the full pytest suite;
- `ruff check .`;
- `mypy src`;
- frontend conformance for every supported adapter;
- the Local NLP contract;
- explicit structural-only capability tests;
- the complete semantic-dependency conformance matrix;
- exact report/source-navigation and bounded-rescue tests;
- parser and workspace benchmarks;
- packaging checks for adopted optional dependencies;
- a check that no provider/model calls were made.

The final architecture documentation must answer clearly what Thorn contributes beyond
a LaTeX parser, workspace engine, NLP dependency parser, graph library, or theorem
prover.

## Delivery model and pending decisions

The recommended delivery model is one reviewable PR per numbered issue, followed by
multiple bounded PRs for #161 if consolidation cannot remain small.

Two workflow decisions remain to be confirmed before the affected work begins:

1. whether to use one PR per issue as recommended;
2. whether evaluation-only dependencies and external binaries may be installed for
   #158 and #159.

Neither decision blocks starting #157 and the initial #162 contract.
