# Lean handoff

> **Implementation contract.** This document describes Thorn's currently implemented Lean backend and supported subset. For the broader product/design thesis — selective local formal replay as proof-quality evidence rather than arbitrary LaTeX-to-Lean translation — see [`lean-bridge.md`](lean-bridge.md). Issue #115 is evaluating that thesis on ordinary mathematical proofs before broader Lean capability work is justified.

Thorn's first Lean backend is a deliberately small proof-of-life over canonical Proof IR. It does not parse LaTeX, source prose, or `thorn-proof/1`. The public acceptance path is:

```text
ordinary LaTeX
  -> Thorn Math IR
  -> canonical typed Proof IR
  -> symbol/scope resolution
  -> higher proof structure
  -> semantic transformations and explicit obligations
  -> Lean export
  -> Lean 4
```

The backend currently supports only the mechanically recovered subset needed by the issue #77 theorem-application regression:

- natural-number terms that are literals or bound universal variables;
- unary proposition-valued predicate applications over those terms;
- universal quantification over a recovered natural-number domain;
- implication;
- explicit imported-result application and specialization;
- explicit recovered parameter instantiation;
- discharged result preconditions from the local Proof-IR context;
- an exact recovered final theorem conclusion.

Predicate binder types in the generated Lean signature are derived structurally from canonical proposition applications over canonical `Nat` terms. Conflicting or richer uses are unsupported rather than guessed.

## Completeness and holes

`LeanExport.status` is one of `complete`, `partial`, or `unsupported`. Only `complete` output with no recorded formalisation obligations has `is_mechanically_checkable == True`.

When a result application has already been mechanically matched but one of its explicit semantic application obligations is unresolved, the exporter does not manufacture the premise. It emits a source-addressed `THORN_FORMALIZATION_OBLIGATION` and a Lean `sorry` for exactly that missing proposition, then records the export as `partial`. A Lean file containing such a hole is never classified as complete merely because Lean permits `sorry`.

If the result application itself is ambiguous, unmatched, lacks a recovered instantiation, or uses mathematics outside this tranche, the backend refuses to turn it into a proof term and classifies the export as `unsupported`.

Source text is not an input to Lean rendering. Source addresses are carried only as provenance so a hole can be traced back through canonical Proof IR.

## Toolchain and acceptance

The acceptance toolchain is pinned by the repository's `lean-toolchain` file to Lean 4.30.0. The dedicated keyless `Lean contract` workflow installs that toolchain, keeps `OPENAI_API_KEY` blank, regenerates Lean through Thorn's real frontend/canonical pipeline, and invokes the actual `lean` executable on the complete positive case.

The paired negative fixture differs only in the available premise. Its missing precondition remains a formalisation obligation and its export status remains `partial`.

## Current boundary versus future product shape

The current exporter is intentionally a result-oriented proof of life. Its existence should not be read as a commitment to whole-theorem automatic translation as Thorn's long-term formalisation unit.

The hypothesis in [`lean-bridge.md`](lean-bridge.md) and issue #115 is that a more useful boundary may be a mechanically closed local proof operation inside an otherwise informal theorem. If the evaluation supports that hypothesis, future implementation should derive such checks from existing canonical proof/transformation semantics while preserving the same no-confidence-laundering and source-provenance rules documented here.

Unsupported neighbouring mathematics must not be silently reconstructed to make a local check possible, and a successful local replay must not be presented as proof of the surrounding theorem.

## CLI seam

This tranche intentionally exposes the lower-level `project_lean(...)` API rather than adding project generation or a broad CLI surface. A future `thorn lean <file>` command can wrap the settled formalisation/check boundary once target selection and output conventions are justified without changing canonical Proof IR or the confidence rules above.
