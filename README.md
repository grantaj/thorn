# Thorn

**Thorn is a compiler front-end / partial elaborator for mathematical arguments written in ordinary LaTeX.**

It recovers a source-linked mathematical representation and a canonical typed, deliberately partial **Proof IR**. That representation is the centre of the architecture: deterministic analysis, model-backed mathematical review, the proof visualiser, and the bounded Lean handoff all consume or project from the same recovered argument rather than inventing parallel semantics.

Thorn is built for humans doing mathematics with AI assistance. It does not certify an informal paper, replace mathematical judgment, or make ambiguity disappear by guessing. When the source is incomplete or informal, Thorn keeps that uncertainty explicit and preserves a path back to the exact LaTeX.

## What Thorn currently does

- **Deterministic structural analysis** — `thorn analyze` catches mechanically established problems such as broken or ambiguous internal result references, duplicate labels, dependency cycles, and explicit same-scope symbol-role conflicts.
- **Browsable review reports** — `thorn report`, or `--report` on analysis/review, writes a self-contained HTML report with result navigation, assurance boundaries, findings, and exact source provenance.
- **Proof argument visualisation** — `thorn graph` renders the recovered theorem/lemma dependencies and lets you drill into the supporting proof claims without creating a second proof representation.
- **Model-backed mathematical review** — `thorn review` sends the canonical proof state through the stable `thorn-proof/1` representation and bounded `thorn-proof-review/2` protocol, with exact source rescue only from mechanically advertised source handles.
- **Bounded Lean export** — `thorn lean` projects the currently supported canonical Proof-IR subset to Lean and leaves unsupported or missing formalisation content explicit instead of guessing it.

## Quickstart

**Start with [`docs/quickstart.md`](docs/quickstart.md).** It is an end-to-end first-run path for a mathematician:

```text
install Thorn
  -> run a useful keyless analysis
  -> open the browsable report
  -> inspect the recovered proof graph
  -> see an objective structural problem
  -> configure model review
  -> see a genuine mathematical concern
  -> export and check the currently supported Lean subset
```

The walkthrough uses three short manuscripts under [`examples/quickstart/`](examples/quickstart/) rather than evaluation fixtures or third-party papers.

A minimal source-tree installation is:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m spacy download en_core_web_sm
thorn --version
```

Thorn requires Python 3.11 or newer. The local spaCy model is part of the normal proof-recovery path and does not require an API key.

## Assurance boundaries

Thorn deliberately keeps different kinds of assurance distinct:

- **Structural cleanliness is not a proof.** It means the configured deterministic analyses found no structural diagnostic.
- **LLM review is not formal verification.** It is systematic mathematical review assistance over Thorn's recovered proof representation and, when requested, bounded exact source.
- **A Lean artifact is only as broad as the exported subset.** A complete generated theorem can be checked by Lean without implying that the rest of the informal paper was formalised.

The HTML report presents these regimes separately for the same reason.

## Architecture in one page

The normal data flow is:

```text
ordinary LaTeX
  -> source-preserving frontend / Thorn Math IR
  -> canonical typed Proof IR
  -> symbol and scope resolution
  -> higher proof structure and explicit obligations
  -> thorn-proof/1
       -> model review + bounded source rescue
  -> proof visualisation
  -> bounded Lean projection
```

Canonical Proof IR is the semantic centre. `thorn-proof/1` is the model-facing review representation, not a competing truth layer. Source rescue is a closed-world selection over stable source handles already advertised by Thorn. Providers own transport-specific structured parsing; Thorn owns the review protocol and its validation. Accepted replay evidence and quarantined rejected forensic evidence remain mechanically separate.

For the detailed design and assurance model, see:

- [`docs/semantic-dependency-architecture.md`](docs/semantic-dependency-architecture.md)
- [`docs/positioning.md`](docs/positioning.md)
- [`docs/report.md`](docs/report.md)
- [`docs/proof-visualizer.md`](docs/proof-visualizer.md)
- [`docs/lean-handoff.md`](docs/lean-handoff.md)
- [`eval/LLM_PROOF_LANGUAGE.md`](eval/LLM_PROOF_LANGUAGE.md)
- [`eval/PROOF_LANGUAGE_REVIEW.md`](eval/PROOF_LANGUAGE_REVIEW.md)

## CLI

The public entry points are:

```bash
thorn analyze paper.tex
thorn report paper.tex --open
thorn graph paper.tex --open
thorn review paper.tex --report --open
thorn lean paper.tex --result thm:main
thorn ir paper.tex --format json
```

`analyze`, `report`, `graph`, `lean`, and `ir` are keyless. `review` requires `OPENAI_API_KEY` and can incur provider charges. Run `thorn --help` for current options rather than relying on older issue examples.

## Development

For contributor tooling, install the development extra:

```bash
python -m pip install -e '.[dev]'
python -m spacy download en_core_web_sm
```

The repository's ordinary contracts are keyless:

```bash
pytest -q
ruff check .
mypy src
```

GitHub also runs dedicated **Local NLP contract** and **Lean contract** workflows. The Lean workflow uses the toolchain pinned by [`lean-toolchain`](lean-toolchain); model-backed live evaluations are separate, explicit, bounded operations and are not part of ordinary CI.

## Status

Thorn is an active research/prototype codebase, but the user-facing path above is real rather than aspirational: it operates on ordinary LaTeX, preserves exact source provenance, exposes recovered proof structure, reviews through `thorn-proof/1`, and supports a small mechanically honest Lean handoff.
