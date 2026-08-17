# Browsable review reports

Thorn can write one self-contained HTML artifact for local mathematical review. The report is a presentation of results Thorn has already produced; it is not another mathematical IR, and rendering it does not invoke a model.

For a keyless structural report:

```bash
thorn report paper.tex
thorn report paper.tex --open
```

The default output is `paper.thorn-report.html`. Structural analysis can write the same report while preserving its normal terminal/JSON output:

```bash
thorn analyze paper.tex --report
thorn analyze paper.tex --report review.html
```

The normal model-backed review command can also emit a report from the Proof-IR review it already performed:

```bash
thorn review paper.tex --report
thorn review paper.tex --report review.html --open
```

Report generation itself makes no additional provider request. A model-backed report records the existing `thorn-proof/1` / `thorn-proof-review/2` review boundary, exact bounded source-rescue provenance when rescue occurred, and the model-facing proof packet used for that result. The report schema also has stable presentation seams for canonical unresolved proof obligations and Lean export status.

The interactive proof argument visualiser is currently a separate self-contained artifact rather than duplicated inside the report:

```bash
thorn graph paper.tex --open
```

Both views project existing Thorn representations; neither creates tutorial- or presentation-specific mathematical semantics.

## What the report means

The overview deliberately separates three assurance regimes rather than producing a universal pass/fail score:

- **Structural** — deterministic mechanical diagnostics and, when supplied by upstream analysis, unresolved canonical obligations. These do not by themselves establish theorem invalidity.
- **Semantic review** — model-backed mathematical findings. These are review judgments, not formal verification. Source-rescue sections show the exact additional source supplied to the reviewer and label it as review context rather than mechanically verified evidence.
- **Formal / Lean** — formalisation state supplied by the existing Lean handoff. A complete export describes only the subset Thorn translated without formalisation holes; independent Lean checking is still a separate step, and partial exports remain visibly partial.

The primary reading path is manuscript -> result -> finding/obligation -> evidence/source. Protocol IDs, hashes, `thorn-proof/1` text, source-rescue mechanics, and formalisation details stay in expandable secondary sections.

A quiet report is deliberately not labelled as a proof of correctness. It means no attached structural/model/formal state currently demands attention.

## Source navigation

Every source-linked item shows a copyable `file:line` or `file:start-end` reference. When Thorn has a normal local filesystem path, the report also emits an editor-neutral `file://` link. Browsers may restrict local-file navigation, so the visible source reference is always retained as the reliable fallback. Source excerpts are bounded; the report does not embed the whole manuscript merely for navigation.

## Synthetic visual fixture

The public demo contains only provenance-free synthetic data and exercises clean, structural, semantic, source-rescued, Lean-complete, Lean-partial, unresolved-Proof-IR, long-content, and quiet states:

```bash
OPENAI_API_KEY="" python scripts/generate_report_demo.py --output /tmp/thorn-report-demo.html
```

This is suitable for visual inspection without a model key or private-paper material. For the actual first-run product path, use the ordinary manuscripts in [`../examples/quickstart/`](../examples/quickstart/) via [`quickstart.md`](quickstart.md).

## Schema and future cache provenance

`thorn.report.Report` is the immutable, serializable presentation model (`thorn-report/1`). Review metadata is provider-neutral. It has optional fields for cache status, recheck reason, and avoided requests so future dependency-aware reuse can be displayed without teaching the renderer cache internals. Those fields are omitted unless real upstream data supplies them.
