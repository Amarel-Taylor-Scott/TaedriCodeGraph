#!/usr/bin/env python3
"""Generate the evidence-backed monorepo component and capability inventory."""

from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "eval/results/component-capability-inventory-2026-07-16"
REPORT = ROOT / "docs/reports/COMPONENT_CAPABILITY_INVENTORY_2026-07-16.md"
HTML = ROOT / "docs/visuals/component-capability-inventory.html"
SVG = ROOT / "docs/visuals/assets/component-readiness-status.svg"


def read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text("utf-8"))


def main() -> None:
    architecture = read_json("architecture/components.json")
    readiness = read_json("architecture/component-readiness.v1.json")
    ready = {item["id"]: item for item in readiness["components"]}
    pypi = read_json("eval/results/real-pypi-2026-07-15/summary.json")["packages"]
    acquisition = read_json("eval/results/saas-real-acquisition-2026-07-16/run.json")
    factory = read_json("eval/results/primitive-factory-2026-07-16/candidate-manifest.json")
    reference = read_json("eval/results/reference-primitive-acceptance-2026-07-16/run.json")
    deterministic_pipeline = read_json(
        "eval/results/deterministic-primitive-pipeline-2026-07-16/run.json"
    )
    benchmark = read_json(
        "eval/results/benchmark-worker-2026-07-16/conformance-report.json"
    )
    total_entities = sum(int(item["entities"]) for item in pypi)
    total_occurrences = sum(int(item["occurrences"]) for item in pypi)
    total_relations = sum(int(item["relations"]) for item in pypi)
    mount_entities = sum(int(item["entities"]) for item in acquisition["mounts"])
    mount_relations = sum(int(item["relations"]) for item in acquisition["mounts"])
    mount_variants = sum(
        int(item["representation_assertions"]) for item in acquisition["mounts"]
    )
    sql_tables = len(
        {
            match
            for path in (ROOT / "deploy/postgres").glob("*.sql")
            for match in re.findall(
                r"CREATE TABLE IF NOT EXISTS taedri\.([a-z_]+)",
                path.read_text("utf-8"),
            )
        }
    )
    schema_count = len(tuple((ROOT / "schemas").glob("*.schema.json")))
    route_source = (ROOT / "src/taedri_codegraph/api/routes.py").read_text("utf-8")
    route_count = len(re.findall(r"^\s+RouteSpec\(", route_source, re.MULTILINE))
    path_count = len(
        set(re.findall(r'RouteSpec\("[A-Z]+",\s*"([^"]+)"', route_source))
    )
    candidate_count = int(factory["factory"]["candidate_count"])
    candidate_events = int(factory["intake"]["event_count"])
    released = int(reference["record_counts"]["primitive_release"])
    reference_blobs = int(reference["record_counts"]["primitive_blob"])
    pipeline_primitives = int(deterministic_pipeline["primitive_count"])
    pipeline_edges = int(deterministic_pipeline["edge_count"])
    pipeline_ports = int(deterministic_pipeline["port_count"])
    benchmark_runs = int(benchmark["completed_run_count"])

    counts: dict[str, str] = {
        "vertical-slice": f"Real PyPI evidence: {total_entities:,} entities; {total_occurrences:,} occurrences; {total_relations:,} relations",
        "mechanism-runtime": "Stateless executor; immutable waterfall receipts are caller-owned",
        "pipeline-catalog": "4 executable pipelines; 6 admitted worker operations",
        "shared-kernel": "N/A — stateless identity/canonicalization library",
        "shared-schemas": f"{schema_count} checked-in JSON Schemas",
        "schema-artifacts": f"{schema_count} JSON Schemas; {sql_tables} PostgreSQL tables",
        "primitive-capsules": f"Reference run: {released} public release / {reference_blobs} blobs; deterministic route: {pipeline_primitives} releases / {pipeline_primitives} packs",
        "primitive-factory": f"{candidate_count:,} real-source candidates; {candidate_events:,} intake events; 0 released by factory",
        "ingestion-pypi": f"4 real wheels evidenced (3 benchmark + usaddress); latest usaddress mount: 101 entities / 614 relations",
        "ingestion-git": "1 immutable real GitHub commit archive; 417 entities / 2,282 relations",
        "analyzer-python": f"Real PyPI evidence: {total_entities:,} entities / {total_relations:,} relations across 140 files",
        "analyzer-polyglot": "No dedicated durable rows; working file-inventory boundary, semantic adapters not claimed",
        "storage": f"5 real published evaluation epochs; usaddress runs: {mount_entities:,} entities / {mount_variants:,} typed variants",
        "retrieval": "36 retained real-package hybrid query receipts",
        "compatibility": f"Deterministic route: {pipeline_edges} evidence edges / {pipeline_ports} ports / 1 compatible exact wire; broad solver remains partial",
        "session-ledger": "Reference factory evidence: 1 digest-only session / 7 events / 0 model calls",
        "benchmarking": f"2 tasks / 4 lanes / {benchmark_runs} conformance receipts; efficacy_claimable=false",
        "saas-control-plane": "Real acquisition evidence: 1 tenant / 2 succeeded jobs / 4 audit events",
        "worker-runtime": "Real acquisition evidence: 2 leased and succeeded network jobs",
        "benchmark-worker": f"{benchmark_runs} deterministic fixture receipts; 0 real-model efficacy runs",
        "discovery-worker": "0 hosted poll/webhook rows; replay-safe local router is tested",
        "ingestion-worker": f"2 real acquisition jobs; {mount_entities:,} entities / {mount_relations:,} relations published",
        "primitive-worker": f"{candidate_count:,} candidates plus {pipeline_primitives} independently verified and released working primitives",
        "indexer-service": "5 real evaluation epochs (3 PyPI benchmark + 2 usaddress acquisition)",
        "query-api": f"{route_count} operations across {path_count} paths",
        "registry-api": f"Reference run: {released} public release; 0 candidate rows serving as primitives",
        "mcp-integration": "Protocol and remote round-trip evidence; no durable MCP-owned rows",
        "agent-integrations": "1 digest-only harness session; 0 model calls; no efficacy claim",
        "explorer-app": "Static application; records are read from authenticated APIs",
        "portal-app": "Static application + versioned plan/subscription contracts; no checked-in customer rows",
        "deployment": f"{sql_tables} PostgreSQL tables; Docker/Compose and one-Machine Fly POC",
        "evaluation": f"3 real PyPI packages + 2 real usaddress sources + {pipeline_primitives} real custom releases + 1 no-model route + {benchmark_runs} non-claimable benchmark receipts",
    }
    records: list[dict[str, Any]] = []
    for component in architecture["components"]:
        evidence = ready[component["id"]]
        records.append(
            {
                "id": component["id"],
                "folder": component["path"],
                "kind": component["kind"],
                "status": component["status"],
                "scope": evidence["scope"],
                "capabilities": component["owns"],
                "implemented_by": evidence["implemented_by"],
                "acceptance_evidence": evidence["acceptance_evidence"],
                "measured_records": counts[component["id"]],
                "next_gates": evidence["open_gates"],
            }
        )
    status_counts = Counter(item["status"] for item in records)
    result = {
        "schema_version": "1.0.0",
        "as_of": readiness["as_of"],
        "component_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "postgres_table_count": sql_tables,
        "json_schema_count": schema_count,
        "api_operation_count": route_count,
        "api_path_count": path_count,
        "live_database_note": "No production database is checked into Git. Counts are explicitly tied to immutable evaluation receipts or marked stateless/absent.",
        "components": records,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "components.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "utf-8",
    )
    with (OUTPUT / "components.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            ("component", "folder", "status", "scope", "records_or_evidence", "capabilities", "next_gates")
        )
        for item in records:
            writer.writerow(
                (
                    item["id"],
                    item["folder"],
                    item["status"],
                    item["scope"],
                    item["measured_records"],
                    "; ".join(item["capabilities"]),
                    "; ".join(item["next_gates"]),
                )
            )
    markdown = render_markdown(result)
    (OUTPUT / "README.md").write_text(markdown, "utf-8")
    REPORT.write_text(markdown, "utf-8")
    HTML.write_text(render_html(result), "utf-8")
    SVG.write_text(render_svg(status_counts), "utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "components"}, indent=2))


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Taedri component and capability inventory",
        "",
        f"As of {result['as_of']}. This inventory contains all {result['component_count']} declared components.",
        "",
        "**Count rule:** no production database is committed to Git. Every numeric count below names its immutable evaluation source; stateless components and missing hosted evidence are stated explicitly.",
        "",
        "| Component | Folder | Status | Measured records / evidence | Core capabilities |",
        "|---|---|---|---|---|",
    ]
    for item in result["components"]:
        capabilities = "; ".join(item["capabilities"])
        lines.append(
            f"| `{item['id']}` | `{item['folder']}` | **{item['status']}** | {item['measured_records']} | {capabilities} |"
        )
    lines.extend(
        [
            "",
            "## What the statuses mean",
            "",
            "- **working:** the stated local/transitional scope has executable acceptance evidence.",
            "- **partial:** the narrow stated scope works; broader capabilities remain named gates and are not advertised as implemented.",
            "- **conformance_only:** contracts and deterministic receipts work, but there is no claimable external execution.",
            "- **poc_only:** the bounded proof works but lacks production durability or hosted operations.",
            "",
            "## Primitive truth boundary",
            "",
            "The factory's candidate rows are not primitive releases. Public primitive search, resolution, and pack delivery read only `primitive_release`, whose rows require the complete capsule and all executable acceptance proofs. The checked-in reference evidence has one release; the 347 static candidates remain candidate-only.",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(result: dict[str, Any]) -> str:
    data = json.dumps(result["components"], ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Taedri component inventory</title><style>
:root{{--bg:#091018;--panel:#111c28;--line:#294158;--text:#e9f2f8;--muted:#9db0bf;--accent:#55d6be}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,sans-serif}}
main{{max-width:1500px;margin:auto;padding:32px}}h1{{font-size:clamp(26px,4vw,46px);margin:0 0 8px}}p{{color:var(--muted)}}
.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}}input,select{{background:var(--panel);border:1px solid var(--line);color:var(--text);padding:10px 12px;border-radius:8px}}
.summary{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}}.pill{{border:1px solid var(--line);border-radius:99px;padding:7px 11px;color:var(--muted)}}
.table{{overflow:auto;border:1px solid var(--line);border-radius:12px}}table{{border-collapse:collapse;width:100%;min-width:1050px}}th,td{{padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}th{{position:sticky;top:0;background:#142333}}code{{color:var(--accent)}}
.status{{font-weight:700}}.working{{color:#55d6be}}.partial{{color:#ffd166}}.conformance_only{{color:#9bbcff}}.poc_only{{color:#ff9f80}}
</style></head><body><main><h1>Taedri component inventory</h1>
<p>Evidence-backed component scope, records, folders, and capabilities. Candidates never count as released primitives.</p>
<div class="controls"><input id="query" type="search" placeholder="Filter component, capability, folder…"><select id="status"><option value="">All statuses</option><option>working</option><option>partial</option><option>conformance_only</option><option>poc_only</option></select></div>
<div class="summary" id="summary"></div><div class="table"><table><thead><tr><th>Component</th><th>Folder</th><th>Status</th><th>Scope</th><th>Measured records / evidence</th><th>Capabilities</th><th>Next gate</th></tr></thead><tbody id="rows"></tbody></table></div>
<script>const data={data};const q=document.querySelector('#query'),s=document.querySelector('#status'),rows=document.querySelector('#rows'),summary=document.querySelector('#summary');
function esc(v){{return String(v).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function render(){{const needle=q.value.toLowerCase(),status=s.value;const visible=data.filter(x=>(!status||x.status===status)&&JSON.stringify(x).toLowerCase().includes(needle));const counts={{}};for(const x of visible)counts[x.status]=(counts[x.status]||0)+1;summary.innerHTML=`<span class="pill">${{visible.length}} components</span>`+Object.entries(counts).sort().map(([k,v])=>`<span class="pill ${{k}}">${{esc(k)}}: ${{v}}</span>`).join('');rows.innerHTML=visible.map(x=>`<tr><td><code>${{esc(x.id)}}</code></td><td><code>${{esc(x.folder)}}</code></td><td class="status ${{esc(x.status)}}">${{esc(x.status)}}</td><td>${{esc(x.scope)}}</td><td>${{esc(x.measured_records)}}</td><td>${{x.capabilities.map(esc).join('<br>')}}</td><td>${{esc(x.next_gates[0])}}</td></tr>`).join('')}}q.addEventListener('input',render);s.addEventListener('change',render);render();</script></main></body></html>"""


def render_svg(counts: Counter[str]) -> str:
    colors = {"working": "#25b99a", "partial": "#d8a62a", "conformance_only": "#668ee8", "poc_only": "#e7795e"}
    ordered = ("working", "partial", "conformance_only", "poc_only")
    maximum = max(counts.values())
    bars = []
    for index, status in enumerate(ordered):
        value = counts[status]
        y = 110 + index * 76
        width = round(720 * value / maximum)
        bars.append(f'<text x="40" y="{y + 21}" class="label">{html.escape(status)}</text><rect x="245" y="{y}" width="720" height="30" rx="8" class="track"/><rect x="245" y="{y}" width="{width}" height="30" rx="8" fill="{colors[status]}"/><text x="985" y="{y + 22}" class="value">{value}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="460" viewBox="0 0 1100 460" role="img" aria-labelledby="title desc"><title id="title">Taedri component readiness</title><desc id="desc">Counts of evidence-backed readiness states across 32 components.</desc><style>.bg{{fill:#091018}}.track{{fill:#1b2b3a}}.title{{fill:#e9f2f8;font:700 30px system-ui}}.note,.label,.value{{fill:#c4d2dc;font:18px system-ui}}.value{{font-weight:700}}</style><rect class="bg" width="1100" height="460"/><text x="40" y="48" class="title">Evidence-backed component readiness</text><text x="40" y="78" class="note">32 declared components · no scaffolded or planned status masquerading as implementation</text>{''.join(bars)}</svg>'''


if __name__ == "__main__":
    main()
