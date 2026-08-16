# Thorn

**Thorn is a compiler front-end / partial elaborator for mathematical arguments written in ordinary LaTeX.**

It turns a manuscript into an explicit, source-linked mathematical representation and then into a canonical typed, deliberately partial **Proof IR**. That representation is the centre of the architecture. Two primary downstream paths are systematic LLM review and progressive handoff to Lean or another formal proof system.

Thorn is built for humans doing mathematics with machine assistance. It does not certify an informal paper, replace mathematical judgment, or make ambiguity disappear by guessing. When the source is incomplete or informal, the IR stays incomplete or informal in an explicit way.

## Why Thorn

Mathematicians should be able to **write normal LaTeX first**. Interactive agents and chat tools are useful for exploration, explanation and rewriting, but ad-hoc review repeatedly asks a model to reconstruct the manuscript's proof structure from prose.

Thorn's job is different: treat the manuscript as a mathematical artifact and compile as much of its argument structure as can be recovered faithfully. Hypotheses, goals, dependencies, proof obligations, theorem applications, substitutions, witnesses, rewrites, symbol identity, higher proof structure and unresolved steps should become explicit machine structure whenever the evidence justifies it.

The architecture is:

```text
ordinary mathematical LaTeX
        |
        v
source-preserving Math IR
        |------------------> thorn analyze
        |                     deterministic structural diagnostics
        v
canonical typed / partial Proof IR
      /                     \
     v                       v
systematic                 Lean / formal
LLM review                 proof handoff
```

The two handoffs share the same canonical semantics, uncertainty and source correspondence. They are not separate semantic systems.

`thorn ir` currently exposes the rich frontend Math IR. The stronger canonical Proof IR is an internal downstream representation built from that evidence. Its current stable LLM-facing projection is `thorn-proof/1`.

`thorn analyze` reports mechanically visible structural facts such as duplicate labels, missing internal references, circular result dependencies and conflicting explicit symbol roles. It **does not decide whether a proof is mathematically valid**. Local checkability is useful, but it does not define what mathematics Thorn is allowed to represent.

See [the positioning statement](docs/positioning.md) for the project-level contract and [`docs/mathematical-ir.md`](docs/mathematical-ir.md) for the technical IR architecture.

## Two user paths

### 1. Systematic LLM review

Thorn aims to make model-backed mathematical review reproducible and source-aware rather than equivalent to pasting a paper into a chat window.

The machinery around the model is the point:

- deterministic extraction and partial elaboration of mathematical structure;
- explicit hypotheses, dependencies, proof steps, obligations and uncertainty;
- source-addressed unresolved and opaque material;
- bounded exact source-on-demand instead of indiscriminate whole-paper context;
- stable, fingerprintable review packets;
- a basis for replay, caching, incremental review, regression testing and browsable reports.

The stable `thorn-proof/1` format and its bounded `NEED_SOURCE` contract are implemented. Issue #78 tracks the remaining production handoff and evaluation: **the current `thorn review` command still uses the existing semantic-review request path rather than `thorn-proof/1` as its normal provider input**.

The LLM remains a mathematical reviewer, not a trusted formal kernel. A clean model-backed review is not formal verification.

### 2. Bridge toward Lean and formal proof

The same Proof IR should progressively support formalisation. The goal is not arbitrary paper-to-Lean translation. It is to translate only the subset Thorn has genuinely recovered, emit useful proof skeletons and explicit holes elsewhere, and preserve exact source correspondence for every remaining formalisation obligation.

Lean can then act as an independent checker of the mechanically translated subset.

Issue #77 tracks the first bounded end-to-end proof of life:

```text
ordinary LaTeX
  -> Thorn Math IR
  -> canonical Proof IR
  -> generated Lean
  -> Lean accepts the mechanically recovered subset
```

Thorn is therefore **not Lean-lite**. It is intended to lower the activation energy between ordinary mathematical writing and formal proof without requiring authors to formalise everything before receiving value.

## What Thorn is not

Thorn is deliberately not:

- a formal proof assistant or proof certificate;
- an offline theorem prover;
- an automatic arbitrary-LaTeX-to-Lean translator;
- a claim that LLM review is formal verification;
- an autonomous replacement for mathematical judgment;
- a general-purpose mathematical writing agent;
- line-by-line autocomplete or an LSP that reacts to every edit;
- a tool that rewrites substantive mathematics merely to make a diagnostic disappear.

## Current status

Thorn is still an early-stage prototype, but the canonical Proof-IR construction sequence is now substantial rather than merely planned.

Implemented programme tranches include:

- graph-derived canonical proof slicing, source recovery and unresolved/load-bearing context (#57 / PR #58);
- typed formula ASTs, binders and partial lowering (#60);
- explicit proof obligations and typed proof-step edges (#61);
- symbol/type/scope resolution, substitutions, theorem instantiations and witnesses (#62);
- higher proof structure including cases, contradiction, induction and WLOG/symmetry (#63);
- definition use, rewriting and result-application semantics (#64);
- the stable `thorn-proof/1` LLM-facing projection and bounded source-on-demand contract (#65);
- real-paper fidelity repairs preserving load-bearing context and result applications (#75 / PR #76).

The next stage is **consumer handoff and evaluation**, not another speculative semantic layer:

- #78 integrates `thorn-proof/1` into the actual semantic-review provider path and compares it with the existing raw-source baseline;
- #77 builds the first bounded Lean export from canonical Proof IR.

The earlier IR-assisted semantic-review programme (#20) provides useful request/evaluation infrastructure, but semantic review is one consumer of Proof IR rather than the architectural endpoint.

No formal verification is claimed. A clean deterministic analysis means only that no implemented structural diagnostic fired. A clean model-backed review means only that no configured review diagnostic survived its review procedure.

## Install for development

The PyPI name `thorn` is already occupied, so the distribution is currently named `thorn-math` while the command remains `thorn`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m spacy download en_core_web_sm
```

With `uv`:

```bash
uv sync --extra dev
uv run python -m spacy download en_core_web_sm
```

The spaCy package is a normal runtime dependency. The English model is installed locally; once installed, the linguistic frontend makes no remote NLP/model calls.

## First use

Run deterministic structural analysis with no API key:

```bash
thorn analyze paper.tex
```

For a deliberately reduced structural-only run, useful in constrained environments and lightweight tests:

```bash
thorn analyze paper.tex --structural-only
```

Inspect the recovered frontend Math IR:

```bash
thorn ir paper.tex
```

Export that frontend IR as JSON:

```bash
thorn ir paper.tex --format json > thorn-ir.json
```

Run the current model-backed semantic-review path:

```bash
export OPENAI_API_KEY=...
thorn review paper.tex
```

Review one extracted result while developing prompts:

```bash
thorn review paper.tex --limit 1
```

Emit deterministic or review findings as JSON:

```bash
thorn analyze paper.tex --format json > thorn-analysis.json
thorn review paper.tex --format json > thorn-review.json
```

The historical shorthand `thorn paper.tex` continues to mean `thorn review paper.tex`. There is no `thorn check` mode: Thorn's deterministic frontend performs structural analysis, not mathematical correctness checking.

Useful options:

```text
--fail-on LEVEL        never | error | warning
--frontend NAME        current | regex | pylatexenc
--structural-only      disable the normal local linguistic frontend

review-specific:
--limit N              review only the first N extracted results
--model MODEL          model used for attacker and defender
--no-defender          show attacker findings without the defender pass
--no-cache             ignore and do not write the local cache
--cache-dir PATH       default: .thorn/cache
--min-confidence FLOAT suppress lower-confidence surviving findings
```

By default Thorn returns a non-zero exit status only when an `error` diagnostic is emitted.

See [`docs/analysis.md`](docs/analysis.md) for the deterministic rule boundary, [`docs/proof-support-ir.md`](docs/proof-support-ir.md) and [`docs/symbol-ir.md`](docs/symbol-ir.md) for frontend evidence layers, and [`docs/local-nlp.md`](docs/local-nlp.md) for the linguistic frontend and uncertainty contract.

The canonical Proof-IR layers are documented in [`eval/CANONICAL_PROOF_IR.md`](eval/CANONICAL_PROOF_IR.md), [`eval/TYPED_FORMULA_IR.md`](eval/TYPED_FORMULA_IR.md), [`eval/PROOF_OBLIGATIONS.md`](eval/PROOF_OBLIGATIONS.md), [`eval/HIGHER_PROOF_STRUCTURE.md`](eval/HIGHER_PROOF_STRUCTURE.md), [`eval/SEMANTIC_TRANSFORMATIONS.md`](eval/SEMANTIC_TRANSFORMATIONS.md), and [`eval/LLM_PROOF_LANGUAGE.md`](eval/LLM_PROOF_LANGUAGE.md).

## What the frontend handles

- common theorem-like environments (`theorem`, `lemma`, `proposition`, `corollary`, `claim`)
- theorem environments declared with `\\newtheorem` / `\\newtheorem*`
- an immediately following `proof` environment
- multi-file projects discovered through `\\input` and `\\include`
- source file + line ranges
- direct theorem dependencies referenced through `\\ref`, `\\eqref`, `\\autoref`, `\\cref`, or `\\Cref` when the referenced label belongs to another extracted theorem-like unit
- conservative symbol, definition, role, constraint, and lexical-scope evidence for explicit introductions
- local linguistic support/symbol candidates with exact source provenance and first-class ambiguity

The LaTeX and linguistic layers are evidence-producing frontends, not the canonical semantics of a proof. Parser or NLP vocabulary should disappear from Proof IR whenever Thorn has safely recovered the corresponding mathematical meaning.

## Design principles

### Structured mathematics first

If Thorn understands that a phrase means a quantifier, implication, membership relation, theorem application, substitution, witness introduction, rewrite or another mathematical operation, canonical Proof IR should encode that structure rather than preserve only the vocabulary used to narrate it.

### Mixed certainty is first-class

Unknown is preferable to guessed. Fully recovered structure, ambiguous bindings, partial expressions, unresolved proof obligations and opaque load-bearing prose may coexist in one proof.

### No confidence laundering

Lowering, rendering or exporting mathematics may never make it more certain than the recovered evidence. Formal-looking output is not permission to promote an unresolved inference into a known one.

### Provenance is permanent

Every lowered, unresolved or opaque item must retain an exact route back to manuscript source. More formal structure must never mean losing the author's original wording.

### Load-bearing mathematics must not disappear

If a recovered proof edge depends on mathematical content, that content must either be represented in Proof IR or remain reachable through a stable source handle.

### The IR is not designed around one consumer

LLM review and Lean/formal export are primary intended consumers, but the canonical representation must not become prompt-shaped or Lean-shaped. Deterministic tools, navigation, reports, specialised models and formal systems should share the same semantics.

### Offline diagnostics do not define the architecture

A useful deterministic rule is welcome, but inability to check a mathematical fact locally is not a reason to omit it from Proof IR. Different consumers can apply different assurance regimes to the same faithful representation.

## Diagnostic and readability boundary

A Thorn finding should be specific enough that an author can either fix it or refute it. Model-backed findings should identify a concrete mathematical concern rather than produce vague referee prose.

Deterministic `thorn analyze` findings state only mechanically established facts. Ambiguous or unresolved relations can remain useful IR without becoming findings, and Thorn must not claim that a theorem is false merely because a relation is missing or linguistically uncertain.

Thorn also distinguishes objective mathematical readability from subjective style. A simultaneous notation collision or materially ambiguous convention can be reviewable; merely preferring a different symbol, prose rhythm or house style is not. Style rules should come from an explicitly adopted external style guide rather than model taste.

## Test-driven specification

The public synthetic corpus specifies desired behavior, including clean controls that constrain false positives. The rough L1--L10 difficulty ladder is complemented by an orthogonal fault matrix covering theorem truth, proof validity, locality, fault class, repairability, detection method, reader consequence and downstream impact.

The same fixtures can exercise several layers independently: frontend extraction, canonical Proof IR, deterministic structural analysis, LLM review and eventually formal export. This is intentional. A fault may be faithfully represented in Proof IR even when deterministic analysis cannot diagnose it.

See [the test matrix](docs/test-matrix.md) and the [evaluation corpus](eval/README.md).

## Development

```bash
pytest
ruff check .
mypy src
```
