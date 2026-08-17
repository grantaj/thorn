# Thorn quickstart

This walkthrough starts with ordinary LaTeX, stays keyless until the model-review step, and uses the same CLI and report paths intended for real manuscripts.

Run the commands from the repository root. The three tiny manuscripts live in `examples/quickstart/`; they are teaching examples, not evaluation fixtures.

## 1. Install Thorn and its local language model

Thorn currently requires Python 3.11 or newer. The supported source-tree installation is an editable install; Thorn is not currently documented as a PyPI package.

```bash
git clone https://github.com/grantaj/thorn.git
cd thorn
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m spacy download en_core_web_sm
thorn --version
```

On Windows, activate the virtual environment with the appropriate `Scripts` command instead of `source .venv/bin/activate`.

The spaCy model is local. It is part of Thorn's normal proof-recovery path and does not call OpenAI. If it is missing, Thorn reports that explicitly and points to `--structural-only` as a constrained/debugging fallback; install the model for the walkthrough rather than treating that fallback as the normal product path.

`thorn --version` should print the installed Thorn version. `thorn --help` shows the current public commands.

## 2. First useful run: no API key

Start with the healthy example:

```bash
thorn analyze examples/quickstart/clean/paper.tex \
  --report .thorn/quickstart-clean.html --open
```

You should see `thorn analyze: no deterministic structural diagnostics`, followed by the path to the HTML report. The report is the normal human-facing review artifact: its overview separates structural, semantic-review, and formal/Lean assurance; each theorem-like result links back to the exact LaTeX location; and expandable source context keeps provenance next to the mathematics.

A quiet structural result is deliberately narrow. It means Thorn did not find one of its deterministic structural problems. It does **not** prove the theorem, and at this point no model has reviewed the mathematics.

Now open the recovered proof argument:

```bash
thorn graph examples/quickstart/clean/paper.tex \
  --output .thorn/quickstart-clean-graph.html --open
```

At paper level, the graph shows that the final theorem uses the two lemmas. Select the theorem to inspect the recovered claims and their source locations. An arrow means Thorn recovered a support relationship in the argument; graph connectivity is not a claim that the step is mathematically valid.

Both commands are keyless.

## 3. See an objective structural problem

The second paper contains an ordinary authoring mistake: its proof cites a lemma label that does not exist in the manuscript.

```bash
thorn analyze examples/quickstart/structural-problem/paper.tex \
  --report .thorn/quickstart-structural.html --open
```

Thorn should report `TH103 Missing internal reference` and point to the broken `\ref{...}` in the proof. The HTML report carries the same diagnostic and source location.

Because `TH103` is an error-level diagnostic, the command exits with status 1. That is useful in CI. If you are running the walkthrough from a shell configured to stop on any nonzero status, add `--fail-on never`; the finding itself is unchanged.

This is the zero-cost first success case: the result comes entirely from deterministic analysis.

## 4. Model-backed mathematical review

The third paper is structurally ordinary but mathematically wrong:

```latex
If ac=bc, then a=b.
```

Its proof divides by `c` without assuming `c \ne 0`. That is a mathematical-review problem, not a broken-reference diagnostic.

Before configuring a key, you can see Thorn's failure path:

```bash
unset OPENAI_API_KEY
thorn review examples/quickstart/mathematical-problem/paper.tex
```

Thorn stops before constructing the OpenAI provider and explains that deterministic analysis, reports, and proof graphs remain available without a key.

When you want model review, put the key in the process environment rather than in the repository:

```bash
export OPENAI_API_KEY='your-key-here'
thorn review examples/quickstart/mathematical-problem/paper.tex \
  --report .thorn/quickstart-mathematical.html --open
```

Provider-backed review is billable. These examples are intentionally tiny, while `thorn analyze`, `thorn report`, and `thorn graph` require no provider call. Do not commit API keys; `.env` is ignored by this repository, but an environment variable or your normal secret manager is preferable to putting credentials in source files.

The normal `thorn review` path reviews Thorn's canonical proof state through `thorn-proof/1` and the bounded `thorn-proof-review/2` protocol. If the reviewer needs exact source that Thorn advertised as mechanically reachable, it may request one bounded source-rescue turn; the report keeps that supplied source visibly separate from mechanically verified evidence.

Model wording, finding IDs, confidence values, and even the exact number of findings are nondeterministic. For this example, look for the mathematical substance: division by `c` is unjustified unless `c` is known to be nonzero (and `c=0` gives immediate counterexamples). An invalid or expired key is reported as a provider/review failure rather than being mistaken for a mathematical result.

LLM review is mathematical review assistance, not formal proof certification. A quiet model-backed review means the configured review procedure returned no visible concern; it is not a theorem certificate.

## 5. The current Lean handoff

Thorn also has a deliberately small Lean export over the same canonical proof representation. The clean example's final theorem lies inside that supported subset.

The repository pins Lean in `lean-toolchain` (currently Lean 4.30.0). Install [Elan](https://github.com/leanprover/elan) if `lean` is not already available; from the repository root, Elan will honor the pinned toolchain. Check it with:

```bash
lean --version
```

Export the final theorem:

```bash
thorn lean examples/quickstart/clean/paper.tex \
  --result thm:main --output .thorn/quickstart-main.lean
```

For this example Thorn reports `Status: complete`, meaning the exported subset has no Thorn formalisation holes. Now ask the independent Lean executable to check that generated file:

```bash
lean .thorn/quickstart-main.lean
```

This is intentionally a bounded handoff. The generated theorem establishes that the recovered final theorem follows from the recovered lemma statements in the subset Thorn knows how to translate. It does **not** mean Thorn translated or Lean-verified the informal proofs of those lemmas, and it does not certify the whole manuscript. Unsupported mathematics remains unsupported or becomes an explicit source-linked formalisation obligation rather than being guessed into Lean.

See [`lean-handoff.md`](lean-handoff.md) for the exact supported subset.

## What Thorn has and has not established

Keep the three assurance regimes separate:

- A clean **structural** run means no configured deterministic structural diagnostic was found. It is not a proof.
- A clean **model review** means no configured model-review finding survived that review. It is not formal verification.
- A **Lean-complete export** describes only the subset Thorn actually exported without holes. Running Lean checks that generated artifact; it does not retroactively formalize the rest of the paper.

Thorn's job is to recover a faithful, source-linked representation of an ordinary mathematical argument and make systematic review and partial formalisation easier. The manuscript remains the human-facing source of truth.

For deeper detail, continue with [`positioning.md`](positioning.md), [`report.md`](report.md), [`proof-visualizer.md`](proof-visualizer.md), and [`lean-handoff.md`](lean-handoff.md).
