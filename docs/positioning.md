# Thorn positioning

Thorn is a **compiler front-end / partial elaborator for mathematical arguments**. It starts from ordinary mathematical LaTeX and recovers the strongest faithful, source-linked proof representation it can justify mechanically.

The centre of the architecture is Thorn's canonical, typed and deliberately partial **Proof IR**. It is not a model prompt and it is not a proof certificate. It is the shared mathematical representation from which downstream consumers work.

```text
ordinary mathematical LaTeX
          |
          v
 source-preserving Math IR
          |
          v
 canonical typed / partial Proof IR
       /          |          \
      v           v           v
systematic     proof       Lean / formal
LLM review     graph       replay handoff
```

Deterministic structural analysis is another consumer of recovered structure, but local checkability does not define what belongs in Proof IR.

## Write normal mathematics first

Thorn should meet mathematicians where they already work. Authors should not have to rewrite a paper in a bespoke formal language before receiving useful machine assistance.

The manuscript remains the human-facing source of truth. Thorn recovers explicit machine structure from it: expressions and binders, hypotheses and goals, proof obligations, dependencies, symbol identity and scope, theorem applications, substitutions, witnesses, rewrites, higher proof structure, and unresolved material where interpretation remains incomplete.

A proof may therefore contain fully recovered structure beside ambiguous steps, opaque but load-bearing prose, and explicit holes. That mixture is intentional. Informal mathematics is partially elaborated input, and Thorn must represent that fact rather than guess merely to make the result look formal.

## Path 1: systematic LLM review

The normal `thorn review` path performs mathematical review over the stable `thorn-proof/1` projection of canonical Proof IR using the bounded `thorn-proof-review/2` protocol.

The mathematical judgment still comes from the configured model. Thorn supplies the machinery around that judgment:

- deterministic recovery of proof structure before the provider is called;
- explicit hypotheses, dependencies, proof steps, obligations and uncertainty;
- source-addressed unresolved or opaque material;
- a typed closed-world source-selection contract;
- at most one bounded exact source-rescue turn from advertised stable handles;
- explicit carried review state across that rescue boundary;
- stable, fingerprintable provider requests;
- protocol validation owned by Thorn rather than the provider transport;
- mechanically distinct accepted replay evidence and quarantined rejected forensic evidence;
- report provenance that keeps source rescue visibly separate from mechanically verified evidence.

`thorn-proof/1` is a model-facing projection, not a second semantic truth layer. Provider adapters own transport/request-specific structured parsing; Thorn owns the higher-level review protocol and decides which responses are acceptable. The underlying Proof-IR review/provider path was established by #78 / PR #82; the current public `thorn review` command routes normal user review through that path.

An LLM reviewer is not a trusted formal kernel. A clean model-backed review means only that no configured mathematical finding survived that review procedure.

## Path 2: selective formal replay with Lean

The same canonical Proof IR supports a deliberately bounded Lean handoff without creating a second semantic system or requiring authors to write formal proof language. `thorn lean` exposes the currently implemented exporter without broadening what Thorn knows how to formalise.

The current handoff can translate a small, mechanically recovered subset including natural-number terms, unary predicates, universal implication, imported result application/specialisation, recovered instantiation, discharged application preconditions, and exact terminal conclusions. Missing supported preconditions remain explicit `sorry` obligations; structurally unsupported material remains unsupported.

A `complete` Thorn export means the generated subset contains no Thorn formalisation holes. Running the independent Lean executable then checks that generated artifact. Neither fact implies that an arbitrary informal manuscript, or even every supporting informal lemma proof, has been formalised.

The broader product thesis is **not** "translate increasingly large fractions of arbitrary LaTeX into Lean". The hypothesis being tested in #115 is that Thorn can identify **mechanically closed local proof operations** inside otherwise informal proofs, replay those exact operations independently in Lean, and return source-linked proof-quality evidence to the mathematician.

For example, a deep informal argument may contain an exact theorem application, specialization, rewrite or witness step that is precise enough to replay even though neighboring mathematics remains outside automatic formalisation. The useful question is therefore not "what percentage of this paper is formalised?" but which mathematical commitments already made by the manuscript Thorn can independently stress-test without guessing.

The full design thesis, assurance semantics and anti-goals are documented in [`lean-bridge.md`](lean-bridge.md). The current implementation contract remains in [`lean-handoff.md`](lean-handoff.md).

Thorn is therefore not Lean-lite and not an automatic arbitrary-LaTeX-to-Lean translator. Lean is one potential independent proof-quality instrument over faithfully recovered semantics. Complete theorem certification may emerge in unusually recoverable cases, but it is not the default workflow target and must not be achieved by pushing Lean-specific authoring requirements back into the manuscript.

## Proof IR is the shared contract

LLM review, the proof visualiser, reports, and Lean export/replay are consumers or projections of the same recovered semantics, not separate interpretations of the manuscript.

### Mixed certainty is first-class

Recovered structure can be confident, ambiguous, unresolved or opaque. Those states must remain visible to downstream consumers.

### No confidence laundering

Lowering, rendering or exporting mathematics may never make it more certain than the evidence from which it was recovered. A guessed inference does not become trustworthy because it is printed in a formal-looking syntax.

### Source correspondence is permanent

Every lowered, unresolved or opaque item must retain a stable route back to the manuscript. A compact model packet or a Lean formalisation obligation may omit source text initially, but Thorn must be able to recover the exact relevant source when the product contract says it is reachable.

### Load-bearing mathematics must not disappear

If a proof edge depends on mathematical content, that content must either be represented in Proof IR or remain mechanically reachable through a stable source handle. Compression and delaboration must not erase a premise simply because it is awkward to formalise.

### Canonical semantics are consumer-independent

`thorn-proof/1`, Lean code, JSON, reports and visualisations are projections over canonical Proof IR or adjacent stable analysis boundaries. None should become a competing semantic representation or drive the IR toward one provider's prompt format or one theorem prover's convenient encoding.

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

## Current product boundary

The current user-facing path is real and deliberately layered:

- `thorn analyze` — keyless deterministic structural analysis;
- `thorn report` / `--report` — source-linked self-contained HTML presentation;
- `thorn graph` — keyless interactive view of the recovered proof argument;
- `thorn review` — provider-backed `thorn-proof/1` mathematical review with bounded source rescue;
- `thorn lean` — keyless export of the currently supported formal subset, to be checked by the pinned Lean toolchain.

Start with [`quickstart.md`](quickstart.md) for the executable first-run path. The deeper evaluation documents retain the historical raw/Proof-IR comparison work and frozen experiments; those experiments are evidence about the architecture, not alternate end-user workflows.

The current command surface does not settle how far either downstream path should be pushed. Semantic-review fidelity remains evidence-driven, and #115 explicitly tests whether selective local Lean replay produces enough actionable proof-quality intelligence to justify expanding the formal bridge. Canonical Proof IR remains the stable semantic centre; consumer capabilities should expand only where they preserve fidelity and demonstrably help humans review mathematics.
