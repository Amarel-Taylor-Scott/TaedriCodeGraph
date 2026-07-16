from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from taedri_codegraph.portal import (
    BillingUnavailable,
    PlanCatalog,
    PlanDefinition,
    PortalService,
    RedirectSession,
    SubscriptionRepository,
    SubscriptionState,
    default_plan_catalog,
)
from taedri_codegraph.saas import SQLiteControlPlane, Tenant


class _Gateway:
    def create_checkout(self, *, tenant_id, plan, return_url):
        return RedirectSession(
            "fixture", "checkout-1", "https://billing.example/checkout-1", "2026-07-16T12:10:00Z"
        )

    def create_portal(self, *, tenant_id, provider_customer_ref, return_url):
        return RedirectSession(
            "fixture", "portal-1", "https://billing.example/portal-1", "2026-07-16T12:10:00Z"
        )


class PortalSubscriptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.control = SQLiteControlPlane(Path(self.temporary.name) / "control.sqlite")
        self.tenant = self.control.create_tenant(
            Tenant.create(
                slug="portal-test",
                display_name="Portal test",
                created_at="2026-07-16T12:00:00Z",
            )
        )
        self.catalog = default_plan_catalog()
        self.repository = SubscriptionRepository(self.control, self.catalog)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def apply(self, *, event="event-1", digest="sha256:" + "1" * 64, state=SubscriptionState.ACTIVE):
        return self.repository.apply_event(
            self.tenant.identity.id,
            plan_ref="taedri.plan.team@1.0.0",
            state=state,
            provider="fixture",
            provider_customer_ref="customer-1",
            provider_subscription_ref="subscription-1",
            effective_at="2026-07-16T12:01:00Z",
            source_event_id=event,
            source_event_digest=digest,
            actor="fixture-webhook",
        )

    def test_events_are_replay_safe_and_entitlements_derive_from_active_plan(self) -> None:
        first = self.apply()
        replay = self.apply()
        self.assertEqual(replay.identity.id, first.identity.id)
        snapshot = self.repository.entitlements(self.tenant.identity.id)
        self.assertTrue(snapshot.entitlements["taedri.entitlement.source_disclosure"])
        self.assertEqual(len(self.repository.history(self.tenant.identity.id)), 1)
        with self.assertRaisesRegex(ValueError, "changed its payload digest"):
            self.apply(digest="sha256:" + "2" * 64)

    def test_cancelled_revision_links_history_and_removes_entitlements(self) -> None:
        first = self.apply()
        cancelled = self.apply(
            event="event-2",
            digest="sha256:" + "2" * 64,
            state=SubscriptionState.CANCELLED,
        )
        self.assertEqual(cancelled.previous_revision_id, first.identity.id)
        snapshot = self.repository.entitlements(self.tenant.identity.id)
        self.assertEqual(snapshot.state, "cancelled")
        self.assertEqual(dict(snapshot.entitlements), {})

    def test_checkout_requires_allowlisted_return_and_configured_provider_plan(self) -> None:
        service = PortalService(
            self.repository,
            gateway=_Gateway(),
            allowed_return_origins=("https://app.example",),
        )
        with self.assertRaisesRegex(ValueError, "origin is not allowed"):
            service.checkout(
                self.tenant.identity.id,
                plan_ref="taedri.plan.team@1.0.0",
                return_url="https://evil.example/steal",
            )
        with self.assertRaises(BillingUnavailable):
            service.checkout(
                self.tenant.identity.id,
                plan_ref="taedri.plan.team@1.0.0",
                return_url="https://app.example/account",
            )

        configured = PlanCatalog(
            (
                PlanDefinition(
                    "taedri.plan.configured",
                    "1.0.0",
                    "Configured",
                    "Fixture provider plan",
                    {"taedri.entitlement.search_requests_per_minute": 10},
                    provider_price_ref="price_fixture",
                    commercialization_state="provider_configured",
                ),
            )
        )
        configured_service = PortalService(
            SubscriptionRepository(self.control, configured),
            gateway=_Gateway(),
            allowed_return_origins=("https://app.example",),
        )
        session = configured_service.checkout(
            self.tenant.identity.id,
            plan_ref="taedri.plan.configured@1.0.0",
            return_url="https://app.example/account",
        )
        self.assertEqual(session.provider, "fixture")


if __name__ == "__main__":
    unittest.main()
