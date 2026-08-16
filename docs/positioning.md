# Thorn positioning

Thorn is a **compiler front-end / partial elaborator for mathematical arguments**. It starts from ordinary mathematical LaTeX and recovers the strongest faithful, source-linked proof representation it can justify mechanically.

The centre of the architecture is Thorn's canonical, typed and deliberately partial **Proof IR**. It is not a model prompt and it is not a proof certificate. It is the shared mathematical representation from which different downstream consumers can work.

```text
ordinary mathematical LaTeX
          |
          v
 source-preserving Math IR
          |
          v
 canonical typed / partial Proof IR
       /                    \
      v                      v
systematic                Lean / formal
LLM review                proof handoff
```

Deterministic structural analysis is another consumer of recovered structure, but local checkability does not define what belongs in Proof IR.

## Write normal mathematics first

Thorn should meet mathematicians where they already work. Authors should not have to rewrite a paper in a bespoke formal language before receiving useful machine assistance.

The manuscript remains the human-facing source of truth. Thorn's job is to recover explicit machine structure from it: expressions and binders, hypotheses and goals, proof obligations, dependencies, symbol identity and scope, theorem applications, substitutions, witnesses, rewrites, higher proof structure, and unresolved material where interpretation remains incomplete.

A proof may therefore contain fully recovered structure beside ambiguous steps, opaque but load-bearing prose, and explicit holes. That mixture is intentional. Informal mathematics is only partially elaborated input, and Thorn must represent that fact rather than guess merely to make the result look formal.

## Path 1: systematic LLM review

Thorn's LLM path is intended as a disciplined alternative to repeatedly giving a general model a block of LaTeX and asking whether the proof is correct.

The mathematical judgment may still come from an LLM, but Thorn supplies the machinery around that judgment:

- deterministic recovery of proof structure before the model is called;
- explicit hypotheses, dependencies, proof steps, obligations and uncertainty;
- source-addressed unresolved or opaque material;
- bounded exact source-on-demand rather than indiscriminate whole-paper context;
- stable, fingerprintable review packets;
- a basis for replay, caching, incremental review, regression testing and browsable reports.

The stable `thorn-proof/1` projection already provides a compact deterministic rendering of canonical Proof IR together with a bounded `NEED_SOURCE` rescue contract. Issue #78 tracks the remaining production handoff and controlled evaluation: `thorn review` does **not yet** use `thorn-proof/1` as its normal provider input.

An LLM reviewer is not a trusted formal kernel. A clean model-backed review means only that no configured review diagnostic survived that review procedure.

## Path 2: bridge toward Lean and formal proof

The same Proof IR should progressively support formalisation without creating a second semantic system.

The intended Lean handoff is deliberately bounded:

- export theorem statements and mechanically recovered structure;
- translate only operations Thorn genuinely understands;
- emit useful proof skeletons with explicit holes for everything else;
- retain exact source correspondence for those formalisation obligations;
- use Lean as an independent checker of the subset that was actually exported.

Issue #77 tracks the first end-to-end Lean proof of life. Thorn does **not** currently claim arbitrary-paper Lean translation, and unsupported prose must never be reconstructed or invented merely to make generated Lean compile.

Thorn is therefore not Lean-lite. Its useful role is to lower the activation energy between ordinary mathematical writing and formal proof while remaining useful long before a manuscript is fully formalised.

## Proof IR is the shared contract

LLM review and Lean export are consumers of the same canonical semantics, not separate interpretations of the manuscript.

That implies several permanent constraints.

### Mixed certainty is first-class

Recovered structure can be confident, ambiguous, unresolved or opaque. Those states must remain visible to downstream consumers.

### No confidence laundering

Lowering, rendering or exporting mathematics may never make it more certain than the evidence from which it was recovered. A guessed inference does not become trustworthy because it is printed in a formal-looking syntax.

### Source correspondence is permanent

Every lowered, unresolved or opaque item must retain a stable route back to the manuscript. A compact LLM packet or a Lean hole may omit source text initially, but Thorn must be able to recover the exact relevant source on demand.

### Load-bearing mathematics must not disappear

If a proof edge depends on mathematical content, that content must either be represented in Proof IR or remain reachable through a stable source handle. Compression and delaboration must not erase a premise simply because it is awkward to formalise.

### Canonical semantics are consumer-independent

`thorn-proof/1`, Lean code, JSON, reports and future interfaces are projections over canonical Proof IR. None of them should become a competing semantic representation or drive the IR toward one provider's prompt format.

## What Thorn is not

Thorn is not:

- a formal proof assistant or proof certificate;
- an offline theorem prover disguised as a linter;
- an automatic arbitrary-LaTeX-to-Lean translator;
- a claim that LLM review is formal verification;
- a hidden LLM inside deterministic IR construction;
- a general-purpose mathematical writing agent;
- a substitute for mathematical judgment.

`thorn analyze` has a deliberately narrower contract: it reports mechanically established structural facts. A clean deterministic run does not establish mathematical correctness.

## Current implementation boundary

The canonical Proof-IR construction sequence through issues #60-#65 is implemented, including typed formulas, proof obligations and typed edges, symbol/type/scope resolution, higher proof structure, semantic transformations, and the stable `thorn-proof/1` projection. The real-paper fidelity work in #75 / PR #76 repaired cases where load-bearing context or result-application information could otherwise be lost.

The next work is consumer handoff rather than another semantic layer:

- #78 integrates `thorn-proof/1` into the actual semantic-review provider path and evaluates it against the existing raw-source baseline;
- #77 builds the first bounded Proof-IR-to-Lean export and requires Lean to accept a mechanically recovered subset while preserving explicit holes elsewhere.

That distinction matters in the public documentation: the representation exists, while the two handoffs are still being completed and tested.
