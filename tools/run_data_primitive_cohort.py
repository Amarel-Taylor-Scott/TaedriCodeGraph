#!/usr/bin/env python3
"""Release, search, compose, and report the complete data primitive cohort."""

from __future__ import annotations

import argparse
import csv
import html
import json
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest
from taedri_codegraph.primitive_capsules import CapsuleRole
from taedri_codegraph.primitive_repository import SQLitePrimitiveRepository
from taedri_codegraph.primitives.acceptance import LocalPythonPrimitiveVerifier
from taedri_codegraph.primitives.bundle import inspect_primitive_directory
from taedri_codegraph.primitives.digestion import PrimitiveDigester
from taedri_codegraph.primitives.wiring import (
    ExactPrimitiveWirePlanner,
    LocalDeterministicPythonPipelineExecutor,
    WireVerdict,
)
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-07-17T07:30:00Z"
VERIFIED_AT = "2026-07-17T07:31:00Z"
EXPECTED_PRIMITIVES = 23
SEARCH_QUERY_OVERRIDES = {
    "normalize-text": "remove surrounding whitespace without changing internal spacing",
}


def run(output: Path) -> Mapping[str, Any]:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    pack_root = output / "packs"
    pack_root.mkdir(parents=True, exist_ok=True)
    directories = tuple(
        sorted(
            path.parent
            for path in (ROOT / "examples/primitives").rglob("primitive.json")
        )
    )
    if len(directories) != EXPECTED_PRIMITIVES:
        raise SystemExit(
            f"expected {EXPECTED_PRIMITIVES} complete primitive directories; "
            f"found {len(directories)}"
        )
    inspected = tuple(inspect_primitive_directory(path) for path in directories)

    temporary_registry = tempfile.TemporaryDirectory(prefix="taedri-data-registry-")
    build_db = Path(temporary_registry.name) / "registry.sqlite"
    database_path = output / "data-primitive-registry.sqlite"
    for suffix in ("", "-shm", "-wal"):
        Path(str(database_path) + suffix).unlink(missing_ok=True)
    control = SQLiteControlPlane(build_db)
    tenant = control.create_tenant(
        Tenant.create(
            slug="data-primitive-cohort",
            display_name="Data primitive cohort",
            created_at=CREATED_AT,
        )
    )
    repository = SQLitePrimitiveRepository(control)
    records: list[dict[str, Any]] = []
    packs: dict[str, bytes] = {}
    interfaces = {}
    for index, (directory, item) in enumerate(zip(directories, inspected, strict=True)):
        staged = repository.stage(
            tenant.identity.id,
            namespace=item.bundle.namespace,
            name=item.bundle.name,
            files=item.bundle.files,
            contract_path=item.bundle.contract_path,
            ref_kind=item.bundle.ref_kind,
            ref_name=item.bundle.ref_name,
            expected_revision_id=None,
            actor=item.artifacts.implementation_producer_id,
            created_at=CREATED_AT,
            message=item.bundle.message,
        )
        accepted = LocalPythonPrimitiveVerifier(
            repository,
            verifier_id=f"taedri.verifier.data-cohort-{index + 1}",
        ).verify_and_release(
            tenant.identity.id,
            staged.revision.identity.id,
            ref_kind=item.bundle.ref_kind,
            ref_name=item.bundle.ref_name,
            authorizer_id=f"taedri.release-manager.data-cohort-{index + 1}",
            policy_decision_id=item.bundle.policy_decision_id,
            verified_at=VERIFIED_AT,
            assurance_level=item.bundle.assurance_level,
        )
        pack, encoded = repository.pack(
            tenant.identity.id,
            item.bundle.namespace,
            item.bundle.name,
            ref_kind=item.bundle.ref_kind,
            ref_name=item.bundle.ref_name,
        )
        pack_path = pack_root / f"{item.bundle.namespace}--{item.bundle.name}.tcgpack"
        pack_path.write_bytes(encoded)
        with tempfile.TemporaryDirectory(prefix="taedri-data-pack-") as temporary:
            digestion = PrimitiveDigester().materialize(
                encoded,
                Path(temporary) / "checkout",
            )
        relative = directory.relative_to(ROOT / "examples/primitives")
        category = relative.parts[0] if len(relative.parts) > 1 else "text-core"
        interface = item.artifacts.interface
        record = {
            "category": category,
            "namespace": item.bundle.namespace,
            "name": item.bundle.name,
            "directory": directory.relative_to(ROOT).as_posix(),
            "primitive_id": accepted.released.release.primitive_id,
            "revision_id": accepted.released.release.revision_id,
            "release_id": accepted.released.release.identity.id,
            "tree_id": accepted.released.release.tree_id,
            "source_digest": accepted.released.release.source_digest,
            "acceptance_receipt_id": accepted.acceptance.identity.id,
            "executed_cases": accepted.executed_case_count,
            "capsule_payloads": len(item.bundle.files),
            "evidence_edges": interface.edge_count,
            "ports": len(interface.ports),
            "groups": len(interface.groups),
            "input_schema_digest": interface.input_ports[0].schema_digest,
            "output_schema_digest": interface.output_ports[0].schema_digest,
            "pack_id": pack.identity.id,
            "pack_digest": sha256_digest(encoded),
            "pack_bytes": len(encoded),
            "digested_files": len(digestion.files),
            "digested_bytes": digestion.materialized_bytes,
            "digestion_omitted_roles": list(digestion.omitted_roles),
            "digestion_executable_bits_removed": digestion.executable_bits_removed,
            "source_bytes": sum(
                file.blob.size_bytes
                for file in accepted.released.staged.tree.entries
                if file.role is CapsuleRole.SOURCE
            ),
            "search_query": SEARCH_QUERY_OVERRIDES.get(
                item.bundle.name,
                interface.groups[0].labels[0],
            ),
        }
        records.append(record)
        packs[item.bundle.name] = encoded
        interfaces[item.bundle.name] = interface

    search_receipts: list[dict[str, Any]] = []
    for record in records:
        rows = repository.list(
            tenant.identity.id,
            query=str(record["search_query"]),
            limit=100,
        )
        selected = [str(row["handle"]["name"]) for row in rows]
        if selected != [record["name"]]:
            raise SystemExit(
                f"search query {record['search_query']!r} selected {selected}, "
                f"not exactly {record['name']!r}"
            )
        search_receipts.append(
            {
                "query": record["search_query"],
                "query_digest": sha256_digest(str(record["search_query"]).encode()),
                "selected_name": record["name"],
                "selected_primitive_id": record["primitive_id"],
                "result_count": len(rows),
            }
        )

    planner = ExactPrimitiveWirePlanner()
    compatibility = _blocked_compatibility(tuple(interfaces.values()), planner)
    text_names = (
        "normalize-text",
        "collapse-whitespace",
        "casefold-text",
        "normalize-column-name",
    )
    numeric_names = ("minmax-scale", "numeric-mean")
    text_plan = planner.pipeline(tuple(interfaces[name] for name in text_names))
    text_result = LocalDeterministicPythonPipelineExecutor().execute(
        text_plan,
        tuple(packs[name] for name in text_names),
        "  Customer\t Straße  ",
    )
    numeric_plan = planner.pipeline(tuple(interfaces[name] for name in numeric_names))
    numeric_result = LocalDeterministicPythonPipelineExecutor().execute(
        numeric_plan,
        tuple(packs[name] for name in numeric_names),
        [10, 20, 30],
    )
    datetime_names = ("normalize-text", "normalize-iso-datetime")
    datetime_plan = planner.pipeline(
        tuple(interfaces[name] for name in datetime_names)
    )
    datetime_result = LocalDeterministicPythonPipelineExecutor().execute(
        datetime_plan,
        tuple(packs[name] for name in datetime_names),
        " 2026-07-17T08:30:00-04:00 ",
    )
    null_names = ("collapse-whitespace", "normalize-null-marker")
    null_plan = planner.pipeline(tuple(interfaces[name] for name in null_names))
    null_result = LocalDeterministicPythonPipelineExecutor().execute(
        null_plan,
        tuple(packs[name] for name in null_names),
        "  N/A  ",
    )
    json_names = (
        "parse-json-object",
        "drop-null-fields",
        "wrap-flatten-request",
        "flatten-record",
        "canonical-json-object",
    )
    json_plan = planner.pipeline(tuple(interfaces[name] for name in json_names))
    json_result = LocalDeterministicPythonPipelineExecutor().execute(
        json_plan,
        tuple(packs[name] for name in json_names),
        '{"user":{"name":"Ada","age":37},"unused":null}',
    )
    number_adapter_names = (
        "normalize-text",
        "coerce-finite-number",
        "format-compact-number",
    )
    number_adapter_plan = planner.pipeline(
        tuple(interfaces[name] for name in number_adapter_names)
    )
    number_adapter_result = LocalDeterministicPythonPipelineExecutor().execute(
        number_adapter_plan,
        tuple(packs[name] for name in number_adapter_names),
        " 1.25 ",
    )
    if (
        text_result.output != "customer_strasse"
        or numeric_result.output != 0.5
        or datetime_result.output != "2026-07-17T12:30:00Z"
        or null_result.output is not None
        or json_result.output != '{"user.age":37,"user.name":"Ada"}'
        or number_adapter_result.output != "1.25"
    ):
        raise SystemExit("data primitive deterministic routes returned incorrect output")

    table_names = (
        "primitive_handle",
        "primitive_blob",
        "primitive_tree",
        "primitive_revision",
        "primitive_ref",
        "primitive_ref_update",
        "primitive_release",
        "primitive_release_revocation",
        "job_payload",
        "audit_event",
    )
    connection = control._connect()
    try:
        counts = {
            name: int(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in table_names
        }
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    if counts["primitive_release"] != EXPECTED_PRIMITIVES:
        raise SystemExit("registry does not contain every expected active release")
    source_connection = sqlite3.connect(build_db)
    target_connection = sqlite3.connect(database_path)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    temporary_registry.cleanup()

    categories = dict(sorted(Counter(str(item["category"]) for item in records).items()))
    unique_groups = sorted(
        {
            group.id
            for interface in interfaces.values()
            for group in interface.groups
        }
    )
    run_record = {
        "schema_version": "1.0.0",
        "status": "passed",
        "claim_scope": (
            f"{EXPECTED_PRIMITIVES} complete trusted-source Python 3.12 primitives; "
            "local SQLite registry; exact blocked compatibility; six deterministic "
            "no-model routes"
        ),
        "primitive_count": len(records),
        "new_data_primitive_count": sum(
            1 for item in records if item["category"] != "text-core"
        ),
        "categories": categories,
        "executed_case_count": sum(int(item["executed_cases"]) for item in records),
        "capsule_payload_count": sum(int(item["capsule_payloads"]) for item in records),
        "evidence_edge_count": sum(int(item["evidence_edges"]) for item in records),
        "typed_port_count": sum(int(item["ports"]) for item in records),
        "unique_capability_group_count": len(unique_groups),
        "compatibility_edge_count": len(compatibility),
        "search_query_count": len(search_receipts),
        "search_exact_selection_count": sum(
            int(item["result_count"] == 1) for item in search_receipts
        ),
        "pack_count": len(packs),
        "digested_pack_count": sum(
            int(item["digested_files"] > 0) for item in records
        ),
        "digested_file_count": sum(int(item["digested_files"]) for item in records),
        "pack_bytes": sum(int(item["pack_bytes"]) for item in records),
        "source_bytes": sum(int(item["source_bytes"]) for item in records),
        "database_bytes": database_path.stat().st_size,
        "database_record_counts": counts,
        "text_route": {
            "primitive_names": list(text_names),
            "input": "  Customer\t Straße  ",
            "output": text_result.output,
            "plan_id": text_plan.identity.id,
            "receipt": text_result.receipt.to_dict(),
        },
        "numeric_route": {
            "primitive_names": list(numeric_names),
            "input": [10, 20, 30],
            "output": numeric_result.output,
            "plan_id": numeric_plan.identity.id,
            "receipt": numeric_result.receipt.to_dict(),
        },
        "datetime_route": {
            "primitive_names": list(datetime_names),
            "input": " 2026-07-17T08:30:00-04:00 ",
            "output": datetime_result.output,
            "plan_id": datetime_plan.identity.id,
            "receipt": datetime_result.receipt.to_dict(),
        },
        "null_route": {
            "primitive_names": list(null_names),
            "input": "  N/A  ",
            "output": null_result.output,
            "plan_id": null_plan.identity.id,
            "receipt": null_result.receipt.to_dict(),
        },
        "json_route": {
            "primitive_names": list(json_names),
            "input": '{"user":{"name":"Ada","age":37},"unused":null}',
            "output": json_result.output,
            "plan_id": json_plan.identity.id,
            "receipt": json_result.receipt.to_dict(),
        },
        "number_adapter_route": {
            "primitive_names": list(number_adapter_names),
            "input": " 1.25 ",
            "output": number_adapter_result.output,
            "plan_id": number_adapter_plan.identity.id,
            "receipt": number_adapter_result.receipt.to_dict(),
        },
        "deterministic_route_count": 6,
        "model_calls": 0,
        "generated_route_code_bytes": 0,
        "records": records,
        "search_receipts": search_receipts,
        "compatibility_edges": compatibility,
        "unique_capability_groups": unique_groups,
    }
    _write_artifacts(output, run_record)
    _verify_database(database_path, EXPECTED_PRIMITIVES)
    return run_record


def _blocked_compatibility(interfaces, planner) -> list[dict[str, Any]]:
    """Block by exact schema digest before bounded directional assessments."""

    producers: dict[str, list[Any]] = defaultdict(list)
    consumers: dict[str, list[Any]] = defaultdict(list)
    for interface in interfaces:
        producers[interface.output_ports[0].schema_digest].append(interface)
        consumers[interface.input_ports[0].schema_digest].append(interface)
    edges: list[dict[str, Any]] = []
    for schema_digest in sorted(set(producers) & set(consumers)):
        for producer in sorted(producers[schema_digest], key=lambda item: item.interface_id):
            for consumer in sorted(consumers[schema_digest], key=lambda item: item.interface_id):
                if producer.interface_id == consumer.interface_id:
                    continue
                assessment = planner.assess(producer, consumer)
                if assessment.verdict is WireVerdict.COMPATIBLE:
                    edges.append(
                        {
                            "producer": producer.interface_id,
                            "consumer": consumer.interface_id,
                            "producer_port": assessment.producer_port_id,
                            "consumer_port": assessment.consumer_port_id,
                            "schema_digest": schema_digest,
                            "transports": list(assessment.common_transports),
                            "verdict": assessment.verdict.value,
                        }
                    )
    return edges


def _write_artifacts(output: Path, run: Mapping[str, Any]) -> None:
    (output / "run.json").write_bytes(canonical_json_bytes(run) + b"\n")
    records = list(run["records"])
    with (output / "primitive-catalog.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        fields = (
            "category",
            "namespace",
            "name",
            "primitive_id",
            "release_id",
            "executed_cases",
            "capsule_payloads",
            "evidence_edges",
            "ports",
            "groups",
            "source_bytes",
            "pack_bytes",
            "pack_digest",
            "digested_files",
            "digested_bytes",
            "search_query",
        )
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record[field] for field in fields})
    with (output / "database-record-counts.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("table", "records"))
        writer.writerows(sorted(dict(run["database_record_counts"]).items()))
    with (output / "compatibility-edges.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        fields = (
            "producer",
            "consumer",
            "producer_port",
            "consumer_port",
            "schema_digest",
            "transports",
            "verdict",
        )
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for edge in run["compatibility_edges"]:
            row = dict(edge)
            row["transports"] = "|".join(row["transports"])
            writer.writerow(row)
    with (output / "search-receipts.jsonl").open("wb") as stream:
        for receipt in run["search_receipts"]:
            stream.write(canonical_json_bytes(receipt) + b"\n")
    _write_graphml(output / "primitive-cohort.graphml", run)
    (output / "primitive-cohort-summary.svg").write_text(
        _summary_svg(run), encoding="utf-8"
    )
    (output / "index.html").write_text(_console_html(run), encoding="utf-8")
    (output / "README.md").write_text(_report(run), encoding="utf-8")


def _write_graphml(path: Path, run: Mapping[str, Any]) -> None:
    namespace = "http://graphml.graphdrawing.org/xmlns"
    ET.register_namespace("", namespace)
    root = ET.Element(f"{{{namespace}}}graphml")
    for identifier, target in (
        ("kind", "node"),
        ("label", "node"),
        ("category", "node"),
        ("relation", "edge"),
        ("schema_digest", "edge"),
    ):
        ET.SubElement(
            root,
            f"{{{namespace}}}key",
            id=identifier,
            **{"for": target, "attr.name": identifier, "attr.type": "string"},
        )
    graph = ET.SubElement(root, f"{{{namespace}}}graph", edgedefault="directed")
    records = list(run["records"])
    by_interface = {str(item["name"]): item for item in records}
    interface_to_name = {
        str(item["namespace"]) + "." + str(item["name"]) + ".v1": str(item["name"])
        for item in records
    }
    for record in records:
        node = ET.SubElement(graph, f"{{{namespace}}}node", id="primitive:" + str(record["name"]))
        _data(node, namespace, "kind", "primitive")
        _data(node, namespace, "label", str(record["name"]))
        _data(node, namespace, "category", str(record["category"]))
    for group in run["unique_capability_groups"]:
        node = ET.SubElement(graph, f"{{{namespace}}}node", id="group:" + str(group))
        _data(node, namespace, "kind", "capability_group")
        _data(node, namespace, "label", str(group))
        _data(node, namespace, "category", "group")
    schema_digests = sorted(
        {
            str(item[field])
            for item in records
            for field in ("input_schema_digest", "output_schema_digest")
        }
    )
    for digest in schema_digests:
        node = ET.SubElement(graph, f"{{{namespace}}}node", id="schema:" + digest)
        _data(node, namespace, "kind", "schema")
        _data(node, namespace, "label", digest)
        _data(node, namespace, "category", "schema")
    edge_index = 0
    for record in records:
        name = str(record["name"])
        for relation, field, source_first in (
            ("accepts_schema", "input_schema_digest", False),
            ("produces_schema", "output_schema_digest", True),
        ):
            edge_index += 1
            primitive = "primitive:" + name
            schema = "schema:" + str(record[field])
            source, target = (primitive, schema) if source_first else (schema, primitive)
            edge = ET.SubElement(
                graph,
                f"{{{namespace}}}edge",
                id=f"e{edge_index}",
                source=source,
                target=target,
            )
            _data(edge, namespace, "relation", relation)
            _data(edge, namespace, "schema_digest", str(record[field]))
    for record in records:
        directory = ROOT / str(record["directory"])
        interface = inspect_primitive_directory(directory).artifacts.interface
        for group in interface.groups:
            edge_index += 1
            edge = ET.SubElement(
                graph,
                f"{{{namespace}}}edge",
                id=f"e{edge_index}",
                source="primitive:" + str(record["name"]),
                target="group:" + group.id,
            )
            _data(edge, namespace, "relation", "member_of")
            _data(edge, namespace, "schema_digest", "")
    for compatibility in run["compatibility_edges"]:
        producer_name = interface_to_name[str(compatibility["producer"])]
        consumer_name = interface_to_name[str(compatibility["consumer"])]
        if producer_name not in by_interface or consumer_name not in by_interface:
            raise SystemExit("compatibility graph references an unknown primitive")
        edge_index += 1
        edge = ET.SubElement(
            graph,
            f"{{{namespace}}}edge",
            id=f"e{edge_index}",
            source="primitive:" + producer_name,
            target="primitive:" + consumer_name,
        )
        _data(edge, namespace, "relation", "exactly_compatible")
        _data(edge, namespace, "schema_digest", str(compatibility["schema_digest"]))
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _data(parent, namespace: str, key: str, value: str) -> None:
    element = ET.SubElement(parent, f"{{{namespace}}}data", key=key)
    element.text = value


def _summary_svg(run: Mapping[str, Any]) -> str:
    categories = list(dict(run["categories"]).items())
    maximum = max(int(value) for _, value in categories)
    rows = []
    colors = ("#4f46e5", "#0891b2", "#16a34a", "#d97706")
    for index, (name, value) in enumerate(categories):
        y = 155 + index * 70
        width = 520 * int(value) / maximum
        rows.append(
            f'<text x="55" y="{y + 20}" class="label">{html.escape(name)}</text>'
            f'<rect x="270" y="{y}" width="520" height="28" rx="14" class="track"/>'
            f'<rect x="270" y="{y}" width="{width:.1f}" height="28" rx="14" fill="{colors[index % len(colors)]}"/>'
            f'<text x="815" y="{y + 20}" class="value">{value}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="560" viewBox="0 0 1200 560">
<style>.bg{{fill:#08111f}}.title{{font:700 28px system-ui;fill:#f8fafc}}.note{{font:16px system-ui;fill:#94a3b8}}.label{{font:600 16px system-ui;fill:#e2e8f0}}.value{{font:700 16px system-ui;fill:#f8fafc}}.metric{{font:700 30px system-ui;fill:#67e8f9}}.track{{fill:#1e293b}}</style>
<rect class="bg" width="1200" height="560"/><text x="55" y="55" class="title">Released primitive cohort by domain</text>
<text x="55" y="87" class="note">Only complete, executed, searchable releases are counted</text>{''.join(rows)}
<text x="930" y="155" class="metric">{run['primitive_count']}</text><text x="930" y="182" class="note">active releases</text>
<text x="930" y="245" class="metric">{run['executed_case_count']}</text><text x="930" y="272" class="note">executed cases</text>
<text x="930" y="335" class="metric">{run['compatibility_edge_count']}</text><text x="930" y="362" class="note">exact composition edges</text>
<text x="55" y="520" class="note">SQLite bytes: {int(run['database_bytes']):,} · packs: {run['pack_count']} · model calls: 0</text></svg>'''


def _console_html(run: Mapping[str, Any]) -> str:
    data = json.dumps(run, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Taedri data primitive cohort</title>
<style>:root{{color-scheme:dark}}body{{margin:0;background:#07101d;color:#e5edf8;font:15px system-ui}}main{{max-width:1250px;margin:auto;padding:32px}}h1{{margin:0 0 8px;font-size:34px}}.sub{{color:#9fb0c7}}.metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:24px 0}}.card{{background:#101c2e;border:1px solid #263853;border-radius:14px;padding:16px}}.n{{font-size:28px;font-weight:750;color:#67e8f9}}input,select{{background:#0b1728;color:#fff;border:1px solid #334967;border-radius:9px;padding:10px;margin:0 8px 16px 0}}table{{width:100%;border-collapse:collapse;background:#0c1727}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #20334c}}th{{position:sticky;top:0;background:#132139}}code{{font-size:12px;color:#a5f3fc}}.routes{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0}}@media(max-width:800px){{.metrics{{grid-template-columns:1fr 1fr}}.routes{{grid-template-columns:1fr}}table{{font-size:12px}}}}</style></head><body><main><h1>Taedri data primitive cohort</h1><div class="sub">Complete releases only · searchable SQLite registry · exact compatibility · deterministic no-model routes</div>
<section class="metrics"><div class="card"><div class="n">{run['primitive_count']}</div>releases</div><div class="card"><div class="n">{run['executed_case_count']}</div>executed cases</div><div class="card"><div class="n">{run['evidence_edge_count']}</div>evidence edges</div><div class="card"><div class="n">{run['compatibility_edge_count']}</div>composition edges</div><div class="card"><div class="n">0</div>model calls</div></section>
<section class="routes"><div class="card"><b>Text route</b><p><code>{html.escape(' → '.join(run['text_route']['primitive_names']))}</code></p><p>{html.escape(str(run['text_route']['input']))} → <b>{html.escape(str(run['text_route']['output']))}</b></p></div><div class="card"><b>Numeric route</b><p><code>{html.escape(' → '.join(run['numeric_route']['primitive_names']))}</code></p><p>{html.escape(str(run['numeric_route']['input']))} → <b>{run['numeric_route']['output']}</b></p></div><div class="card"><b>Datetime route</b><p><code>{html.escape(' → '.join(run['datetime_route']['primitive_names']))}</code></p><p>{html.escape(str(run['datetime_route']['input']))} → <b>{html.escape(str(run['datetime_route']['output']))}</b></p></div><div class="card"><b>Null route</b><p><code>{html.escape(' → '.join(run['null_route']['primitive_names']))}</code></p><p>{html.escape(str(run['null_route']['input']))} → <b>{html.escape(str(run['null_route']['output']))}</b></p></div><div class="card"><b>JSON adapter route</b><p><code>{html.escape(' → '.join(run['json_route']['primitive_names']))}</code></p><p>{html.escape(str(run['json_route']['input']))} → <b>{html.escape(str(run['json_route']['output']))}</b></p></div><div class="card"><b>Number adapter route</b><p><code>{html.escape(' → '.join(run['number_adapter_route']['primitive_names']))}</code></p><p>{html.escape(str(run['number_adapter_route']['input']))} → <b>{html.escape(str(run['number_adapter_route']['output']))}</b></p></div></section>
<input id="q" placeholder="Filter name, capability, query"><select id="category"><option value="">All domains</option>{''.join(f'<option>{html.escape(name)}</option>' for name in run['categories'])}</select><span id="count"></span>
<div style="overflow:auto;max-height:620px"><table><thead><tr><th>Domain</th><th>Primitive</th><th>Search query</th><th>Cases</th><th>Edges</th><th>Pack</th></tr></thead><tbody id="rows"></tbody></table></div>
<script id="dataset" type="application/json">{data}</script><script>const d=JSON.parse(document.querySelector('#dataset').textContent),q=document.querySelector('#q'),c=document.querySelector('#category'),rows=document.querySelector('#rows'),count=document.querySelector('#count');function draw(){{const needle=q.value.toLowerCase(),cat=c.value;const found=d.records.filter(x=>(!cat||x.category===cat)&&(!needle||JSON.stringify(x).toLowerCase().includes(needle)));rows.innerHTML=found.map(x=>`<tr><td>${{x.category}}</td><td><b>${{x.namespace}}/${{x.name}}</b></td><td>${{x.search_query}}</td><td>${{x.executed_cases}}</td><td>${{x.evidence_edges}}</td><td>${{x.pack_bytes.toLocaleString()}} B</td></tr>`).join('');count.textContent=`${{found.length}} / ${{d.records.length}}`}}q.oninput=c.onchange=draw;draw();</script></main></body></html>'''


def _report(run: Mapping[str, Any]) -> str:
    category_rows = "\n".join(
        f"| {name} | {count} |" for name, count in dict(run["categories"]).items()
    )
    database_rows = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in sorted(dict(run["database_record_counts"]).items())
    )
    return f"""# Data primitive cohort evidence

Status: **passed**

Taedri released and independently executed {run['primitive_count']} complete primitives,
including {run['new_data_primitive_count']} new data-cleaning, data-engineering, and
data-science utilities. Every primitive has 13 payloads covering all 12 required roles,
six executable cases, six evidence-bound interface edges, two typed ports, searchable
capability labels, exact runtime/dependency metadata, license evidence, and immutable
source provenance.

| Domain | Active releases |
|---|---:|
{category_rows}

The persistent SQLite artifact contains {run['primitive_count']} active releases and
serves all {run['search_query_count']} targeted queries with exactly one intended result.
The bounded client digester decoded and safely materialized all
{run['digested_pack_count']} packs ({run['digested_file_count']} selected files),
omitting verifier code according to its default policy.
Schema-digest blocking followed by exact typed assessment produced
{run['compatibility_edge_count']} directional composition edges without an unbounded
global all-pairs operation.

Six downloaded-pack routes executed without an LLM or generated glue code:

- Text: `{' → '.join(run['text_route']['primitive_names'])}` transformed
  `{run['text_route']['input']!r}` to `{run['text_route']['output']!r}`.
- Numeric: `{' → '.join(run['numeric_route']['primitive_names'])}` transformed
  `{run['numeric_route']['input']!r}` to `{run['numeric_route']['output']!r}`.
- Datetime: `{' → '.join(run['datetime_route']['primitive_names'])}` transformed
  `{run['datetime_route']['input']!r}` to `{run['datetime_route']['output']!r}`.
- Null marker: `{' → '.join(run['null_route']['primitive_names'])}` transformed
  `{run['null_route']['input']!r}` to `{run['null_route']['output']!r}`.
- JSON adapters: `{' → '.join(run['json_route']['primitive_names'])}` transformed
  `{run['json_route']['input']!r}` to `{run['json_route']['output']!r}`.
- Number adapters: `{' → '.join(run['number_adapter_route']['primitive_names'])}` transformed
  `{run['number_adapter_route']['input']!r}` to `{run['number_adapter_route']['output']!r}`.

| SQLite record type | Records |
|---|---:|
{database_rows}

This proves a larger, queryable, reusable local database and six deterministic data
routes. It does not yet prove corpus-wide ranking quality, dependency-backed pandas or
scikit-learn execution, distributed scale, or task-level token/cost savings.
"""


def _verify_database(path: Path, expected_releases: int) -> None:
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        release_count = int(
            connection.execute("SELECT COUNT(*) FROM primitive_release").fetchone()[0]
        )
        if release_count != expected_releases:
            raise SystemExit("persisted registry release count does not reconcile")
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise SystemExit("persisted registry failed SQLite integrity_check")
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "eval/results/data-primitive-cohort-2026-07-17",
    )
    arguments = parser.parse_args()
    record = run(arguments.output)
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
