# Thorn

**Thorn is an AI-assisted correctness linter for mathematical manuscripts.**

Thorn does not certify proofs. It tries to break them before your readers do.

## Where Thorn fits

Thorn is designed as a **review pass**, not an authoring environment. Interactive agents and chat tools are excellent for exploring ideas, finding proof strategies, explaining mathematics, and rewriting text. Thorn assumes those tools may already be part of the author's workflow.

Its job begins when a manuscript reaches a point worth checking as an artifact. Given the LaTeX source, Thorn applies a repeatable adversarial review procedure to the mathematical argument and reports specific, source-located findings. The author should not have to remember which questions to ask an agent, construct the right review prompt, or manually keep track of what has and has not been checked.

That makes Thorn complementary to an agent in an editor: the agent helps you **write and think**; Thorn gives the resulting manuscript a **defined correctness pass** that can be rerun at useful checkpoints and, eventually, as part of a build or CI workflow.

Thorn is deliberately not:

- a formal proof assistant or proof certificate;
- a general-purpose mathematical writing agent;
- line-by-line autocomplete or an LSP that reacts to every edit;
- a tool that rewrites substantive mathematics in order to make a warning disappear.

### Thorn and formal proof

Formal proof assistants such as **Lean** provide much stronger assurance once a theorem and its proof have been formalized: a small trusted kernel can check the resulting proof object. That is a different contract from Thorn's. Thorn starts from ordinary mathematical manuscripts and aims to provide useful correctness checking **without requiring the author to formalize the paper first**.

The intended position is therefore between unchecked informal mathematics and full formal verification. Formal methods are an escalation path, not an entry requirement. A mathematician should be able to get value from Thorn while continuing to write ordinary LaTeX; where a claim is sufficiently explicit and tractable, a future Thorn could ask a stronger backend to check a bounded proof obligation.

The current parser and offline structural checks are a credible first step in that direction. They already recover machine-usable structure such as theorem/proof units, source locations, references, and local dependencies. A plausible longer-term architecture is:

```text
LaTeX
  -> deterministic parsing and structural checks
  -> increasingly explicit mathematical representation
  -> bounded proof obligations
  -> optional formal checks (for example, Lean)
```

This is a direction, not a current capability. Thorn does not currently translate manuscripts to Lean, and a clean Thorn run is never a proof certificate. The goal is to make stronger forms of checking progressively available without making formalization a prerequisite for ordinary users.

The intended unit of review is often larger than a line: a proof may depend on hypotheses, definitions, notation, or earlier results elsewhere in the manuscript. Thorn therefore favors bounded whole-argument review over continuous local prompting, and favors reviewable diagnostics over open-ended generated prose.

The initial target is LaTeX mathematics. Thorn extracts theorem/proposition/lemma + proof units,
builds a small local dependency context, asks an adversarial model for specific falsifiable
objections, then gives a second model pass the job of defeating those objections before anything
is reported.

## Status

Very early prototype. The useful invariant for v0.1 is deliberately narrow:

```text
LaTeX -> theorem/proof units -> attack -> defend -> source-located diagnostics
```

No formal verification is claimed. A clean Thorn run means only that no issue survived the configured
audit.

## Install for development

The PyPI name `thorn` is already occupied, so the distribution is currently named `thorn-math` while
the command remains `thorn`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

With `uv`:

```bash
uv sync --extra dev
```

## First use

Inspect what Thorn sees without making any API calls:

```bash
thorn paper.tex --dry-run
```

Audit one result while developing prompts:

```bash
export OPENAI_API_KEY=...
thorn paper.tex --limit 1
```

Audit the document and emit JSON:

```bash
thorn paper.tex --format json > thorn.json
```

Useful options:

```text
--model MODEL          model used for attacker and defender
--limit N              audit only the first N extracted units
--no-defender          show attacker findings without the defender pass
--no-cache             ignore and do not write the local cache
--cache-dir PATH       default: .thorn/cache
--min-confidence FLOAT suppress lower-confidence surviving findings
--fail-on LEVEL        never | error | warning
```

By default Thorn returns a non-zero exit status only when a surviving `error` diagnostic is emitted.

## What the first parser handles

- common theorem-like environments (`theorem`, `lemma`, `proposition`, `corollary`, `claim`)
- theorem environments declared with `\\newtheorem` / `\\newtheorem*`
- an immediately following `proof` environment
- multi-file projects discovered through `\\input` and `\\include`
- source file + line ranges
- direct theorem dependencies referenced through `\\ref`, `\\eqref`, `\\autoref`, `\\cref`, or
  `\\Cref` when the referenced label belongs to another extracted theorem-like unit

This is intentionally a pragmatic LaTeX frontend, not a complete TeX interpreter.

## Diagnostic philosophy

A Thorn finding should be specific enough that an author can either fix it or refute it. Good findings
look like:

```text
TH301 error paper.tex:418-431 theorem 5.3
Possible hypothesis mismatch
The proof uses gradient smoothness, but the stated assumption gives only quadratic growth.
Defender: survives (0.94)
```

Vague referee-style comments such as "more justification is needed" are not useful lint diagnostics.

Thorn also distinguishes objective mathematical readability from subjective style. A simultaneous
notation collision or materially ambiguous asymptotic convention can be lintable; merely preferring a
different symbol or prose style is not. Style rules should come from an explicitly adopted external
style guide, not from model taste.

## Test-driven specification

The public synthetic corpus is a specification of Thorn's behavior, including clean controls that
constrain false positives. The rough L1--L10 difficulty ladder is complemented by an orthogonal fault
matrix covering theorem truth, proof validity, locality, fault class, repairability, detection method,
reader consequence, and downstream impact.

See [the test matrix](docs/test-matrix.md) and the [evaluation corpus](eval/README.md).

## Development

```bash
pytest
ruff check .
mypy src
```
