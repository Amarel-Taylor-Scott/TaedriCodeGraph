from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.pipelines import (
    DiscoveryKind,
    DiscoveryPolicy,
    SourceDiscoveryEvent,
    SourceDiscoveryRouter,
)
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


class SourceDiscoveryRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.control = SQLiteControlPlane(Path(self.temporary.name) / "control.sqlite")
        self.tenant = self.control.create_tenant(
            Tenant.create(
                slug="discovery",
                display_name="Discovery",
                created_at="2026-07-16T18:00:00Z",
            )
        )
        self.router = SourceDiscoveryRouter(
            self.control,
            DiscoveryPolicy(("pypi-poller", "github-webhook")),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_pypi_event_is_replay_safe_and_retains_lineage(self) -> None:
        event = SourceDiscoveryEvent.create(
            source="pypi-poller",
            source_event_id="usaddress:0.5.10",
            kind=DiscoveryKind.PYPI_RELEASE,
            subject="pypi:usaddress==0.5.10",
            occurred_at="2026-07-16T18:01:00Z",
            data={"package": "usaddress", "version": "0.5.10"},
        )
        first = self.router.enqueue(self.tenant.identity.id, event)
        replay = self.router.enqueue(self.tenant.identity.id, event)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(first.job_id, replay.job_id)
        payload = self.control.job_payload(self.tenant.identity.id, first.payload_ref)
        self.assertEqual(payload["discovery"]["event_id"], event.identity.id)
        self.assertEqual(payload["operation"], "ingest_pypi_wheel")

    def test_github_inventory_routes_the_conditional_capability(self) -> None:
        event = SourceDiscoveryEvent.create(
            source="github-webhook",
            source_event_id="delivery-123",
            kind=DiscoveryKind.GITHUB_COMMIT,
            subject="github:owner/repo@" + "a" * 40,
            occurred_at="2026-07-16T18:02:00Z",
            data={
                "repository": "owner/repo",
                "commit_sha": "a" * 40,
                "analysis": "inventory",
            },
        )
        receipt = self.router.enqueue(self.tenant.identity.id, event)
        stored = self.router.jobs.get(self.tenant.identity.id, receipt.job_id)
        self.assertIn("polyglot-inventory", stored.job.required_capabilities)
        self.assertNotIn("python-ast", stored.job.required_capabilities)

    def test_untrusted_source_is_rejected_before_payload_storage(self) -> None:
        event = SourceDiscoveryEvent.create(
            source="unknown-scraper",
            source_event_id="event",
            kind=DiscoveryKind.PYPI_RELEASE,
            subject="pypi:demo==1",
            occurred_at="2026-07-16T18:03:00Z",
            data={"package": "demo", "version": "1"},
        )
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            self.router.enqueue(self.tenant.identity.id, event)


if __name__ == "__main__":
    unittest.main()
