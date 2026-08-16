from __future__ import annotations

from html import escape
from pathlib import Path

from thorn.report import (
    FormalStatus,
    Report,
    ReportFinding,
    ReportObligation,
    ReportResult,
    ReportSource,
    ReviewMetadata,
    stable_anchor,
)

_CSS = r"""
:root {
  color-scheme: light;
  --paper: #fbfaf7;
  --surface: #ffffff;
  --ink: #202522;
  --muted: #626a65;
  --line: #d9ddd9;
  --line-strong: #b8c0ba;
  --structural: #375a67;
  --semantic: #745b2b;
  --formal: #315b43;
  --warning: #7a5419;
  --error: #873c35;
  --quiet: #eef1ee;
  --focus: #1e596b;
  font-family: Georgia, Cambria, "Times New Roman", serif;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-size: 16px;
  line-height: 1.55;
}
a { color: #245568; text-decoration-thickness: .08em; text-underline-offset: .15em; }
a:hover { color: #163c4b; }
button, summary { font: inherit; }
button:focus-visible, a:focus-visible, summary:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--focus) 30%, transparent);
  outline-offset: 2px;
}
.shell {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  max-width: 1480px;
  margin: 0 auto;
  min-height: 100vh;
}
.sidebar {
  position: sticky;
  top: 0;
  align-self: start;
  height: 100vh;
  overflow: auto;
  padding: 28px 22px 36px;
  border-right: 1px solid var(--line);
  background: #f5f4f0;
}
.brand {
  margin: 0 0 4px;
  font: 700 19px/1.2 system-ui, -apple-system, sans-serif;
  letter-spacing: .02em;
}
.manuscript-name {
  margin: 0 0 20px;
  color: var(--muted);
  font: 13px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}
.filter-row { display: flex; gap: 6px; margin: 0 0 16px; }
.filter-row button, .copy-button {
  appearance: none;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink);
  padding: 5px 9px;
  border-radius: 4px;
  cursor: pointer;
  font: 600 12px/1.2 system-ui, -apple-system, sans-serif;
}
.filter-row button[aria-pressed="true"] { border-color: #6d7770; background: #e7ebe7; }
.result-nav { list-style: none; margin: 0; padding: 0; }
.result-nav li { margin: 2px 0; }
.result-nav a {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr);
  gap: 8px;
  padding: 7px 6px;
  border-radius: 4px;
  color: var(--ink);
  text-decoration: none;
  font: 13px/1.25 system-ui, -apple-system, sans-serif;
}
.result-nav a:hover { background: #e9ebe7; }
.nav-dot { width: 7px; height: 7px; border-radius: 50%; background: #9ba39d; margin-top: 4px; }
.nav-dot.attention { background: var(--warning); }
.nav-label { overflow-wrap: anywhere; }
.nav-kind { display: block; color: var(--muted); font-size: 11px; margin-top: 2px; }
.main { min-width: 0; padding: 34px clamp(24px, 5vw, 72px) 80px; }
.overview { max-width: 960px; margin: 0 auto 42px; }
.eyebrow {
  color: var(--muted);
  font: 650 11px/1.2 system-ui, -apple-system, sans-serif;
  letter-spacing: .11em;
  text-transform: uppercase;
}
h1 { margin: 7px 0 8px; font-size: clamp(30px, 4vw, 46px); line-height: 1.08; font-weight: 600; }
.lede { margin: 0; max-width: 720px; color: #414944; font-size: 18px; }
.assurance-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0;
  margin-top: 28px;
  border-top: 1px solid var(--line-strong);
  border-bottom: 1px solid var(--line-strong);
}
.assurance-summary { padding: 16px 18px 17px 0; min-width: 0; }
.assurance-summary + .assurance-summary { padding-left: 18px; border-left: 1px solid var(--line); }
.assurance-title { font: 700 13px/1.2 system-ui, -apple-system, sans-serif; }
.assurance-value { margin-top: 4px; font-size: 17px; }
.assurance-note { margin-top: 3px; color: var(--muted); font-size: 13px; }
.attention-line {
  margin: 18px 0 0;
  padding: 11px 13px;
  border-left: 3px solid var(--warning);
  background: #f5efe5;
  font: 14px/1.45 system-ui, -apple-system, sans-serif;
}
.attention-line.clean { border-left-color: var(--formal); background: #edf3ee; }
.results { max-width: 960px; margin: 0 auto; }
.result {
  scroll-margin-top: 18px;
  padding: 30px 0 36px;
  border-top: 1px solid var(--line-strong);
}
.result:first-child { border-top: 0; }
.result-heading {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 20px;
}
.result h2 { margin: 4px 0 2px; font-size: 26px; line-height: 1.2; font-weight: 600; }
.result-id {
  color: var(--muted);
  font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}
.status-chip {
  flex: none;
  border: 1px solid var(--line-strong);
  padding: 4px 7px;
  border-radius: 999px;
  color: #46504a;
  background: var(--quiet);
  font: 650 11px/1.1 system-ui, -apple-system, sans-serif;
  white-space: nowrap;
}
.status-chip.attention { border-color: #c9ad7d; background: #f6efe2; color: #684716; }
.statement {
  margin: 17px 0 12px;
  padding: 14px 16px;
  border-left: 3px solid #aeb7b1;
  background: #f5f5f1;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 16px;
}
.source-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
  margin: 9px 0 17px;
  color: var(--muted);
  font: 12px/1.35 system-ui, -apple-system, sans-serif;
}
.source-ref {
  color: #343b37;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  overflow-wrap: anywhere;
}
.findings { display: grid; gap: 12px; margin: 20px 0 0; }
.finding {
  scroll-margin-top: 18px;
  border-top: 1px solid var(--line);
  padding: 15px 0 2px;
}
.finding-head { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
.regime {
  padding: 2px 5px;
  border: 1px solid currentColor;
  border-radius: 3px;
  font: 700 10px/1.2 system-ui, -apple-system, sans-serif;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.regime.structural { color: var(--structural); }
.regime.semantic { color: var(--semantic); }
.regime.formal { color: var(--formal); }
.severity { font: 650 11px/1.2 system-ui, -apple-system, sans-serif; }
.severity.error { color: var(--error); }
.severity.warning { color: var(--warning); }
.finding h3 { margin: 7px 0 5px; font-size: 18px; line-height: 1.3; }
.finding p { margin: 0 0 8px; max-width: 780px; }
.evidence { margin: 10px 0 0; padding-left: 20px; color: #414944; }
.evidence li { margin: 3px 0; }
details {
  margin-top: 12px;
  border-top: 1px solid #e3e5e2;
  padding-top: 9px;
}
summary {
  width: fit-content;
  cursor: pointer;
  color: #47514b;
  font: 650 12px/1.35 system-ui, -apple-system, sans-serif;
}
.detail-body { margin: 10px 0 0; color: #414944; font-size: 14px; }
.meta-grid {
  display: grid; grid-template-columns: max-content minmax(0, 1fr);
  gap: 4px 12px; margin: 8px 0;
}
.meta-grid dt {
  color: var(--muted);
  font: 600 11px/1.4 system-ui, -apple-system, sans-serif;
  text-transform: uppercase; letter-spacing: .04em;
}
.meta-grid dd { margin: 0; overflow-wrap: anywhere; }
code, pre, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
pre.source {
  max-width: 100%;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  margin: 9px 0 0;
  padding: 11px 12px;
  border: 1px solid var(--line);
  background: #f6f6f3;
  font-size: 12px;
  line-height: 1.45;
}
.obligation-list { display: grid; gap: 9px; margin: 17px 0 0; }
.obligation {
  padding: 10px 12px;
  border-left: 3px solid var(--line-strong);
  background: #f6f6f3;
  font-size: 14px;
}
.obligation.formal { border-left-color: var(--formal); }
.obligation.structural { border-left-color: var(--structural); }
.formal-line { margin: 17px 0 0; font: 14px/1.45 system-ui, -apple-system, sans-serif; }
.formal-complete { color: var(--formal); font-weight: 700; }
.formal-partial { color: var(--warning); font-weight: 700; }
.quiet { color: var(--muted); }
.rescue { border-left: 3px solid #c7b17e; padding-left: 12px; margin-top: 12px; }
.footer {
  max-width: 960px; margin: 34px auto 0; padding-top: 15px;
  border-top: 1px solid var(--line); color: var(--muted);
  font: 11px/1.5 system-ui, -apple-system, sans-serif;
}
.js .result[data-attention="false"].filtered-out { display: none; }
@media (max-width: 820px) {
  .shell { display: block; }
  .sidebar {
    position: relative; height: auto; max-height: none; border-right: 0;
    border-bottom: 1px solid var(--line); padding: 18px 18px 16px;
  }
  .result-nav { display: flex; gap: 4px; overflow-x: auto; padding-bottom: 3px; }
  .result-nav li { flex: 0 0 auto; }
  .result-nav a { min-width: 150px; border: 1px solid var(--line); background: #fafaf7; }
  .main { padding: 26px 18px 60px; }
  .assurance-grid { grid-template-columns: 1fr; }
  .assurance-summary { padding: 12px 0; }
  .assurance-summary + .assurance-summary {
    padding-left: 0; border-left: 0; border-top: 1px solid var(--line);
  }
  .result-heading { display: block; }
  .status-chip { display: inline-block; margin-top: 9px; }
  .meta-grid { grid-template-columns: 1fr; gap: 1px; }
  .meta-grid dd { margin-bottom: 6px; }
}
@media print {
  body { background: white; }
  .shell { display: block; max-width: none; }
  .sidebar, .filter-row, .copy-button { display: none !important; }
  .main { padding: 0; }
  .result { break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
  details > * { display: block; }
}
"""

_JS = r"""
document.documentElement.classList.add('js');
(function () {
  const allButton = document.querySelector('[data-filter="all"]');
  const attentionButton = document.querySelector('[data-filter="attention"]');
  const results = Array.from(document.querySelectorAll('.result'));
  function apply(mode) {
    results.forEach((result) => result.classList.toggle(
      'filtered-out', mode === 'attention' && result.dataset.attention === 'false'));
    allButton.setAttribute('aria-pressed', mode === 'all' ? 'true' : 'false');
    attentionButton.setAttribute('aria-pressed', mode === 'attention' ? 'true' : 'false');
  }
  allButton && allButton.addEventListener('click', () => apply('all'));
  attentionButton && attentionButton.addEventListener('click', () => apply('attention'));
  document.querySelectorAll('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy || '');
        const old = button.textContent;
        button.textContent = 'Copied';
        window.setTimeout(() => { button.textContent = old; }, 900);
      } catch (_) {
        button.title = 'Copy unavailable; select the source reference beside this button.';
      }
    });
  });
})();
"""


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _safe_file_uri(uri: str | None) -> str | None:
    if uri is None or not uri.startswith("file://"):
        return None
    return uri


def _source(source: ReportSource, *, show_excerpt: bool = True) -> str:
    parts = [f'<span class="source-ref">{_e(source.reference)}</span>']
    uri = _safe_file_uri(source.uri)
    if uri:
        parts.append(f'<a href="{_e(uri)}">Open file</a>')
    parts.append(
        f'<button class="copy-button" type="button" '
        f'data-copy="{_e(source.reference)}">Copy location</button>'
    )
    row = '<div class="source-row">' + ''.join(parts) + '</div>'
    if show_excerpt and source.excerpt:
        row += f'<pre class="source">{_e(source.excerpt)}</pre>'
    return row


def _review_details(review: ReviewMetadata | None) -> str:
    if review is None:
        return ''
    rows: list[tuple[str, str]] = []
    if review.representation:
        rows.append(('Representation', review.representation))
    if review.protocol:
        rows.append(('Protocol', review.protocol))
    if review.model:
        rows.append(('Model', review.model))
    rows.append(('Execution', review.execution.value))
    if review.request_fingerprint:
        rows.append(('Request fingerprint', review.request_fingerprint))
    if review.cache_status:
        rows.append(('Cache', review.cache_status))
    if review.recheck_reason:
        rows.append(('Recheck reason', review.recheck_reason))
    if review.avoided_requests is not None:
        rows.append(('Avoided requests', str(review.avoided_requests)))
    body = '<dl class="meta-grid">' + ''.join(
        f'<dt>{_e(label)}</dt><dd class="mono">{_e(value)}</dd>' for label, value in rows
    ) + '</dl>'
    if review.source_rescue:
        rescue = []
        for item in review.source_rescue:
            location = _source(item.source, show_excerpt=False) if item.source is not None else ''
            related = (
                (
                    '<p class="quiet">Referenced result: <code>'
                    f'{_e(item.referenced_result_identifier)}</code></p>'
                )
                if item.referenced_result_identifier else ''
            )
            rescue.append(
                '<div class="rescue">'
                f'<strong>Requested <code>@{_e(item.address)}</code></strong>'
                f'{location}{related}'
                '<p class="quiet">Additional source supplied to the model for review; '
                'this is not mechanically verified evidence.</p>'
                f'<pre class="source">{_e(item.text)}</pre>'
                '</div>'
            )
        body += '<h4>Source rescue (NEED_SOURCE)</h4>' + ''.join(rescue)
    return body


def _finding(finding: ReportFinding) -> str:
    anchor = stable_anchor('finding', finding.identifier)
    evidence = ''
    if finding.evidence:
        evidence = (
            '<ul class="evidence">'
            + ''.join(f'<li>{_e(item)}</li>' for item in finding.evidence)
            + '</ul>'
        )
    technical = _review_details(finding.review)
    related: list[str] = []
    if finding.related_result_identifiers:
        values = ', '.join(_e(item) for item in finding.related_result_identifiers)
        related.append(f'<p><strong>Related results:</strong> <code>{values}</code></p>')
    if finding.related_obligation_identifiers:
        values = ', '.join(_e(item) for item in finding.related_obligation_identifiers)
        related.append(f'<p><strong>Related obligations:</strong> <code>{values}</code></p>')
    technical += ''.join(related)
    confidence = (
        f'<span class="quiet">confidence {finding.confidence:.2f}</span>'
        if finding.confidence is not None
        else ''
    )
    details = (
        '<details><summary>Review and evidence details</summary><div class="detail-body">'
        f'{technical}{evidence}{_source(finding.source)}</div></details>'
    )
    return (
        f'<article class="finding" id="{_e(anchor)}">'
        '<div class="finding-head">'
        f'<span class="regime {finding.assurance.value}">{_e(finding.assurance.value)}</span>'
        f'<span class="severity {finding.severity.value}">{_e(finding.severity.value)}</span>'
        f'<span class="quiet">{_e(finding.category.replace("_", " "))}</span>'
        f'<span class="quiet">{_e(finding.status.replace("_", " "))}</span>'
        f'{confidence}'
        '</div>'
        f'<h3>{_e(finding.title)}</h3>'
        f'<p>{_e(finding.explanation)}</p>'
        f'{details}'
        '</article>'
    )


def _obligation(item: ReportObligation) -> str:
    expected = f'<div>Expected: <code>{_e(item.expected)}</code></div>' if item.expected else ''
    location = _source(item.source) if item.source is not None else ''
    handles = (
        '<div class="quiet">Source handles: '
        + ', '.join(f'<code>@{_e(address)}</code>' for address in item.source_addresses)
        + '</div>'
        if item.source_addresses else ''
    )
    return (
        f'<div class="obligation {item.assurance.value}">'
        f'<strong>{_e(item.identifier)}</strong> · '
        f'{_e(item.kind.replace("_", " "))} · {_e(item.status)}'
        f'<div>{_e(item.explanation)}</div>{expected}{handles}{location}'
        '</div>'
    )


def _formal_status(result: ReportResult) -> str:
    formal = result.formalization
    if formal.status == FormalStatus.COMPLETE and formal.mechanically_checkable:
        return '<span class="formal-complete">Mechanically checked Lean subset</span>'
    if formal.status == FormalStatus.PARTIAL:
        return '<span class="formal-partial">Partial formalisation — open obligations remain</span>'
    if formal.status == FormalStatus.UNSUPPORTED:
        return '<span class="quiet">Lean export unsupported for this result</span>'
    return '<span class="quiet">Lean formalisation not attempted</span>'


def _result(result: ReportResult) -> str:
    anchor = stable_anchor('result', result.identifier)
    name = result.name or result.identifier
    chip = 'Needs attention' if result.needs_attention else 'No current findings'
    chip_class = ' attention' if result.needs_attention else ''
    findings = ''.join(_finding(item) for item in result.findings)
    if not findings:
        findings = (
            '<p class="quiet">No structural or semantic findings are currently attached '
            'to this result.</p>'
        )
    obligations = ''.join(_obligation(item) for item in result.proof_obligations)
    formal_obligations = ''.join(_obligation(item) for item in result.formalization.obligations)
    dependencies = (
        '<p>Dependencies: '
        + ', '.join(f'<code>{_e(item)}</code>' for item in result.dependencies)
        + '</p>'
        if result.dependencies
        else '<p class="quiet">No direct theorem/result dependencies recorded.</p>'
    )
    display_context = (
        '<h4>Nearby source context</h4>'
        f'<pre class="source">{_e(result.display_context)}</pre>'
        if result.display_context
        else ''
    )
    proof_language = (
        '<details><summary>Proof structure / thorn-proof/1</summary>'
        '<div class="detail-body"><pre class="source">'
        f'{_e(result.proof_language)}</pre></div></details>'
        if result.proof_language else ''
    )
    review = (
        '<details><summary>Review context and provenance</summary>'
        f'<div class="detail-body">{_review_details(result.review)}</div></details>'
        if result.review else ''
    )
    formal_details = (
        '<details><summary>Formalisation details</summary>'
        '<div class="detail-body"><div class="obligation-list">'
        f'{formal_obligations}</div></div></details>'
        if formal_obligations else ''
    )
    obligation_section = (
        '<div class="obligation-list"><div class="eyebrow">'
        'Open structural obligations</div>'
        + obligations
        + '</div>'
        if obligations else ''
    )
    return (
        f'<section class="result" id="{_e(anchor)}" '
        f'data-attention="{str(result.needs_attention).lower()}">'
        '<div class="result-heading"><div>'
        f'<div class="eyebrow">{_e(result.kind)}</div><h2>{_e(name)}</h2>'
        f'<div class="result-id">{_e(result.identifier)}</div>'
        f'</div><span class="status-chip{chip_class}">{_e(chip)}</span></div>'
        f'<div class="statement">{_e(result.statement)}</div>'
        f'{_source(result.source, show_excerpt=False)}'
        f'<div class="formal-line">{_formal_status(result)}</div>'
        f'{obligation_section}'
        f'<div class="findings">{findings}</div>'
        '<details><summary>Dependencies and source context</summary>'
        f'<div class="detail-body">{dependencies}{display_context}'
        f'{_source(result.source)}</div></details>'
        f'{review}{proof_language}{formal_details}'
        '</section>'
    )


def render_report_html(report: Report) -> str:
    structural = report.counts.structural_findings
    semantic = report.counts.semantic_findings
    formal_note = (
        f'{report.counts.lean_complete} mechanically complete; {report.counts.lean_partial} partial'
        if report.counts.lean_complete or report.counts.lean_partial
        else 'No Lean-complete subset recorded'
    )
    attention = (
        '<div class="attention-line"><strong>'
        f'{report.counts.attention} result(s) need attention.</strong> '
        'Start with the marked results in the navigation.</div>'
        if report.counts.attention
        else (
            '<div class="attention-line clean"><strong>No current result is marked for '
            'attention.</strong> This is not a proof of correctness; it means no attached '
            'structural/model/formal state currently demands action.</div>'
        )
    )
    nav = ''.join(
        '<li>'
        f'<a href="#{_e(stable_anchor("result", item.identifier))}">'
        f'<span class="nav-dot{" attention" if item.needs_attention else ""}"></span>'
        f'<span class="nav-label">{_e(item.name or item.identifier)}'
        f'<span class="nav-kind">{_e(item.kind)}</span></span>'
        '</a></li>'
        for item in report.results
    )
    manuscript_findings = ''.join(_finding(item) for item in report.manuscript_findings)
    manuscript_block = (
        '<section class="result"><div class="eyebrow">Manuscript-level structural diagnostics</div>'
        f'<div class="findings">{manuscript_findings}</div></section>'
        if manuscript_findings else ''
    )
    generated = report.generation.generated_at.isoformat()
    version = (
        f' · Thorn {_e(report.generation.thorn_version)}'
        if report.generation.thorn_version
        else ''
    )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>Thorn review — {_e(Path(report.manuscript).name)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="shell">
  <nav class="sidebar" aria-label="Result navigation">
    <div class="brand">Thorn review</div>
    <div class="manuscript-name">{_e(report.manuscript)}</div>
    <div class="filter-row" aria-label="Filter results">
      <button type="button" data-filter="all" aria-pressed="true">All</button>
      <button type="button" data-filter="attention" aria-pressed="false">Needs attention</button>
    </div>
    <ol class="result-nav">{nav}</ol>
  </nav>
  <main class="main">
    <header class="overview">
      <div class="eyebrow">Mathematical review report</div>
      <h1>{_e(Path(report.manuscript).name)}</h1>
      <p class="lede">A source-linked view of Thorn's structural analysis, model-backed
      semantic review, and formalisation state. These assurance regimes are deliberately kept
      separate.</p>
      <div class="assurance-grid">
        <div class="assurance-summary">
          <div class="assurance-title">Structural</div>
          <div class="assurance-value">{structural} diagnostic(s)</div>
          <div class="assurance-note">Deterministic mechanical analysis; unresolved structure
          does not imply theorem invalidity.</div>
        </div>
        <div class="assurance-summary">
          <div class="assurance-title">Semantic review</div>
          <div class="assurance-value">{semantic} finding(s)</div>
          <div class="assurance-note">Model-backed mathematical judgement where supplied; not
          formal verification.</div>
        </div>
        <div class="assurance-summary">
          <div class="assurance-title">Formal / Lean</div>
          <div class="assurance-value">{_e(formal_note)}</div>
          <div class="assurance-note">Only complete, obligation-free Lean exports are described
          as mechanically checked.</div>
        </div>
      </div>
      {attention}
      <p class="quiet">{report.counts.results} theorem-like result(s) analysed ·
      {report.counts.clean_results} quiet/clean result(s) · {report.counts.open_obligations}
      open structural/formal obligation(s)</p>
    </header>
    <div class="results">{manuscript_block}{''.join(_result(item) for item in report.results)}</div>
    <footer class="footer">Schema {_e(report.schema_version)} · generated {_e(generated)}{version}.
    This self-contained report contains no external runtime assets.</footer>
  </main>
</div>
<script>{_JS}</script>
</body>
</html>
'''


def write_report_html(report: Report, destination: Path) -> Path:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_report_html(report), encoding="utf-8")
    return destination
