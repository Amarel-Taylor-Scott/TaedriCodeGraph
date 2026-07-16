#!/usr/bin/env python3
"""Stage, verify, release, search, download, and report the reference primitive."""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest
from taedri_codegraph.primitive_capsules import decode_primitive_pack
from taedri_codegraph.primitive_repository import SQLitePrimitiveRepository
from taedri_codegraph.primitives.acceptance import LocalPythonPrimitiveVerifier
from taedri_codegraph.primitives.bundle import load_primitive_directory
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


CREATED_AT = "2026-07-16T22:00:00Z"
VERIFIED_AT = "2026-07-16T22:01:00Z"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--primitive",
        default="examples/primitives/normalize-text",
        help="repository-native primitive directory",
    )
    parser.add_argument(
        "--output",
        default="eval/results/reference-primitive-acceptance-2026-07-16",
        help="report output directory",
    )
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    primitive_path = (root / arguments.primitive).resolve()
    output = (root / arguments.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    bundle = load_primitive_directory(primitive_path)

    with tempfile.TemporaryDirectory(prefix="taedri-reference-primitive-") as temporary:
        control = SQLiteControlPlane(Path(temporary) / "control.sqlite")
        tenant = control.create_tenant(
            Tenant.create(
                slug="reference-acceptance",
                display_name="Reference primitive acceptance",
                created_at=CREATED_AT,
            )
        )
        repository = SQLitePrimitiveRepository(control)
        staged = repository.stage(
            tenant.identity.id,
            namespace=bundle.namespace,
            name=bundle.name,
            files=bundle.files,
            contract_path=bundle.contract_path,
            ref_kind=bundle.ref_kind,
            ref_name=bundle.ref_name,
            expected_revision_id=None,
            actor="taedri.example.author.normalize-text-v1",
            created_at=CREATED_AT,
            message=bundle.message,
        )
        hidden_before_release = repository.list(tenant.identity.id) == ()
        try:
            repository.pack(
                tenant.identity.id,
                bundle.namespace,
                bundle.name,
                ref_kind=bundle.ref_kind,
                ref_name=bundle.ref_name,
            )
        except LookupError:
            download_denied_before_release = True
        else:
            download_denied_before_release = False
        accepted = LocalPythonPrimitiveVerifier(
            repository,
            verifier_id="taedri.verifier.reference-worker-v1",
        ).verify_and_release(
            tenant.identity.id,
            staged.revision.identity.id,
            ref_kind=bundle.ref_kind,
            ref_name=bundle.ref_name,
            authorizer_id="taedri.release-manager.reference-v1",
            policy_decision_id=bundle.policy_decision_id,
            verified_at=VERIFIED_AT,
            assurance_level=bundle.assurance_level,
        )
        search_results = repository.list(
            tenant.identity.id, query="unicode whitespace"
        )
        pack, encoded = repository.pack(
            tenant.identity.id,
            bundle.namespace,
            bundle.name,
            ref_kind=bundle.ref_kind,
            ref_name=bundle.ref_name,
        )
        manifest, payloads = decode_primitive_pack(encoded)
        source_downloaded = any(b"def normalize_text" in item for item in payloads.values())
        table_names = (
            "primitive_handle",
            "primitive_blob",
            "primitive_tree",
            "primitive_revision",
            "primitive_ref",
            "primitive_ref_update",
            "primitive_release",
            "primitive_release_revocation",
            "candidate_submission",
        )
        with control._connect() as connection:
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in table_names
            }
        run = {
            "schema_version": "1.0.0",
            "status": "passed",
            "claim_scope": "real local Python reference primitive; no model or network",
            "primitive_directory": primitive_path.relative_to(root).as_posix(),
            "primitive_id": accepted.released.release.primitive_id,
            "revision_id": accepted.released.release.revision_id,
            "release_id": accepted.released.release.identity.id,
            "tree_id": accepted.released.release.tree_id,
            "source_digest": accepted.released.release.source_digest,
            "acceptance_receipt_id": accepted.acceptance.identity.id,
            "acceptance_receipt_ref": accepted.acceptance_receipt_ref,
            "assurance_level": accepted.released.release.assurance_level.value,
            "proofs": [item.value for item in accepted.released.release.proofs],
            "acceptance_proofs": [item.value for item in accepted.acceptance.proofs],
            "executed_case_count": accepted.executed_case_count,
            "hidden_before_release": hidden_before_release,
            "download_denied_before_release": download_denied_before_release,
            "search_result_count": len(search_results),
            "source_downloaded": source_downloaded,
            "pack_id": pack.identity.id,
            "pack_digest": sha256_digest(encoded),
            "pack_size_bytes": len(encoded),
            "pack_payload_count": len(payloads),
            "manifest_identity_valid": manifest["identity"]["id"] == pack.identity.id,
            "record_counts": counts,
        }
        if not all(
            (
                hidden_before_release,
                download_denied_before_release,
                len(search_results) == 1,
                source_downloaded,
                run["manifest_identity_valid"],
                counts["primitive_release"] == 1,
            )
        ):
            raise SystemExit("reference primitive acceptance invariants failed")
        (output / "run.json").write_bytes(canonical_json_bytes(run) + b"\n")
        (output / "normalize-text.tcgpack").write_bytes(encoded)
        with (output / "record-counts.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(("table", "records"))
            writer.writerows(sorted(counts.items()))
        (output / "README.md").write_text(_report(run), encoding="utf-8")
    print(json.dumps(run, indent=2, sort_keys=True))


def _report(run: dict[str, object]) -> str:
    rows = "\n".join(
        f"| `{name}` | {count} |"
        for name, count in sorted(dict(run["record_counts"]).items())
    )
    return f"""# Reference primitive acceptance evidence

Status: **passed**

This is a real execution receipt for the checked-in `normalize-text` primitive. The
capsule was staged, proven absent from public search/download, materialized, executed
against positive/boundary/negative vectors, released under `{run['assurance_level']}`
assurance, searched, and downloaded as a digest-checked pack.

- Release: `{run['release_id']}`
- Acceptance receipt: `{run['acceptance_receipt_id']}`
- Executed cases: {run['executed_case_count']}
- Pack payloads: {run['pack_payload_count']}
- Pack bytes: {run['pack_size_bytes']}

| SQLite record type | Records |
|---|---:|
{rows}

The local verifier is a working trusted-source bootstrap worker, not a security
boundary for hostile code. Untrusted execution requires the documented isolated
runtime deployment gate.
"""


if __name__ == "__main__":
    main()
