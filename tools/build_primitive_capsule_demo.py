#!/usr/bin/env python3
"""Build a real-source primitive capsule and a selective downloadable pack."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest  # noqa: E402
from taedri_codegraph.contracts import ProducerRef  # noqa: E402
from taedri_codegraph.identity import IdentityRecord  # noqa: E402
from taedri_codegraph.primitive_capsules import (  # noqa: E402
    CapsuleRole,
    PrimitiveRegistry,
    PrimitiveTreeEntry,
    RefKind,
    decode_primitive_pack,
    encode_primitive_pack,
)

OUTPUT = ROOT / "eval" / "results" / "primitive-capsule-2026-07-16"


def main() -> int:
    registry = PrimitiveRegistry()
    producer = ProducerRef(
        "taedri.tool.build-primitive-capsule-demo",
        "1.0.0",
        sha256_digest(Path(__file__).read_bytes()),
    )
    handle = registry.register_handle("taedri.core", "canonical-identity-encoding")
    source_bytes = (ROOT / "src" / "taedri_codegraph" / "canonical.py").read_bytes()
    test_bytes = (ROOT / "tests" / "unit" / "test_identity.py").read_bytes()
    contract_bytes = canonical_json_bytes(
        {
            "schema_version": "1.0.0",
            "capability": "deterministic canonical CBOR/JSON and SHA-256 identity encoding",
            "inputs": ["identity-safe Python primitives", "bytes"],
            "outputs": ["canonical bytes", "sha256-prefixed digest"],
            "effects": [],
            "limitations": ["floats are forbidden in exact identity keys"],
        }
    )
    graph_bytes = canonical_json_bytes(
        {
            "schema_version": "1.0.0",
            "source": "src/taedri_codegraph/canonical.py",
            "edges": [
                ["canonical_digest", "calls", "canonical_cbor"],
                ["canonical_digest", "calls", "sha256_digest"],
                ["sha256_digest", "calls", "hashlib.sha256"],
            ],
            "claim_scope": "reviewed demo neighborhood; not a complete analyzer epoch",
        }
    )
    source = registry.put_blob(source_bytes, "text/x-python")
    tests = registry.put_blob(test_bytes, "text/x-python")
    contract = registry.put_blob(
        contract_bytes, "application/vnd.taedri.primitive.contract.v1+json"
    )
    graph = registry.put_blob(
        graph_bytes, "application/vnd.taedri.codegraph.edges.v1+json"
    )
    tree = registry.create_tree(
        (
            PrimitiveTreeEntry("src/canonical.py", CapsuleRole.SOURCE, source),
            PrimitiveTreeEntry("contract.json", CapsuleRole.CONTRACT, contract),
            PrimitiveTreeEntry("tests/test_identity.py", CapsuleRole.TEST, tests),
            PrimitiveTreeEntry("graph/neighborhood.json", CapsuleRole.GRAPH_DELTA, graph),
        )
    )
    graph_epoch_id = IdentityRecord.create(
        "graph_epoch", {"demo_tree_id": tree.identity.id, "scope": "reviewed-neighborhood"}
    ).id
    initial = registry.commit(
        primitive=handle,
        tree_id=tree.identity.id,
        contract_digest=contract.digest,
        graph_epoch_id=graph_epoch_id,
        producer=producer,
        generation_run_id=IdentityRecord.create(
            "generation_run", {"tool": producer.to_dict(), "tree_id": tree.identity.id}
        ).id,
        evidence_ids=(sha256_digest(test_bytes),),
        author="taedri-demo-builder",
        created_at="2026-07-16T12:00:00Z",
        message="Package existing canonical identity implementation",
    )
    registry.update_ref(
        primitive=handle,
        ref_kind=RefKind.BRANCH,
        ref_name="main",
        new_revision_id=initial.identity.id,
        expected_revision_id=None,
        actor="taedri-demo-builder",
        updated_at="2026-07-16T12:00:00Z",
    )
    registry.update_ref(
        primitive=handle,
        ref_kind=RefKind.TAG,
        ref_name="poc-v1",
        new_revision_id=initial.identity.id,
        expected_revision_id=None,
        actor="taedri-demo-builder",
        updated_at="2026-07-16T12:00:01Z",
    )
    fork = registry.fork(
        source_revision_id=initial.identity.id,
        target_namespace="taedri.demo",
        target_name="canonical-identity-encoding",
        branch_name="main",
        producer=producer,
        author="taedri-demo-builder",
        created_at="2026-07-16T12:00:02Z",
        message="Demonstrate cross-namespace fork lineage",
    )
    merged = registry.merge(
        primitive=handle,
        branch_name="main",
        current_revision_id=initial.identity.id,
        merged_revision_id=fork.identity.id,
        result_tree_id=tree.identity.id,
        contract_digest=contract.digest,
        graph_epoch_id=graph_epoch_id,
        producer=producer,
        author="taedri-demo-builder",
        created_at="2026-07-16T12:00:03Z",
        message="Demonstrate reviewed two-parent merge",
    )
    pack = registry.build_pack(
        merged.identity.id,
        include_roles=(
            CapsuleRole.SOURCE,
            CapsuleRole.CONTRACT,
            CapsuleRole.TEST,
            CapsuleRole.GRAPH_DELTA,
        ),
        have_digests=(source.digest,),
        include_history=True,
    )
    encoded = encode_primitive_pack(pack, registry.payloads_for(pack))
    decoded_manifest, decoded_payloads = decode_primitive_pack(encoded)
    if decoded_manifest["identity"]["id"] != pack.identity.id:
        raise RuntimeError("pack round-trip identity mismatch")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pack_path = OUTPUT / "canonical-identity-encoding.tcgpack"
    pack_path.write_bytes(encoded)
    report = {
        "schema_version": "1.0.0",
        "evidence_class": "transport-and-history-poc-not-production-authorization",
        "primitive": handle.to_dict(),
        "tree": tree.to_dict(),
        "initial_revision": initial.to_dict(),
        "fork_revision": fork.to_dict(),
        "merged_revision": merged.to_dict(),
        "ref_updates": [update.to_dict() for update in registry.ref_updates],
        "pack": pack.to_dict(),
        "pack_file": pack_path.name,
        "pack_digest": sha256_digest(encoded),
        "pack_bytes": len(encoded),
        "decoded_blob_count": len(decoded_payloads),
        "source_blob_assumed_cached": source.digest,
        "source_bytes_omitted_from_pack": source.size_bytes,
    }
    (OUTPUT / "primitive-capsule-demo.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), **report["pack"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
