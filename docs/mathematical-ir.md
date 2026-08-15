# Thorn mathematical IR architecture

## Purpose

Thorn should not treat zero-inference checking as a small collection of cheap lint rules. The offline pass should be the deterministic mathematical front-end for the entire system.

The core pipeline is:

```text
LaTeX project
    |
    v
source-preserving LaTeX frontend
    |
    v
Thorn mathematical IR
    |-- results and theorem dependencies
    |-- symbols, definitions, roles, and scopes
    |-- claims and explicit support relationships
    `-- exact provenance back to source
    |
    +--> thorn check
    |       deterministic structural/support analysis
    |
    `--> thorn review
            selective semantic judgment over distilled structure
```

The result-level dependency graph introduced in #12 is the first layer of this IR. This document describes how to grow that layer without coupling Thorn to one LaTeX parser or pretending that syntactic parsing is mathematical understanding.

## Architectural rule: separate parsing from mathematical interpretation

A parser backend should answer syntactic questions such as:

- which files form the project;
- where environments begin and end;
- which macro calls occur and what arguments they contain;
- where inline and displayed mathematics occur;
- where text spans occur;
- exact byte/character offsets and line/column locations;
- enough error information to continue on imperfect input.

A parser backend should **not** decide that:

- `Let $f:X\to Y$` introduces a map;
- a sentence is a mathematical claim;
- `by compactness` supports a particular proof step;
- a use of a symbol is out of scope;
- prose is load-bearing;
- an implication is mathematically valid.

Those are Thorn concepts and belong above the parser boundary.

This gives us the key dependency direction:

```text
parser-specific syntax
        |
        v
frontend-neutral source model
        |
        v
Thorn mathematical IR
        |
        v
analyses / review
```

Nothing in the mathematical IR or analysis layers should import parser-specific node classes.

## 1. Frontend abstraction

Introduce a narrow frontend interface owned by Thorn. The exact Python names can evolve, but conceptually it should look like:

```python
class LatexFrontend(Protocol):
    def parse_project(self, main_file: Path) -> ParsedProject: ...
```

`ParsedProject` should contain frontend-neutral nodes or events sufficient for Thorn's extractors. Candidate primitives include:

- `ParsedFile`
- `EnvironmentSpan`
- `MacroCall`
- `MathSpan`
- `TextSpan`
- `ParseDiagnostic`
- `SourceRange`

Every frontend-neutral node must retain exact source provenance and raw source text (or stable access to it).

The initial implementation may adapt the current parser behind this interface. A later `pylatexenc`, Tree-sitter, or other backend should be able to implement the same contract.

### Backend selection

During development, backend selection should be explicit enough to support A/B tests, for example:

```text
thorn check paper.tex --frontend=current
thorn check paper.tex --frontend=pylatexenc
thorn check paper.tex --frontend=treesitter
```

This need not remain a permanent public CLI option. It is primarily a development and regression mechanism.

## 2. Conformance harness

Parser choice should be empirical. Each backend must run through the same source corpus and produce normalized structural facts that can be compared.

The conformance corpus should cover at least:

- theorem/lemma/proposition/corollary environments;
- custom `\newtheorem` declarations;
- theorem-to-proof association;
- labels and references;
- `\input` and `\include` across multiple files;
- inline and displayed mathematics;
- nested groups and environments;
- macros with optional and mandatory arguments;
- comments and escaped characters;
- malformed or incomplete LaTeX where useful recovery is possible;
- source ranges spanning included files;
- duplicate labels and ambiguous references;
- realistic user-defined macros around mathematical notation.

### Golden invariant from #12

The first-level theorem/result dependency graph is already a valuable compatibility oracle.

For every backend, the harness should ask:

> Does this backend reproduce the expected result units, labels, references, edge resolutions, source locations, transitive dependencies, and cycles?

A backend change that alters the graph is not automatically wrong, but every difference must be visible and explained. Parser replacement must never silently change Thorn's mathematical interpretation.

### Backend evaluation dimensions

Record at least:

- structural correctness against fixtures;
- exact source-location fidelity;
- macro/environment handling;
- recovery on malformed/incomplete input;
- multi-file project handling;
- performance;
- dependency and packaging complexity;
- amount of backend-specific adapter code;
- incremental parsing potential;
- stability/maintenance of the upstream dependency.

The goal is not to choose a parser forever. The goal is to make parser choice reversible.

## 3. Thorn mathematical IR

The mathematical IR is Thorn-owned and must remain independent of the syntax frontend.

### 3.1 Results

The result layer already includes theorem-like units and the result dependency graph from #12.

It should continue to represent:

- result identity and environment;
- statement;
- proof association;
- labels;
- direct/reverse/transitive dependencies;
- ambiguous dependencies;
- cycles;
- exact source provenance.

### 3.2 Symbols, definitions, and scopes

The next layer should conservatively represent explicitly introduced mathematical objects.

Candidate concepts:

```text
Symbol
Definition
Use
Scope
Role
Constraint
```

Examples of high-confidence introductions include:

```latex
Let $X$ be a compact space.
Let $f:X\to\mathbb R$ be continuous.
For $\epsilon>0$, choose $N$ ...
Define $g(x)=...$.
Set $A := ...$.
```

The IR should allow unknown or partial roles rather than forcing a guess. For example, if Thorn can establish that `f` is introduced but cannot determine its mathematical type, that is still useful.

Conventional mathematical notation must not generate undefined-symbol noise merely because it lacks a local declaration.

### 3.3 Claims and support

The proof layer should grow incrementally. Start with support relationships that are explicit in the source rather than attempting general proof understanding.

Examples include:

- `by Lemma~\ref{...}`;
- `from (12)`;
- `by definition`;
- named properties such as `by compactness` or `by continuity`;
- sufficiently clear `since ... therefore ...` relationships;
- a prose assertion that is subsequently depended on as a mathematical claim.

A possible conceptual model is:

```text
Claim
  source
  raw source
  normalized content (optional/partial)

SupportEdge
  source claim(s)
  target claim
  justification kind
  justification source
  explicitness/confidence
```

Crucially, a support edge can exist without Thorn knowing whether it is mathematically valid.

This gives the central division of responsibility:

> **Offline Thorn finds structural defects and suspicious support edges; semantic review judges whether mathematically nontrivial edges are valid.**

### 3.4 Load-bearing prose

Issue #14 treats load-bearing or "sneaky" prose as a first-class correctness risk.

The IR must therefore preserve mathematical assertions regardless of whether they appear in displayed mathematics or prose. Expository prose need not survive into distilled review context unless it carries mathematical dependency weight.

A useful future property is that the argument/support graph itself determines much of what prose is retained for semantic review.

## 4. Provenance is mandatory

Every IR object derived from source should retain enough information to return to the exact manuscript location.

At minimum:

```text
source file
source range / offsets
line and column information where practical
raw source span or stable access to it
```

This is required for:

- precise diagnostics;
- browsable reports;
- review prompts containing the original wording;
- revision-aware caching;
- explaining parser disagreements;
- safe future autofix.

Normalization must never destroy the route back to original source.

## 5. `thorn check`

`thorn check` consumes the mathematical IR and reports only mechanically justified findings.

Early high-confidence checks should include:

- duplicate/conflicting labels;
- ambiguous or broken result dependencies where resolvable structurally;
- result dependency cycles;
- explicit use-before-definition where scope/order make this objective;
- high-confidence undefined symbols;
- incompatible explicit redefinitions;
- conflicting symbol roles where both roles are explicit;
- explicit arity inconsistencies;
- scope violations;
- support references to unavailable results/definitions;
- structurally load-bearing claims with no identifiable incoming support when the claim/use relationship is sufficiently certain.

A zero-inference diagnostic must not claim that a nontrivial mathematical implication is false simply because the checker cannot establish it.

False positives are especially costly because this mode is intended to run routinely.

## 6. `thorn review`

The semantic reviewer should increasingly consume IR-derived context rather than rediscovering project structure from raw LaTeX.

A review request should eventually be able to contain only the relevant load-bearing material:

```text
THEOREM
statement
hypotheses

SYMBOLS / DEFINITIONS IN SCOPE
...

DEPENDENCIES
...

PROOF CLAIMS
P1 ...
P2 ... because ...
P3 ... because ...

STRUCTURAL CONCERNS
P3 has no explicit incoming support
```

Raw source remains available and should be included where wording matters.

This architecture enables selective escalation: deterministic analysis can identify the small number of edges or claims that require semantic judgment rather than paying a strong model to reread an entire paper indiscriminately.

## 7. Incremental implementation plan

Keep #6 as the umbrella for zero-inference mathematical IR and checking. Implement it through independently mergeable steps.

### Stage A — frontend abstraction and conformance

1. Define the frontend-neutral parser contract.
2. Wrap the current extraction path behind it without changing #12 behaviour.
3. Build the conformance corpus and normalized comparison harness.
4. Treat the existing result dependency graph as a golden compatibility layer.

### Stage B — parser backend experiment

1. Implement a serious alternative backend (initially `pylatexenc`).
2. Optionally spike a Tree-sitter backend.
3. Run both through the same conformance harness.
4. Document differences and choose a default based on evidence.

### Stage C — symbol/definition/scope IR

1. Define Thorn-owned symbol, definition, use, role, and scope models.
2. Extract only high-confidence introductions first.
3. Add synthetic bad cases plus nearby clean controls.
4. Add deterministic diagnostics only after the IR is stable enough to support them.

### Stage D — explicit proof/support skeleton

1. Add claim/support primitives.
2. Capture explicit citations and named justifications.
3. Add conservative prose-derived claims where structure is clear.
4. Exercise the sneaky-prose cases from #14.

### Stage E — semantic review over IR

1. Render model context from the IR.
2. Compare raw-LaTeX and IR-assisted review on the synthetic corpus.
3. Measure accuracy, false positives, requests, and token cost.
4. Use the result to drive selective escalation and dependency-aware caching.

## 8. Design invariants

The following should remain true as the implementation evolves:

1. **Parser backends are replaceable.** Mathematical analysis never depends directly on parser-specific node classes.
2. **Parser differences are testable.** All backends run through the same conformance harness.
3. **#12 behaviour is protected.** The result dependency graph is an early golden compatibility oracle.
4. **Provenance is never discarded.** Every derived mathematical object can point back to source.
5. **Unknown is preferable to guessed.** The deterministic IR may be partial.
6. **Offline does not masquerade as proof verification.** Structural absence of support and semantic invalidity are different findings.
7. **Prose can be mathematical.** Load-bearing prose belongs in the argument representation.
8. **The IR serves both modes.** `thorn check` and `thorn review` should share extraction and structure rather than maintaining parallel interpretations of the manuscript.
9. **False-positive control is a feature.** Every deterministic rule requires planted failures and nearby clean controls.
10. **Architecture should permit A/B testing.** Parser and later extraction strategies should be comparable on the same corpus before becoming defaults.

## 9. What success looks like

A mature Thorn run should look less like "send a paper to a model" and more like a compiler/static-analysis toolchain:

```text
LaTeX
  -> source-preserving parse
  -> mathematical IR
  -> deterministic analyses
  -> argument/support graph
  -> selective semantic review
  -> source-linked diagnostics/report
```

The difficult mathematical judgment remains a semantic task, but it is performed over a much cleaner, smaller, dependency-aware representation. The offline checker is therefore not a reduced version of Thorn; it is the structural foundation on which deep review depends.
