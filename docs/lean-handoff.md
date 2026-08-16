# Lean handoff

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

## CLI seam

This tranche intentionally exposes the lower-level `project_lean(...)` API rather than adding project generation or a broad CLI surface. A future `thorn lean <file>` command can wrap this backend once target selection and output conventions are settled without changing the canonical Proof IR or the confidence rules above.
