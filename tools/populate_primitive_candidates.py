#!/usr/bin/env python3
"""Populate a real-source primitive candidate corpus with operational receipts."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.canonical import (  # noqa: E402
    canonical_digest,
    canonical_json_bytes,
    sha256_digest,
)
from taedri_codegraph.contracts import ProducerRef  # noqa: E402
from taedri_codegraph.intake import (  # noqa: E402
    CandidateIntakeLedger,
    CandidateVisibility,
    LicenseEvidenceState,
)
from taedri_codegraph.primitive_capsules import (  # noqa: E402
    CapsuleRole,
    PrimitiveRegistry,
    encode_primitive_pack,
)
from taedri_codegraph.primitive_factory import PrimitiveFactory  # noqa: E402
from taedri_codegraph.sessions import (  # noqa: E402
    HarnessRef,
    PromptPrivacyMode,
    PromptSession,
    PromptSessionLedger,
    SessionEventKind,
)
from taedri_codegraph.workers import JobKind, WorkerJob, WorkerQueue  # noqa: E402

OUTPUT = ROOT / "eval" / "results" / "primitive-factory-2026-07-16"
SOURCE_ROOT = ROOT / "src" / "taedri_codegraph"
SOURCE_URI = "https://github.com/Amarel-Taylor-Scott/TaedriCodeGraph/tree/agent/initial-vertical-slice/src/taedri_codegraph"
CREATED_AT = "2026-07-16T12:00:00Z"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _source_payload_ref() -> str:
    inventory = [
        {
            "path": path.relative_to(SOURCE_ROOT).as_posix(),
            "digest": sha256_digest(path.read_bytes()),
        }
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts
    ]
    return sha256_digest(canonical_json_bytes(inventory))


def _graphml(candidates: list[dict[str, object]]) -> str:
    candidate_ids = {
        str(candidate["identity"]["id"]): f"candidate-{index}"
        for index, candidate in enumerate(candidates)
    }
    external_labels = sorted(
        {
            str(label)
            for candidate in candidates
            for label in candidate.get("call_labels", [])
        }
    )
    external_ids = {label: f"external-{index}" for index, label in enumerate(external_labels)}
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="kind" for="node" attr.name="kind" attr.type="string"/>',
        '  <key id="predicate" for="edge" attr.name="predicate" attr.type="string"/>',
        '  <graph id="primitive-candidate-calls" edgedefault="directed">',
    ]
    for candidate in candidates:
        identity_id = str(candidate["identity"]["id"])
        lines.extend(
            [
                f'    <node id="{candidate_ids[identity_id]}">',
                f'      <data key="label">{escape(str(candidate["module"]) + ":" + str(candidate["qualified_name"]))}</data>',
                f'      <data key="kind">{escape(str(candidate["entity_kind"]))}</data>',
                "    </node>",
            ]
        )
    for label in external_labels:
        lines.extend(
            [
                f'    <node id="{external_ids[label]}">',
                f'      <data key="label">{escape(label)}</data>',
                '      <data key="kind">unresolved-call-label</data>',
                "    </node>",
            ]
        )
    edge_index = 0
    for candidate in candidates:
        source = candidate_ids[str(candidate["identity"]["id"])]
        for label in candidate.get("call_labels", []):
            lines.extend(
                [
                    f'    <edge id="edge-{edge_index}" source="{source}" target="{external_ids[str(label)]}">',
                    '      <data key="predicate">uceg.predicate.calls_may</data>',
                    "    </edge>",
                ]
            )
            edge_index += 1
    lines.extend(["  </graph>", "</graphml>", ""])
    return "\n".join(lines)


def _mermaid(candidates: list[dict[str, object]], limit: int = 60) -> str:
    selected = candidates[:limit]
    lines = [
        "flowchart LR",
        "  %% Real Taedri source candidates; capped for GitHub rendering.",
        "  %% Call targets are unresolved labels, not compatibility proof.",
    ]
    external: dict[str, str] = {}
    for index, candidate in enumerate(selected):
        label = f'{candidate["module"]}:{candidate["qualified_name"]}'.replace('"', "'")
        lines.append(f'  c{index}["{label}"]')
        for call in candidate.get("call_labels", [])[:8]:
            call_label = str(call)
            target = external.setdefault(call_label, f"x{len(external)}")
            lines.append(f'  {target}(["{call_label.replace(chr(34), chr(39))}"])')
            lines.append(f"  c{index} -->|calls may| {target}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "graphs").mkdir(exist_ok=True)
    producer = ProducerRef(
        "taedri.tool.populate-primitive-candidates",
        "1.0.0",
        sha256_digest(Path(__file__).read_bytes()),
    )
    workers = WorkerQueue()
    source_payload = _source_payload_ref()
    extract_job = workers.enqueue(
        WorkerJob.create(
            queue="indexing",
            kind=JobKind.EXTRACT,
            subject_id="repository:taedri-codegraph:working-tree",
            payload_ref=source_payload,
            idempotency_key=f"extract:{source_payload}",
            created_at=CREATED_AT,
            priority=90,
            required_capabilities=("python-ast", "primitive-capsule-v1"),
        )
    )
    extract_lease = workers.claim(
        queue="indexing",
        worker_id="local-static-worker",
        leased_at="2026-07-16T12:00:01Z",
        expires_at="2026-07-16T12:10:01Z",
        lease_nonce="real-source-extract-1",
        capabilities=("python-ast", "primitive-capsule-v1"),
    )
    if extract_lease is None:  # pragma: no cover - conformance guard
        raise RuntimeError("extract job was not leaseable")
    registry = PrimitiveRegistry()
    intake = CandidateIntakeLedger()
    result = PrimitiveFactory().generate(
        SOURCE_ROOT,
        registry=registry,
        intake=intake,
        producer=producer,
        package_name="taedri_codegraph",
        namespace="taedri.candidates",
        source_uri=SOURCE_URI,
        source_revision=None,
        created_at="2026-07-16T12:00:02Z",
        license_expression=None,
        license_evidence_state=LicenseEvidenceState.UNKNOWN,
        visibility=CandidateVisibility.PRIVATE,
    )
    workers.complete(
        extract_lease,
        occurred_at="2026-07-16T12:00:05Z",
        output_refs=(result.identity.id,),
        metrics={
            "source_files": result.source_file_count,
            "source_bytes": result.scanned_source_bytes,
            "candidate_count": len(result.candidates),
            "diagnostic_count": len(result.diagnostics),
        },
    )
    index_projection_ref = canonical_digest(
        [
            {
                "candidate_id": candidate.identity.id,
                "descriptor_digest": candidate.descriptor_digest,
            }
            for candidate in result.candidates
        ]
    )
    index_job = workers.enqueue(
        WorkerJob.create(
            queue="indexing",
            kind=JobKind.INDEX,
            subject_id=result.identity.id,
            payload_ref=result.identity.id,
            idempotency_key=f"index:{result.identity.id}",
            created_at="2026-07-16T12:00:06Z",
            priority=80,
            required_capabilities=("candidate-descriptor-v1",),
        )
    )
    index_lease = workers.claim(
        queue="indexing",
        worker_id="local-index-worker",
        leased_at="2026-07-16T12:00:07Z",
        expires_at="2026-07-16T12:10:07Z",
        lease_nonce="real-source-index-1",
        capabilities=("candidate-descriptor-v1",),
    )
    if index_lease is None:  # pragma: no cover - conformance guard
        raise RuntimeError("index job was not leaseable")
    workers.complete(
        index_lease,
        occurred_at="2026-07-16T12:00:09Z",
        output_refs=(index_projection_ref,),
        metrics={
            "descriptor_count": len(result.candidates),
            "lsh_input_families": 3,
            "embedding_calls": 0,
        },
    )

    selected = next(
        (
            candidate
            for candidate in result.candidates
            if candidate.qualified_name == "canonical_json_bytes"
        ),
        result.candidates[0],
    )
    pack = registry.build_pack(
        selected.revision_id,
        include_roles=(
            CapsuleRole.SOURCE,
            CapsuleRole.CONTRACT,
            CapsuleRole.DESCRIPTOR,
            CapsuleRole.GRAPH_DELTA,
            CapsuleRole.DOCUMENTATION,
        ),
    )
    encoded_pack = encode_primitive_pack(pack, registry.payloads_for(pack))
    pack_digest = sha256_digest(encoded_pack)
    (OUTPUT / "selected-candidate.tcgpack").write_bytes(encoded_pack)

    session_ledger = PromptSessionLedger()
    session = PromptSession.create(
        tenant_id="taedri-poc",
        workspace_id="taedri-codegraph-real-source",
        repository_snapshot_id=result.generation_run_id,
        harness=HarnessRef(
            "taedri.local-search-first-harness",
            "1.0.0",
            sha256_digest(b"digest-only:D0-D4:no-model-execution"),
            "mcp-compatible-reference",
        ),
        policy_digest=sha256_digest(b"candidate-only:no-auto-promotion:no-model-execution"),
        privacy_mode=PromptPrivacyMode.DIGEST_ONLY,
        started_at="2026-07-16T12:01:00Z",
    )
    session_ledger.start(session, actor="local-coding-harness")
    request_digest = sha256_digest(b"find a deterministic canonical JSON byte encoder")
    session_ledger.record(
        session.identity.id,
        SessionEventKind.REQUEST_CAPTURED,
        actor="local-coding-harness",
        occurred_at="2026-07-16T12:01:01Z",
        input_refs=(request_digest,),
        attributes={"capture": "digest_only", "intent": "reuse_search"},
    )
    session_ledger.record(
        session.identity.id,
        SessionEventKind.SEARCH_RECEIPT,
        actor="local-candidate-index",
        occurred_at="2026-07-16T12:01:02Z",
        input_refs=(request_digest, index_projection_ref),
        output_refs=(canonical_digest({"selected": selected.identity.id, "query": request_digest}),),
        attributes={
            "candidate_count": len(result.candidates),
            "lanes": ["exact", "lexical", "blocking", "lsh-input"],
            "disclosure_depth": "D1",
        },
    )
    session_ledger.record(
        session.identity.id,
        SessionEventKind.CANDIDATE_SELECTED,
        actor="local-coding-harness",
        occurred_at="2026-07-16T12:01:03Z",
        output_refs=(selected.revision_id,),
        attributes={"selection_reason": "exact qualified-name and lexical descriptor match"},
    )
    session_ledger.record(
        session.identity.id,
        SessionEventKind.MATERIALIZATION_RECEIPT,
        actor="local-primitive-registry",
        occurred_at="2026-07-16T12:01:04Z",
        input_refs=(selected.revision_id,),
        output_refs=(pack_digest,),
        attributes={
            "roles": [role.value for role in (CapsuleRole.SOURCE, CapsuleRole.CONTRACT, CapsuleRole.DESCRIPTOR, CapsuleRole.GRAPH_DELTA)],
            "disclosure_depth": "D4",
            "pack_bytes": len(encoded_pack),
        },
    )
    session_ledger.record(
        session.identity.id,
        SessionEventKind.ABSTAINED,
        actor="local-coding-harness",
        occurred_at="2026-07-16T12:01:05Z",
        attributes={"reason_code": "model_and_independent_verifier_not_configured"},
    )
    session_ledger.record(
        session.identity.id,
        SessionEventKind.SESSION_CLOSED,
        actor="local-coding-harness",
        occurred_at="2026-07-16T12:01:06Z",
    )

    candidate_records = [candidate.to_dict() for candidate in result.candidates]
    (OUTPUT / "candidates.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in candidate_records),
        "utf-8",
    )
    (OUTPUT / "submissions.jsonl").write_text(
        "".join(
            json.dumps(submission.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            for submission in intake.submissions.values()
        ),
        "utf-8",
    )
    (OUTPUT / "intake-events.jsonl").write_text(
        "".join(
            json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
            for event in intake.events
        ),
        "utf-8",
    )
    search_records: list[dict[str, object]] = []
    for candidate in result.candidates:
        descriptor = json.loads(registry.blobs[candidate.descriptor_digest])
        search_records.append(
            {
                "candidate_id": candidate.identity.id,
                "primitive_id": candidate.primitive.identity.id,
                "revision_id": candidate.revision_id,
                "descriptor_digest": candidate.descriptor_digest,
                "descriptor": descriptor,
            }
        )
    (OUTPUT / "search-index.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in search_records),
        "utf-8",
    )
    with (OUTPUT / "candidate-summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "candidate_id",
                "handle",
                "module",
                "qualified_name",
                "entity_kind",
                "source_path",
                "start_line",
                "end_line",
                "positional_arity",
                "call_count",
                "intake_state",
                "license_evidence_state",
            ]
        )
        for candidate in result.candidates:
            writer.writerow(
                [
                    candidate.identity.id,
                    f"{candidate.primitive.namespace}/{candidate.primitive.name}",
                    candidate.module,
                    candidate.qualified_name,
                    candidate.entity_kind,
                    candidate.source_path,
                    candidate.start_line,
                    candidate.end_line,
                    candidate.positional_arity,
                    len(candidate.call_labels),
                    candidate.intake_state,
                    LicenseEvidenceState.UNKNOWN.value,
                ]
            )
    (OUTPUT / "graphs" / "primitive-candidates.graphml").write_text(
        _graphml(candidate_records), "utf-8"
    )
    (OUTPUT / "graphs" / "primitive-candidates.mmd").write_text(
        _mermaid(candidate_records), "utf-8"
    )
    _write_json(
        OUTPUT / "worker-receipts.json",
        {
            "schema_version": "1.0.0",
            "jobs": [job.to_dict() for job in (extract_job, index_job)],
            "events": [event.to_dict() for event in workers.events],
        },
    )
    _write_json(
        OUTPUT / "harness-session.json",
        {
            "schema_version": "1.0.0",
            "session": session.to_dict(),
            "events": [event.to_dict() for event in session_ledger.events],
        },
    )

    business_model = json.loads((ROOT / "architecture" / "business-model.v1.json").read_text("utf-8"))
    compact_candidates = [
        {
            "id": candidate.identity.id,
            "handle": f"{candidate.primitive.namespace}/{candidate.primitive.name}",
            "module": candidate.module,
            "qualified_name": candidate.qualified_name,
            "kind": candidate.entity_kind,
            "path": candidate.source_path,
            "lines": [candidate.start_line, candidate.end_line],
            "arity": candidate.positional_arity,
            "calls": list(candidate.call_labels),
            "tokens": list(candidate.lexical_tokens),
            "summary": candidate.doc_summary,
            "state": candidate.intake_state,
            "license": LicenseEvidenceState.UNKNOWN.value,
            "revision_id": candidate.revision_id,
            "contract_digest": candidate.contract_digest,
            "descriptor_digest": candidate.descriptor_digest,
        }
        for candidate in result.candidates
    ]
    console_data = {
        "schema_version": "1.0.0",
        "evidence_class": "real-repository-source-candidate-poc",
        "summary": result.summary(),
        "candidates": compact_candidates,
        "operations": {
            "intake_event_count": len(intake.events),
            "worker_jobs": [job.to_dict() for job in (extract_job, index_job)],
            "worker_events": [event.to_dict() for event in workers.events],
            "session": session.to_dict(),
            "session_events": [event.to_dict() for event in session_ledger.events],
        },
        "business_model": business_model,
        "selected_candidate": selected.identity.id,
        "selected_pack": {"digest": pack_digest, "size_bytes": len(encoded_pack)},
    }
    _write_json(OUTPUT / "registry-console-data.json", console_data)
    manifest = {
        "schema_version": "1.0.0",
        "evidence_class": "real-source-static-candidate-poc-not-production-authorization",
        "source": {
            "uri": SOURCE_URI,
            "local_scope": SOURCE_ROOT.relative_to(ROOT).as_posix(),
            "source_revision": None,
            "content_root_digest": result.root_digest,
            "license_expression": None,
            "license_evidence_state": LicenseEvidenceState.UNKNOWN.value,
        },
        "factory": result.summary(),
        "artifacts": {
            "candidate_jsonl": "candidates.jsonl",
            "submission_jsonl": "submissions.jsonl",
            "intake_event_jsonl": "intake-events.jsonl",
            "search_index_jsonl": "search-index.jsonl",
            "candidate_csv": "candidate-summary.csv",
            "call_graph_graphml": "graphs/primitive-candidates.graphml",
            "call_graph_mermaid": "graphs/primitive-candidates.mmd",
            "console_data": "registry-console-data.json",
            "selected_pack": "selected-candidate.tcgpack",
            "worker_receipts": "worker-receipts.json",
            "harness_session": "harness-session.json",
        },
        "intake": {
            "submission_count": len(intake.submissions),
            "event_count": len(intake.events),
            "states": sorted(
                {intake.state(submission_id).value for submission_id in intake.submissions}
            ),
            "promoted_count": 0,
        },
        "worker": {
            "job_count": len(workers.jobs),
            "event_count": len(workers.events),
            "states": {job_id: workers.state(job_id).value for job_id in workers.jobs},
        },
        "harness_session": {
            "session_id": session.identity.id,
            "privacy_mode": session.privacy_mode.value,
            "event_kinds": [event.event_kind.value for event in session_ledger.events],
            "terminal_outcome": "abstained",
            "model_calls": 0,
            "verification_calls": 0,
        },
        "selected_candidate": selected.to_dict(),
        "selected_pack": {
            "digest": pack_digest,
            "size_bytes": len(encoded_pack),
            "identity": pack.identity.id,
        },
    }
    _write_json(OUTPUT / "candidate-manifest.json", manifest)
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), **result.summary()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
