# Issue #137 proof-review schema/transport repair

This directory records the deterministic repair boundary exposed by the stopped A3 turn in issue #134.

The owning defect is not mathematical: the provider-facing structured-output contract admitted an action/state combination that Thorn's local validator rejected only after the provider response had completed, and the auto-parse path lost usage/response evidence on that failure.

The repair is keyless. It makes the provider-visible initial response schema action-safe, accounts for a completed provider response before Thorn-local validation, preserves a rejected response payload and usage when local validation fails, and retains the existing fail-closed protocol/replay behavior. No A1/A2 resampling and no #125 implementation belong to this tranche.

The focused implementation gate ran the exact A3 failure regression together with proof-review, rejected-replay, #128 bounded-rescue, and #132 finding-accounting coverage: 34 targeted tests passed, followed by Ruff and mypy. A second keyless gate then ran the full pytest suite, full Ruff check, and mypy successfully after adapting the historical #101 tooling to recognize assurance-tree drift before fingerprint drift. No provider credential was present and no paid request was made.
