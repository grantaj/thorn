# Thorn IR architecture

## Purpose

Thorn exists to provide **strong machine support for humans doing mathematics**, especially in workflows where AI systems help inspect, reason about, and improve ordinary mathematical manuscripts.

The deterministic frontend is not an offline mathematical correctness checker. Its main job is to recover faithful source-addressed mathematical evidence from LaTeX. The architectural endpoint is stronger: Thorn should partially elaborate that evidence into a canonical computer proof representation that downstream tools can reason over directly.

This distinction is important enough to be a project invariant.

```text
ordinary LaTeX manuscript
        |
        v
source-preserving mathematical frontend
        |
        v
rich / uncertainty-bearing Thorn Math IR
        |------------------> deterministic structural analysis
        |
        `-> partial mathematical elaboration
                |
                v
        canonical typed Proof IR
                |
                +--> AI-facing proof language / semantic review
                +--> deterministic proof tooling
                +--> dependency / navigation / reporting
                `--> future bounded proof-assistant export
```

The Math IR and Proof IR are related but have different jobs.

- **Math IR** records recoverable document, dependency, symbol, support, linguistic, uncertainty, and provenance evidence.
- **Proof IR** is the strongest faithful mathematical meaning Thorn can canonically recover from that evidence.

Do not collapse those layers merely because a particular parser, review prompt, or deterministic diagnostic would be easier to implement that way.

## Human + AI contract

The human-facing artifact remains ordinary mathematical writing. Thorn should not require authors to rewrite papers in a bespoke formal language before they can benefit from structured AI assistance.

The machine-facing artifact should increasingly be the canonical Proof IR together with exact source correspondence.

That gives an AI reviewer or reasoning system a better interface than raw LaTeX. If Thorn knows that the manuscript introduced a witness, instantiated a theorem, substituted a term, opened a case, or discharged an obligation, downstream AI should receive that operation as structure rather than being asked to rediscover it from prose.

AI is therefore a first-class consumer of the IR, but not its semantic authority. The canonical representation must remain Thorn-owned, deterministic in construction, loss-aware, and independent of any one model provider or prompt format.

## Lean-informed architecture

Lean is an architectural precedent, not Thorn's target language or semantic model.

Useful ideas to borrow include the separation between:

- surface syntax and elaborated meaning;
- a small typed core expression representation and presentation syntax;
- local hypotheses / goals and narrated tactics;
- metavariables or unresolved obligations and completed terms;
- semantic objects and source-information trees;
- canonical representation and later delaboration for humans or other consumers.

Thorn solves a different problem because its source is ordinary mathematical prose rather than deliberately formal syntax.

A useful description is therefore:

```text
informal LaTeX
    -> source-preserving evidence recovery
    -> partial elaboration
    -> typed / partial Proof IR + explicit holes + source correspondence
    -> deterministic consumers / AI-facing delaboration / formal-subset export
```

The crucial Thorn-specific property is **mixed certainty**. A single proof may contain fully lowered mathematical expressions, known dependencies with an unknown inference rule, unresolved formulas, explicit proof obligations, ambiguous symbol identity, and irreducible source-addressed prose.

Partiality is not a temporary error state that must be guessed away. It is part of the semantics of working with informal mathematics.

## Layer 1: source-preserving frontend and Math IR

### Parser boundary

A parser backend should answer syntactic questions such as which files form the project, where environments and macro calls occur, and what exact source spans produced them. It should not decide that a theorem is true, that an implication follows, or that two same-spelling variables are the same mathematical object.

```text
parser-specific syntax
        |
        v
frontend-neutral source model
        |
        v
Thorn Math IR evidence
```

Nothing above the parser boundary should depend directly on parser-specific node classes.

### Result and dependency evidence

The result layer records theorem-like units, proof association, labels, references, direct/reverse/transitive dependencies, ambiguous dependencies, cycles, and exact source provenance.

### Symbol / definition / scope evidence

The frontend symbol layer records explicit introductions, candidate uses, roles, constraints, definitions, lexical scopes, and ambiguity. It is evidence for later elaboration; it is not yet the final identity or type theory of Proof IR.

Equal spelling must never be sufficient to identify two symbols. Conversely, lack of a local declaration must not turn conventional mathematical notation into an error.

### Claim and support evidence

The proof-support layer records source claims and visible relationships such as result references, equation references, definition use, named-property use, and sufficiently explicit reason clauses.

A support edge means that the manuscript presents one item as support for another. It does **not** establish that the inference is mathematically valid, and it should not become the permanent semantic vocabulary for proof reasoning merely because it was useful during extraction.

### Linguistic evidence

The local NLP layer provides grammatical and dependency evidence. It may suggest candidate bindings or support relations, but parser confidence is not mathematical truth.

Ambiguous evidence remains first-class and source-addressed.

## Layer 2: canonical typed Proof IR

The computer proof IR programme is tracked in issue #59.

Its guiding principle is:

> Represent mathematics structurally rather than as compressed English wherever Thorn can do so safely.

The canonical Proof IR should increasingly contain:

- typed formula / expression syntax;
- binders and quantifiers;
- canonical symbol identity and scope;
- hypotheses and local context;
- theorem goals and intermediate propositions;
- explicit proof obligations / holes;
- typed proof-step edges;
- result and definition application;
- substitutions and theorem instantiations;
- existential witnesses and witness provenance;
- rewriting and equality-based replacement;
- case splits, contradiction, induction, WLOG / symmetry, and other higher proof structure;
- exact source correspondence for every lowered, unresolved, or opaque item.

Where interpretation is incomplete, the IR must say so explicitly. An unknown rule, unresolved binding, partial expression, or source-addressed opaque proof step is preferable to invented structure.

## Current programme state

The Proof IR is already more than a design sketch.

- Issue #57 / PR #58 established graph-derived canonical proof slicing, safe normalization, unresolved-math nodes, irreducible load-bearing prose, and source recovery.
- Issue #60 established a Thorn-owned typed formula AST with binders and explicit full/partial/opaque lowering states.
- Issue #61 established explicit proof obligations and typed proof-step edges with local proof context.
- Issue #62 is the current tranche: canonical symbol/type/scope resolution together with substitution, instantiation, and witness representation.

Later planned tranches cover higher proof structure, rewriting/result-application semantics, a stable LLM-facing proof-language projection, and bounded proof-assistant export experiments.

## Canonical semantics versus rendering

The canonical Proof IR is not a prompt and should not be designed as one.

There are at least three distinct representations:

1. **Source / frontend evidence** — rich, provenance-heavy and potentially parser/NLP-oriented.
2. **Canonical Proof IR** — typed, explicit, partial, source-addressable mathematical semantics.
3. **Consumer projection / delaboration** — compact deterministic rendering for an LLM, human report, debugger, or formal backend.

For example, an LLM-facing rendering might eventually contain something like:

```text
T4 ∀(x:ℝ). P(x)⇒Q(x)
H1 P(a)
C1 Q(a) <- H1,T4[x:=a]
C2 R(a) <- C1,D3
C3 ? <- C2 @P7
```

The compact syntax is not the semantics. The structures behind quantification, application, substitution, dependency, and unresolved obligation must be canonical typed objects.

## Source provenance is permanent

Every IR object derived from source must retain enough information to return to the manuscript location: file, range/offsets, line information where practical, and raw source or stable access to it.

Normalization and elaboration must never destroy that route back to the manuscript.

This supports:

- precise diagnostics;
- AI source-on-demand;
- browsable reports;
- revision-aware caching;
- parser comparisons;
- safe bounded autofix;
- proof-assistant export diagnostics;
- human inspection of every machine interpretation.

A more formal internal representation is valuable only if the mathematician can still see exactly what source produced it.

## Deterministic analysis

`thorn analyze` reports only mechanically justified findings. Current examples include duplicate/conflicting labels, ambiguous or broken result dependencies, dependency cycles, and incompatible explicit symbol roles.

The presence of rich Math IR or Proof IR does **not** imply that every suspicious fact should become a diagnostic. Parser ambiguity, unresolved uses, unsupported obligations, unusual notation, or unknown inference rules may be valuable machine state without establishing a user-facing defect.

Most importantly:

> **Deterministic analyzability does not define what belongs in Proof IR.**

A mathematical relation can be worth representing even when Thorn cannot verify it locally. The representation should capture the strongest faithful structure available; consumers with different assurance regimes can then reason about it.

This prevents the abandoned `thorn check` idea from creeping back into the architecture through implementation convenience.

## AI semantic review

Semantic review is one important consumer of Thorn's representation, not the endpoint that defines it.

Issue #20 established IR-assisted review contexts, provider-neutral review requests, and controlled raw/IR/targeted evaluation paths. That work demonstrated that model-backed review can consume Thorn-owned structure rather than rediscovering the whole document graph from raw LaTeX.

The next architectural step is stronger: review should increasingly consume a deterministic projection of canonical Proof IR. The reviewer should reason over explicit propositions, obligations, dependencies, symbol identities, substitutions, and unresolved steps, with bounded source-on-demand when wording matters.

Do not weaken the canonical IR merely because an LLM could infer the missing information from prose.

## Formal proof backends

Formal proof assistants such as Lean provide a much stronger assurance regime once a theorem and proof have been formalized into kernel-checkable terms.

Thorn does not provide that guarantee. Its source is informal and its Proof IR explicitly permits partiality and holes.

A future proof-assistant backend should therefore be treated as:

- a consumer of the subset of Proof IR that has become formal enough;
- a way to expose remaining elaboration obligations;
- a quality test for the canonical representation;
- never the definition of Thorn's internal semantics.

## Design invariants

These invariants are intended to constrain future implementation work and prevent architectural regression.

1. **Human mathematical writing remains the source format.** Thorn adds machine structure without requiring wholesale formalisation first.
2. **Parser backends are replaceable.** Parser-specific node types do not become mathematical semantics.
3. **Frontend evidence is not canonical proof semantics.** Support edges, linguistic candidates, and symbol tables feed elaboration; they do not define the final proof language.
4. **Structured mathematics beats narrated mathematics.** Once meaning is known safely, canonical Proof IR encodes the mathematical operation rather than its prose wording.
5. **Partiality is first-class.** Unknown, ambiguous, partial, and opaque states are represented explicitly rather than guessed away.
6. **Provenance is never discarded.** Every canonical object remains traceable to source.
7. **Same spelling is not symbol identity.** Binding and scope resolution must be semantic and conservative.
8. **Proof obligations are explicit objects.** Missing or unresolved reasoning must not disappear into prose sequencing.
9. **Canonical semantics are consumer-independent.** Model prompts, serializers, reports, and formal exports are projections of the IR, not the IR itself.
10. **Deterministic diagnostics do not define the architecture.** Local checkability is useful but is not the criterion for whether mathematical structure belongs in the representation.
11. **AI is a primary consumer, not an oracle baked into construction.** Canonical Proof IR is built deterministically; models reason over it.
12. **A proof-assistant backend is a quality test, not a semantic dependency.** Thorn remains useful on mathematics that cannot yet be fully formalized.
13. **False-positive control remains a feature.** Deterministic diagnostics require strong evidence and nearby clean controls even when the IR itself records richer uncertainty.
14. **Metamorphic equivalence matters.** Surface variants such as alpha-renaming or safely equivalent quantifier spellings should converge to the same canonical meaning when evidence permits.

## What success looks like

A mature Thorn workflow should look less like "send a paper to a model" and more like a mathematical compiler/toolchain supporting a human researcher:

```text
human writes ordinary mathematics
        |
        v
Thorn recovers and partially elaborates proof structure
        |
        v
canonical typed Proof IR + exact source map
        |
        +--> AI reasons over explicit mathematics
        +--> deterministic tools inspect known structure
        +--> reports navigate proof dependencies and holes
        `--> formal backends consume sufficiently explicit subsets
        |
        v
human inspects, decides, edits, and continues the mathematics
```

The north-star question is not "can Thorn check the paper offline?"

It is:

> Can a human mathematician and an AI system share a faithful machine representation of the proof that is substantially better than repeatedly reconstructing the mathematics from prose?

That is the role of Thorn Proof IR.
