from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from taedri_codegraph.metering import (
    MeteringError,
    QuotaExceeded,
    SQLiteMeteringRepository,
)
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def timestamp(offset: int = 0) -> str:
    return (NOW + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


class SQLiteMeteringRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.control = SQLiteControlPlane(
            Path(self.temporary.name) / "control.sqlite"
        )
        self.tenant = self.control.create_tenant(
            Tenant.create(slug="metered", display_name="Metered", created_at=timestamp())
        )
        self.metering = SQLiteMeteringRepository(self.control)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_limit_revisions_are_append_only_and_time_selected(self) -> None:
        first = self.metering.set_limit(
            self.tenant.identity.id,
            metric="api.request",
            window_seconds=60,
            hard_limit=10,
            effective_at=timestamp(),
            actor="operator:one",
            reason="initial trial allocation",
        )
        second = self.metering.set_limit(
            self.tenant.identity.id,
            metric="api.request",
            window_seconds=60,
            hard_limit=20,
            effective_at=timestamp(120),
            actor="operator:two",
            reason="approved expansion",
        )
        self.assertEqual(
            self.metering.effective_limit(
                self.tenant.identity.id, "api.request", at=timestamp(60)
            ),
            first,
        )
        self.assertEqual(
            self.metering.effective_limit(
                self.tenant.identity.id, "api.request", at=timestamp(180)
            ),
            second,
        )
        self.assertEqual(
            self.metering.set_limit(
                self.tenant.identity.id,
                metric="api.request",
                window_seconds=60,
                hard_limit=10,
                effective_at=timestamp(),
                actor="operator:one",
                reason="initial trial allocation",
            ),
            first,
        )
        self.assertEqual(len(self.metering.limit_history(self.tenant.identity.id)), 2)

    def test_consumption_is_idempotent_and_quota_failure_is_not_recorded(self) -> None:
        self.metering.set_limit(
            self.tenant.identity.id,
            metric="search.request",
            window_seconds=60,
            hard_limit=2,
            effective_at=timestamp(),
            actor="system",
            reason="test allocation",
        )
        first = self.metering.consume(
            self.tenant.identity.id,
            metric="search.request",
            quantity=1,
            occurred_at=timestamp(1),
            idempotency_key="request-1",
            resource_id="request-1",
            dimensions={"route": "/v1/search"},
        )
        self.assertEqual(
            self.metering.consume(
                self.tenant.identity.id,
                metric="search.request",
                quantity=1,
                occurred_at=timestamp(1),
                idempotency_key="request-1",
                resource_id="request-1",
                dimensions={"route": "/v1/search"},
            ),
            first,
        )
        self.metering.consume(
            self.tenant.identity.id,
            metric="search.request",
            quantity=1,
            occurred_at=timestamp(2),
            idempotency_key="request-2",
            resource_id="request-2",
        )
        with self.assertRaises(QuotaExceeded) as raised:
            self.metering.consume(
                self.tenant.identity.id,
                metric="search.request",
                quantity=1,
                occurred_at=timestamp(3),
                idempotency_key="request-3",
                resource_id="request-3",
            )
        self.assertEqual(raised.exception.used, 2)
        self.assertEqual(len(self.metering.receipts(self.tenant.identity.id)), 2)
        self.assertEqual(self.metering.summary(self.tenant.identity.id)[0]["quantity"], 2)

    def test_idempotency_conflict_and_tenant_isolation_fail_closed(self) -> None:
        receipt = self.metering.consume(
            self.tenant.identity.id,
            metric="storage.byte",
            quantity=10,
            occurred_at=timestamp(1),
            idempotency_key="object-a",
            resource_id="sha256:" + "a" * 64,
        )
        with self.assertRaisesRegex(MeteringError, "cannot describe two"):
            self.metering.consume(
                self.tenant.identity.id,
                metric="storage.byte",
                quantity=11,
                occurred_at=timestamp(1),
                idempotency_key="object-a",
                resource_id="sha256:" + "a" * 64,
            )
        other = self.control.create_tenant(
            Tenant.create(slug="other", display_name="Other", created_at=timestamp(2))
        )
        self.assertEqual(self.metering.receipts(other.identity.id), ())
        self.assertEqual(receipt.tenant_id, self.tenant.identity.id)

    def test_concurrent_admission_cannot_oversubscribe_a_fixed_window(self) -> None:
        barrier = threading.Barrier(4)
        admitted: list[str] = []
        denied: list[str] = []
        failures: list[BaseException] = []

        def attempt(number: int) -> None:
            try:
                barrier.wait()
                self.metering.consume(
                    self.tenant.identity.id,
                    metric="worker.job",
                    quantity=1,
                    occurred_at=timestamp(1),
                    idempotency_key=f"job-{number}",
                    resource_id=f"job-{number}",
                    fallback_window_seconds=60,
                    fallback_hard_limit=2,
                )
                admitted.append(str(number))
            except QuotaExceeded:
                denied.append(str(number))
            except BaseException as exc:  # pragma: no cover - diagnostic guard
                failures.append(exc)

        threads = [threading.Thread(target=attempt, args=(number,)) for number in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(len(admitted), 2)
        self.assertEqual(len(denied), 2)
        self.assertEqual(len(self.metering.receipts(self.tenant.identity.id)), 2)


if __name__ == "__main__":
    unittest.main()
