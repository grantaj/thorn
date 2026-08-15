# Thorn

**Thorn is a mathematical document analysis and AI-assisted review system for LaTeX manuscripts.**

Thorn does not certify proofs. Its deterministic frontend turns an ordinary mathematical manuscript into source-preserving Math IR; semantic reviewers can then use that representation to look for mathematical problems.

## What Thorn does

Thorn is designed as a **review pass**, not an authoring environment. Interactive agents and chat tools are excellent for exploring ideas, finding proof strategies, explaining mathematics, and rewriting text. Thorn assumes those tools may already be part of the author's workflow.

Its distinctive job is to treat the manuscript as an artifact: recover theorem/proof units, references, dependencies, symbols, proof-support evidence, ambiguity, and exact source locations; retain those facts in a Thorn-owned representation; and make that representation available to repeatable analysis and review procedures.

The core architecture is:

```text
LaTeX
  -> source-preserving frontend
  -> typed mathematical projection
  -> local linguistic structure
  -> ambiguity/evidence-bearing Thorn Math IR
       -> thorn analyze   deterministic structural diagnostics
       -> thorn ir        inspect/export the IR
       `-> thorn review   model-backed semantic mathematical review
```

The distinction matters. `thorn analyze` can establish mechanically visible structural facts such as a duplicate label, missing internal reference, circular result dependency, or conflicting explicit symbol roles. It **does not decide whether a proof is mathematically valid**. Mathematical judgment belongs to the semantic review layer (or, in a different assurance regime, to a formal proof system).

Thorn is deliberately not:

- a formal proof assistant or proof certificate;
- an offline theorem prover;
- a general-purpose mathematical writing agent;
- line-by-line autocomplete or an LSP that reacts to every edit;
- a tool that rewrites substantive mathematics in order to make a diagnostic disappear.

## Thorn and formal proof

Formal proof assistants such as **Lean** provide much stronger assurance once a theorem and its proof have been formalized: a small trusted kernel can check the resulting proof object. That is a different contract from Thorn's.

Thorn starts from ordinary mathematical manuscripts. Its frontend may eventually make it easier to translate sufficiently explicit obligations into formal systems, but Thorn's own Math IR is not a proof language and a clean Thorn review is never a proof certificate.

A plausible longer-term architecture is:

```text
ordinary LaTeX
  -> Thorn Math IR
       -> semantic review
       -> dependency/navigation tooling
       -> specialised mathematical models
       `-> bounded formalisation / proof-assistant backends
```

The IR is therefore a first-class product, not merely preprocessing for one model provider.

## Status

Very early prototype. The current pipeline recovers machine-usable theorem/proof structure, exact source provenance, internal dependencies, symbol structure, and ambiguity-bearing proof-support evidence. Semantic review is still evolving; issue #20 is testing review over distilled IR against the older raw-theorem-unit path.

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

Inspect the recovered IR:

```bash
thorn ir paper.tex
```

Export the complete Thorn Math IR as JSON:

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

See [`docs/analysis.md`](docs/analysis.md) for the deterministic rule boundary, [`docs/mathematical-ir.md`](docs/mathematical-ir.md) for the IR, and [`docs/local-nlp.md`](docs/local-nlp.md) for the linguistic frontend and uncertainty contract.

## What the frontend handles

- common theorem-like environments (`theorem`, `lemma`, `proposition`, `corollary`, `claim`)
- theorem environments declared with `\\newtheorem` / `\\newtheorem*`
- an immediately following `proof` environment
- multi-file projects discovered through `\\input` and `\\include`
- source file + line ranges
- direct theorem dependencies referenced through `\\ref`, `\\eqref`, `\\autoref`, `\\cref`, or `\\Cref` when the referenced label belongs to another extracted theorem-like unit
- conservative symbol, definition, role, constraint, and lexical-scope IR for explicit introductions
- local linguistic support/symbol candidates with exact source provenance and first-class ambiguity

The LaTeX layer is intentionally pragmatic, not a complete TeX interpreter. The linguistic layer supplies grammatical/dependency evidence only; it does not decide mathematical truth.

## Diagnostic philosophy

A Thorn finding should be specific enough that an author can either fix it or refute it. Model-backed findings should identify a concrete mathematical concern rather than produce vague referee prose.

Deterministic `thorn analyze` findings use lower-numbered structural rule codes and state only mechanically established facts. Parser-derived ambiguous relations can be retained in the IR without becoming findings. Thorn does not claim that a theorem is false because a structural relation is missing, suspicious, or linguistically ambiguous.

Thorn also distinguishes objective mathematical readability from subjective style. A simultaneous notation collision or materially ambiguous asymptotic convention can be reviewable; merely preferring a different symbol or prose style is not. Style rules should come from an explicitly adopted external style guide, not model taste.

## Test-driven specification

The public synthetic corpus specifies desired behavior, including clean controls that constrain false positives. The rough L1--L10 difficulty ladder is complemented by an orthogonal fault matrix covering theorem truth, proof validity, locality, fault class, repairability, detection method, reader consequence, and downstream impact.

The same fixtures exercise different layers: deterministic extraction/analysis should remain silent on many semantic mathematical faults that semantic review is expected to detect. This is intentional and makes the capability boundary testable.

See [the test matrix](docs/test-matrix.md) and the [evaluation corpus](eval/README.md).

## Development

```bash
pytest
ruff check .
mypy src
```
