# Thorn

**Thorn is an AI-assisted correctness linter for mathematical manuscripts.**

Thorn does not certify proofs. It tries to break them before your readers do.

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
