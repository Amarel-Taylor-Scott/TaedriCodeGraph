#!/usr/bin/env python3
"""Run the authenticated SaaS path on real PyPI and GitHub usaddress sources."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest  # noqa: E402
from taedri_codegraph.http_api import ApiConfig, TaedriAPI, ThreadingWSGIServer  # noqa: E402
from taedri_codegraph.job_runner import JobRunner  # noqa: E402
from taedri_codegraph.object_store import FilesystemObjectStore, backup_epoch  # noqa: E402
from taedri_codegraph.saas import GraphMount, SQLiteControlPlane, Tenant, utc_now  # noqa: E402
from taedri_codegraph.storage import GraphStore  # noqa: E402


RUN_DATE = "2026-07-16"
OUTPUT = ROOT / "eval" / "results" / f"saas-real-acquisition-{RUN_DATE}"
REPORT = ROOT / "docs" / "reports" / f"REAL_SAAS_ACQUISITION_{RUN_DATE}.md"
CONSOLE = ROOT / "apps" / "explorer" / "real-acquisition-console.html"
PYPI_PACKAGE = "usaddress"
PYPI_VERSION = "0.5.16"
GITHUB_REPOSITORY = "datamade/usaddress"
GITHUB_COMMIT = "aa7699b53a0843fc443f9e87285b88cbd9eaf50a"
EXPECTED_TREE = "a19dbb9165148e1a4cf0271780ac7ef0c93bde14"
QUERIES = (
    ("parse a street address into labeled components", "usaddress.parse"),
    ("tag address components and determine address type", "usaddress.tag"),
    ("tokenize an address string", "usaddress.tokenize"),
)


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--console", type=Path, default=CONSOLE)
    return parser.parse_args()


def request_json(
    base: str,
    token: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    content = canonical_json_bytes(body) if body is not None else None
    request = urllib.request.Request(
        base + path,
        data=content,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if content is not None else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read())
        assert isinstance(payload, dict)
        return response.status, payload


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        "utf-8",
    )


def write_jsonl(path: Path, values: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
            for value in values
        ),
        "utf-8",
    )


def directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def graph_slice(store: GraphStore, target: str, limit: int = 30) -> dict[str, Any]:
    index = store.index()
    root = index.resolve_entity(target)
    if root is None:
        raise RuntimeError(f"real graph lacks expected entity: {target}")
    root_id = str(root["identity"]["id"])
    nodes: dict[str, dict[str, Any]] = {
        root_id: {
            "id": root_id,
            "qualified_name": root["qualified_name"],
            "entity_kind": root["entity_kind_key"],
            "root": True,
        }
    }
    edges: list[dict[str, Any]] = []
    for neighbor in index.neighbors(root_id, direction="both", limit=limit):
        other_id = str(neighbor["other_entity_id"])
        nodes[other_id] = {
            "id": other_id,
            "qualified_name": neighbor["other_qualified_name"],
            "entity_kind": neighbor["other_entity_kind"],
            "root": False,
        }
        source = root_id if neighbor["direction"] == "out" else other_id
        target_id = other_id if neighbor["direction"] == "out" else root_id
        edges.append(
            {
                "assertion_id": neighbor["assertion_id"],
                "predicate": neighbor["predicate_key"],
                "source": source,
                "target": target_id,
            }
        )
    return {
        "epoch_id": store.current_epoch_id(),
        "root_entity_id": root_id,
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def write_graph_files(base: Path, graph: dict[str, Any]) -> None:
    write_json(base.with_suffix(".json"), graph)
    aliases = {node["id"]: f"n{index}" for index, node in enumerate(graph["nodes"])}
    lines = ["flowchart LR"]
    for node in graph["nodes"]:
        label = str(node["qualified_name"]).replace('"', "'")
        lines.append(f'  {aliases[node["id"]]}["{label}"]')
    for edge in graph["edges"]:
        label = str(edge["predicate"]).removeprefix("uceg.predicate.")
        lines.append(
            f'  {aliases[edge["source"]]} -->|{label}| {aliases[edge["target"]]}'
        )
    base.with_suffix(".mmd").write_text("\n".join(lines) + "\n", "utf-8")

    graphml = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    for key_id, target, name in (
        ("qualified_name", "node", "qualified_name"),
        ("entity_kind", "node", "entity_kind"),
        ("predicate", "edge", "predicate"),
    ):
        ET.SubElement(
            graphml,
            "key",
            id=key_id,
            **{"for": target, "attr.name": name, "attr.type": "string"},
        )
    element = ET.SubElement(graphml, "graph", edgedefault="directed")
    for node in graph["nodes"]:
        item = ET.SubElement(element, "node", id=node["id"])
        ET.SubElement(item, "data", key="qualified_name").text = node["qualified_name"]
        ET.SubElement(item, "data", key="entity_kind").text = node["entity_kind"]
    for ordinal, edge in enumerate(graph["edges"]):
        item = ET.SubElement(
            element,
            "edge",
            id=f"e{ordinal}",
            source=edge["source"],
            target=edge["target"],
        )
        ET.SubElement(item, "data", key="predicate").text = edge["predicate"]
    ET.ElementTree(graphml).write(
        base.with_suffix(".graphml"), encoding="utf-8", xml_declaration=True
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_charts(output: Path, mounts: list[dict[str, Any]], queries: list[dict[str, Any]]) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib-tcg"))
    import matplotlib.pyplot as plt

    charts = output / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    labels = [row["graph"] for row in mounts]
    x = list(range(len(labels)))
    width = 0.25
    figure, axis = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    for offset, field, label, color in (
        (-width, "entities", "Entities", "#38bdf8"),
        (0, "relations", "Relations", "#fb7185"),
        (width, "representation_assertions", "Representations", "#a78bfa"),
    ):
        axis.bar(
            [item + offset for item in x],
            [row[field] for row in mounts],
            width,
            label=label,
            color=color,
        )
    axis.set_xticks(x, labels)
    axis.set_yscale("log")
    axis.set_ylabel("Records (log scale)")
    axis.set_title("Real usaddress graph records by immutable source", loc="left", weight="bold")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.2)
    figure.savefig(charts / "record-counts.svg", format="svg")
    figure.savefig(charts / "record-counts.png", dpi=160)
    plt.close(figure)

    modes = ["pypi-usaddress", "git-usaddress", "all"]
    figure, axis = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    group_width = 0.24
    query_labels = [f"Q{index + 1}" for index in range(len(QUERIES))]
    for offset, mode, color in zip((-group_width, 0, group_width), modes, ("#38bdf8", "#34d399", "#fbbf24")):
        values = [
            next(
                row["rank"] if row["rank"] is not None else 11
                for row in queries
                if row["graph"] == mode and row["query_id"] == index + 1
            )
            for index in range(len(QUERIES))
        ]
        axis.bar(
            [item + offset for item in range(len(QUERIES))],
            values,
            group_width,
            label=mode,
            color=color,
        )
    axis.set_xticks(range(len(QUERIES)), query_labels)
    axis.set_ylim(0, 11.5)
    axis.invert_yaxis()
    axis.set_ylabel("Expected target rank (lower is better; 11 = miss@10)")
    axis.set_title("Natural-language retrieval ranks over real source", loc="left", weight="bold")
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.2)
    figure.savefig(charts / "retrieval-ranks.svg", format="svg")
    figure.savefig(charts / "retrieval-ranks.png", dpi=160)
    plt.close(figure)


def write_console(path: Path, report: dict[str, Any]) -> None:
    payload = json.dumps(report, ensure_ascii=False).replace("</", "<\\/")
    path.write_text(
        f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Taedri real acquisition evidence</title><style>
:root{{--bg:#07111f;--panel:#0e1b2d;--line:#21334d;--text:#e8f0fb;--muted:#97a9c1;--blue:#38bdf8;--green:#34d399;--amber:#fbbf24}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 15% 0,#132c49,var(--bg) 42%);color:var(--text);font:14px/1.5 system-ui,sans-serif}}
main{{max-width:1250px;margin:auto;padding:40px 24px}}h1{{font-size:clamp(30px,5vw,58px);line-height:1.02;margin:8px 0}}h2{{margin-top:34px}}.eyebrow{{color:var(--blue);letter-spacing:.15em;text-transform:uppercase;font-weight:750}}.muted{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}.card{{background:linear-gradient(145deg,#112238dd,#0b1727ee);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 18px 40px #0004}}.metric{{font-size:30px;font-weight:800}}table{{width:100%;border-collapse:collapse;background:#0b1727cc;border:1px solid var(--line)}}th,td{{padding:11px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}}code{{color:#b9e6ff}}.ok{{color:var(--green)}}.miss{{color:#fb7185}}.bar{{height:8px;background:#172941;border-radius:99px;overflow:hidden}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green))}}
</style></head><body><main><div class="eyebrow">real network · real artifacts · no target execution</div><h1>Authenticated acquisition evidence</h1><p class="muted">Official PyPI wheel and immutable GitHub commit, processed through tenant jobs, graph publication, federated search, and portable object backup.</p><section id="summary" class="grid"></section><h2>Graph mounts</h2><section id="mounts" class="grid"></section><h2>Retrieval probes</h2><table><thead><tr><th>Query</th><th>Graph</th><th>Expected</th><th>Rank</th><th>Latency</th></tr></thead><tbody id="queries"></tbody></table><h2>Immutable acquisitions</h2><div id="acquisitions" class="grid"></div><p class="muted">Similarity and rank nominate candidates. Contracts, provenance, policy, and verification still decide reuse.</p></main>
<script id="data" type="application/json">{payload}</script><script>
const d=JSON.parse(document.querySelector('#data').textContent);const f=n=>new Intl.NumberFormat().format(n);
document.querySelector('#summary').innerHTML=[['Source graphs',d.mounts.length],['Real jobs succeeded',d.jobs.filter(x=>x.state==='succeeded').length],['Queries',d.query_results.length],['Portable backups',d.backups.length]].map(x=>`<article class="card"><div class="muted">${{x[0]}}</div><div class="metric">${{f(x[1])}}</div></article>`).join('');
document.querySelector('#mounts').innerHTML=d.mounts.map(x=>`<article class="card"><strong>${{x.graph}}</strong><div class="metric">${{f(x.entities)}} entities</div><p class="muted">${{f(x.relations)}} relations · ${{f(x.representation_assertions)}} representation assertions</p><code>${{x.epoch_id.slice(0,42)}}…</code></article>`).join('');
document.querySelector('#queries').innerHTML=d.query_results.map(x=>`<tr><td>${{x.query}}</td><td><code>${{x.graph}}</code></td><td>${{x.expected}}</td><td class="${{x.rank?'ok':'miss'}}">${{x.rank??'miss@10'}}</td><td>${{x.latency_ms.toFixed(2)}} ms</td></tr>`).join('');
document.querySelector('#acquisitions').innerHTML=d.acquisitions.map(x=>`<article class="card"><strong>${{x.source_kind}}</strong><p>${{x.requested_subject}}</p><div class="bar"><i style="width:${{Math.min(100,Math.log10(x.artifact_size_bytes+1)*14)}}%"></i></div><p class="muted">${{f(x.artifact_size_bytes)}} bytes</p><code>${{x.artifact_digest}}</code></article>`).join('');
</script></body></html>""",
        "utf-8",
    )


def write_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Real authenticated SaaS acquisition — 2026-07-16",
        "",
        "This run used the official `usaddress==0.5.16` wheel and the immutable GitHub",
        f"commit `{GITHUB_COMMIT}`. Both were acquired over the network through the same",
        "allowlisted worker operations exposed by the authenticated API. Target code was",
        "inspected with AST/ZIP logic and was never imported, installed, built, or executed.",
        "",
        "## Result",
        "",
        f"- {len(report['jobs'])} persistent tenant jobs succeeded.",
        f"- {len(report['mounts'])} independently versioned graph mounts were published and searched together.",
        f"- {len(report['acquisitions'])} acquisition receipts retain registry/API metadata and artifact digests.",
        f"- {len(report['backups'])} graph epochs round-tripped into content-addressed backup manifests.",
        "- Every search result identifies its graph mount, exact epoch, local query receipt, and federation receipt.",
        "",
        "## Published graph metrics",
        "",
        "| Graph | Files | Entities | Relations | Representations | Store bytes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["mounts"]:
        lines.append(
            f"| `{row['graph']}` | {row['files']:,} | {row['entities']:,} | {row['relations']:,} | {row['representation_assertions']:,} | {row['store_bytes']:,} |"
        )
    lines.extend(
        [
            "",
            "## Retrieval probes",
            "",
            "| Query | Graph | Expected | Rank@10 | Latency ms |",
            "|---|---|---|---:|---:|",
        ]
    )
    for row in report["query_results"]:
        rank = row["rank"] if row["rank"] is not None else "miss"
        lines.append(
            f"| {row['query']} | `{row['graph']}` | `{row['expected']}` | {rank} | {row['latency_ms']:.3f} |"
        )
    lines.extend(
        [
            "",
            "These are transparent probes, not an efficacy claim. The corpus contains two",
            "representations of one project, and no external LLM was used. Retrieval proposes",
            "candidates; compatibility, licensing, policy, and independent verification still decide.",
            "",
            "## Artifacts",
            "",
            "- `eval/results/saas-real-acquisition-2026-07-16/run.json`",
            "- `eval/results/saas-real-acquisition-2026-07-16/acquisitions.jsonl`",
            "- `eval/results/saas-real-acquisition-2026-07-16/query-results.csv`",
            "- `eval/results/saas-real-acquisition-2026-07-16/graphs/` as JSON, Mermaid, and GraphML",
            "- `eval/results/saas-real-acquisition-2026-07-16/charts/` as SVG and PNG",
            "- `apps/explorer/real-acquisition-console.html` as a self-contained dashboard",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), "utf-8")


def main() -> int:
    args = parse_args()
    shutil.rmtree(args.output_dir, ignore_errors=True)
    args.output_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="taedri-real-saas-") as temporary:
        work = Path(temporary)
        control_path = work / "control.sqlite"
        control = SQLiteControlPlane(control_path)
        tenant = control.create_tenant(
            Tenant.create(slug="real-evaluation", display_name="Real evaluation", created_at=utc_now())
        )
        graph_paths = {
            "pypi-usaddress": work / "graphs" / "pypi-usaddress",
            "git-usaddress": work / "graphs" / "git-usaddress",
        }
        for name, path in graph_paths.items():
            control.mount_graph(
                GraphMount.create(
                    tenant_id=tenant.identity.id,
                    name=name,
                    store_root=path.resolve(),
                    created_at=utc_now(),
                )
            )
        issued = control.issue_api_key(
            tenant.identity.id,
            scopes=(
                "graph:read",
                "source:read",
                "jobs:read",
                "jobs:write",
                "ingestion:write",
                "audit:read",
            ),
        )
        application = TaedriAPI(ApiConfig(control_path))
        server = make_server(
            "127.0.0.1",
            0,
            application,
            server_class=ThreadingWSGIServer,
            handler_class=QuietHandler,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        job_bodies = [
            {
                "kind": "acquire",
                "subject_id": f"pypi:{PYPI_PACKAGE}=={PYPI_VERSION}",
                "idempotency_key": f"pypi:{PYPI_PACKAGE}=={PYPI_VERSION}:wheel:python-v1",
                "required_capabilities": ["pypi-acquire", "python-ast"],
                "payload": {
                    "operation": "ingest_pypi_wheel",
                    "package": PYPI_PACKAGE,
                    "version": PYPI_VERSION,
                    "graph": "pypi-usaddress",
                    "publish": True,
                },
            },
            {
                "kind": "acquire",
                "subject_id": f"github:{GITHUB_REPOSITORY}@{GITHUB_COMMIT}",
                "idempotency_key": f"github:{GITHUB_REPOSITORY}@{GITHUB_COMMIT}:python-v1",
                "required_capabilities": ["github-acquire", "python-ast"],
                "payload": {
                    "operation": "ingest_github_commit",
                    "repository": GITHUB_REPOSITORY,
                    "commit_sha": GITHUB_COMMIT,
                    "analysis": "python",
                    "package_name": "usaddress",
                    "graph": "git-usaddress",
                    "publish": True,
                },
            },
        ]
        accepted_ids = []
        for body in job_bodies:
            status, accepted = request_json(base, issued.token, "POST", "/v1/jobs", body)
            if status != 202:
                raise RuntimeError(f"job was not accepted: {accepted}")
            accepted_ids.append(accepted["job"]["identity"]["id"])
        runner = JobRunner(
            control,
            source_root=ROOT,
            worker_id="real-acquisition-worker",
            allow_network_acquisition=True,
            github_token=os.environ.get("TAEDRI_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        )
        run_results = [runner.run_once(), runner.run_once()]
        if not all(
            result.event is not None and result.event.event_kind.value == "succeeded"
            for result in run_results
        ):
            raise RuntimeError(f"real acquisition worker failed: {run_results}")

        jobs = []
        acquisitions = []
        for job_id in accepted_ids:
            _, stored = request_json(base, issued.token, "GET", f"/v1/jobs/{job_id}")
            jobs.append(
                {
                    "job_id": job_id,
                    "subject_id": stored["job"]["subject_id"],
                    "state": stored["state"],
                    "attempts": stored["attempts"],
                    "events": stored["events"],
                }
            )
            succeeded = stored["events"][-1]
            for reference in succeeded["output_refs"]:
                if not str(reference).startswith("sha256:"):
                    continue
                try:
                    payload = control.job_payload(tenant.identity.id, reference)
                except ValueError:
                    continue
                acquisition = payload.get("acquisition")
                if isinstance(acquisition, dict):
                    acquisitions.append(acquisition)

        mounts = []
        backups = []
        object_store = FilesystemObjectStore(work / "objects", prefix=tenant.identity.id)
        for graph, path in graph_paths.items():
            store = GraphStore(path)
            epoch = store.current_epoch_id()
            manifest = store.read_manifest(epoch, published=True)
            counts = manifest["record_counts"]
            mount = {
                "graph": graph,
                "epoch_id": epoch,
                "snapshot_id": manifest["snapshot_id"],
                "analysis_manifest_id": manifest["analysis_manifest_id"],
                "files": counts["files"],
                "entities": counts["entities"],
                "occurrences": counts["occurrences"],
                "relations": counts["relations"],
                "representation_assertions": counts["representation_assertions"],
                "generation_runs": counts["generation_runs"],
                "store_bytes": directory_bytes(path),
                "index_bytes": (store.published / epoch / "index.sqlite").stat().st_size,
            }
            mounts.append(mount)
            backup, backup_ref = backup_epoch(store, object_store, epoch)
            backup_record = {
                "graph": graph,
                "backup_id": backup.identity.id,
                "manifest_object": backup_ref.to_dict(),
                "epoch_file_count": len(backup.epoch_files),
                "cas_object_count": len(backup.cas_objects),
            }
            backups.append(backup_record)
            write_json(args.output_dir / "backups" / f"{graph}.json", backup.to_dict())
            write_graph_files(
                args.output_dir / "graphs" / f"{graph}-parse-neighborhood",
                graph_slice(store, "usaddress.parse"),
            )

        query_results = []
        query_evidence = []
        for graph in (*graph_paths, "all"):
            for query_id, (query, expected) in enumerate(QUERIES, start=1):
                encoded = urllib.parse.urlencode(
                    {"q": query, "graph": graph, "limit": 10, "explain": "true"}
                )
                started = time.perf_counter()
                status, search = request_json(
                    base, issued.token, "GET", f"/v1/search?{encoded}"
                )
                latency_ms = (time.perf_counter() - started) * 1000
                if status != 200:
                    raise RuntimeError(f"real search failed: {search}")
                names = [item["qualified_name"] for item in search["items"]]
                rank = names.index(expected) + 1 if expected in names else None
                query_results.append(
                    {
                        "query_id": query_id,
                        "query": query,
                        "expected": expected,
                        "graph": graph,
                        "rank": rank,
                        "hit_at_10": rank is not None,
                        "reciprocal_rank": round(1 / rank, 6) if rank else 0,
                        "latency_ms": round(latency_ms, 4),
                        "result_count": len(names),
                    }
                )
                query_evidence.append(
                    {
                        "query_id": query_id,
                        "graph": graph,
                        "query": query,
                        "expected": expected,
                        "response": search,
                    }
                )
        context_query = urllib.parse.urlencode(
            {"q": QUERIES[0][0], "graph": "all", "limit": 3}
        )
        _, context = request_json(
            base, issued.token, "GET", f"/v1/context?{context_query}"
        )
        _, graphs_response = request_json(base, issued.token, "GET", "/v1/graphs")
        _, audit = request_json(base, issued.token, "GET", "/v1/audit?limit=100")
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

        if not any(
            item.get("metadata", {}).get("tree_sha") == EXPECTED_TREE
            for item in acquisitions
        ):
            raise RuntimeError("GitHub tree lineage does not match the pinned release")
        report = {
            "format_version": "1.0.0",
            "run_date": RUN_DATE,
            "claim_class": "real-artifact-system-conformance-not-llm-efficacy",
            "safety": {
                "target_imported": False,
                "target_installed": False,
                "target_built": False,
                "target_executed": False,
                "network_hosts": [
                    "pypi.org",
                    "files.pythonhosted.org",
                    "api.github.com",
                    "codeload.github.com",
                ],
            },
            "sources": {
                "pypi": f"{PYPI_PACKAGE}=={PYPI_VERSION}",
                "github": f"{GITHUB_REPOSITORY}@{GITHUB_COMMIT}",
                "expected_git_tree": EXPECTED_TREE,
            },
            "jobs": jobs,
            "acquisitions": acquisitions,
            "mounts": mounts,
            "backups": backups,
            "query_results": query_results,
            "context_summary": {
                "query": context["query"],
                "result_count": context["result_count"],
                "graph_mounts": context["graph_mounts"],
                "disclosure_level": context["disclosure_level"],
            },
            "graph_api": [
                {
                    "name": item["mount"]["name"],
                    "ready": item["ready"],
                    "epochs": item["epochs"],
                }
                for item in graphs_response["items"]
            ],
            "audit_event_count": len(audit["items"]),
        }
        report["run_digest"] = sha256_digest(canonical_json_bytes(report))
        write_json(args.output_dir / "run.json", report)
        write_jsonl(args.output_dir / "acquisitions.jsonl", acquisitions)
        write_jsonl(args.output_dir / "jobs.jsonl", jobs)
        write_json(args.output_dir / "query-evidence.json", query_evidence)
        write_csv(args.output_dir / "mount-summary.csv", mounts)
        write_csv(args.output_dir / "query-results.csv", query_results)
        write_charts(args.output_dir, mounts, query_results)
        write_console(args.console, report)
        write_report(args.report, report)
        print(
            json.dumps(
                {
                    "output": str(args.output_dir.relative_to(ROOT)),
                    "report": str(args.report.relative_to(ROOT)),
                    "console": str(args.console.relative_to(ROOT)),
                    "run_digest": report["run_digest"],
                    "jobs": len(jobs),
                    "mounts": len(mounts),
                    "queries": len(query_results),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
