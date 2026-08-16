# Browsable review reports

Thorn can write one self-contained HTML artifact for local mathematical review. The report is a
presentation of results Thorn has already produced; it is not another mathematical IR and rendering
it does not invoke a model.

For a keyless structural report:

```bash
thorn report paper.tex
```

The default output is `paper.thorn-report.html`. Open it explicitly with the normal operating-system
browser mechanism when desired:

```bash
thorn report paper.tex --open
```

Structural analysis can write the same report while preserving its normal terminal/JSON output:

```bash
thorn analyze paper.tex --report
thorn analyze paper.tex --report review.html
```

The current model-backed review command can also emit a report from the audits it already performed:

```bash
thorn review paper.tex --report
thorn review paper.tex --report review.html --open
```

Report generation itself makes no additional provider request. The report schema also accepts the
`thorn-proof/1` / `thorn-proof-review/1` result boundary, exact `NEED_SOURCE` rescue provenance,
record/replay metadata, canonical unresolved proof obligations, and existing Lean export status. This
keeps report presentation independent of issue #83's pending production-path disposition: raw/replay
and Proof-IR-backed reviews are both representable without changing their semantics.

## What the report means

The overview deliberately separates three assurance regimes rather than producing a universal
pass/fail score:

- **Structural** — deterministic mechanical diagnostics and unresolved canonical obligations. These
  do not by themselves establish theorem invalidity.
- **Semantic review** — model-backed mathematical findings. These are review judgments, not formal
  verification. `NEED_SOURCE` sections show the exact additional source supplied to the reviewer and
  label it as review context rather than mechanically verified evidence.
- **Formal / Lean** — the status reported by the existing Lean handoff. Only a complete,
  obligation-free export is described as mechanically checked. Partial exports and their source-linked
  formalisation obligations remain visibly partial; a file containing `sorry` is never presented as
  verified.

The primary reading path is manuscript -> result -> finding/obligation -> evidence/source. Protocol
IDs, hashes, `thorn-proof/1` text, replay details, source-rescue mechanics, and formalisation details
stay in expandable secondary sections.

## Source navigation

Every source-linked item shows a copyable `file:line` or `file:start-end` reference. When Thorn has a
normal local filesystem path, the report also emits an editor-neutral `file://` link. Browsers may
restrict local-file navigation, so the visible source reference is always retained as the reliable
fallback. Source excerpts are bounded; the report does not embed the whole manuscript merely for
navigation.

## Synthetic visual fixture

The public demo contains only provenance-free synthetic data and exercises clean, structural,
semantic, source-rescued, Lean-complete, Lean-partial, unresolved-Proof-IR, long-content, and quiet
states:

```bash
OPENAI_API_KEY="" python scripts/generate_report_demo.py --output /tmp/thorn-report-demo.html
```

This is suitable for visual inspection without a model key or private-paper material.

## Schema and future cache provenance

`thorn.report.Report` is the immutable, serializable presentation model (`thorn-report/1`). Review
metadata is provider-neutral. It has optional fields for cache status, recheck reason, and avoided
requests so issue #10 can later expose dependency-aware reuse without teaching the renderer cache
internals. Those fields are omitted unless real upstream data supplies them.
