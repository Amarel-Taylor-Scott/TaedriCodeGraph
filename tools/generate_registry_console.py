#!/usr/bin/env python3
"""Generate the self-contained registry console and GitHub-renderable SVG views."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "eval" / "results" / "primitive-factory-2026-07-16" / "registry-console-data.json"
APP_PATH = ROOT / "apps" / "explorer" / "registry-console.html"
INLINE_PATH = Path("/workspace/taedri-registry-console.html")
ASSET_ROOT = ROOT / "docs" / "visuals" / "assets"


FULL_TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Taedri Registry Console</title>
  <style>
    :root { color-scheme: light dark; --bg:#f5f6f8; --panel:#fff; --text:#18212f; --muted:#637083; --line:#d8dde6; --accent:#6656d9; --accent-soft:#eeebff; --good:#147a55; --warn:#9a5b00; --danger:#a23b3b; --shadow:0 12px 30px rgba(20,30,50,.08); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    @media (prefers-color-scheme: dark) { :root { --bg:#11141a; --panel:#1a1f28; --text:#edf1f7; --muted:#a7b0bf; --line:#333b49; --accent:#a99cff; --accent-soft:#282442; --good:#61d0a1; --warn:#f1bd66; --danger:#f08b8b; --shadow:none; } }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text); }
    button,input,select { font:inherit; }
    button:focus-visible,input:focus-visible,select:focus-visible { outline:3px solid color-mix(in srgb,var(--accent) 55%,transparent); outline-offset:2px; }
    header { padding:28px clamp(18px,4vw,54px) 18px; display:flex; gap:20px; justify-content:space-between; align-items:flex-start; }
    h1,h2,h3,p { margin-top:0; }
    h1 { margin-bottom:7px; font-size:clamp(1.55rem,3vw,2.35rem); font-weight:650; letter-spacing:-.035em; }
    h2 { font-size:1.05rem; margin-bottom:14px; }
    h3 { font-size:.96rem; margin-bottom:8px; }
    .subtitle,.muted { color:var(--muted); }
    .subtitle { margin:0; max-width:760px; }
    .status { border:1px solid var(--line); background:var(--panel); padding:8px 12px; border-radius:999px; white-space:nowrap; color:var(--warn); }
    nav { display:flex; gap:7px; padding:0 clamp(18px,4vw,54px) 18px; flex-wrap:wrap; }
    nav button { border:1px solid var(--line); color:var(--text); background:transparent; border-radius:10px; padding:9px 14px; cursor:pointer; }
    nav button[aria-selected="true"] { background:var(--accent); color:#fff; border-color:var(--accent); }
    main { padding:0 clamp(18px,4vw,54px) 54px; }
    .panel[hidden] { display:none; }
    .metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:16px; }
    .metric,.surface { background:var(--panel); border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow); }
    .metric { padding:16px; }
    .metric strong { display:block; font-size:1.55rem; margin-top:5px; }
    .surface { padding:18px; margin-bottom:16px; }
    .filters { display:grid; grid-template-columns:minmax(240px,2fr) minmax(150px,1fr) minmax(180px,1fr); gap:10px; }
    label { display:grid; gap:6px; color:var(--muted); font-size:.86rem; }
    input,select { width:100%; border:1px solid var(--line); border-radius:10px; color:var(--text); background:var(--bg); padding:10px 11px; }
    .registry-grid { display:grid; grid-template-columns:minmax(280px,.9fr) minmax(360px,1.1fr); gap:16px; align-items:start; }
    .candidate-list { display:grid; gap:7px; }
    .candidate { text-align:left; border:1px solid var(--line); background:transparent; color:var(--text); border-radius:11px; padding:11px 12px; cursor:pointer; }
    .candidate:hover { background:var(--accent-soft); }
    .candidate[aria-pressed="true"] { border-color:var(--accent); background:var(--accent-soft); }
    .candidate strong,.candidate span { display:block; overflow-wrap:anywhere; }
    .candidate span { color:var(--muted); margin-top:3px; font-size:.82rem; }
    .detail { position:sticky; top:14px; }
    .badges { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 16px; }
    .badge { border-radius:999px; background:var(--accent-soft); padding:5px 8px; font-size:.78rem; }
    dl { display:grid; grid-template-columns:max-content 1fr; gap:8px 13px; margin:0; }
    dt { color:var(--muted); }
    dd { margin:0; overflow-wrap:anywhere; }
    code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.82em; }
    .bars { display:grid; gap:11px; }
    .bar-row { display:grid; grid-template-columns:150px 1fr 44px; gap:10px; align-items:center; }
    .track { height:12px; border-radius:999px; background:var(--bg); overflow:hidden; }
    .fill { height:100%; background:var(--accent); border-radius:inherit; }
    .timeline { display:grid; gap:0; }
    .event { display:grid; grid-template-columns:20px minmax(140px,.5fr) minmax(220px,1.5fr); gap:11px; padding:11px 0; border-bottom:1px solid var(--line); align-items:start; }
    .event:last-child { border-bottom:0; }
    .dot { width:11px; height:11px; margin-top:4px; border-radius:50%; background:var(--accent); }
    .event small { color:var(--muted); }
    .offer-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
    .offer { border:1px solid var(--line); border-radius:13px; padding:14px; }
    .offer .state { color:var(--warn); font-size:.8rem; overflow-wrap:anywhere; }
    .offer ul { padding-left:18px; color:var(--muted); }
    table { width:100%; border-collapse:collapse; }
    th,td { text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    .empty { color:var(--muted); padding:18px 0; }
    .footnote { color:var(--muted); font-size:.82rem; margin:13px 0 0; }
    @media (max-width:900px) { .metrics,.offer-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .registry-grid { grid-template-columns:1fr; } .detail { position:static; } }
    @media (max-width:600px) { header { display:block; } .status { display:inline-block; margin-top:14px; } .metrics,.offer-grid,.filters { grid-template-columns:1fr; } .event { grid-template-columns:18px 1fr; } .event > :last-child { grid-column:2; } .bar-row { grid-template-columns:110px 1fr 36px; } dl { grid-template-columns:1fr; gap:3px; } dd { margin-bottom:8px; } }
  </style>
</head>
<body>
  <header>
    <div><h1>Taedri Registry Console</h1><p class="subtitle">Real-source primitive candidates, immutable receipts, search descriptors, and a commercial hypothesis in one inspectable POC.</p></div>
    <div class="status">Candidate-only · 0 promoted</div>
  </header>
  <nav aria-label="Console sections">
    <button type="button" data-tab="registry" aria-selected="true">Registry</button>
    <button type="button" data-tab="operations" aria-selected="false">Operations</button>
    <button type="button" data-tab="business" aria-selected="false">Business model</button>
  </nav>
  <main>
    <section id="registry" class="panel">
      <div class="metrics" id="metrics"></div>
      <div class="surface">
        <div class="filters">
          <label>Search candidates<input id="search" type="search" placeholder="name, module, docstring, call, token"></label>
          <label>Kind<select id="kind"><option value="">All kinds</option></select></label>
          <label>Module<select id="module"><option value="">All modules</option></select></label>
        </div>
      </div>
      <div class="registry-grid">
        <section class="surface"><h2 id="result-count">Candidates</h2><div id="candidate-list" class="candidate-list"></div></section>
        <aside class="surface detail" id="candidate-detail" aria-live="polite"></aside>
      </div>
    </section>
    <section id="operations" class="panel" hidden>
      <div class="metrics" id="operation-metrics"></div>
      <section class="surface"><h2>Candidate kind distribution</h2><div class="bars" id="kind-bars"></div></section>
      <section class="surface"><h2>Worker receipts</h2><div class="timeline" id="worker-events"></div></section>
      <section class="surface"><h2>Digest-only harness session</h2><div class="timeline" id="session-events"></div></section>
    </section>
    <section id="business" class="panel" hidden>
      <section class="surface"><h2>Core value unit</h2><h3 id="value-unit"></h3><p id="value-definition"></p><p class="footnote" id="billing-rule"></p></section>
      <section class="surface"><h2>Offer ladder</h2><div class="offer-grid" id="offers"></div></section>
      <section class="surface"><h2>Meter contracts</h2><table><thead><tr><th>Meter</th><th>Unit</th><th>Integrity rule</th></tr></thead><tbody id="meters"></tbody></table></section>
      <section class="surface"><h2>Validation gates before pricing or claims</h2><div class="timeline" id="gates"></div></section>
    </section>
  </main>
  <script id="dataset" type="application/json">__DATA__</script>
  <script>
  (() => {
    "use strict";
    const data = JSON.parse(document.getElementById("dataset").textContent);
    const candidates = data.candidates;
    const summary = data.summary;
    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]);
    const short = (value) => value && value.length > 31 ? value.slice(0, 18) + "…" + value.slice(-10) : value;
    const metric = (label, value, context) => `<div class="metric"><span class="muted">${esc(label)}</span><strong>${esc(value)}</strong><span class="muted">${esc(context)}</span></div>`;
    document.getElementById("metrics").innerHTML = [
      metric("Primitive candidates", summary.candidate_count, "real Taedri source"),
      metric("Syntax call edges", summary.call_edge_count, "unverified calls-may"),
      metric("Unique CAS blobs", summary.unique_blob_count, `${summary.unique_blob_bytes.toLocaleString()} bytes`),
      metric("Promoted", 0, "independent verification required")
    ].join("");
    document.getElementById("operation-metrics").innerHTML = [
      metric("Source files", summary.source_files, `${summary.scanned_source_bytes.toLocaleString()} bytes`),
      metric("Intake events", data.operations.intake_event_count, "four per candidate"),
      metric("Worker jobs", data.operations.worker_jobs.length, "both succeeded"),
      metric("Model calls", 0, "sample session abstained")
    ].join("");

    const kinds = [...new Set(candidates.map((item) => item.kind))].sort();
    const modules = [...new Set(candidates.map((item) => item.module))].sort();
    const kindSelect = document.getElementById("kind");
    const moduleSelect = document.getElementById("module");
    kinds.forEach((value) => kindSelect.insertAdjacentHTML("beforeend", `<option value="${esc(value)}">${esc(value)}</option>`));
    modules.forEach((value) => moduleSelect.insertAdjacentHTML("beforeend", `<option value="${esc(value)}">${esc(value)}</option>`));
    const search = document.getElementById("search");
    let selectedId = data.selected_candidate;

    function candidateText(item) {
      return [item.handle,item.module,item.qualified_name,item.kind,item.path,item.summary,...item.calls,...item.tokens].join(" ").toLowerCase();
    }
    function filteredCandidates() {
      const query = search.value.trim().toLowerCase();
      return candidates.filter((item) => (!query || candidateText(item).includes(query)) && (!kindSelect.value || item.kind === kindSelect.value) && (!moduleSelect.value || item.module === moduleSelect.value));
    }
    function renderDetail(item) {
      if (!item) { document.getElementById("candidate-detail").innerHTML = '<p class="empty">No candidate matches the current filters.</p>'; return; }
      document.getElementById("candidate-detail").innerHTML = `
        <h2>${esc(item.qualified_name)}</h2><p class="muted">${esc(item.module)}</p>
        <div class="badges"><span class="badge">${esc(item.kind)}</span><span class="badge">${esc(item.state)}</span><span class="badge">license: ${esc(item.license)}</span><span class="badge">D2 descriptor</span></div>
        <p>${esc(item.summary || "No docstring summary was extracted.")}</p>
        <dl>
          <dt>Source</dt><dd><code>${esc(item.path)}:${item.lines[0]}–${item.lines[1]}</code></dd>
          <dt>Handle</dt><dd><code>${esc(item.handle)}</code></dd>
          <dt>Arity</dt><dd>${item.arity}</dd>
          <dt>Calls may</dt><dd>${item.calls.length ? item.calls.map((call) => `<code>${esc(call)}</code>`).join(" · ") : "none extracted"}</dd>
          <dt>Revision</dt><dd><code>${esc(short(item.revision_id))}</code></dd>
          <dt>Contract</dt><dd><code>${esc(short(item.contract_digest))}</code></dd>
          <dt>Descriptor</dt><dd><code>${esc(short(item.descriptor_digest))}</code></dd>
        </dl>`;
    }
    function renderCandidates() {
      const filtered = filteredCandidates();
      const shown = filtered.slice(0, 60);
      if (!filtered.some((item) => item.id === selectedId)) selectedId = shown[0]?.id;
      document.getElementById("result-count").textContent = `${filtered.length} candidates${filtered.length > 60 ? " · first 60 shown" : ""}`;
      document.getElementById("candidate-list").innerHTML = shown.length ? shown.map((item) => `<button type="button" class="candidate" data-id="${esc(item.id)}" aria-pressed="${item.id === selectedId}"><strong>${esc(item.qualified_name)}</strong><span>${esc(item.module)} · ${esc(item.kind)} · ${item.calls.length} calls</span></button>`).join("") : '<p class="empty">No matching candidates.</p>';
      renderDetail(candidates.find((item) => item.id === selectedId));
      document.querySelectorAll(".candidate").forEach((button) => button.addEventListener("click", () => { selectedId = button.dataset.id; renderCandidates(); }));
    }
    [search, kindSelect, moduleSelect].forEach((control) => control.addEventListener(control === search ? "input" : "change", renderCandidates));
    renderCandidates();

    const maximumKind = Math.max(...Object.values(summary.candidate_kinds));
    document.getElementById("kind-bars").innerHTML = Object.entries(summary.candidate_kinds).sort((a,b) => b[1]-a[1]).map(([label,value]) => `<div class="bar-row"><span>${esc(label)}</span><div class="track"><div class="fill" style="width:${(value/maximumKind)*100}%"></div></div><strong>${value}</strong></div>`).join("");
    function eventRows(events, labelKey, detail) {
      return events.map((event) => `<div class="event"><span class="dot"></span><strong>${esc(event[labelKey])}</strong><div><span>${esc(detail(event))}</span><br><small>${esc(event.occurred_at)} · ${esc(event.actor || event.worker_id || "system")}</small></div></div>`).join("");
    }
    document.getElementById("worker-events").innerHTML = eventRows(data.operations.worker_events, "event_kind", (event) => event.detail);
    document.getElementById("session-events").innerHTML = eventRows(data.operations.session_events, "event_kind", (event) => `${event.input_refs.length} inputs · ${event.output_refs.length} outputs`);

    const business = data.business_model;
    document.getElementById("value-unit").textContent = business.core_value_unit.name;
    document.getElementById("value-definition").textContent = business.core_value_unit.definition;
    document.getElementById("billing-rule").textContent = business.core_value_unit.billing_rule;
    document.getElementById("offers").innerHTML = business.offers.map((offer) => `<article class="offer"><h3>${esc(offer.id)}</h3><p class="state">${esc(offer.commercial_state)}</p><p>${esc(offer.target)}</p><ul>${offer.value.map((value) => `<li>${esc(value)}</li>`).join("")}</ul><p><strong>Model:</strong> ${esc(offer.revenue_model)}</p></article>`).join("");
    document.getElementById("meters").innerHTML = business.meters.map((meter) => `<tr><td><code>${esc(meter.id)}</code></td><td>${esc(meter.unit)}</td><td>${esc(meter.anti_abuse_rule)}</td></tr>`).join("");
    document.getElementById("gates").innerHTML = business.validation_gates.map((gate) => `<div class="event"><span class="dot"></span><strong>${esc(gate.id)}</strong><div>${esc(gate.question)}<br><small>${esc(gate.required_receipts.join(" · "))}</small></div></div>`).join("");

    document.querySelectorAll("nav button").forEach((button) => button.addEventListener("click", () => {
      document.querySelectorAll("nav button").forEach((peer) => peer.setAttribute("aria-selected", String(peer === button)));
      document.querySelectorAll(".panel").forEach((panel) => { panel.hidden = panel.id !== button.dataset.tab; });
    }));
  })();
  </script>
</body>
</html>
'''


INLINE_TEMPLATE = r'''<div id="taedri-registry-console">
  <style>
    #taedri-registry-console .tcg-bars { display:grid; gap:.5rem; margin:.75rem 0; }
    #taedri-registry-console .tcg-bar { display:grid; grid-template-columns:minmax(7rem,1fr) 3fr 2.5rem; gap:.5rem; align-items:center; }
    #taedri-registry-console .tcg-track { height:.75rem; border-radius:999px; background:var(--muted); overflow:hidden; }
    #taedri-registry-console .tcg-fill { height:100%; border-radius:inherit; background:var(--viz-series-1); }
    #taedri-registry-console .tcg-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr)); gap:.45rem; margin-top:.75rem; }
    #taedri-registry-console .tcg-grid .btn { min-width:0; overflow-wrap:anywhere; }
    #taedri-registry-console .tcg-selected { margin-top:.75rem; }
    @media (max-width:520px) { #taedri-registry-console .tcg-bar { grid-template-columns:6rem 1fr 2rem; } }
  </style>
  <div class="viz-grid">
    <div class="card viz-stat"><span class="text-muted">Candidates</span><span class="viz-stat-value" data-stat="candidates"></span><span class="text-small text-muted">real source</span></div>
    <div class="card viz-stat"><span class="text-muted">Call edges</span><span class="viz-stat-value" data-stat="edges"></span><span class="text-small text-muted">calls-may</span></div>
    <div class="card viz-stat"><span class="text-muted">Promoted</span><span class="viz-stat-value">0</span><span class="text-small text-muted">verification gated</span></div>
  </div>
  <div class="viz-controls">
    <label class="form-label">Search<input class="form-control" type="search" data-control="search" placeholder="name, module, call"></label>
    <label class="form-label">Kind<select class="form-select" data-control="kind"><option value="">All kinds</option></select></label>
  </div>
  <div class="tcg-bars" data-view="bars" aria-label="Candidate counts by kind"></div>
  <div class="card tcg-selected" data-view="selected" aria-live="polite"></div>
  <div class="tcg-grid" data-view="grid"></div>
  <script type="application/json" id="taedri-registry-console-data">__DATA__</script>
</div>
<script>
(() => {
  "use strict";
  const root = document.getElementById("taedri-registry-console");
  const data = JSON.parse(document.getElementById("taedri-registry-console-data").textContent);
  const candidates = data.candidates;
  const summary = data.summary;
  const search = root.querySelector('[data-control="search"]');
  const kind = root.querySelector('[data-control="kind"]');
  const grid = root.querySelector('[data-view="grid"]');
  const selected = root.querySelector('[data-view="selected"]');
  const escapeText = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[character]);
  root.querySelector('[data-stat="candidates"]').textContent = summary.candidate_count;
  root.querySelector('[data-stat="edges"]').textContent = summary.call_edge_count;
  [...new Set(candidates.map((item) => item.kind))].sort().forEach((value) => kind.insertAdjacentHTML("beforeend", `<option value="${escapeText(value)}">${escapeText(value)}</option>`));
  const maximum = Math.max(...Object.values(summary.candidate_kinds));
  root.querySelector('[data-view="bars"]').innerHTML = Object.entries(summary.candidate_kinds).sort((a,b) => b[1]-a[1]).map(([label,value]) => `<div class="tcg-bar"><span>${escapeText(label)}</span><div class="tcg-track"><div class="tcg-fill" style="width:${(value/maximum)*100}%"></div></div><strong>${value}</strong></div>`).join("");
  let selectedId = data.selected_candidate;
  function text(item) { return [item.qualified_name,item.module,item.summary,...item.calls,...item.tokens].join(" ").toLowerCase(); }
  function showSelected(item) { selected.innerHTML = item ? `<strong>${escapeText(item.qualified_name)}</strong> <span class="text-muted">${escapeText(item.module)} · ${escapeText(item.kind)} · ${item.calls.length} calls · ${escapeText(item.state)}</span>` : '<span class="text-muted">No matching candidate</span>'; }
  function render() {
    const query = search.value.trim().toLowerCase();
    const filtered = candidates.filter((item) => (!query || text(item).includes(query)) && (!kind.value || item.kind === kind.value));
    if (!filtered.some((item) => item.id === selectedId)) selectedId = filtered[0]?.id;
    grid.innerHTML = filtered.slice(0,48).map((item) => `<button type="button" class="btn viz-tile" data-id="${escapeText(item.id)}" aria-pressed="${item.id === selectedId}">${escapeText(item.qualified_name)}</button>`).join("");
    showSelected(candidates.find((item) => item.id === selectedId));
    grid.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => { selectedId = button.dataset.id; render(); }));
  }
  search.addEventListener("input", render);
  kind.addEventListener("change", render);
  render();
})();
</script>
'''


def _embedded(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def _kind_svg(data: dict[str, object]) -> str:
    counts = data["summary"]["candidate_kinds"]
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    maximum = max(counts.values())
    rows = []
    for index, (label, value) in enumerate(ordered):
        y = 142 + index * 76
        width = round(780 * value / maximum)
        rows.append(f'<text x="50" y="{y + 20}" class="label">{label}</text>')
        rows.append(f'<rect x="260" y="{y}" width="780" height="28" rx="14" class="track"/>')
        rows.append(f'<rect x="260" y="{y}" width="{width}" height="28" rx="14" class="bar"/>')
        rows.append(f'<text x="1065" y="{y + 21}" class="value">{value}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="430" viewBox="0 0 1200 430" role="img" aria-labelledby="title desc">
<title id="title">Real-source primitive candidates by entity kind</title>
<desc id="desc">Distribution of {data['summary']['candidate_count']} candidates extracted from Taedri CodeGraph source without executing it.</desc>
<style>:root{{--bg:#fff;--fg:#18212f;--muted:#657083;--track:#e9ecf2;--bar:#6656d9}}@media(prefers-color-scheme:dark){{:root{{--bg:#11141a;--fg:#edf1f7;--muted:#a7b0bf;--track:#2a303b;--bar:#a99cff}}}}.bg{{fill:var(--bg)}}text{{font-family:Inter,system-ui,sans-serif;fill:var(--fg)}}.title{{font-size:28px;font-weight:600}}.note{{font-size:16px;fill:var(--muted)}}.label,.value{{font-size:18px}}.value{{font-weight:600}}.track{{fill:var(--track)}}.bar{{fill:var(--bar)}}</style>
<rect class="bg" width="1200" height="430"/><text x="50" y="58" class="title">Real-source primitive candidates</text><text x="50" y="88" class="note">{data['summary']['source_files']} files · {data['summary']['scanned_source_bytes']:,} source bytes · {data['summary']['diagnostic_count']} parse diagnostics · candidate-only</text>{''.join(rows)}<text x="50" y="397" class="note">Syntax-derived records; none are behaviorally verified or promoted.</text></svg>'''


def _operating_model_svg(data: dict[str, object]) -> str:
    summary = data["summary"]
    events = data["operations"]["intake_event_count"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="760" viewBox="0 0 1500 760" role="img" aria-labelledby="title desc">
<title id="title">Taedri product and operating model</title><desc id="desc">Real-source pipeline, evidence gate, and planned commercial offer ladder.</desc>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="arrow"/></marker></defs>
<style>:root{{--bg:#fff;--fg:#18212f;--muted:#657083;--line:#cfd5df;--accent:#6656d9;--soft:#eeebff;--good:#147a55;--warn:#9a5b00}}@media(prefers-color-scheme:dark){{:root{{--bg:#11141a;--fg:#edf1f7;--muted:#a7b0bf;--line:#3a4352;--accent:#a99cff;--soft:#282442;--good:#61d0a1;--warn:#f1bd66}}}}.bg{{fill:var(--bg)}}text{{font-family:Inter,system-ui,sans-serif;fill:var(--fg)}}.title{{font-size:30px;font-weight:600}}.subtitle,.small{{fill:var(--muted)}}.subtitle{{font-size:17px}}.small{{font-size:14px}}.box{{fill:var(--soft);stroke:var(--line);stroke-width:1.5}}.gate{{fill:var(--bg);stroke:var(--accent);stroke-width:2}}.line{{stroke:var(--line);stroke-width:2;fill:none;marker-end:url(#arrow)}}.arrow{{fill:var(--line)}}.stage{{font-size:18px;font-weight:600}}.value{{fill:var(--good);font-size:18px;font-weight:600}}.warn{{fill:var(--warn)}}.divider{{stroke:var(--line);stroke-width:1}}</style>
<rect class="bg" width="1500" height="760"/><text x="55" y="60" class="title">Product and operating model</text><text x="55" y="92" class="subtitle">One immutable evidence spine; replaceable analyzers, indexes, models, workers, harnesses, and commercial packaging.</text>
<g transform="translate(55 145)"><rect class="box" width="210" height="105" rx="16"/><text x="20" y="35" class="stage">Acquire real source</text><text x="20" y="63" class="small">{summary['source_files']} Python files</text><text x="20" y="84" class="small">No import or execution</text></g>
<path class="line" d="M265 197H310"/><g transform="translate(310 145)"><rect class="box" width="210" height="105" rx="16"/><text x="20" y="35" class="stage">Extract candidates</text><text x="20" y="63" class="small">{summary['candidate_count']} primitives</text><text x="20" y="84" class="small">{summary['call_edge_count']} call edges</text></g>
<path class="line" d="M520 197H565"/><g transform="translate(565 145)"><rect class="box" width="210" height="105" rx="16"/><text x="20" y="35" class="stage">Intake ledger</text><text x="20" y="63" class="small">{events} events</text><text x="20" y="84" class="small">0 auto-promoted</text></g>
<path class="line" d="M775 197H820"/><g transform="translate(820 145)"><rect class="box" width="210" height="105" rx="16"/><text x="20" y="35" class="stage">Build projections</text><text x="20" y="63" class="small">Sparse · blocking · LSH</text><text x="20" y="84" class="small">Embeddings deferred</text></g>
<path class="line" d="M1030 197H1075"/><g transform="translate(1075 145)"><rect class="box" width="210" height="105" rx="16"/><text x="20" y="35" class="stage">Harness retrieval</text><text x="20" y="63" class="small">Digest-only prompt</text><text x="20" y="84" class="small">Selective D0–D4</text></g>
<path class="line" d="M1285 197H1330"/><g transform="translate(1330 145)"><rect class="gate" width="115" height="105" rx="16"/><text x="18" y="35" class="stage">Decide</text><text x="18" y="63" class="small">Verify</text><text x="18" y="84" class="small warn">or abstain</text></g>
<line x1="55" y1="305" x2="1445" y2="305" class="divider"/><text x="55" y="348" class="value">Value unit: independently accepted, policy-compliant outcome</text><text x="55" y="378" class="subtitle">Rejected, abstained, unverified, timed-out, and policy-blocked attempts never count as successful outcomes.</text>
<g transform="translate(55 430)"><rect class="box" width="250" height="150" rx="16"/><text x="20" y="35" class="stage">Local evaluator</text><text x="20" y="65" class="small">Pre-alpha source</text><text x="20" y="90" class="small">Local ingestion + search</text><text x="20" y="115" class="small">License decision pending</text></g>
<path class="line" d="M305 505H335"/><g transform="translate(335 430)"><rect class="box" width="250" height="150" rx="16"/><text x="20" y="35" class="stage">Team registry</text><text x="20" y="65" class="small">Base subscription</text><text x="20" y="90" class="small">Private namespaces + ACLs</text><text x="20" y="115" class="small">Storage/index capacity</text></g>
<path class="line" d="M585 505H615"/><g transform="translate(615 430)"><rect class="box" width="250" height="150" rx="16"/><text x="20" y="35" class="stage">Managed control plane</text><text x="20" y="65" class="small">Subscription + usage</text><text x="20" y="90" class="small">Workers + verification</text><text x="20" y="115" class="small">Provider pass-through</text></g>
<path class="line" d="M865 505H895"/><g transform="translate(895 430)"><rect class="box" width="250" height="150" rx="16"/><text x="20" y="35" class="stage">Enterprise</text><text x="20" y="65" class="small">Annual agreement</text><text x="20" y="90" class="small">Residency + assurance</text><text x="20" y="115" class="small">Dedicated deployment</text></g>
<path class="line" d="M1145 505H1175"/><g transform="translate(1175 430)"><rect class="box" width="270" height="150" rx="16"/><text x="20" y="35" class="stage">Marketplace later</text><text x="20" y="65" class="small">Optional take rate</text><text x="20" y="90" class="small">Only after supply, demand,</text><text x="20" y="115" class="small">reputation + license proof</text></g>
<text x="55" y="640" class="subtitle">Pricing remains unset until customer discovery, real provider costs, retention, retrieval lift, and verification economics are measured.</text><text x="55" y="675" class="small">Deployment: modular monolith → independently scaled Fly process groups → separate services only after security, scaling, failure-domain, runtime, ownership, or residency evidence.</text></svg>'''


def main() -> int:
    data = json.loads(DATA_PATH.read_text("utf-8"))
    embedded = _embedded(data)
    APP_PATH.parent.mkdir(parents=True, exist_ok=True)
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    APP_PATH.write_text(FULL_TEMPLATE.replace("__DATA__", embedded), "utf-8")
    INLINE_PATH.write_text(INLINE_TEMPLATE.replace("__DATA__", embedded), "utf-8")
    (ASSET_ROOT / "primitive-candidate-kinds.svg").write_text(_kind_svg(data), "utf-8")
    (ASSET_ROOT / "product-operating-model.svg").write_text(_operating_model_svg(data), "utf-8")
    print(json.dumps({"app": str(APP_PATH.relative_to(ROOT)), "inline": str(INLINE_PATH), "candidates": len(data["candidates"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

