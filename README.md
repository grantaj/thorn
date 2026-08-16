# Thorn

**Thorn builds machine-usable proof structure from ordinary mathematical writing so humans and AI can reason about manuscripts together.**

Thorn is an early-stage **partial mathematical elaborator** for LaTeX. It recovers a source-preserving mathematical representation from an ordinary manuscript and increasingly lowers that representation into a canonical typed **Proof IR**: expressions, binders, hypotheses, goals, proof obligations, dependencies, inference edges, symbol identity, and explicit unresolved holes.

The aim is strong support for humans doing mathematics with AI assistance. Thorn is not trying to replace the mathematician, certify an informal paper, or turn LaTeX into a formal proof by pretending ambiguity does not exist. It gives AI and other tools a faithful mathematical substrate so they do not have to reconstruct the proof from English prose on every pass.

## What Thorn does

Interactive agents and chat tools are excellent for exploring ideas, finding proof strategies, explaining mathematics, and rewriting text. Thorn assumes they may already be part of the author's workflow.

Its distinctive job is to treat the manuscript as a mathematical artifact and **compile as much of its proof structure as can be recovered safely**. The representation remains partial when the source is partial: uncertainty, unresolved operations, proof holes, and load-bearing prose are preserved rather than guessed away.

The architectural direction is:

```text
ordinary LaTeX manuscript
        |
        v
source-preserving mathematical frontend
        |
        v
rich / uncertainty-bearing Thorn Math IR
        |------------------> thorn analyze
        |                     deterministic structural diagnostics
        |
        `-> partial mathematical elaboration
                |
                v
        canonical typed Proof IR
          - expressions and binders
          - hypotheses and goals
          - proof obligations
          - typed inference edges
          - symbol identity and scope
          - substitutions / instantiations / witnesses
          - explicit holes and unresolved structure
          - permanent source correspondence
                |
                +--> AI-facing proof language / semantic review
                +--> deterministic proof tooling
                +--> dependency and navigation tooling
                `--> future bounded formalisation / proof-assistant export
```

`thorn ir` currently exposes the rich frontend Math IR. The canonical Proof IR is being built as a stronger downstream semantic layer under the programme in issue #59.

`thorn analyze` can establish mechanically visible structural facts such as a duplicate label, missing internal reference, circular result dependency, or conflicting explicit symbol roles. It **does not decide whether a proof is mathematically valid**. A clean deterministic analysis is therefore not the product goal and must not constrain the Proof IR to facts that can be checked offline.

## Human + AI mathematics

Thorn is intended to sit between ordinary mathematical practice and increasingly capable AI systems.

A mathematician should be able to keep writing normal mathematics while Thorn provides a stable shared representation that an AI reviewer, proof assistant, editor, navigator, or specialised mathematical model can consume. The human-facing source remains the manuscript; the machine-facing source of truth is increasingly the canonical Proof IR plus exact correspondence back to the manuscript.

This gives AI a better interface than raw LaTeX alone. Instead of repeatedly inferring that a sentence introduced a witness, instantiated a theorem, discharged an obligation, or reused a definition, Thorn should encode those operations structurally whenever it has enough evidence.

The long-term success criterion is:

> Can a computer or LLM consume Thorn Proof IR and reason about the proof without first reconstructing the mathematics from English prose?

Over time, the answer should increasingly be yes.

## Thorn and Lean

Lean is an important **architectural precedent**, not Thorn's target language and not a claim about Thorn's assurance level.

Lean separates human-facing syntax, elaboration, a small typed core expression language, local proof state and metavariables, source/semantic information, and later presentation/delaboration. Thorn is borrowing that separation of concerns while solving a different problem.

Lean starts from deliberately formal input and elaborates to proof terms that a small trusted kernel can check. Thorn starts from ordinary mathematical prose and notation, where information may be omitted, implicit, ambiguous, or genuinely informal. Thorn's elaboration is therefore partial. Its Proof IR must be able to contain, in one proof:

- fully lowered typed expressions;
- explicit hypotheses, goals, and derived propositions;
- known dependencies whose inference rule is unresolved;
- substitutions, instantiations, and witnesses when recoverable;
- explicit proof obligations / holes;
- mathematical fragments that are only partially understood;
- source-addressed prose when it remains genuinely load-bearing.

So Thorn is **not Lean-lite** and a clean Thorn run is never a proof certificate. A future Lean or other proof-assistant backend would be a consumer and a test of Proof IR quality, not the definition of Thorn's semantics.

## What Thorn is not

Thorn is deliberately not:

- a formal proof assistant or proof certificate;
- an offline theorem prover;
- an autonomous replacement for mathematical judgment;
- a general-purpose mathematical writing agent;
- line-by-line autocomplete or an LSP that reacts to every edit;
- a tool that rewrites substantive mathematics merely to make a diagnostic disappear.

## Status

Very early prototype. The architecture is moving from document extraction plus review toward the computer-proof-IR programme tracked in issue #59.

Completed programme tranches include:

- graph-derived canonical proof slicing and source recovery;
- a Thorn-owned typed formula AST with binders and partial lowering (#60);
- explicit proof obligations and typed proof-step edges (#61).

The current tranche (#62) is strengthening symbol identity, type/domain and scope resolution together with structural substitution, theorem instantiation, and witness representation. Later tranches cover higher proof structure, rewriting/result-application semantics, a stable LLM-facing proof language, and bounded proof-assistant export experiments.

The earlier IR-assisted semantic-review programme (#20) is complete enough to provide review/evaluation infrastructure, but semantic review is now one consumer of a stronger Proof IR rather than the architectural endpoint.

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

Inspect the recovered frontend IR:

```bash
thorn ir paper.tex
```

Export the complete frontend Math IR as JSON:

```bash
thorn ir paper.tex --format json > thorn-ir.json
```

Run model-backed semantic review:

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

See [`docs/mathematical-ir.md`](docs/mathematical-ir.md) for the Math-IR / Proof-IR architecture, [`docs/analysis.md`](docs/analysis.md) for the deterministic rule boundary, [`docs/proof-support-ir.md`](docs/proof-support-ir.md) and [`docs/symbol-ir.md`](docs/symbol-ir.md) for frontend evidence layers, and [`docs/local-nlp.md`](docs/local-nlp.md) for the linguistic frontend and uncertainty contract.

The programme-level canonical Proof IR experiments are documented in [`eval/CANONICAL_PROOF_IR.md`](eval/CANONICAL_PROOF_IR.md), [`eval/TYPED_FORMULA_IR.md`](eval/TYPED_FORMULA_IR.md), and [`eval/PROOF_OBLIGATIONS.md`](eval/PROOF_OBLIGATIONS.md).

## What the frontend handles

- common theorem-like environments (`theorem`, `lemma`, `proposition`, `corollary`, `claim`)
- theorem environments declared with `\\newtheorem` / `\\newtheorem*`
- an immediately following `proof` environment
- multi-file projects discovered through `\\input` and `\\include`
- source file + line ranges
- direct theorem dependencies referenced through `\\ref`, `\\eqref`, `\\autoref`, `\\cref`, or `\\Cref` when the referenced label belongs to another extracted theorem-like unit
- conservative symbol, definition, role, constraint, and lexical-scope evidence for explicit introductions
- local linguistic support/symbol candidates with exact source provenance and first-class ambiguity

The LaTeX and linguistic layers are evidence-producing frontends, not the canonical semantics of a proof. Parser or NLP vocabulary should disappear from the Proof IR whenever Thorn has safely recovered the corresponding mathematical meaning.

## Design principles

### Structured mathematics first

If Thorn understands that a phrase means a quantifier, implication, membership relation, theorem application, substitution, witness introduction, or other mathematical operation, the canonical Proof IR should encode that structure rather than preserve the vocabulary used to narrate it.

### Partiality is first-class

Unknown is preferable to guessed. Thorn should expose unresolved proof obligations, ambiguous bindings, partially lowered expressions, and opaque load-bearing prose rather than manufacture certainty to make the representation look formal.

### Provenance is permanent

Every lowered, unresolved, or opaque item must retain an exact route back to manuscript source. More formal structure must never mean losing the author's original wording.

### The IR is not designed around one consumer

AI semantic review is a primary intended consumer, but the canonical representation must not be weakened or made prompt-shaped for one model provider. Deterministic tools, navigation, specialised models, reports, and formal-system experiments should share the same semantics.

### Offline diagnostics do not define the architecture

A useful deterministic rule is welcome, but inability to check a mathematical fact locally is not a reason to omit it from the IR. The representation should capture the strongest faithful mathematical structure Thorn can recover; different consumers can apply different assurance regimes to it.

## Test-driven specification

The public synthetic corpus specifies desired behavior, including clean controls that constrain false positives. The rough L1--L10 difficulty ladder is complemented by an orthogonal fault matrix covering theorem truth, proof validity, locality, fault class, repairability, detection method, reader consequence, and downstream impact.

The same fixtures can exercise several layers independently: frontend extraction, canonical Proof IR, deterministic structural analysis, AI review, and eventually formal export. This is intentional. A fault may be faithfully represented in Proof IR even when deterministic analysis cannot diagnose it.

See [the test matrix](docs/test-matrix.md) and the [evaluation corpus](eval/README.md).

## Development

```bash
pytest
ruff check .
mypy src
```
