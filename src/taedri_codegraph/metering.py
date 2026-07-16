"""Append-only usage metering and transactional tenant quota enforcement.

The SQLite adapter is the executable single-node contract.  It deliberately keeps
usage receipts and limit revisions immutable so billing exports, incident review,
and later PostgreSQL adapters can replay the same decisions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .canonical import canonical_json_bytes, to_primitive
from .contracts import RecordMixin
from .identity import IdentityRecord
from .saas import SQLiteControlPlane, utc_now


class MeteringError(ValueError):
    """Raised when a metering record violates its durable contract."""


class QuotaExceeded(MeteringError):
    """Raised before a usage event is committed when a hard limit is exceeded."""

    def __init__(
        self,
        *,
        metric: str,
        hard_limit: int,
        used: int,
        requested: int,
        window_start: str,
        window_end: str,
    ) -> None:
        super().__init__(
            f"quota exceeded for {metric}: {used} used + {requested} requested "
            f"> {hard_limit} in [{window_start}, {window_end})"
        )
        self.metric = metric
        self.hard_limit = hard_limit
        self.used = used
        self.requested = requested
        self.window_start = window_start
        self.window_end = window_end


_METRIC_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_MAX_DIMENSIONS_BYTES = 16_384


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MeteringError(f"invalid metering timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise MeteringError("metering timestamps must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _window(occurred_at: str, window_seconds: int) -> tuple[str, str]:
    if not 1 <= window_seconds <= 31_536_000:
        raise MeteringError("quota window must be between one second and one year")
    instant = _parse_time(occurred_at)
    epoch_seconds = int(instant.timestamp())
    start = datetime.fromtimestamp(
        epoch_seconds - (epoch_seconds % window_seconds), tz=timezone.utc
    )
    return _format_time(start), _format_time(start + timedelta(seconds=window_seconds))


def _metric(value: str) -> str:
    if not _METRIC_RE.fullmatch(value):
        raise MeteringError("metric must be a lowercase dotted identifier")
    return value


@dataclass(frozen=True, slots=True)
class UsageLimitRevision(RecordMixin):
    identity: IdentityRecord
    format_version: str
    tenant_id: str
    metric: str
    window_seconds: int
    hard_limit: int
    effective_at: str
    actor: str
    reason: str

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        metric: str,
        window_seconds: int,
        hard_limit: int,
        effective_at: str,
        actor: str,
        reason: str,
    ) -> "UsageLimitRevision":
        _metric(metric)
        canonical_effective_at = _format_time(_parse_time(effective_at))
        _window(canonical_effective_at, window_seconds)
        if hard_limit <= 0:
            raise MeteringError("hard limit must be positive")
        if not tenant_id or not actor.strip() or not reason.strip():
            raise MeteringError("limit tenant, actor, and reason are required")
        key = {
            "format_version": "1.0.0",
            "tenant_id": tenant_id,
            "metric": metric,
            "window_seconds": window_seconds,
            "hard_limit": hard_limit,
            "effective_at": canonical_effective_at,
            "actor": actor.strip(),
            "reason": reason.strip(),
        }
        return cls(
            IdentityRecord.create("usage_limit_revision", key),
            "1.0.0",
            tenant_id,
            metric,
            window_seconds,
            hard_limit,
            canonical_effective_at,
            actor.strip(),
            reason.strip(),
        )


@dataclass(frozen=True, slots=True)
class UsageReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    tenant_id: str
    metric: str
    quantity: int
    occurred_at: str
    window_start: str
    window_end: str
    idempotency_key: str
    resource_id: str
    dimensions: Mapping[str, Any]
    applied_limit_id: str | None

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        metric: str,
        quantity: int,
        occurred_at: str,
        window_start: str,
        window_end: str,
        idempotency_key: str,
        resource_id: str,
        dimensions: Mapping[str, Any] | None,
        applied_limit_id: str | None,
    ) -> "UsageReceipt":
        _metric(metric)
        canonical_occurred_at = _format_time(_parse_time(occurred_at))
        if quantity <= 0 or not tenant_id or not idempotency_key or not resource_id:
            raise MeteringError(
                "positive quantity, tenant, idempotency key, and resource are required"
            )
        primitive_dimensions = to_primitive(dict(dimensions or {}))
        if not isinstance(primitive_dimensions, dict):  # pragma: no cover
            raise MeteringError("usage dimensions must be a mapping")
        if len(canonical_json_bytes(primitive_dimensions)) > _MAX_DIMENSIONS_BYTES:
            raise MeteringError("usage dimensions exceed the 16 KiB limit")
        key = {
            "format_version": "1.0.0",
            "tenant_id": tenant_id,
            "metric": metric,
            "quantity": quantity,
            "occurred_at": canonical_occurred_at,
            "window_start": window_start,
            "window_end": window_end,
            "idempotency_key": idempotency_key,
            "resource_id": resource_id,
            "dimensions": primitive_dimensions,
            "applied_limit_id": applied_limit_id,
        }
        return cls(
            IdentityRecord.create("usage_receipt", key),
            "1.0.0",
            tenant_id,
            metric,
            quantity,
            canonical_occurred_at,
            window_start,
            window_end,
            idempotency_key,
            resource_id,
            primitive_dimensions,
            applied_limit_id,
        )


class SQLiteMeteringRepository:
    """Tenant-isolated usage ledger with atomic fixed-window admission."""

    def __init__(self, control: SQLiteControlPlane):
        self.control = control

    def set_limit(
        self,
        tenant_id: str,
        *,
        metric: str,
        window_seconds: int,
        hard_limit: int,
        actor: str,
        reason: str,
        effective_at: str | None = None,
    ) -> UsageLimitRevision:
        self.control.tenant(tenant_id)
        revision = UsageLimitRevision.create(
            tenant_id=tenant_id,
            metric=metric,
            window_seconds=window_seconds,
            hard_limit=hard_limit,
            effective_at=effective_at or utc_now(),
            actor=actor,
            reason=reason,
        )
        with self.control._transaction() as connection:
            existing = connection.execute(
                "SELECT record_json FROM usage_limit_revision "
                "WHERE tenant_id=? AND limit_id=?",
                (tenant_id, revision.identity.id),
            ).fetchone()
            if existing is not None:
                return self._limit_from_json(str(existing["record_json"]))
            connection.execute(
                "INSERT INTO usage_limit_revision(tenant_id, limit_id, metric, "
                "window_seconds, hard_limit, effective_at, record_json) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    revision.identity.id,
                    metric,
                    window_seconds,
                    hard_limit,
                    revision.effective_at,
                    canonical_json_bytes(revision).decode("utf-8"),
                ),
            )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action="usage_limit.revised",
                resource_id=revision.identity.id,
                occurred_at=revision.effective_at,
                detail={
                    "metric": metric,
                    "window_seconds": window_seconds,
                    "hard_limit": hard_limit,
                    "reason": reason,
                },
            )
        return revision

    def effective_limit(
        self, tenant_id: str, metric: str, *, at: str | None = None
    ) -> UsageLimitRevision | None:
        _metric(metric)
        effective_at = _format_time(_parse_time(at or utc_now()))
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM usage_limit_revision "
                "WHERE tenant_id=? AND metric=? AND effective_at<=? "
                "ORDER BY effective_at DESC, limit_id DESC LIMIT 1",
                (tenant_id, metric, effective_at),
            ).fetchone()
        return None if row is None else self._limit_from_json(str(row["record_json"]))

    def limit_history(
        self, tenant_id: str, *, metric: str | None = None, limit: int = 100
    ) -> tuple[UsageLimitRevision, ...]:
        if not 1 <= limit <= 1000:
            raise MeteringError("limit history size must be between 1 and 1000")
        clauses = ["tenant_id=?"]
        parameters: list[Any] = [tenant_id]
        if metric is not None:
            clauses.append("metric=?")
            parameters.append(_metric(metric))
        parameters.append(limit)
        with self.control._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM usage_limit_revision WHERE "
                + " AND ".join(clauses)
                + " ORDER BY effective_at DESC, limit_id DESC LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(self._limit_from_json(str(row["record_json"])) for row in rows)

    def consume(
        self,
        tenant_id: str,
        *,
        metric: str,
        quantity: int,
        idempotency_key: str,
        resource_id: str,
        occurred_at: str | None = None,
        dimensions: Mapping[str, Any] | None = None,
        fallback_window_seconds: int | None = None,
        fallback_hard_limit: int | None = None,
    ) -> UsageReceipt:
        self.control.tenant(tenant_id)
        effective_at = _format_time(_parse_time(occurred_at or utc_now()))
        configured = self.effective_limit(tenant_id, metric, at=effective_at)
        if configured is not None:
            window_seconds = configured.window_seconds
            hard_limit = configured.hard_limit
            applied_limit_id = configured.identity.id
        elif fallback_window_seconds is not None and fallback_hard_limit is not None:
            window_seconds = fallback_window_seconds
            hard_limit = fallback_hard_limit
            applied_limit_id = None
        elif fallback_window_seconds is None and fallback_hard_limit is None:
            window_seconds = 31_536_000
            hard_limit = None
            applied_limit_id = None
        else:
            raise MeteringError("fallback quota window and limit must be supplied together")
        window_start, window_end = _window(effective_at, window_seconds)
        receipt = UsageReceipt.create(
            tenant_id=tenant_id,
            metric=metric,
            quantity=quantity,
            occurred_at=effective_at,
            window_start=window_start,
            window_end=window_end,
            idempotency_key=idempotency_key,
            resource_id=resource_id,
            dimensions=dimensions,
            applied_limit_id=applied_limit_id,
        )
        with self.control._transaction() as connection:
            existing = connection.execute(
                "SELECT record_json FROM usage_event WHERE tenant_id=? AND metric=? "
                "AND idempotency_key=?",
                (tenant_id, metric, idempotency_key),
            ).fetchone()
            if existing is not None:
                current = self._receipt_from_json(str(existing["record_json"]))
                if current != receipt:
                    raise MeteringError(
                        "usage idempotency key cannot describe two different receipts"
                    )
                return current
            used = int(
                connection.execute(
                    "SELECT COALESCE(SUM(quantity), 0) FROM usage_event "
                    "WHERE tenant_id=? AND metric=? AND occurred_at>=? AND occurred_at<?",
                    (tenant_id, metric, window_start, window_end),
                ).fetchone()[0]
            )
            if hard_limit is not None and used + quantity > hard_limit:
                raise QuotaExceeded(
                    metric=metric,
                    hard_limit=hard_limit,
                    used=used,
                    requested=quantity,
                    window_start=window_start,
                    window_end=window_end,
                )
            connection.execute(
                "INSERT INTO usage_event(tenant_id, usage_id, metric, quantity, "
                "occurred_at, window_start, window_end, idempotency_key, resource_id, "
                "record_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    receipt.identity.id,
                    metric,
                    quantity,
                    effective_at,
                    window_start,
                    window_end,
                    idempotency_key,
                    resource_id,
                    canonical_json_bytes(receipt).decode("utf-8"),
                ),
            )
        return receipt

    def receipts(
        self,
        tenant_id: str,
        *,
        metric: str | None = None,
        limit: int = 100,
    ) -> tuple[UsageReceipt, ...]:
        if not 1 <= limit <= 1000:
            raise MeteringError("usage receipt limit must be between 1 and 1000")
        clauses = ["tenant_id=?"]
        parameters: list[Any] = [tenant_id]
        if metric is not None:
            clauses.append("metric=?")
            parameters.append(_metric(metric))
        parameters.append(limit)
        with self.control._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM usage_event WHERE "
                + " AND ".join(clauses)
                + " ORDER BY occurred_at DESC, usage_id DESC LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(self._receipt_from_json(str(row["record_json"])) for row in rows)

    def summary(self, tenant_id: str) -> tuple[dict[str, Any], ...]:
        with self.control._connect() as connection:
            rows = connection.execute(
                "SELECT metric, window_start, window_end, SUM(quantity) AS quantity, "
                "COUNT(*) AS receipt_count FROM usage_event WHERE tenant_id=? "
                "GROUP BY metric, window_start, window_end "
                "ORDER BY metric, window_start DESC",
                (tenant_id,),
            ).fetchall()
        return tuple(
            {
                "metric": str(row["metric"]),
                "window_start": str(row["window_start"]),
                "window_end": str(row["window_end"]),
                "quantity": int(row["quantity"]),
                "receipt_count": int(row["receipt_count"]),
            }
            for row in rows
        )

    @staticmethod
    def _limit_from_json(value: str) -> UsageLimitRevision:
        data = json.loads(value)
        identity = data["identity"]
        return UsageLimitRevision(
            IdentityRecord(
                str(identity["id"]),
                str(identity["kind"]),
                identity.get("canonical_key"),
            ),
            str(data["format_version"]),
            str(data["tenant_id"]),
            str(data["metric"]),
            int(data["window_seconds"]),
            int(data["hard_limit"]),
            str(data["effective_at"]),
            str(data["actor"]),
            str(data["reason"]),
        )

    @staticmethod
    def _receipt_from_json(value: str) -> UsageReceipt:
        data = json.loads(value)
        identity = data["identity"]
        return UsageReceipt(
            IdentityRecord(
                str(identity["id"]),
                str(identity["kind"]),
                identity.get("canonical_key"),
            ),
            str(data["format_version"]),
            str(data["tenant_id"]),
            str(data["metric"]),
            int(data["quantity"]),
            str(data["occurred_at"]),
            str(data["window_start"]),
            str(data["window_end"]),
            str(data["idempotency_key"]),
            str(data["resource_id"]),
            data["dimensions"],
            data.get("applied_limit_id"),
        )
