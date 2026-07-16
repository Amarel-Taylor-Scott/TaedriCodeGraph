"""Append-only subscription state and provider-independent entitlement evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol
from urllib.parse import urlsplit

from ..canonical import canonical_digest, canonical_json_bytes, to_primitive
from ..contracts import RecordMixin
from ..identity import IdentityRecord
from ..saas import SQLiteControlPlane

_PLAN_KEY = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}$")
_ACTIVE_STATES = frozenset({"trialing", "active"})


class SubscriptionState(str, Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class PlanDefinition(RecordMixin):
    key: str
    version: str
    display_name: str
    description: str
    entitlements: Mapping[str, bool | int | str]
    public: bool = True
    provider_price_ref: str | None = None
    commercialization_state: str = "price_not_configured"

    def __post_init__(self) -> None:
        if not _PLAN_KEY.fullmatch(self.key) or not _VERSION.fullmatch(self.version):
            raise ValueError("plan key or version is invalid")
        if not self.display_name or not self.description:
            raise ValueError("plan display name and description are required")
        primitive = to_primitive(dict(self.entitlements))
        if not primitive or any(
            not _PLAN_KEY.fullmatch(str(key))
            or not isinstance(value, bool | int | str)
            for key, value in primitive.items()
        ):
            raise ValueError("plan entitlements must be namespaced scalar values")
        if self.commercialization_state not in {
            "price_not_configured",
            "provider_configured",
            "contact_sales",
        }:
            raise ValueError("plan commercialization state is invalid")
        if self.commercialization_state == "provider_configured" and not self.provider_price_ref:
            raise ValueError("configured plans require a provider price reference")
        object.__setattr__(self, "entitlements", MappingProxyType(primitive))

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"


class PlanCatalog:
    def __init__(self, plans: Iterable[PlanDefinition] = ()) -> None:
        self._plans: dict[str, PlanDefinition] = {}
        for plan in plans:
            self.register(plan)

    def register(self, plan: PlanDefinition) -> None:
        if plan.ref in self._plans:
            raise ValueError(f"plan is already registered: {plan.ref}")
        self._plans[plan.ref] = plan

    def resolve(self, plan_ref: str) -> PlanDefinition:
        try:
            return self._plans[plan_ref]
        except KeyError as exc:
            raise LookupError(f"unknown plan: {plan_ref}") from exc

    def public_plans(self) -> tuple[PlanDefinition, ...]:
        return tuple(
            plan for _, plan in sorted(self._plans.items()) if plan.public
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {key: plan.to_dict() for key, plan in sorted(self._plans.items())}
        )


@dataclass(frozen=True, slots=True)
class SubscriptionRevision(RecordMixin):
    identity: IdentityRecord
    tenant_id: str
    plan_ref: str
    state: SubscriptionState
    provider: str
    provider_customer_ref: str
    provider_subscription_ref: str
    effective_at: str
    ends_at: str | None
    source_event_id: str
    source_event_digest: str
    previous_revision_id: str | None

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        plan_ref: str,
        state: SubscriptionState,
        provider: str,
        provider_customer_ref: str,
        provider_subscription_ref: str,
        effective_at: str,
        source_event_id: str,
        source_event_digest: str,
        ends_at: str | None = None,
        previous_revision_id: str | None = None,
    ) -> "SubscriptionRevision":
        if not all(
            (
                tenant_id,
                plan_ref,
                provider,
                provider_customer_ref,
                provider_subscription_ref,
                effective_at,
                source_event_id,
            )
        ):
            raise ValueError("subscription provenance fields are required")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_event_digest):
            raise ValueError("subscription event digest must be sha256")
        key = {
            "tenant_id": tenant_id,
            "plan_ref": plan_ref,
            "state": state.value,
            "provider": provider,
            "provider_customer_ref": provider_customer_ref,
            "provider_subscription_ref": provider_subscription_ref,
            "effective_at": effective_at,
            "ends_at": ends_at,
            "source_event_id": source_event_id,
            "source_event_digest": source_event_digest,
            "previous_revision_id": previous_revision_id,
        }
        return cls(
            IdentityRecord.create("subscription_revision", key),
            tenant_id,
            plan_ref,
            state,
            provider,
            provider_customer_ref,
            provider_subscription_ref,
            effective_at,
            ends_at,
            source_event_id,
            source_event_digest,
            previous_revision_id,
        )


@dataclass(frozen=True, slots=True)
class EntitlementSnapshot(RecordMixin):
    tenant_id: str
    subscription_revision_id: str | None
    plan_ref: str | None
    state: str
    entitlements: Mapping[str, bool | int | str]
    catalog_digest: str


class SubscriptionRepository:
    """SQLite reference adapter with replay-safe provider events and revision history."""

    def __init__(self, control: SQLiteControlPlane, catalog: PlanCatalog) -> None:
        self.control = control
        self.catalog = catalog

    def apply_event(
        self,
        tenant_id: str,
        *,
        plan_ref: str,
        state: SubscriptionState,
        provider: str,
        provider_customer_ref: str,
        provider_subscription_ref: str,
        effective_at: str,
        source_event_id: str,
        source_event_digest: str,
        actor: str,
        ends_at: str | None = None,
    ) -> SubscriptionRevision:
        self.control.tenant(tenant_id)
        self.catalog.resolve(plan_ref)
        if not actor:
            raise ValueError("subscription event actor is required")
        with self.control._transaction() as connection:
            existing = connection.execute(
                "SELECT revision_id, source_event_digest FROM billing_event "
                "WHERE provider=? AND source_event_id=?",
                (provider, source_event_id),
            ).fetchone()
            if existing is not None:
                if str(existing["source_event_digest"]) != source_event_digest:
                    raise ValueError("billing event replay changed its payload digest")
                row = connection.execute(
                    "SELECT record_json FROM subscription_revision "
                    "WHERE tenant_id=? AND revision_id=?",
                    (tenant_id, str(existing["revision_id"])),
                ).fetchone()
                if row is None:
                    raise ValueError("billing event belongs to a different tenant")
                return _subscription(json.loads(str(row["record_json"])))
            previous_row = connection.execute(
                "SELECT record_json FROM subscription_revision WHERE tenant_id=? "
                "ORDER BY sequence DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
            previous = (
                _subscription(json.loads(str(previous_row["record_json"])))
                if previous_row is not None
                else None
            )
            revision = SubscriptionRevision.create(
                tenant_id=tenant_id,
                plan_ref=plan_ref,
                state=state,
                provider=provider,
                provider_customer_ref=provider_customer_ref,
                provider_subscription_ref=provider_subscription_ref,
                effective_at=effective_at,
                ends_at=ends_at,
                source_event_id=source_event_id,
                source_event_digest=source_event_digest,
                previous_revision_id=(previous.identity.id if previous else None),
            )
            connection.execute(
                "INSERT INTO subscription_revision(tenant_id, revision_id, plan_ref, state, "
                "provider, provider_customer_ref, provider_subscription_ref, effective_at, "
                "ends_at, source_event_id, record_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    revision.identity.id,
                    revision.plan_ref,
                    revision.state.value,
                    revision.provider,
                    revision.provider_customer_ref,
                    revision.provider_subscription_ref,
                    revision.effective_at,
                    revision.ends_at,
                    revision.source_event_id,
                    canonical_json_bytes(revision).decode("utf-8"),
                ),
            )
            connection.execute(
                "INSERT INTO billing_event(provider, source_event_id, tenant_id, revision_id, "
                "source_event_digest, received_at) VALUES(?, ?, ?, ?, ?, ?)",
                (
                    provider,
                    source_event_id,
                    tenant_id,
                    revision.identity.id,
                    source_event_digest,
                    effective_at,
                ),
            )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action="subscription.revision.applied",
                resource_id=revision.identity.id,
                occurred_at=effective_at,
                detail={
                    "plan_ref": plan_ref,
                    "state": state.value,
                    "provider": provider,
                    "source_event_id": source_event_id,
                    "source_event_digest": source_event_digest,
                },
            )
        return revision

    def current(self, tenant_id: str) -> SubscriptionRevision | None:
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM subscription_revision WHERE tenant_id=? "
                "ORDER BY sequence DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
        return _subscription(json.loads(str(row["record_json"]))) if row else None

    def history(self, tenant_id: str, *, limit: int = 100) -> tuple[SubscriptionRevision, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("subscription history limit must be 1..1000")
        with self.control._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM subscription_revision WHERE tenant_id=? "
                "ORDER BY sequence DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return tuple(_subscription(json.loads(str(row["record_json"]))) for row in rows)

    def entitlements(self, tenant_id: str) -> EntitlementSnapshot:
        current = self.current(tenant_id)
        if current is None:
            return EntitlementSnapshot(
                tenant_id, None, None, "none", MappingProxyType({}), self.catalog.digest
            )
        values: Mapping[str, bool | int | str] = MappingProxyType({})
        if current.state.value in _ACTIVE_STATES:
            values = self.catalog.resolve(current.plan_ref).entitlements
        return EntitlementSnapshot(
            tenant_id,
            current.identity.id,
            current.plan_ref,
            current.state.value,
            values,
            self.catalog.digest,
        )


@dataclass(frozen=True, slots=True)
class RedirectSession(RecordMixin):
    provider: str
    session_id: str
    url: str
    expires_at: str


class BillingGateway(Protocol):
    def create_checkout(
        self,
        *,
        tenant_id: str,
        plan: PlanDefinition,
        return_url: str,
    ) -> RedirectSession: ...

    def create_portal(
        self,
        *,
        tenant_id: str,
        provider_customer_ref: str,
        return_url: str,
    ) -> RedirectSession: ...


class BillingUnavailable(RuntimeError):
    pass


class PortalService:
    def __init__(
        self,
        subscriptions: SubscriptionRepository,
        *,
        gateway: BillingGateway | None = None,
        allowed_return_origins: Iterable[str] = (),
    ) -> None:
        self.subscriptions = subscriptions
        self.catalog = subscriptions.catalog
        self.gateway = gateway
        self.allowed_return_origins = frozenset(allowed_return_origins)

    def public_plans(self) -> dict[str, object]:
        plans = self.catalog.public_plans()
        return {
            "catalog_digest": self.catalog.digest,
            "count": len(plans),
            "items": [item.to_dict() for item in plans],
        }

    def subscription(self, tenant_id: str) -> dict[str, object]:
        current = self.subscriptions.current(tenant_id)
        return {
            "subscription": current.to_dict() if current else None,
            "entitlements": self.subscriptions.entitlements(tenant_id).to_dict(),
        }

    def checkout(self, tenant_id: str, *, plan_ref: str, return_url: str) -> RedirectSession:
        self._return_url(return_url)
        plan = self.catalog.resolve(plan_ref)
        if not plan.public:
            raise LookupError("plan is not publicly subscribable")
        if plan.commercialization_state != "provider_configured":
            raise BillingUnavailable("plan price is not configured")
        if self.gateway is None:
            raise BillingUnavailable("billing gateway is not configured")
        return self.gateway.create_checkout(
            tenant_id=tenant_id, plan=plan, return_url=return_url
        )

    def billing_portal(self, tenant_id: str, *, return_url: str) -> RedirectSession:
        self._return_url(return_url)
        current = self.subscriptions.current(tenant_id)
        if current is None:
            raise BillingUnavailable("tenant has no billing customer")
        if self.gateway is None:
            raise BillingUnavailable("billing gateway is not configured")
        return self.gateway.create_portal(
            tenant_id=tenant_id,
            provider_customer_ref=current.provider_customer_ref,
            return_url=return_url,
        )

    def _return_url(self, value: str) -> None:
        parsed = urlsplit(value)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or origin not in self.allowed_return_origins
        ):
            raise ValueError("billing return URL origin is not allowed")


def default_plan_catalog() -> PlanCatalog:
    """Feature catalog without invented currency prices or provider identifiers."""

    return PlanCatalog(
        (
            PlanDefinition(
                "taedri.plan.explorer",
                "1.0.0",
                "Explorer",
                "Evaluate private code search and primitive digestion with bounded usage.",
                {
                    "taedri.entitlement.search_requests_per_minute": 60,
                    "taedri.entitlement.private_primitives": 100,
                    "taedri.entitlement.source_disclosure": False,
                    "taedri.entitlement.benchmark_runs_per_month": 0,
                },
            ),
            PlanDefinition(
                "taedri.plan.team",
                "1.0.0",
                "Team",
                "Shared primitive registry, higher search limits, and verification workflows.",
                {
                    "taedri.entitlement.search_requests_per_minute": 600,
                    "taedri.entitlement.private_primitives": 10000,
                    "taedri.entitlement.source_disclosure": True,
                    "taedri.entitlement.benchmark_runs_per_month": 100,
                },
            ),
            PlanDefinition(
                "taedri.plan.enterprise",
                "1.0.0",
                "Enterprise",
                "Private deployment, policy controls, support, and negotiated capacity.",
                {
                    "taedri.entitlement.search_requests_per_minute": 5000,
                    "taedri.entitlement.private_primitives": 1000000,
                    "taedri.entitlement.source_disclosure": True,
                    "taedri.entitlement.benchmark_runs_per_month": 1000,
                },
                commercialization_state="contact_sales",
            ),
        )
    )


def _subscription(value: Mapping[str, Any]) -> SubscriptionRevision:
    identity_value = value.get("identity")
    if not isinstance(identity_value, dict):
        raise ValueError("subscription identity is missing")
    identity = IdentityRecord(
        str(identity_value.get("id", "")),
        str(identity_value.get("kind", "")),
        identity_value.get("canonical_key"),
    )
    identity.validate()
    revision = SubscriptionRevision(
        identity,
        str(value.get("tenant_id", "")),
        str(value.get("plan_ref", "")),
        SubscriptionState(str(value.get("state", ""))),
        str(value.get("provider", "")),
        str(value.get("provider_customer_ref", "")),
        str(value.get("provider_subscription_ref", "")),
        str(value.get("effective_at", "")),
        str(value["ends_at"]) if value.get("ends_at") is not None else None,
        str(value.get("source_event_id", "")),
        str(value.get("source_event_digest", "")),
        (
            str(value["previous_revision_id"])
            if value.get("previous_revision_id") is not None
            else None
        ),
    )
    if revision.identity != SubscriptionRevision.create(
        tenant_id=revision.tenant_id,
        plan_ref=revision.plan_ref,
        state=revision.state,
        provider=revision.provider,
        provider_customer_ref=revision.provider_customer_ref,
        provider_subscription_ref=revision.provider_subscription_ref,
        effective_at=revision.effective_at,
        ends_at=revision.ends_at,
        source_event_id=revision.source_event_id,
        source_event_digest=revision.source_event_digest,
        previous_revision_id=revision.previous_revision_id,
    ).identity:
        raise ValueError("subscription revision identity mismatch")
    return revision
