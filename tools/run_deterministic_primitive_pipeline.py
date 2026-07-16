#!/usr/bin/env python3
"""Release two real primitives, wire exact ports, and execute without an LLM."""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

from taedri_codegraph.canonical import canonical_json_bytes
from taedri_codegraph.discovery.triggers import (
    SearchTriggerSignal,
    TriggerKind,
    default_trigger_router,
    intent_digest,
)
from taedri_codegraph.primitive_repository import SQLitePrimitiveRepository
from taedri_codegraph.primitives.acceptance import LocalPythonPrimitiveVerifier
from taedri_codegraph.primitives.bundle import inspect_primitive_directory
from taedri_codegraph.primitives.wiring import (
    ExactPrimitiveWirePlanner,
    LocalDeterministicPythonPipelineExecutor,
)
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


ROOT = Path(__file__).resolve().parents[1]
CREATED_AT = "2026-07-16T23:00:00Z"
VERIFIED_AT = "2026-07-16T23:01:00Z"
INTENT = "trim surrounding whitespace and apply Unicode case folding"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="eval/results/deterministic-primitive-pipeline-2026-07-16",
    )
    arguments = parser.parse_args()
    output_root = (ROOT / arguments.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    directories = (
        ROOT / "examples/primitives/normalize-text",
        ROOT / "examples/primitives/casefold-text",
    )
    inspected = tuple(inspect_primitive_directory(path) for path in directories)

    signal = SearchTriggerSignal(
        event_id="deterministic-pipeline-reference-v1",
        session_id="deterministic-pipeline-reference-session-v1",
        kind=TriggerKind.USER_EXPLICIT,
        intent_digest=intent_digest(INTENT),
        occurred_at=CREATED_AT,
        language="python",
        labels=("reuse", "text"),
        attributes={"entity_kind": "primitive"},
    )
    trigger = default_trigger_router(monotonic_ms=lambda: 1).decide(signal)
    if not trigger.should_search:
        raise SystemExit("explicit primitive search trigger did not fire")

    with tempfile.TemporaryDirectory(prefix="taedri-deterministic-reference-") as temporary:
        control = SQLiteControlPlane(Path(temporary) / "control.sqlite")
        tenant = control.create_tenant(
            Tenant.create(
                slug="deterministic-pipeline",
                display_name="Deterministic primitive pipeline",
                created_at=CREATED_AT,
            )
        )
        repository = SQLitePrimitiveRepository(control)
        packs: list[bytes] = []
        releases = []
        for index, item in enumerate(inspected):
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
                verifier_id=f"taedri.verifier.deterministic-reference-{index + 1}",
            ).verify_and_release(
                tenant.identity.id,
                staged.revision.identity.id,
                ref_kind=item.bundle.ref_kind,
                ref_name=item.bundle.ref_name,
                authorizer_id=f"taedri.release-manager.deterministic-reference-{index + 1}",
                policy_decision_id=item.bundle.policy_decision_id,
                verified_at=VERIFIED_AT,
                assurance_level=item.bundle.assurance_level,
            )
            _, encoded = repository.pack(
                tenant.identity.id,
                item.bundle.namespace,
                item.bundle.name,
                ref_kind=item.bundle.ref_kind,
                ref_name=item.bundle.ref_name,
            )
            packs.append(encoded)
            releases.append(accepted.released.release)

        search_queries = (
            "trim surrounding whitespace",
            "unicode case folding",
        )
        search_results = tuple(
            repository.list(tenant.identity.id, query=query)
            for query in search_queries
        )
        selected_ids = tuple(
            str(rows[0]["handle"]["identity"]["id"]) if len(rows) == 1 else ""
            for rows in search_results
        )
        if selected_ids != tuple(item.primitive_id for item in releases):
            raise SystemExit("released primitive search did not select the exact intended pair")

        interfaces = tuple(item.artifacts.interface for item in inspected)
        planner = ExactPrimitiveWirePlanner()
        plan = planner.pipeline(interfaces)
        pipeline = LocalDeterministicPythonPipelineExecutor().execute(
            plan,
            packs,
            "  Straße  ",
        )
        if pipeline.output != "strasse":
            raise SystemExit("deterministic primitive pipeline returned the wrong value")

        run = {
            "schema_version": "1.0.0",
            "status": "passed",
            "claim_scope": "two trusted-source Python primitives; exact adapter-free wiring; no LLM",
            "intent": INTENT,
            "intent_digest": signal.intent_digest,
            "trigger": trigger.to_dict(),
            "search_queries": list(search_queries),
            "search_result_counts": [len(rows) for rows in search_results],
            "selected_release_ids": list(selected_ids),
            "primitive_count": len(interfaces),
            "interface_ids": [item.interface_id for item in interfaces],
            "interface_graph_digests": [item.graph_digest for item in interfaces],
            "edge_count": sum(item.edge_count for item in interfaces),
            "port_count": sum(len(item.ports) for item in interfaces),
            "capability_group_count": sum(len(item.groups) for item in interfaces),
            "wire_count": len(plan.wires),
            "wire_verdicts": [item.assessment.verdict.value for item in plan.wires],
            "plan_id": plan.identity.id,
            "input": "  Straße  ",
            "output": pipeline.output,
            "pipeline_receipt": pipeline.receipt.to_dict(),
            "model_calls": 0,
            "generated_code_bytes": 0,
            "rewritten_primitive_bytes": 0,
        }
        (output_root / "normalize-text.tcgpack").write_bytes(packs[0])
        (output_root / "casefold-text.tcgpack").write_bytes(packs[1])
        (output_root / "run.json").write_bytes(canonical_json_bytes(run) + b"\n")
        with (output_root / "wire-assessments.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                (
                    "producer_interface",
                    "producer_port",
                    "consumer_interface",
                    "consumer_port",
                    "verdict",
                    "schema_digest",
                    "transport",
                )
            )
            for wire in plan.wires:
                writer.writerow(
                    (
                        wire.producer_interface_id,
                        wire.producer_port_id,
                        wire.consumer_interface_id,
                        wire.consumer_port_id,
                        wire.assessment.verdict.value,
                        wire.schema_digest,
                        wire.transport,
                    )
                )
        (output_root / "README.md").write_text(_report(run), "utf-8")
    print(json.dumps(run, indent=2, ensure_ascii=False, sort_keys=True))


def _report(run: dict[str, object]) -> str:
    return f"""# Deterministic primitive pipeline evidence

Status: **passed**

An explicit user-tier trigger fired for `{run['intent']}`. Two released primitives were
found by separate registry queries, their evidence-bound interface graphs were loaded,
and the normalize-text output port was connected to the casefold-text input port only
after exact schema, transport, runtime, determinism, purity, network, and call-style
checks passed.

The trusted-source local executor downloaded and digest-checked both complete packs,
materialized them, and transformed `"  Straße  "` into `"strasse"`. It made zero model
calls and generated or rewrote zero primitive code bytes.

- Plan: `{run['plan_id']}`
- Interfaces: {run['primitive_count']}
- Evidence-bound edges: {run['edge_count']}
- Typed ports: {run['port_count']}
- Exact wires: {run['wire_count']}
- Pipeline receipt: `{dict(run['pipeline_receipt'])['identity']['id']}`

This proves a narrow deterministic reuse path, not general natural-language planning,
adapter synthesis, hostile-code isolation, or population-level token/cost savings.
"""


if __name__ == "__main__":
    main()
