from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.candidate_repository import SQLiteCandidateRepository
from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.contracts import ProducerRef
from taedri_codegraph.intake import (
    CandidateIntakeError,
    CandidateIntakeLedger,
    CandidateState,
)
from taedri_codegraph.primitive_capsules import PrimitiveRegistry
from taedri_codegraph.primitive_factory import PrimitiveFactory
from taedri_codegraph.primitive_repository import SQLitePrimitiveRepository
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


class CandidateRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "control.sqlite"
        self.control = SQLiteControlPlane(self.database)
        self.tenant = self.control.create_tenant(
            Tenant.create(
                slug="candidate-test",
                display_name="Candidate test",
                created_at="2026-07-16T13:00:00Z",
            )
        )
        source = self.root / "source"
        source.mkdir()
        self.source = source
        (source / "normalize.py").write_text(
            "def normalize(value: str) -> str:\n"
            "    return ' '.join(value.split())\n",
            "utf-8",
        )
        self.registry = PrimitiveRegistry()
        self.ledger = CandidateIntakeLedger()
        self.result = PrimitiveFactory().generate(
            source,
            registry=self.registry,
            intake=self.ledger,
            producer=ProducerRef(
                "taedri.test.factory", "1.0.0", sha256_digest(b"factory-config")
            ),
            package_name="fixture",
            namespace="fixture.candidates",
            source_uri="git+https://example.invalid/fixture",
            source_revision="abc123",
            created_at="2026-07-16T13:01:00Z",
        )
        SQLitePrimitiveRepository(self.control).import_registry(
            self.tenant.identity.id,
            self.registry,
            actor="worker:factory",
            imported_at="2026-07-16T13:02:00Z",
            resource_id=self.result.identity.id,
        )
        self.repository = SQLiteCandidateRepository(self.control)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_import_is_restart_safe_searchable_and_idempotent(self) -> None:
        imported = self.repository.import_ledger(
            self.tenant.identity.id,
            self.ledger,
            actor="worker:factory",
            imported_at="2026-07-16T13:02:01Z",
            resource_id=self.result.identity.id,
        )
        self.assertEqual(imported.submissions_created, 1)
        self.assertEqual(imported.events_created, 4)
        restarted = SQLiteCandidateRepository(SQLiteControlPlane(self.database))
        items = restarted.list(
            self.tenant.identity.id,
            state=CandidateState.INDEXED_CANDIDATE,
            query="normalize",
        )
        self.assertEqual(len(items), 1)
        submission_id = self.result.candidates[0].submission_id or ""
        self.assertEqual(restarted.get(self.tenant.identity.id, submission_id)["current_state"], "indexed_candidate")
        repeated = restarted.import_ledger(
            self.tenant.identity.id,
            self.ledger,
            actor="worker:factory",
            imported_at="2026-07-16T13:02:02Z",
            resource_id=self.result.identity.id,
        )
        self.assertEqual(repeated.submissions_created, 0)
        self.assertEqual(repeated.events_created, 0)

    def test_curation_uses_domain_policy_and_never_regresses_on_reimport(self) -> None:
        self.repository.import_ledger(
            self.tenant.identity.id,
            self.ledger,
            actor="worker:factory",
            imported_at="2026-07-16T13:02:01Z",
            resource_id=self.result.identity.id,
        )
        submission_id = self.result.candidates[0].submission_id or ""
        with self.assertRaises(CandidateIntakeError):
            self.repository.transition(
                self.tenant.identity.id,
                submission_id,
                CandidateState.CURATED_CANDIDATE,
                actor="taedri.test.factory",
                occurred_at="2026-07-16T13:03:00Z",
                reason="producer self approval",
                evidence_ids=("verify:fixture",),
                policy_decision_id="policy:fixture",
            )
        curated = self.repository.transition(
            self.tenant.identity.id,
            submission_id,
            CandidateState.CURATED_CANDIDATE,
            actor="verifier:independent",
            occurred_at="2026-07-16T13:04:00Z",
            reason="independent structural and contract checks passed",
            evidence_ids=("verify:fixture",),
            policy_decision_id="policy:fixture",
        )
        self.assertEqual(curated.to_state, CandidateState.CURATED_CANDIDATE)
        self.repository.import_ledger(
            self.tenant.identity.id,
            self.ledger,
            actor="worker:factory",
            imported_at="2026-07-16T13:05:00Z",
            resource_id=self.result.identity.id,
        )
        self.assertEqual(
            self.repository.get(self.tenant.identity.id, submission_id)["current_state"],
            "curated_candidate",
        )

    def test_another_tenant_cannot_see_candidates(self) -> None:
        self.repository.import_ledger(
            self.tenant.identity.id,
            self.ledger,
            actor="worker:factory",
            imported_at="2026-07-16T13:02:01Z",
            resource_id=self.result.identity.id,
        )
        other = self.control.create_tenant(
            Tenant.create(
                slug="candidate-other",
                display_name="Other",
                created_at="2026-07-16T13:10:00Z",
            )
        )
        self.assertEqual(self.repository.list(other.identity.id), ())

    def test_later_generation_uses_an_immutable_version_ref_on_conflict(self) -> None:
        second_registry = PrimitiveRegistry()
        second = PrimitiveFactory().generate(
            self.source,
            registry=second_registry,
            producer=ProducerRef(
                "taedri.test.factory", "1.0.0", sha256_digest(b"factory-config")
            ),
            package_name="fixture",
            namespace="fixture.candidates",
            source_uri="git+https://example.invalid/fixture",
            source_revision="def456",
            created_at="2026-07-16T14:00:00Z",
        )
        suffix = second.generation_run_id.rsplit(":", 1)[-1][:16]
        imported = SQLitePrimitiveRepository(self.control).import_registry(
            self.tenant.identity.id,
            second_registry,
            actor="worker:factory",
            imported_at="2026-07-16T14:01:00Z",
            resource_id=second.identity.id,
            conflict_ref_suffix=suffix,
        )
        self.assertEqual(imported.refs_created, 1)
        with self.control._connect() as connection:
            refs = connection.execute(
                "SELECT ref_name FROM primitive_ref WHERE tenant_id=? ORDER BY ref_name",
                (self.tenant.identity.id,),
            ).fetchall()
        self.assertEqual(
            [str(row["ref_name"]) for row in refs],
            ["candidate", f"candidate/{suffix}"],
        )


if __name__ == "__main__":
    unittest.main()
