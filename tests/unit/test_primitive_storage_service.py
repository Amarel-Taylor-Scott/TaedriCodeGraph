from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.mechanisms import MechanismDefinition, MechanismResult, RunStatus
from taedri_codegraph.primitive_capsules import CapsuleRole, RefKind
from taedri_codegraph.primitive_repository import PrimitiveFileInput, SQLitePrimitiveRepository
from taedri_codegraph.primitives.storage import (
    PrimitiveStorageService,
    PrimitiveWriteRequest,
)
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


class _SearchProjection:
    definition = MechanismDefinition(
        "taedri.test.project_search",
        "1.0.0",
        PrimitiveStorageService.PROJECT,
        True,
    )

    def project(self, request, staged):
        return MechanismResult(
            {"revision_id": staged.revision.identity.id},
            1_000_000,
            (request.evidence_ids[0],),
        )


class PrimitiveStorageServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        control = SQLiteControlPlane(Path(self.temporary.name) / "control.sqlite")
        self.tenant = control.create_tenant(
            Tenant.create(
                slug="storage-waterfall",
                display_name="Storage waterfall",
                created_at="2026-07-16T12:00:00Z",
            )
        )
        self.service = PrimitiveStorageService(
            SQLitePrimitiveRepository(control), projections=(_SearchProjection(),)
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_atomic_stage_runs_required_then_projection_stages(self) -> None:
        request = PrimitiveWriteRequest(
            self.tenant.identity.id,
            "acme",
            "normalize",
            (
                PrimitiveFileInput(
                    "src/normalize.py",
                    CapsuleRole.SOURCE,
                    "text/x-python",
                    b"def normalize(value): return value.strip()\n",
                ),
                PrimitiveFileInput(
                    "contract.json",
                    CapsuleRole.CONTRACT,
                    "application/json",
                    b'{"input":"str","output":"str"}',
                ),
                PrimitiveFileInput(
                    "descriptor.json",
                    CapsuleRole.DESCRIPTOR,
                    "application/json",
                    b'{"keywords":["normalize","strip"]}',
                ),
            ),
            "contract.json",
            RefKind.BRANCH,
            "main",
            None,
            "test-suite",
            "2026-07-16T12:01:00Z",
            "publish through storage waterfall",
            evidence_ids=("evidence:reviewed",),
        )
        receipt = self.service.stage(request)
        self.assertEqual(receipt.waterfall.status, RunStatus.SUCCEEDED)
        self.assertEqual(
            [item.stage_key for item in receipt.waterfall.receipts],
            [
                PrimitiveStorageService.VALIDATE,
                PrimitiveStorageService.PERSIST,
                PrimitiveStorageService.PROJECT,
            ],
        )
        self.assertTrue(receipt.staged.revision.identity.id.startswith("uceg:v1:"))
        self.assertTrue(receipt.content_manifest_digest.startswith("sha256:"))
        self.assertNotIn("def normalize", str(receipt.waterfall.to_dict()))

    def test_contract_and_source_are_required_before_repository_mutation(self) -> None:
        with self.assertRaisesRegex(ValueError, "source-role"):
            PrimitiveWriteRequest(
                self.tenant.identity.id,
                "acme",
                "invalid",
                (
                    PrimitiveFileInput(
                        "contract.json",
                        CapsuleRole.CONTRACT,
                        "application/json",
                        b"{}",
                    ),
                ),
                "contract.json",
                RefKind.BRANCH,
                "main",
                None,
                "test-suite",
                "2026-07-16T12:01:00Z",
                "invalid",
            )


if __name__ == "__main__":
    unittest.main()
