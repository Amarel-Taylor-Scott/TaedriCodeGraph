#!/usr/bin/env python3
"""Generate the evidence-backed monorepo component and capability inventory."""

from __future__ import annotations

import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "eval/results/component-capability-inventory-2026-07-16"
REPORT = ROOT / "docs/reports/COMPONENT_CAPABILITY_INVENTORY_2026-07-16.md"
HTML = ROOT / "docs/visuals/component-capability-inventory.html"
SVG = ROOT / "docs/visuals/assets/component-readiness-status.svg"
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.prompt_interception import (  # noqa: E402
    PromptInterceptionError,
    validate_prompt_interception_campaign_document,
)


def read_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text("utf-8"))


def _task_fixture_counts(path: str) -> tuple[int, int]:
    document = read_json(path)
    tasks = document.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError(f"{path} has no task list")
    case_count = 0
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not isinstance(task.get("hidden_cases"), list):
            raise ValueError(f"{path} task {index} has no hidden cases")
        case_count += len(task["hidden_cases"])
    return len(tasks), case_count


def _campaign_evidence() -> dict[str, Any]:
    """Validate and count every checked-in live prompt-interception campaign.

    These are observation counts, not a savings claim.  Strict campaign-v2 receipt
    validation proves serialization integrity and matrix completeness; trusted runtime
    attestation and complete overhead accounting remain separate token-proof gates.
    """

    files = sorted(
        (ROOT / "eval/results").glob(
            "prompt-interception-live-*/*.campaign.json"
        )
    )
    versions: Counter[str] = Counter()
    provider_models: set[tuple[str, str]] = set()
    shortlist_limits: set[int] = set()
    def empty_observation_counts() -> dict[str, int]:
        return {
            "campaign_count": 0,
            "provider_call_attempt_count": 0,
            "provider_response_usage_count": 0,
            "matched_pair_observation_count": 0,
            "accepted_provider_response_count": 0,
            "case_execution_observation_count": 0,
            "passed_case_execution_observation_count": 0,
            "usage_complete_pair_count": 0,
            "all_descriptions_reported_tokens": 0,
            "locally_selected_descriptions_reported_tokens": 0,
        }

    totals = empty_observation_counts()
    by_format: dict[str, dict[str, int]] = {}
    for path in files:
        try:
            document = json.loads(path.read_text("utf-8"))
            validation = validate_prompt_interception_campaign_document(document)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, PromptInterceptionError) as exc:
            raise ValueError(f"campaign evidence failed strict validation: {path}: {exc}") from exc
        versions[validation.format_version] += 1
        format_counts = by_format.setdefault(
            validation.format_version, empty_observation_counts()
        )
        format_counts["campaign_count"] += 1
        totals["campaign_count"] += 1
        provider_models.add((str(document["provider_id"]), str(document["model_requested"])))
        shortlist_limits.add(int(document["shortlist_limit"]))
        arms = document["arms"]
        pairs = document["matched_pairs"]
        for counts in (totals, format_counts):
            counts["provider_call_attempt_count"] += len(arms)
            counts["matched_pair_observation_count"] += len(pairs)
            counts["accepted_provider_response_count"] += sum(
                arm.get("status") == "accepted" for arm in arms
            )
        for arm in arms:
            verification = arm.get("verification")
            if isinstance(verification, dict):
                for counts in (totals, format_counts):
                    counts["case_execution_observation_count"] += int(
                        verification["executed_case_count"]
                    )
                    counts["passed_case_execution_observation_count"] += int(
                        verification["passed_case_count"]
                    )
        for pair in pairs:
            full = pair.get("full_catalog_usage")
            selected = pair.get("shortlist_usage")
            response_count = int(isinstance(full, dict)) + int(
                isinstance(selected, dict)
            )
            totals["provider_response_usage_count"] += response_count
            format_counts["provider_response_usage_count"] += response_count
            if not isinstance(full, dict) or not isinstance(selected, dict):
                continue
            full_tokens = int(full["prompt_tokens"]) + int(full["completion_tokens"])
            selected_tokens = int(selected["prompt_tokens"]) + int(
                selected["completion_tokens"]
            )
            for counts in (totals, format_counts):
                counts["usage_complete_pair_count"] += 1
                counts["all_descriptions_reported_tokens"] += full_tokens
                counts["locally_selected_descriptions_reported_tokens"] += selected_tokens
    # Campaign summaries deliberately cannot promote themselves into proof.  The
    # current repository has no trusted isolated-runtime attestation plus complete
    # overhead ledger, so its live campaigns remain non-claimable observations.
    claimable = False
    all_descriptions_tokens = totals["all_descriptions_reported_tokens"]
    locally_selected_tokens = totals[
        "locally_selected_descriptions_reported_tokens"
    ]
    delta = all_descriptions_tokens - locally_selected_tokens
    delta_ppm = (
        delta * 1_000_000 // all_descriptions_tokens
        if all_descriptions_tokens
        else None
    )
    return {
        **totals,
        "campaign_format_counts": dict(sorted(versions.items())),
        "observations_by_campaign_format": {
            key: by_format[key] for key in sorted(by_format)
        },
        "strict_v2_campaign_count": versions["2.0.0"],
        "legacy_v1_campaign_count": versions["1.0.0"],
        "provider_model_count": len(provider_models),
        "provider_models": [
            {"provider_id": provider, "model_requested": model}
            for provider, model in sorted(provider_models)
        ],
        "shortlist_limits": sorted(shortlist_limits),
        "observed_reported_token_delta": delta,
        "observed_reported_token_delta_ppm": delta_ppm,
        "claimable_token_savings": claimable,
        "claim_boundary": (
            "Campaign validation and provider-response counters are observation evidence. "
            "A correctness-preserving savings claim additionally requires trusted isolated "
            "runtime evidence and complete failure-inclusive overhead receipts."
        ),
    }


def main() -> None:
    architecture = read_json("architecture/components.json")
    readiness = read_json("architecture/component-readiness.v1.json")
    architecture_product = architecture.get("product_readiness")
    readiness_product = readiness.get("product_readiness")
    if not isinstance(architecture_product, dict) or not isinstance(
        readiness_product, dict
    ):
        raise ValueError("both architecture manifests must declare product_readiness")
    for field in ("classification", "serves_truth", "public_paid_saas_ready"):
        if architecture_product.get(field) != readiness_product.get(field):
            raise ValueError(f"product readiness manifests disagree on {field}")
    ready = {item["id"]: item for item in readiness["components"]}
    pypi = read_json("eval/results/real-pypi-2026-07-15/summary.json")["packages"]
    acquisition = read_json("eval/results/saas-real-acquisition-2026-07-16/run.json")
    factory = read_json("eval/results/primitive-factory-2026-07-16/candidate-manifest.json")
    data_cohort = read_json(
        "eval/results/data-primitive-cohort-2026-07-16/run.json"
    )
    retrieval_program = read_json(
        "eval/results/primitive-retrieval-program-2026-07-17/run.json"
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
    released = int(data_cohort["primitive_count"])
    release_blobs = int(data_cohort["database_record_counts"]["primitive_blob"])
    pipeline_edges = int(data_cohort["compatibility_edge_count"])
    evidence_edges = int(data_cohort["evidence_edge_count"])
    pipeline_ports = int(data_cohort["typed_port_count"])
    primitive_route_count = sum(
        key in data_cohort
        for key in ("text_route", "numeric_route", "datetime_route", "null_route")
    )
    benchmark_runs = int(benchmark["completed_run_count"])
    natural_task_count, natural_case_count = _task_fixture_counts(
        "fixtures/prompt-interception/natural-tasks.json"
    )
    external_task_count, external_case_count = _task_fixture_counts(
        "fixtures/prompt-interception/external-github-issues-positive-v1.json"
    )
    campaigns = _campaign_evidence()
    strict_observations = campaigns["observations_by_campaign_format"]["2.0.0"]
    legacy_observations = campaigns["observations_by_campaign_format"]["1.0.0"]
    live_campaign_summary = (
        f"{campaigns['campaign_count']} checked live campaign documents "
        f"({campaigns['strict_v2_campaign_count']} strict v2; "
        f"{campaigns['legacy_v1_campaign_count']} legacy non-claimable v1); "
        f"{campaigns['provider_call_attempt_count']} provider-call attempts / "
        f"{campaigns['matched_pair_observation_count']} matched-pair observations / "
        f"{campaigns['case_execution_observation_count']} case-execution observations; "
        f"strict-v2 usage-complete observation "
        f"{strict_observations['all_descriptions_reported_tokens']:,}→"
        f"{strict_observations['locally_selected_descriptions_reported_tokens']:,} "
        f"across {strict_observations['usage_complete_pair_count']} pairs; "
        f"legacy-v1 observation "
        f"{legacy_observations['all_descriptions_reported_tokens']:,}→"
        f"{legacy_observations['locally_selected_descriptions_reported_tokens']:,} "
        f"across {legacy_observations['usage_complete_pair_count']} pairs; "
        f"claimable_token_savings={str(campaigns['claimable_token_savings']).lower()}"
    )

    counts: dict[str, str] = {
        "vertical-slice": f"Real PyPI evidence: {total_entities:,} entities; {total_occurrences:,} occurrences; {total_relations:,} relations",
        "mechanism-runtime": "Stateless executor; immutable waterfall receipts are caller-owned",
        "pipeline-catalog": "4 executable pipelines; 6 admitted worker operations",
        "shared-kernel": "N/A — stateless identity/canonicalization library",
        "shared-schemas": f"{schema_count} checked-in JSON Schemas",
        "schema-artifacts": f"{schema_count} JSON Schemas; {sql_tables} PostgreSQL tables",
        "primitive-capsules": f"Data cohort: {released} public releases / {release_blobs} blobs / {data_cohort['pack_count']} downloadable packs",
        "primitive-factory": f"{candidate_count:,} real-source candidates; {candidate_events:,} intake events; 0 released by factory",
        "ingestion-pypi": f"4 real wheels evidenced (3 benchmark + usaddress); latest usaddress mount: 101 entities / 614 relations",
        "ingestion-git": "1 immutable real GitHub commit archive; 417 entities / 2,282 relations",
        "analyzer-python": f"Real PyPI evidence: {total_entities:,} entities / {total_relations:,} relations across 140 files",
        "analyzer-polyglot": "No dedicated durable rows; working file-inventory boundary, semantic adapters not claimed",
        "storage": f"5 real published evaluation epochs; usaddress runs: {mount_entities:,} entities / {mount_variants:,} typed variants",
        "retrieval": (
            "36 retained real-package hybrid query receipts; primitive-card program: "
            f"{retrieval_program['fixture_case_count']} deterministic cases / "
            f"{retrieval_program['program_metrics']['positive_hits_at_1']}/"
            f"{retrieval_program['positive_case_count']} positive rank-1 hits / "
            f"{retrieval_program['program_metrics']['negative_abstentions']}/"
            f"{retrieval_program['negative_case_count']} unsupported abstentions / "
            f"{retrieval_program['legacy_metrics']['returned_candidate_count']}→"
            f"{retrieval_program['program_metrics']['returned_candidate_count']} "
            "returned candidates"
        ),
        "compatibility": f"Data cohort: {evidence_edges} evidence edges / {pipeline_ports} typed ports / {pipeline_edges} blocked exact compatibility edges / {primitive_route_count} executed routes",
        "session-ledger": "Reference factory evidence: 1 digest-only session / 7 events / 0 model calls",
        "benchmarking": (
            f"{benchmark_runs} deterministic worker-conformance receipts plus 1 "
            f"primitive retrieval program benchmark / "
            f"{retrieval_program['fixture_case_count']} cases; {live_campaign_summary}"
        ),
        "saas-control-plane": "Real acquisition evidence: 1 tenant / 2 succeeded jobs / 4 audit events",
        "worker-runtime": "Real acquisition evidence: 2 leased and succeeded network jobs",
        "benchmark-worker": f"{benchmark_runs} deterministic fixture receipts; 0 live campaigns executed by the durable worker service",
        "discovery-worker": "0 hosted poll/webhook rows; replay-safe local router is tested",
        "ingestion-worker": f"2 real acquisition jobs; {mount_entities:,} entities / {mount_relations:,} relations published",
        "primitive-worker": f"{candidate_count:,} candidates plus {released} locally acceptance-verified released primitives",
        "indexer-service": "5 real evaluation epochs (3 PyPI benchmark + 2 usaddress acquisition)",
        "query-api": f"{route_count} operations across {path_count} paths",
        "registry-api": f"Data cohort: {released} public releases; 0 candidate rows serving as primitives",
        "mcp-integration": "Protocol and remote round-trip evidence; no durable MCP-owned rows",
        "agent-integrations": "1 digest-only harness session; 0 model calls; no efficacy claim",
        "explorer-app": "Static application; records are read from authenticated APIs",
        "portal-app": "Static application + versioned plan/subscription contracts; no checked-in customer rows",
        "deployment": f"{sql_tables} PostgreSQL tables; Docker/Compose and one-Machine Fly POC",
        "evaluation": f"3 real PyPI packages + 2 real usaddress sources + {released} real custom releases + {primitive_route_count} no-model routes + {retrieval_program['fixture_case_count']} primitive retrieval cases + {natural_task_count} constructed tasks/{natural_case_count} cases + {external_task_count} external issue-derived positive tasks/{external_case_count} cases + {live_campaign_summary}",
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
        "product_readiness": readiness["product_readiness"],
        "component_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "postgres_table_count": sql_tables,
        "json_schema_count": schema_count,
        "api_operation_count": route_count,
        "api_path_count": path_count,
        "data_primitive_evidence": {
            "release_count": released,
            "blob_count": release_blobs,
            "pack_count": int(data_cohort["pack_count"]),
            "executed_route_count": primitive_route_count,
        },
        "primitive_retrieval_evidence": {
            "case_count": int(retrieval_program["fixture_case_count"]),
            "positive_rank1_hits": int(
                retrieval_program["program_metrics"]["positive_hits_at_1"]
            ),
            "positive_case_count": int(retrieval_program["positive_case_count"]),
            "negative_abstentions": int(
                retrieval_program["program_metrics"]["negative_abstentions"]
            ),
            "negative_case_count": int(retrieval_program["negative_case_count"]),
            "returned_candidate_count": int(
                retrieval_program["program_metrics"]["returned_candidate_count"]
            ),
            "program_digest": retrieval_program["program_digest"],
        },
        "prompt_interception_evidence": campaigns,
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
            (
                "component",
                "folder",
                "status",
                "scope",
                "records_or_evidence",
                "capabilities",
                "next_gates",
                "product_release_label",
                "serves_truth",
                "public_paid_saas_ready",
            )
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
                    result["product_readiness"]["release_label"],
                    str(result["product_readiness"]["serves_truth"]).lower(),
                    str(
                        result["product_readiness"]["public_paid_saas_ready"]
                    ).lower(),
                )
            )
    markdown = render_markdown(result)
    (OUTPUT / "README.md").write_text(markdown, "utf-8")
    REPORT.write_text(markdown, "utf-8")
    HTML.write_text(render_html(result), "utf-8")
    SVG.write_text(render_svg(status_counts, result["product_readiness"]), "utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "components"}, indent=2))


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Taedri component and capability inventory",
        "",
        f"As of {result['as_of']}. This inventory contains all {result['component_count']} declared components.",
        "",
        "## Launch truth",
        "",
        f"**{result['product_readiness']['release_label']}.** `serves_truth={str(result['product_readiness']['serves_truth']).lower()}` and `public_paid_saas_ready={str(result['product_readiness']['public_paid_saas_ready']).lower()}`. {result['product_readiness']['not_validated']}",
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
            f"The factory's candidate rows are not primitive releases. Public primitive search, resolution, and pack delivery read only `primitive_release`, whose rows require the complete capsule and all executable acceptance proofs. The checked-in data cohort has {result['data_primitive_evidence']['release_count']} active releases; the 347 static candidates remain candidate-only.",
            "",
            "## Prompt-interception evidence boundary",
            "",
            f"The checked-in live evidence contains {result['prompt_interception_evidence']['strict_v2_campaign_count']} strict campaign-v2 documents and {result['prompt_interception_evidence']['legacy_v1_campaign_count']} readable legacy-v1 documents. Strict v2 validates the declared task/seed/two-condition matrix and binds verifier occurrences to each arm. Legacy v1 remains observation-only because it cannot detect omitted whole tasks or prove arm-specific verifier occurrence identity.",
            "",
            f"The strict-v2 usage-complete observations report {result['prompt_interception_evidence']['observations_by_campaign_format']['2.0.0']['all_descriptions_reported_tokens']:,} prompt-plus-completion tokens when every primitive description was shown and {result['prompt_interception_evidence']['observations_by_campaign_format']['2.0.0']['locally_selected_descriptions_reported_tokens']:,} when local retrieval selected a smaller set, across {result['prompt_interception_evidence']['observations_by_campaign_format']['2.0.0']['usage_complete_pair_count']} matched-pair observations. The legacy-v1 observations separately report {result['prompt_interception_evidence']['observations_by_campaign_format']['1.0.0']['all_descriptions_reported_tokens']:,}→{result['prompt_interception_evidence']['observations_by_campaign_format']['1.0.0']['locally_selected_descriptions_reported_tokens']:,} across {result['prompt_interception_evidence']['observations_by_campaign_format']['1.0.0']['usage_complete_pair_count']} pairs. The combined {result['prompt_interception_evidence']['all_descriptions_reported_tokens']:,}→{result['prompt_interception_evidence']['locally_selected_descriptions_reported_tokens']:,} total is only a non-claimable inventory observation because versions and repeated cohorts overlap. `claimable_token_savings={str(result['prompt_interception_evidence']['claimable_token_savings']).lower()}`: none of these counters include all required runtime, retrieval, verification, repair, cache, and tool overhead or trusted isolated-runtime attestation.",
            "",
            f"The fixtures contain {9 + 5} unique tasks and {18 + 10} unique cases (9 constructed tasks/18 cases plus 5 external issue-derived positive tasks/10 cases). Campaign totals are deliberately called provider-call attempts, matched-pair observations, and case-execution observations because the same fixture cases are executed repeatedly across widths, seeds, and campaign formats.",
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
<p><strong>{html.escape(result['product_readiness']['release_label'])}.</strong> serves_truth={str(result['product_readiness']['serves_truth']).lower()}; public_paid_saas_ready={str(result['product_readiness']['public_paid_saas_ready']).lower()}. Evidence-backed component scope, records, folders, and capabilities; candidates never count as released primitives.</p>
<div class="controls"><input id="query" type="search" placeholder="Filter component, capability, folder…"><select id="status"><option value="">All statuses</option><option>working</option><option>partial</option><option>conformance_only</option><option>poc_only</option></select></div>
<div class="summary" id="summary"></div><div class="table"><table><thead><tr><th>Component</th><th>Folder</th><th>Status</th><th>Scope</th><th>Measured records / evidence</th><th>Capabilities</th><th>Next gate</th></tr></thead><tbody id="rows"></tbody></table></div>
<script>const data={data};const q=document.querySelector('#query'),s=document.querySelector('#status'),rows=document.querySelector('#rows'),summary=document.querySelector('#summary');
function esc(v){{return String(v).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function render(){{const needle=q.value.toLowerCase(),status=s.value;const visible=data.filter(x=>(!status||x.status===status)&&JSON.stringify(x).toLowerCase().includes(needle));const counts={{}};for(const x of visible)counts[x.status]=(counts[x.status]||0)+1;summary.innerHTML=`<span class="pill">${{visible.length}} components</span>`+Object.entries(counts).sort().map(([k,v])=>`<span class="pill ${{k}}">${{esc(k)}}: ${{v}}</span>`).join('');rows.innerHTML=visible.map(x=>`<tr><td><code>${{esc(x.id)}}</code></td><td><code>${{esc(x.folder)}}</code></td><td class="status ${{esc(x.status)}}">${{esc(x.status)}}</td><td>${{esc(x.scope)}}</td><td>${{esc(x.measured_records)}}</td><td>${{x.capabilities.map(esc).join('<br>')}}</td><td>${{esc(x.next_gates[0])}}</td></tr>`).join('')}}q.addEventListener('input',render);s.addEventListener('change',render);render();</script></main></body></html>"""


def render_svg(counts: Counter[str], product_readiness: dict[str, Any]) -> str:
    colors = {"working": "#25b99a", "partial": "#d8a62a", "conformance_only": "#668ee8", "poc_only": "#e7795e"}
    ordered = ("working", "partial", "conformance_only", "poc_only")
    maximum = max(counts.values())
    bars = []
    for index, status in enumerate(ordered):
        value = counts[status]
        y = 110 + index * 76
        width = round(720 * value / maximum)
        bars.append(f'<text x="40" y="{y + 21}" class="label">{html.escape(status)}</text><rect x="245" y="{y}" width="720" height="30" rx="8" class="track"/><rect x="245" y="{y}" width="{width}" height="30" rx="8" fill="{colors[status]}"/><text x="985" y="{y + 22}" class="value">{value}</text>')
    label = html.escape(str(product_readiness["release_label"]))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="460" viewBox="0 0 1100 460" role="img" aria-labelledby="title desc"><title id="title">Taedri component readiness</title><desc id="desc">Counts of evidence-backed readiness states across 32 components. Product status: {label}; serves truth is false.</desc><style>.bg{{fill:#091018}}.track{{fill:#1b2b3a}}.title{{fill:#e9f2f8;font:700 30px system-ui}}.note,.label,.value{{fill:#c4d2dc;font:18px system-ui}}.value{{font-weight:700}}</style><rect class="bg" width="1100" height="460"/><text x="40" y="48" class="title">Evidence-backed component readiness</text><text x="40" y="78" class="note">32 components · {label} · serves_truth=false</text>{''.join(bars)}</svg>'''


if __name__ == "__main__":
    main()
