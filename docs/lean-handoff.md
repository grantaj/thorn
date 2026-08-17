# Lean handoff

> **Implementation contract.** This document describes Thorn's currently implemented Lean backend and supported subset. For the broader product/design thesis — selective local formal replay as proof-quality evidence rather than arbitrary LaTeX-to-Lean translation — see [`lean-bridge.md`](lean-bridge.md). Issue #115 is evaluating that thesis on ordinary mathematical proofs before broader Lean capability work is justified.

Thorn's Lean backend is a deliberately small proof-of-life over canonical Proof IR. It does not parse LaTeX, source prose, or `thorn-proof/1` itself. The public path is:

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

The backend currently supports only a mechanically recovered subset:

- natural-number terms that are literals or bound universal variables;
- unary proposition-valued predicate applications over those terms;
- universal quantification over a recovered natural-number domain;
- implication;
- explicit imported-result application and specialization;
- explicit recovered parameter instantiation;
- discharged result preconditions from the local Proof-IR context;
- an exact recovered final theorem conclusion.

Predicate binder types in the generated Lean signature are derived structurally from canonical proposition applications over canonical `Nat` terms. Conflicting or richer uses are unsupported rather than guessed.

## CLI

`thorn lean` is a thin user-facing wrapper over that existing exporter:

```bash
thorn lean paper.tex --result thm:main
thorn lean paper.tex --result thm:main --output generated.lean
thorn lean paper.tex --result thm:main --format json
```

If a manuscript has exactly one theorem-like result, `--result` may be omitted. With multiple results Thorn requires an explicit identifier rather than guessing which theorem the user intended to formalise. The default output is `<paper>.thorn.lean` beside the input manuscript.

The command is keyless and does not invoke the Lean executable. It writes the projection and reports its Thorn export status. Run `lean generated.lean` separately when the export is complete; this keeps Thorn's translation status distinct from the independent kernel check.

The quickstart example shows the complete user path in [`quickstart.md`](quickstart.md).

## Completeness and holes

`LeanExport.status` is one of `complete`, `partial`, or `unsupported`. Only `complete` output with no recorded formalisation obligations has `is_mechanically_checkable == True`.

`is_mechanically_checkable` means the generated artifact has no Thorn formalisation holes and is suitable to hand to Lean. It does **not** mean Thorn already invoked Lean or that the whole informal manuscript was formalised.

When a result application has already been mechanically matched but one of its explicit semantic application obligations is unresolved, the exporter does not manufacture the premise. It emits a source-addressed `THORN_FORMALIZATION_OBLIGATION` and a Lean `sorry` for exactly that missing proposition, then records the export as `partial`. A Lean file containing such a hole is never classified as complete merely because Lean permits `sorry`.

If the result application itself is ambiguous, unmatched, lacks a recovered instantiation, or uses mathematics outside this tranche, the backend refuses to turn it into a proof term and classifies the export as `unsupported`.

Source text is not an input to Lean rendering. Source addresses are carried only as provenance so a hole can be traced back through canonical Proof IR.

## Toolchain and acceptance

The acceptance toolchain is pinned by the repository's `lean-toolchain` file to Lean 4.30.0. The dedicated keyless `Lean contract` workflow installs that toolchain, keeps `OPENAI_API_KEY` blank, regenerates Lean through Thorn's real frontend/canonical pipeline, and invokes the actual `lean` executable on complete positive cases, including the onboarding example.

The original paired negative fixture differs only in the available premise. Its missing precondition remains a formalisation obligation and its export status remains `partial`.

## Current boundary versus future product shape

The current exporter and `thorn lean` command are intentionally result-oriented proofs of life. Their existence should not be read as a commitment to whole-theorem automatic translation as Thorn's long-term formalisation unit.

The hypothesis in [`lean-bridge.md`](lean-bridge.md) and issue #115 is that a more useful boundary may be a mechanically closed local proof operation inside an otherwise informal theorem. If the evaluation supports that hypothesis, future implementation should derive such checks from existing canonical proof/transformation semantics while preserving the same no-confidence-laundering and source-provenance rules documented here.

Unsupported neighbouring mathematics must not be silently reconstructed to make a local check possible, and a successful local replay must not be presented as proof of the surrounding theorem. The current CLI exposes only the bounded capability Thorn actually implements today; broader local replay remains an evidence-driven product direction rather than an implied certification claim.
