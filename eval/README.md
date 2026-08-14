# Thorn evaluation corpus

This directory contains small, self-contained regression cases for Thorn's semantic audit.

The public corpus uses **synthetic mathematical examples** that isolate representative logical failure modes. It intentionally does not identify papers or authors from which a failure mode may have been motivated. Each `.tex` file has a matching `.json` expectation.

Current defect cases:

- `threshold_squared` — a sign test on `a^2 - tau` is incorrectly treated as a threshold on `a - tau`.
- `quadratic_growth` — two-sided quadratic growth is incorrectly promoted to strong convexity and gradient smoothness.
- `convergence_mismatch` — continuity under decreasing convergence is invoked for a sequence known only to converge in `L^1`.

The corpus also includes clean controls. A useful linter must both detect known defects and stay quiet on nearby valid arguments.

Validate fixture parsing without API calls:

```bash
thorn-eval eval/cases --validate-only
```

Run the live semantic regression suite:

```bash
export OPENAI_API_KEY=...
thorn-eval eval/cases --model <model>
```

The command exits nonzero if a known defect is missed or if a clean control produces a surviving diagnostic above the configured confidence threshold.

## Budget safety

Default CI is deliberately offline. It runs unit tests, deterministic mocked provider/integration tests, fixture validation, linting, and type checking with `OPENAI_API_KEY` explicitly blank. Those checks must never make billable model calls.

The GitHub `Live evaluation` workflow is intentionally separate and has only a manual `workflow_dispatch` trigger. It is the only workflow that injects `OPENAI_API_KEY`. Live semantic regression should remain an explicit human action rather than a pull-request or push check.

This is a regression suite, not an accuracy benchmark. Cases are deliberately small and known in advance. A later benchmark should contain held-out and blinded cases.

Exact provenance for research-derived audit cases should be kept outside this public repository.
