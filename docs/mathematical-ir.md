# Thorn IR architecture

## Purpose

Thorn provides **strong machine support for humans doing mathematics** while allowing them to keep writing ordinary mathematical LaTeX.

The deterministic frontend is not an offline mathematical correctness checker. Its job is to recover faithful, source-addressed evidence from a manuscript and partially elaborate that evidence into the strongest canonical proof representation Thorn can justify.

The centre of the architecture is therefore the typed, deliberately partial **Proof IR**. Deterministic analysis, systematic LLM review, reporting/navigation and formal-proof handoff are consumers of that representation rather than competing semantic systems.

```text
ordinary mathematical LaTeX
        |
        v
source-preserving mathematical frontend
        |
        v
rich / uncertainty-bearing Thorn Math IR
        |------------------> thorn analyze
        |                     deterministic structural diagnostics
        v
partial mathematical elaboration
        |
        v
canonical typed / partial Proof IR
      /          |             \
     v           v              v
deterministic  systematic     Lean / formal
proof tooling  LLM review     proof handoff
```

`thorn ir` currently exposes the frontend Math IR, not the canonical Proof IR serialization. The canonical Proof IR is a stronger downstream semantic layer built from the same source-derived evidence.

See [`positioning.md`](positioning.md) for the user-facing project contract. This document describes the technical separation between evidence recovery, canonical semantics and downstream projections.

## Math IR and Proof IR have different jobs

- **Math IR** records recoverable document, dependency, symbol, support, linguistic, uncertainty and provenance evidence.
- **Proof IR** records the strongest faithful mathematical meaning Thorn can canonically recover from that evidence.

Do not collapse these layers merely because a particular parser, review prompt, diagnostic or export backend would be easier to implement that way.

A parser may tell Thorn that a phrase has a certain dependency shape. A support extractor may tell Thorn that the manuscript presents one sentence as a reason for another. Those are useful observations, but neither is automatically the semantic meaning of the proof step.

Once Thorn can justify that the operation is, for example, theorem application with an instantiation and discharged preconditions, canonical Proof IR should encode that mathematical operation directly.

## Human + machine contract

The human-facing artifact remains ordinary mathematical writing. Thorn should not require authors to rewrite papers in a bespoke formal language before they receive useful machine assistance.

The machine-facing artifact is increasingly the canonical Proof IR together with exact source correspondence.

This matters for both primary handoffs:

- an LLM reviewer should receive explicit propositions, obligations, dependencies, transformations and uncertainty instead of reconstructing them from prose on every request;
- a formal backend should translate only mechanically recovered structure and expose explicit source-linked holes for the rest.

AI is therefore a first-class consumer of the IR, but not its semantic authority. Lean can become an independent checker of an exported subset, but is likewise not the definition of Thorn's internal semantics.

## Lean-informed partial elaboration

Lean is a useful architectural precedent because it separates surface syntax, elaborated meaning, typed core expressions, local proof state, metavariables and later presentation.

Thorn borrows that separation while solving a different problem. Its input is ordinary prose and notation rather than deliberately formal syntax, so elaboration is necessarily partial:

```text
informal LaTeX
    -> source-preserving evidence recovery
    -> partial elaboration
    -> typed / partial Proof IR + explicit holes + source correspondence
    -> multiple consumers
```

A single Thorn proof may legitimately contain:

- fully lowered typed expressions and binders;
- explicit hypotheses, goals and derived propositions;
- known dependencies whose inference rule remains unresolved;
- theorem applications, substitutions, instantiations and witnesses;
- rewrites and definition use where mechanically recovered;
- structured cases, contradiction, induction or WLOG reasoning;
- explicit proof obligations / holes;
- mathematical fragments that are only partially understood;
- source-addressed prose that remains genuinely load-bearing.

Partiality is not a temporary error state to be guessed away. It is part of the semantics of working faithfully with informal mathematics.

## Layer 1: source-preserving frontend and Math IR

### Parser boundary

A parser backend answers syntactic questions such as which files form the project, where environments and macro calls occur, and what exact source spans produced them. It does not decide that a theorem is true, that an implication follows or that two same-spelling variables denote the same mathematical object.

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

The result layer records theorem-like units, proof association, labels, references, direct/reverse/transitive dependencies, ambiguous dependencies, cycles and exact source provenance.

### Symbol / definition / scope evidence

The frontend symbol layer records explicit introductions, candidate uses, roles, constraints, definitions, lexical scopes and ambiguity. It is evidence for later elaboration; it is not by itself canonical symbol identity or a complete type system.

Equal spelling is never sufficient to identify two symbols. Conversely, lack of a local declaration does not turn conventional mathematical notation into an error.

### Claim and support evidence

The proof-support layer records source claims and visible relationships such as result references, equation references, definition use, named-property use and sufficiently explicit reason clauses.

A support edge means that the manuscript presents one item as support for another. It does **not** establish that the inference is mathematically valid, and support-extraction vocabulary should disappear once a stronger canonical mathematical interpretation has been recovered.

### Linguistic evidence

The local NLP layer provides grammatical and dependency evidence. It may suggest candidate bindings or support relations, but parser confidence is not mathematical truth.

Ambiguous evidence remains first-class and source-addressed.

## Layer 2: canonical typed / partial Proof IR

The semantic-compilation programme is tracked in issue #59. Its guiding principle is:

> Represent mathematics structurally rather than as compressed English wherever Thorn can do so safely.

The implemented Proof-IR stack now includes:

- typed formula / expression syntax;
- binders and quantifiers;
- canonical symbol identity, type/domain evidence and scope resolution;
- hypotheses, local context, theorem goals and intermediate propositions;
- explicit proof obligations / holes;
- typed proof-step edges;
- substitutions, theorem instantiations and existential witnesses;
- case splits, contradiction, contraposition, induction, WLOG/symmetry and nested proof structure;
- result application and specialization;
- definition use / unfolding semantics;
- equality rewriting;
- named-property support without invented property-specific semantics;
- exact source correspondence for lowered, unresolved and opaque material.

Where interpretation is incomplete, the IR says so explicitly. An unknown rule, unresolved binding, partial expression or source-addressed opaque proof step is preferable to invented structure.

## Current programme state

The main Proof-IR construction sequence is complete through issue #65:

1. #57 / PR #58 — graph-derived canonical proof slicing, safe normalization, unresolved-math nodes, irreducible load-bearing prose and source recovery;
2. #60 — Thorn-owned typed formula AST, binders and full/partial/opaque lowering states;
3. #61 — explicit proof obligations, local proof context and typed proof-step edges;
4. #62 — symbol/type/scope resolution plus substitutions, theorem instantiations and witnesses;
5. #63 — higher proof structure including cases, contradiction, induction and WLOG/symmetry;
6. #64 — definition use, rewriting and result-application semantics;
7. #65 — stable LLM-facing `thorn-proof/1` delaboration with bounded source-on-demand and deterministic fingerprints.

Issue #75 / PR #76 then used real-paper acceptance to repair fidelity failures where load-bearing context or result-application information could be lost. That work reinforced the invariant that no recovered proof edge may depend on mathematics that is neither represented in Proof IR nor reachable by a stable source handle.

The current architectural stage is **consumer handoff and evaluation**, not another semantic layer:

- #78 makes `thorn-proof/1` the actual semantic-review provider input, implements the bounded rescue round end-to-end and compares it with the existing raw-source baseline;
- #77 builds a deliberately bounded Proof-IR-to-Lean export and requires Lean to accept the mechanically recovered subset while preserving explicit holes elsewhere.

## Canonical semantics versus rendering

Canonical Proof IR is not a prompt, a JSON schema or Lean syntax.

There are three distinct representation levels:

1. **Source / frontend evidence** — rich, provenance-heavy and potentially parser/NLP-oriented.
2. **Canonical Proof IR** — typed, explicit, partial, source-addressable mathematical semantics.
3. **Consumer projection / delaboration** — deterministic rendering for an LLM, human report, debugger or formal backend.

The initial LLM-facing delaboration is now frozen as `thorn-proof/1`. A result application can render as:

```text
R1 ∀x∈R.(P(x)⇒Q(x))
H1 P(a)
C1 Q(a) <- R1[x:=a],H1
DEP R1 thm:current>thm:lemma
```

An unresolved obligation can remain explicit:

```text
C1 Q(a) <- R1[x:=a],?O1:P(a) ? @E1
NEED O1: P(a) | ctx R1,H1 @E1
```

The compact syntax is not the semantics. Quantification, application, substitution, dependency, uncertainty and obligation are canonical typed objects before they are rendered.

See [`../eval/LLM_PROOF_LANGUAGE.md`](../eval/LLM_PROOF_LANGUAGE.md) for the stable projection and source-rescue contract.

## Mixed certainty and no confidence laundering

Formal-looking output must not erase uncertainty.

A recovered operation may be confident, ambiguous or unresolved. A proposition may be fully lowered, partial or opaque. An inference may be structurally identified while a mathematical precondition remains open.

The governing rule is:

> Lowering, rendering or exporting mathematics may never make it more certain than the evidence from which it was recovered.

This applies equally to LLM packets and formal-system output. If a Lean backend cannot justify a step from canonical Proof IR, it must leave a hole or obligation rather than invent proof code.

## Source provenance is permanent

Every IR object derived from source retains enough information to return to the manuscript location: file, range/offsets, line information where practical, and raw source or stable access to it.

Normalization and elaboration must never destroy that route back to the manuscript.

This supports:

- precise diagnostics;
- bounded AI source-on-demand;
- browsable reports;
- revision-aware caching;
- parser comparisons;
- safe bounded autofix;
- formalisation obligations;
- human inspection of every machine interpretation.

A more formal internal representation is useful only if the mathematician can still see exactly what source produced it.

## Load-bearing mathematics must not disappear

The real-paper fidelity gate established a companion invariant:

> No recovered proof edge may depend on mathematical content that is neither represented in Proof IR nor reachable by a stable source handle.

Compression, compact delaboration and backend-specific exports are allowed to omit material from an initial view only when exact bounded recovery remains possible. A premise must never vanish merely because it is awkward to formalise or expensive to include in a prompt.

## Deterministic analysis

`thorn analyze` reports only mechanically justified findings. Current examples include duplicate/conflicting labels, ambiguous or broken result dependencies, dependency cycles and incompatible explicit symbol roles.

The presence of rich Math IR or Proof IR does **not** imply that every suspicious fact should become a diagnostic. Parser ambiguity, unresolved uses, unsupported obligations, unusual notation or unknown inference rules may be valuable machine state without establishing a user-facing defect.

Most importantly:

> **Deterministic analyzability does not define what belongs in Proof IR.**

A mathematical relation can be worth representing even when Thorn cannot verify it locally. This is a deliberate guard against the abandoned `thorn check` idea returning through implementation convenience.

See [`analysis.md`](analysis.md) for the deterministic rule boundary.

## Systematic LLM review

Semantic review is one primary consumer of canonical Proof IR, not the endpoint that defines it.

Issue #20 established provider-neutral review requests, IR-assisted contexts and controlled raw/IR/targeted evaluation infrastructure. Issue #65 subsequently established the stronger model-facing representation Thorn actually intends to use: deterministic `thorn-proof/1` plus exact bounded source rescue.

The production handoff is not complete yet. Issue #78 tracks wiring `thorn-proof/1` into the actual review provider path, retaining the older raw path as an evaluation baseline, and measuring whether Proof IR plus bounded source rescue preserves review quality while improving context control and reproducibility.

The reviewer remains responsible for substantive mathematical judgment beyond the mechanically checked subset. Thorn is responsible for presenting that judgment task faithfully and reproducibly.

## Lean / formal proof handoff

A formal proof assistant supplies a stronger assurance regime for the subset translated into kernel-checkable terms.

Thorn does not provide that guarantee itself. Its source is informal and its canonical IR deliberately permits partiality and holes.

Issue #77 therefore defines a bounded Lean handoff:

- export starts from canonical Proof IR, never by reinterpreting raw prose;
- only mechanically justified structure becomes Lean proof structure;
- unsupported structure becomes an explicit hole/goal rather than guessed code;
- source correspondence survives so each hole can be traced back to the manuscript;
- generated output distinguishes complete checked fragments from partial output containing holes;
- Lean acts as an independent checker of the subset Thorn has actually recovered.

This is a bridge toward formalisation, not an automatic paper-to-Lean claim and not a replacement for Lean's kernel.

## Design invariants

These invariants constrain future implementation work and prevent architectural regression.

1. **Human mathematical writing remains the source format.** Thorn adds machine structure without requiring wholesale formalisation first.
2. **Parser backends are replaceable.** Parser-specific node types do not become mathematical semantics.
3. **Frontend evidence is not canonical proof semantics.** Support edges, linguistic candidates and symbol tables feed elaboration; they do not define the final proof language.
4. **Structured mathematics beats narrated mathematics.** Once meaning is known safely, canonical Proof IR encodes the mathematical operation rather than its prose wording.
5. **Mixed certainty and partiality are first-class.** Unknown, ambiguous, partial and opaque states are represented explicitly rather than guessed away.
6. **No confidence laundering.** A projection or backend never promotes uncertainty merely by rendering it formally.
7. **Provenance is never discarded.** Every canonical object remains traceable to source.
8. **Load-bearing mathematics must remain represented or source-reachable.** Compactness is never permission to erase a premise.
9. **Same spelling is not symbol identity.** Binding and scope resolution must be semantic and conservative.
10. **Proof obligations are explicit objects.** Missing or unresolved reasoning must not disappear into prose sequencing.
11. **Canonical semantics are consumer-independent.** Model prompts, serializers, reports and formal exports are projections of the IR, not the IR itself.
12. **Deterministic diagnostics do not define the architecture.** Local checkability is useful but is not the criterion for whether mathematical structure belongs in the representation.
13. **AI is a primary consumer, not an oracle baked into construction.** Canonical Proof IR is built deterministically; models reason over it.
14. **A formal backend is an independent checker and quality test, not a semantic dependency.** Thorn remains useful on mathematics that cannot yet be fully formalised.
15. **False-positive control remains a feature.** Deterministic diagnostics require strong evidence and nearby clean controls even when the IR itself records richer uncertainty.
16. **Metamorphic equivalence matters.** Surface variants such as alpha-renaming or safely equivalent quantifier spellings should converge to the same canonical meaning when evidence permits.

## What success looks like

A mature Thorn workflow should look like a mathematical compiler/toolchain supporting a human researcher:

```text
human writes ordinary mathematics
        |
        v
Thorn recovers and partially elaborates proof structure
        |
        v
canonical typed / partial Proof IR + exact source map
      /                 \
     v                   v
systematic AI          formal handoff
review                 with explicit holes
      \                 /
       v               v
       human inspects, decides, edits
       and continues the mathematics
```

The north-star question is not “can Thorn check the paper offline?”

It is:

> Can downstream systems consume Thorn Proof IR and use the recovered mathematics without first reconstructing the argument from English prose?

That is the role of Thorn Proof IR.
