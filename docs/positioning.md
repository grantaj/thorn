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
LLM review                replay handoff
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

The stable `thorn-proof/1` projection provides the real canonical Proof-IR semantic-review handoff, together with a bounded `NEED_SOURCE` rescue contract. Issue #78 / PR #82 established that provider path while preserving the older raw-source path as an experimental baseline.

An LLM reviewer is not a trusted formal kernel. A clean model-backed review means only that no configured review diagnostic survived that review procedure.

## Path 2: selective formal replay with Lean

The same Proof IR can support an independent formal checking path without creating a second semantic system or requiring authors to write formal proof language.

Issue #77 established a deliberately small real end-to-end path from ordinary LaTeX through canonical Proof IR into generated Lean accepted by the pinned Lean toolchain for a mechanically complete theorem-application case. The backend fails closed when required semantics are ambiguous, missing or unsupported.

The broader product thesis is **not** "translate increasingly large fractions of arbitrary LaTeX into Lean". The hypothesis now being tested in #115 is that Thorn can identify **mechanically closed local proof operations** inside otherwise informal proofs, replay those exact operations independently in Lean, and return source-linked proof-quality evidence to the mathematician.

For example, a deep informal argument may contain an exact theorem application, specialization, rewrite or witness step that is precise enough to replay even though neighboring mathematics remains outside automatic formalisation.

The useful question is therefore not "what percentage of this paper is formalised?" but:

> Which mathematical commitments already made by the manuscript can Thorn independently stress-test, and does the result give the author actionable information about the argument they actually wrote?

The full design thesis, assurance semantics and anti-goals are documented in [`lean-bridge.md`](lean-bridge.md). The current implementation contract remains in [`lean-handoff.md`](lean-handoff.md).

Thorn is therefore not Lean-lite and not an automatic arbitrary-LaTeX-to-Lean translator. Lean is potentially one independent proof-quality instrument over faithfully recovered local semantics. Complete theorem certification may emerge in unusually recoverable cases, but it is not the default workflow target and must not be achieved by pushing Lean-specific authoring requirements back into the manuscript.

## Proof IR is the shared contract

LLM review and Lean export/replay are consumers of the same canonical semantics, not separate interpretations of the manuscript.

That implies several permanent constraints.

### Mixed certainty is first-class

Recovered structure can be confident, ambiguous, unresolved or opaque. Those states must remain visible to downstream consumers.

### No confidence laundering

Lowering, rendering or exporting mathematics may never make it more certain than the evidence from which it was recovered. A guessed inference does not become trustworthy because it is printed in a formal-looking syntax.

### Source correspondence is permanent

Every lowered, unresolved or opaque item must retain a stable route back to the manuscript. A compact LLM packet or a Lean formalisation obligation may omit source text initially, but Thorn must be able to recover the exact relevant source on demand.

### Load-bearing mathematics must not disappear

If a proof edge depends on mathematical content, that content must either be represented in Proof IR or remain reachable through a stable source handle. Compression and delaboration must not erase a premise simply because it is awkward to formalise.

### Canonical semantics are consumer-independent

`thorn-proof/1`, Lean code, JSON, reports and future interfaces are projections over canonical Proof IR. None of them should become a competing semantic representation or drive the IR toward one provider's prompt format or one theorem prover's convenient encoding.

## What Thorn is not

Thorn is not:

- a formal proof assistant or proof certificate;
- an offline theorem prover disguised as a linter;
- an automatic arbitrary-LaTeX-to-Lean translator;
- a requirement to write Lean-flavoured LaTeX;
- a claim that LLM review is formal verification;
- a hidden LLM inside deterministic IR construction;
- a general-purpose mathematical writing agent;
- a substitute for mathematical judgment.

`thorn analyze` has a deliberately narrower contract: it reports mechanically established structural facts. A clean deterministic run does not establish mathematical correctness.

## Current implementation boundary

The canonical Proof-IR construction sequence through issues #60-#65 is implemented, including typed formulas, proof obligations and typed edges, symbol/type/scope resolution, higher proof structure, semantic transformations, and the stable `thorn-proof/1` projection. The real-paper fidelity work in #75 / PR #76 repaired cases where load-bearing context or result-application information could otherwise be lost.

Both initial downstream handoffs now exist:

- #78 / PR #82 made `thorn-proof/1` a real semantic-review provider input with bounded source rescue and exact record/replay;
- #77 / PR #81 added the first bounded Proof-IR-to-Lean export and actual pinned-Lean acceptance regression for a mechanically recovered subset.

Those proof-of-life integrations do not settle how far either path should be pushed. Follow-up work is evidence-driven: semantic-review fidelity is evaluated against natural and adversarial cases, while #115 explicitly tests whether selective local Lean replay produces enough actionable proof-quality intelligence to justify expanding the formal bridge.

That distinction matters in the public documentation: canonical Proof IR is the stable semantic centre; consumer capabilities should expand only where they preserve fidelity and demonstrably help humans review mathematics.
