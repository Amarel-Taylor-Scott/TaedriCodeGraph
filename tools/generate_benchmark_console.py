#!/usr/bin/env python3
"""Generate the self-contained benchmark evidence console."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results" / "benchmark-worker-2026-07-16"
OUTPUT = ROOT / "apps" / "explorer" / "benchmark-console.html"


def main() -> int:
    payload = {
        "report": json.loads((RESULTS / "conformance-report.json").read_text("utf-8")),
        "campaign": json.loads((RESULTS / "campaign-plan.json").read_text("utf-8")),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", encoded)
    OUTPUT.write_text(html, "utf-8")
    return 0


TEMPLATE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Taedri · Benchmark Evidence Console</title>
<style>
:root{--bg:#07111f;--panel:#0e1a2c;--panel2:#132239;--line:#283b56;--muted:#93a7c3;--text:#f3f7fc;--blue:#4d8dff;--cyan:#22d3ee;--green:#35d399;--violet:#9b87f5;--amber:#f5b942;--red:#fb7185;--shadow:0 18px 54px #02081788}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0,#172a4e 0,transparent 30%),radial-gradient(circle at 0 60%,#0c3440 0,transparent 26%),var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;min-height:100vh}.shell{max-width:1500px;margin:auto;padding:26px}.top{display:flex;gap:24px;justify-content:space-between;align-items:center;margin-bottom:22px}.brand{display:flex;align-items:center;gap:13px}.logo{width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,var(--blue),var(--violet));display:grid;place-items:center;font-weight:850;box-shadow:0 8px 24px #4d8dff55}.brand h1{font-size:20px;line-height:1;margin:0}.brand p{margin:7px 0 0;color:var(--muted);font-size:12px}.pill{border:1px solid var(--line);background:#0b1728;border-radius:99px;padding:8px 12px;color:#c7d4e6;font:600 11px ui-monospace,monospace}.warning{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:17px 20px;border:1px solid #a56b1e;background:linear-gradient(90deg,#35260e,#211d18);border-radius:15px;box-shadow:var(--shadow);margin-bottom:20px}.warning strong{color:#ffd782}.warning span{color:#d6c3a0}.tabs{display:flex;gap:8px;margin:20px 0}.tab{border:1px solid var(--line);background:#0d192a;color:#9fb2cc;padding:9px 14px;border-radius:10px;cursor:pointer;font-weight:700}.tab.active{background:#19345d;color:#fff;border-color:#4d8dff}.view{display:none}.view.active{display:block}.grid{display:grid;gap:16px}.kpis{grid-template-columns:repeat(5,minmax(0,1fr));margin-bottom:16px}.card{background:linear-gradient(145deg,#101e32,#0b1728);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)}.kpi{padding:17px 18px}.kpi .label{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.11em}.kpi .value{font-size:28px;font-weight:800;margin-top:8px}.kpi .note{color:#8196b4;font-size:11px;margin-top:3px}.good{color:var(--green)}.bad{color:var(--red)}.amber{color:var(--amber)}.main{grid-template-columns:1.35fr .65fr}.panel{padding:20px}.panel h2{font-size:15px;margin:0}.panel .desc{color:var(--muted);font-size:12px;margin:5px 0 18px}.lane-flow{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;position:relative}.lane{min-height:185px;padding:16px;border-radius:14px;border:1px solid var(--line);background:#101c2e;position:relative;overflow:hidden;cursor:pointer;transition:.18s}.lane:hover,.lane.selected{transform:translateY(-2px);border-color:var(--blue);box-shadow:0 12px 30px #0006}.lane:before{content:"";position:absolute;inset:0 0 auto;height:4px;background:var(--accent)}.lane .num{font:800 11px ui-monospace,monospace;color:var(--accent)}.lane h3{font-size:15px;margin:11px 0 7px}.lane p{font-size:12px;color:#9eb1ca;margin:0 0 13px}.rights{display:flex;flex-wrap:wrap;gap:5px}.right{font-size:10px;padding:4px 6px;border:1px solid #304765;border-radius:6px;color:#c7d5e8;background:#0a1422}.lane[data-lane="bare_model"]{--accent:#94a3b8}.lane[data-lane="search_context"]{--accent:var(--blue)}.lane[data-lane="primitive_plan"]{--accent:var(--violet)}.lane[data-lane="primitive_materialized"]{--accent:var(--green)}.gate{display:grid;gap:10px}.gate-item{display:grid;grid-template-columns:24px 1fr;gap:10px;align-items:start;padding:11px 0;border-bottom:1px solid #22344d}.gate-item:last-child{border:0}.dot{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;font-size:11px;background:#123528;color:var(--green);border:1px solid #1c684e}.dot.no{background:#3b211c;color:var(--amber);border-color:#80542f}.gate-item b{font-size:12px}.gate-item small{display:block;color:var(--muted);margin-top:3px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:800px}th,td{text-align:left;border-bottom:1px solid #22344d;padding:12px 10px}th{font-size:10px;color:#8297b4;text-transform:uppercase;letter-spacing:.08em}td{font:12px ui-monospace,monospace;color:#d7e3f3}.bar{width:90px;height:6px;border-radius:5px;background:#1b2d44;overflow:hidden;display:inline-block;margin-right:8px}.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--cyan))}.track-grid{grid-template-columns:repeat(4,1fr)}.track{padding:18px;min-height:185px}.track .state{font:700 10px ui-monospace,monospace;color:var(--amber);text-transform:uppercase}.track h3{font-size:15px;margin:9px 0}.track p{color:var(--muted);font-size:12px}.track .policy{color:#a9c6ec;border-top:1px solid #243852;padding-top:11px;margin-top:12px;font:11px ui-monospace,monospace}.metric-grid{grid-template-columns:repeat(3,1fr)}.metric{padding:19px}.metric h3{font-size:14px;margin:0 0 10px;color:#dce9fa}.metric ul{padding-left:17px;margin:0;color:#97acc7;font-size:12px}.metric li{margin:6px 0}.formula{padding:20px;background:#091423;border:1px solid #29425f;border-radius:13px;font:12px/1.8 ui-monospace,monospace;color:#c7ddfa;white-space:pre-wrap}.split{grid-template-columns:1fr 1fr}.boundary{padding:20px;position:relative}.boundary-row{display:grid;grid-template-columns:1fr 70px 1fr;align-items:center;margin:12px 0}.box{border:1px solid #315071;background:#0c1d31;border-radius:12px;padding:13px}.arrow{text-align:center;color:var(--cyan);font-size:21px}.forbidden{border-color:#7d3041;background:#2b1520}.footer{color:#6f849f;text-align:center;font-size:11px;padding:30px 0 8px}@media(max-width:1000px){.kpis{grid-template-columns:repeat(2,1fr)}.main,.split{grid-template-columns:1fr}.lane-flow,.track-grid,.metric-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:620px){.shell{padding:15px}.top,.warning{align-items:flex-start;flex-direction:column}.kpis,.lane-flow,.track-grid,.metric-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<main class="shell">
  <header class="top"><div class="brand"><div class="logo">T</div><div><h1>Benchmark Evidence Console</h1><p>Primitive-assisted coding · matched evaluation control plane</p></div></div><div class="pill" id="experiment-id"></div></header>
  <section class="warning"><div><strong>CONFORMANCE FIXTURE — NOT MODEL EFFICACY</strong><br><span>Real Taedri artifacts and registry identities; deterministic fixture receipts; no model/provider call.</span></div><div class="pill" id="claim-state"></div></section>
  <nav class="tabs"><button class="tab active" data-view="evidence">Evidence</button><button class="tab" data-view="lanes">Lane contracts</button><button class="tab" data-view="campaign">Real campaign</button><button class="tab" data-view="economics">Metrics & economics</button></nav>

  <section class="view active" id="evidence">
    <div class="grid kpis">
      <div class="card kpi"><div class="label">Scheduled</div><div class="value" id="scheduled"></div><div class="note">task × lane × seed</div></div>
      <div class="card kpi"><div class="label">Receipts</div><div class="value good" id="completed"></div><div class="note">terminal records retained</div></div>
      <div class="card kpi"><div class="label">Contamination</div><div class="value good" id="leaks"></div><div class="note">detected reference leaks</div></div>
      <div class="card kpi"><div class="label">Claimable pairs</div><div class="value amber" id="claimable-pairs"></div><div class="note">real + clean pairs only</div></div>
      <div class="card kpi"><div class="label">Provider calls</div><div class="value amber">0</div><div class="note">fixture intentionally offline</div></div>
    </div>
    <div class="grid main">
      <div class="card panel"><h2>Progressive assistance lanes</h2><p class="desc">Click a lane to inspect the context boundary. Every lane uses the same frozen experiment budget.</p><div class="lane-flow" id="lane-flow"></div></div>
      <aside class="card panel"><h2>Claim gate</h2><p class="desc">The report compiler refuses efficacy and ROI claims until every condition is true.</p><div class="gate" id="claim-gate"></div></aside>
    </div>
    <div class="card panel" style="margin-top:16px"><h2>Conformance receipt summary</h2><p class="desc">These values demonstrate reconciliation and aggregation only. Zero treatment deltas are not a product result.</p><div class="table-wrap"><table><thead><tr><th>Lane</th><th>Receipts</th><th>Fixture accepted</th><th>Behavior agreement</th><th>Reuse fraction</th><th>Mean tokens</th><th>Mean wall</th></tr></thead><tbody id="summary-body"></tbody></table></div></div>
  </section>

  <section class="view" id="lanes">
    <div class="grid split"><div class="card boundary"><h2>Model-facing side</h2><p class="desc">Only lane-authorized projections and selected immutable revisions.</p><div id="boundary-lanes"></div></div><div class="card boundary forbidden"><h2>Verifier-only sealed side</h2><p class="desc">No reverse flow into search, embeddings, primitive generation, training, or model context.</p><div class="boundary-row"><div class="box">Hidden tests and graders</div><div class="arrow">→</div><div class="box">Independent verifier</div></div><div class="boundary-row"><div class="box">Gold patches and traces</div><div class="arrow">⊘</div><div class="box">Production retrieval</div></div><div class="boundary-row"><div class="box">Cold holdout fingerprints</div><div class="arrow">→</div><div class="box">Contamination strata</div></div></div></div>
  </section>

  <section class="view" id="campaign">
    <div class="card panel"><h2>First claimable campaign</h2><p class="desc" id="primary-question"></p><div class="grid track-grid" id="tracks"></div></div>
    <div class="card panel" style="margin-top:16px"><h2>Matched controls</h2><p class="desc">Pre-register these before any model result is visible.</p><div class="grid metric-grid" id="controls"></div></div>
  </section>

  <section class="view" id="economics">
    <div class="grid metric-grid" id="metrics"></div>
    <div class="grid split" style="margin-top:16px"><div class="card panel"><h2>Failure-inclusive unit economics</h2><p class="desc">Provider savings alone are not total savings.</p><div class="formula">total_cost = provider + retrieval + worker + verification

cost / accepted outcome = Σ(all attempt costs) / independently accepted outcomes

token savings = (bare tokens − treatment tokens) / bare tokens

ROI claim = prohibited without controlled baseline + sourced value receipt</div></div><div class="card panel"><h2>Promotion rule</h2><p class="desc">A representation or lane earns production status only after marginal value repays its complete cost.</p><div class="gate" id="promotion"></div></div></div>
  </section>
  <footer class="footer">Self-contained artifact · no network requests · generated from immutable conformance report and campaign manifest</footer>
</main>
<script id="dataset" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('dataset').textContent),r=data.report,c=data.campaign;
const fmt=n=>n==null?'—':n.toLocaleString(),pct=n=>n==null?'—':(n/10000).toFixed(n%10000?1:0)+'%';
document.getElementById('experiment-id').textContent=r.experiment_id.slice(0,34)+'…';
document.getElementById('claim-state').textContent=r.efficacy_claimable?'CLAIMABLE':'CLAIM DISABLED';
document.getElementById('scheduled').textContent=fmt(r.scheduled_run_count);document.getElementById('completed').textContent=fmt(r.completed_run_count);
document.getElementById('leaks').textContent=fmt(r.contamination_counts.detected||0);
document.getElementById('claimable-pairs').textContent=fmt(r.matched_comparisons.reduce((s,x)=>s+x.claimable_clean_pair_count,0));
const laneNames={bare_model:'Bare model',search_context:'Search context',primitive_plan:'Primitive plan',primitive_materialized:'Primitive materialized'};
document.getElementById('lane-flow').innerHTML=c.lanes.map((l,i)=>`<article class="lane ${i===0?'selected':''}" data-lane="${l.id}"><div class="num">LANE ${i}</div><h3>${laneNames[l.id]}</h3><p>${l.model_visible.join(' · ')}</p><div class="rights">${(l.taedri_access.length?l.taedri_access:['no Taedri access']).map(x=>`<span class="right">${x}</span>`).join('')}</div></article>`).join('');
document.querySelectorAll('.lane').forEach(x=>x.onclick=()=>{document.querySelectorAll('.lane').forEach(y=>y.classList.remove('selected'));x.classList.add('selected')});
const gates=[['Matched block complete',r.is_complete,'All scheduled lanes have terminal receipts'],['Real model usage',r.evidence_class==='real_model','Current provider is deterministic-contract-fixture'],['Clean contamination stratum',(r.contamination_counts.detected||0)===0,'Detected leaks are zero; fixture is clean'],['Efficacy claim enabled',r.efficacy_claimable,'Requires complete + real + clean evidence']];
document.getElementById('claim-gate').innerHTML=gates.map(g=>`<div class="gate-item"><span class="dot ${g[1]?'':'no'}">${g[1]?'✓':'!'}</span><div><b>${g[0]}</b><small>${g[2]}</small></div></div>`).join('');
document.getElementById('summary-body').innerHTML=r.lane_summaries.map(x=>`<tr><td>${laneNames[x.lane]}</td><td>${x.run_count}</td><td>${x.accepted_count} / ${x.run_count}</td><td><span class="bar"><i style="width:${(x.behavior_consistency_ppm||0)/10000}%"></i></span>${pct(x.behavior_consistency_ppm)}</td><td>${pct(x.verified_reuse_fraction_ppm)}</td><td>${fmt(x.mean_model_tokens)}</td><td>${fmt(x.mean_wall_ms)} ms</td></tr>`).join('');
document.getElementById('boundary-lanes').innerHTML=c.lanes.map((l,i)=>`<div class="boundary-row"><div class="box"><b>${laneNames[l.id]}</b><br><span class="desc">${l.taedri_access.join(', ')||'task/repository only'}</span></div><div class="arrow">→</div><div class="box">Model workspace ${i===3?' + selected pack':''}</div></div>`).join('');
document.getElementById('primary-question').textContent=c.primary_question;
document.getElementById('tracks').innerHTML=c.evaluation_tracks.slice(0,4).map(t=>`<article class="card track"><div class="state">${t.adapter_state||'pilot'}</div><h3>${t.id.replaceAll('-',' ')}</h3><p>${t.purpose}</p><div class="policy">${t.source_policy}</div></article>`).join('');
document.getElementById('controls').innerHTML=c.matched_controls.map((x,i)=>`<article class="card metric"><h3>${String(i+1).padStart(2,'0')}</h3><p class="desc">${x}</p></article>`).join('');
document.getElementById('metrics').innerHTML=Object.entries(c.metric_families).map(([k,v])=>`<article class="card metric"><h3>${k[0].toUpperCase()+k.slice(1)}</h3><ul>${v.map(x=>`<li>${x}</li>`).join('')}</ul></article>`).join('');
document.getElementById('promotion').innerHTML=c.promotion_gate.required.map(x=>`<div class="gate-item"><span class="dot">✓</span><div><b>${x}</b></div></div>`).join('');
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));t.classList.add('active');document.getElementById(t.dataset.view).classList.add('active')});
</script>
</body></html>'''


if __name__ == "__main__":
    raise SystemExit(main())
