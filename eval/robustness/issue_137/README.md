# Issue #137 proof-review schema/transport repair

This directory records the deterministic repair boundary exposed by the stopped A3 turn in issue #134.

The owning defect is not mathematical: the provider-facing structured-output contract admitted an action/state combination that Thorn's local validator rejected only after the provider response had completed, and the auto-parse path lost usage/response evidence on that failure.

The repair is keyless. It must make the provider-visible initial response schema action-safe, account for a completed provider response before Thorn-local validation, preserve a rejected response payload and usage when local validation fails, and retain the existing fail-closed protocol/replay behavior. No A1/A2 resampling and no #125 implementation belong to this tranche.
