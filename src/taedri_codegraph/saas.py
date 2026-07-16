"""Persistent tenant, authentication, graph-mount, and worker control plane.

The first executable graph store is intentionally local and immutable.  This module
adds the transactional control records needed to put that graph behind a network
service without mixing mutable SaaS state into graph identity.  SQLite is the runnable
single-node adapter; the checked-in PostgreSQL migration defines the production port.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from .canonical import canonical_json_bytes, sha256_digest, to_primitive
from .contracts import RecordMixin
from .identity import IdentityRecord
from .workers import (
    JobKind,
    JobState,
    WorkerEvent,
    WorkerEventKind,
    WorkerJob,
    WorkerLease,
    WorkerQueueError,
)


class ControlPlaneError(ValueError):
    """Raised when a control-plane invariant is violated."""


class AuthenticationError(ControlPlaneError):
    """Raised for an absent, malformed, revoked, or invalid credential."""


class AuthorizationError(ControlPlaneError):
    """Raised when an authenticated principal lacks a required scope."""


class TenantState(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9_.-]*(?::(?:[a-z][a-z0-9_.-]*|\*))+$")
_KEY_RE = re.compile(r"^tcg_([a-f0-9]{24})_([A-Za-z0-9_-]{32,})$")
_PBKDF2_ITERATIONS = 310_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlPlaneError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ControlPlaneError("control-plane timestamps must include a UTC offset")
    return parsed


def _identity(value: Mapping[str, Any]) -> IdentityRecord:
    record = IdentityRecord(
        str(value.get("id", "")),
        str(value.get("kind", "")),
        value.get("canonical_key"),
    )
    record.validate()
    return record


def _record_json(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _validate_scopes(values: Iterable[str]) -> tuple[str, ...]:
    scopes = tuple(sorted(set(values)))
    if not scopes:
        raise ControlPlaneError("at least one API scope is required")
    invalid = [scope for scope in scopes if not _SCOPE_RE.fullmatch(scope)]
    if invalid:
        raise ControlPlaneError(f"invalid API scope(s): {', '.join(invalid)}")
    return scopes


@dataclass(frozen=True, slots=True)
class Tenant(RecordMixin):
    identity: IdentityRecord
    format_version: str
    slug: str
    display_name: str
    state: TenantState
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        slug: str,
        display_name: str,
        created_at: str,
        state: TenantState = TenantState.ACTIVE,
    ) -> "Tenant":
        if not _SLUG_RE.fullmatch(slug):
            raise ControlPlaneError("tenant slug must be a lowercase DNS-style label")
        if not display_name.strip():
            raise ControlPlaneError("tenant display name is required")
        _timestamp(created_at)
        key = {"format_version": "1.0.0", "slug": slug}
        return cls(
            IdentityRecord.create("tenant", key),
            "1.0.0",
            slug,
            display_name.strip(),
            state,
            created_at,
        )


@dataclass(frozen=True, slots=True)
class GraphMount(RecordMixin):
    identity: IdentityRecord
    format_version: str
    tenant_id: str
    name: str
    store_root: str
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        name: str,
        store_root: str | Path,
        created_at: str,
        updated_at: str | None = None,
    ) -> "GraphMount":
        if not tenant_id or not _SLUG_RE.fullmatch(name):
            raise ControlPlaneError("graph mount requires a tenant and DNS-style name")
        root = Path(store_root).expanduser()
        if not root.is_absolute():
            raise ControlPlaneError("graph store root must be an absolute path")
        _timestamp(created_at)
        effective_updated_at = updated_at or created_at
        _timestamp(effective_updated_at)
        key = {
            "format_version": "1.0.0",
            "tenant_id": tenant_id,
            "name": name,
        }
        return cls(
            IdentityRecord.create("tenant_graph_mount", key),
            "1.0.0",
            tenant_id,
            name,
            str(root),
            created_at,
            effective_updated_at,
        )


@dataclass(frozen=True, slots=True)
class ApiPrincipal:
    tenant_id: str
    key_id: str
    scopes: tuple[str, ...]

    def allows(self, required_scope: str) -> bool:
        if "admin:*" in self.scopes or required_scope in self.scopes:
            return True
        namespace, separator, _ = required_scope.partition(":")
        return bool(separator and f"{namespace}:*" in self.scopes)


@dataclass(frozen=True, slots=True)
class IssuedApiKey(RecordMixin):
    key_id: str
    tenant_id: str
    token: str
    prefix: str
    scopes: tuple[str, ...]
    created_at: str


@dataclass(frozen=True, slots=True)
class StoredJob(RecordMixin):
    tenant_id: str
    job: WorkerJob
    state: JobState
    attempts: int
    active_lease: WorkerLease | None
    cancellation_requested_at: str | None = None


@dataclass(frozen=True, slots=True)
class LeasedJob(RecordMixin):
    tenant_id: str
    job: WorkerJob
    lease: WorkerLease


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migration (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant (
    tenant_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_key (
    key_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    token_prefix TEXT NOT NULL,
    salt BLOB NOT NULL,
    verifier BLOB NOT NULL,
    iterations INTEGER NOT NULL,
    scopes_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS api_key_tenant_idx ON api_key(tenant_id, created_at);

CREATE TABLE IF NOT EXISTS graph_mount (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    name TEXT NOT NULL,
    store_root TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS audit_event (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    previous_event_id TEXT
);
CREATE INDEX IF NOT EXISTS audit_event_tenant_idx
    ON audit_event(tenant_id, sequence);

CREATE TABLE IF NOT EXISTS job_payload (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    payload_ref TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, payload_ref)
);

CREATE TABLE IF NOT EXISTS worker_job (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    job_id TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    priority INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    cancellation_requested_at TEXT,
    cancellation_actor TEXT,
    required_capabilities_json TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE (tenant_id, queue_name, idempotency_key)
);
CREATE INDEX IF NOT EXISTS worker_job_claim_idx
    ON worker_job(queue_name, state, priority DESC, created_at, job_id);

CREATE TABLE IF NOT EXISTS worker_lease (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    lease_id TEXT NOT NULL UNIQUE,
    attempt INTEGER NOT NULL,
    worker_id TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, job_id),
    FOREIGN KEY (tenant_id, job_id) REFERENCES worker_job(tenant_id, job_id)
);
CREATE INDEX IF NOT EXISTS worker_lease_expiry_idx ON worker_lease(expires_at);

CREATE TABLE IF NOT EXISTS worker_event (
    sequence INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    FOREIGN KEY (tenant_id, job_id) REFERENCES worker_job(tenant_id, job_id)
);
CREATE INDEX IF NOT EXISTS worker_event_job_idx
    ON worker_event(tenant_id, job_id, sequence);

CREATE TABLE IF NOT EXISTS primitive_handle (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    primitive_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    name TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, primitive_id),
    UNIQUE (tenant_id, namespace, name)
);
CREATE INDEX IF NOT EXISTS primitive_handle_search_idx
    ON primitive_handle(tenant_id, namespace, name);

CREATE TABLE IF NOT EXISTS primitive_blob (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    digest TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    content BLOB NOT NULL,
    PRIMARY KEY (tenant_id, digest)
);

CREATE TABLE IF NOT EXISTS primitive_tree (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    tree_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, tree_id)
);

CREATE TABLE IF NOT EXISTS primitive_revision (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    revision_id TEXT NOT NULL,
    primitive_id TEXT NOT NULL,
    tree_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, revision_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, tree_id)
        REFERENCES primitive_tree(tenant_id, tree_id)
);
CREATE INDEX IF NOT EXISTS primitive_revision_history_idx
    ON primitive_revision(tenant_id, primitive_id, created_at, revision_id);

CREATE TABLE IF NOT EXISTS primitive_ref (
    tenant_id TEXT NOT NULL,
    primitive_id TEXT NOT NULL,
    ref_kind TEXT NOT NULL,
    ref_name TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    updated_sequence INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, primitive_id, ref_kind, ref_name),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES primitive_revision(tenant_id, revision_id)
);

CREATE TABLE IF NOT EXISTS primitive_ref_update (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    sequence INTEGER NOT NULL,
    update_id TEXT NOT NULL,
    primitive_id TEXT NOT NULL,
    ref_kind TEXT NOT NULL,
    ref_name TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, sequence),
    UNIQUE (tenant_id, update_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES primitive_handle(tenant_id, primitive_id)
);

CREATE TABLE IF NOT EXISTS primitive_release (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    release_id TEXT NOT NULL,
    primitive_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    tree_id TEXT NOT NULL,
    ref_kind TEXT NOT NULL,
    ref_name TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    language TEXT NOT NULL,
    runtime_version TEXT NOT NULL,
    search_document TEXT NOT NULL,
    released_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, release_id),
    UNIQUE (tenant_id, primitive_id, ref_kind, ref_name, revision_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES primitive_revision(tenant_id, revision_id),
    FOREIGN KEY (tenant_id, tree_id)
        REFERENCES primitive_tree(tenant_id, tree_id)
);
CREATE INDEX IF NOT EXISTS primitive_release_ref_idx
    ON primitive_release(tenant_id, primitive_id, ref_kind, ref_name, released_at);
CREATE INDEX IF NOT EXISTS primitive_release_source_idx
    ON primitive_release(tenant_id, source_digest);

CREATE TABLE IF NOT EXISTS primitive_release_revocation (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    revocation_id TEXT NOT NULL,
    release_id TEXT NOT NULL,
    primitive_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    revoked_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, revocation_id),
    UNIQUE (tenant_id, release_id),
    FOREIGN KEY (tenant_id, release_id)
        REFERENCES primitive_release(tenant_id, release_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES primitive_revision(tenant_id, revision_id)
);
CREATE INDEX IF NOT EXISTS primitive_release_revocation_lookup_idx
    ON primitive_release_revocation(tenant_id, primitive_id, revoked_at);

CREATE TABLE IF NOT EXISTS candidate_submission (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    submission_id TEXT NOT NULL,
    primitive_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    current_state TEXT NOT NULL,
    visibility TEXT NOT NULL,
    license_evidence_state TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, submission_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES primitive_revision(tenant_id, revision_id)
);
CREATE INDEX IF NOT EXISTS candidate_submission_state_idx
    ON candidate_submission(tenant_id, current_state, submitted_at, submission_id);

CREATE TABLE IF NOT EXISTS candidate_state_event (
    tenant_id TEXT NOT NULL,
    submission_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    to_state TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, submission_id, sequence),
    UNIQUE (tenant_id, event_id),
    FOREIGN KEY (tenant_id, submission_id)
        REFERENCES candidate_submission(tenant_id, submission_id)
);
CREATE INDEX IF NOT EXISTS candidate_state_event_time_idx
    ON candidate_state_event(tenant_id, occurred_at, event_id);

CREATE TABLE IF NOT EXISTS prompt_session (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    session_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    privacy_mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    closed_at TEXT,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, session_id)
);
CREATE INDEX IF NOT EXISTS prompt_session_workspace_idx
    ON prompt_session(tenant_id, workspace_id, started_at, session_id);

CREATE TABLE IF NOT EXISTS prompt_session_event (
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, session_id, sequence),
    UNIQUE (tenant_id, event_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES prompt_session(tenant_id, session_id)
);
CREATE INDEX IF NOT EXISTS prompt_session_event_time_idx
    ON prompt_session_event(tenant_id, occurred_at, event_id);

CREATE TABLE IF NOT EXISTS usage_limit_revision (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    limit_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    window_seconds INTEGER NOT NULL,
    hard_limit INTEGER NOT NULL,
    effective_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, limit_id)
);
CREATE INDEX IF NOT EXISTS usage_limit_effective_idx
    ON usage_limit_revision(tenant_id, metric, effective_at DESC, limit_id DESC);

CREATE TABLE IF NOT EXISTS usage_event (
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    usage_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (tenant_id, usage_id),
    UNIQUE (tenant_id, metric, idempotency_key)
);
CREATE INDEX IF NOT EXISTS usage_event_window_idx
    ON usage_event(tenant_id, metric, occurred_at, usage_id);

CREATE TABLE IF NOT EXISTS subscription_revision (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    revision_id TEXT NOT NULL,
    plan_ref TEXT NOT NULL,
    state TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_customer_ref TEXT NOT NULL,
    provider_subscription_ref TEXT NOT NULL,
    effective_at TEXT NOT NULL,
    ends_at TEXT,
    source_event_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    UNIQUE (tenant_id, revision_id),
    UNIQUE (provider, provider_subscription_ref, source_event_id)
);
CREATE INDEX IF NOT EXISTS subscription_revision_current_idx
    ON subscription_revision(tenant_id, sequence DESC);

CREATE TABLE IF NOT EXISTS billing_event (
    provider TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES tenant(tenant_id),
    revision_id TEXT NOT NULL,
    source_event_digest TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (provider, source_event_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES subscription_revision(tenant_id, revision_id)
);
CREATE INDEX IF NOT EXISTS billing_event_tenant_idx
    ON billing_event(tenant_id, received_at, source_event_id);
"""


class SQLiteControlPlane:
    """Runnable single-node SaaS control plane with transactional worker leases."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(1, ?)",
                (utc_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(2, ?)",
                (utc_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(3, ?)",
                (utc_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(4, ?)",
                (utc_now(),),
            )
            worker_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(worker_job)").fetchall()
            }
            if "cancellation_requested_at" not in worker_columns:
                connection.execute(
                    "ALTER TABLE worker_job ADD COLUMN cancellation_requested_at TEXT"
                )
            if "cancellation_actor" not in worker_columns:
                connection.execute(
                    "ALTER TABLE worker_job ADD COLUMN cancellation_actor TEXT"
                )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(5, ?)",
                (utc_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(6, ?)",
                (utc_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(7, ?)",
                (utc_now(),),
            )
            release_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(primitive_release)").fetchall()
            }
            if "language" not in release_columns:
                connection.execute("ALTER TABLE primitive_release ADD COLUMN language TEXT")
            if "runtime_version" not in release_columns:
                connection.execute(
                    "ALTER TABLE primitive_release ADD COLUMN runtime_version TEXT"
                )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(8, ?)",
                (utc_now(),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migration(version, applied_at) VALUES(9, ?)",
                (utc_now(),),
            )

    def integrity_check(self) -> str:
        with self._connect() as connection:
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])

    def create_tenant(self, tenant: Tenant, *, actor: str = "system") -> Tenant:
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT record_json FROM tenant WHERE slug=?", (tenant.slug,)
            ).fetchone()
            if existing is not None:
                current = self._tenant_from_json(str(existing["record_json"]))
                if (
                    current.slug != tenant.slug
                    or current.display_name != tenant.display_name
                    or current.state is not tenant.state
                ):
                    raise ControlPlaneError("tenant slug already names a different tenant")
                return current
            connection.execute(
                "INSERT INTO tenant(tenant_id, slug, display_name, state, created_at, record_json) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (
                    tenant.identity.id,
                    tenant.slug,
                    tenant.display_name,
                    tenant.state.value,
                    tenant.created_at,
                    _record_json(tenant),
                ),
            )
            self._append_audit(
                connection,
                tenant_id=tenant.identity.id,
                actor=actor,
                action="tenant.created",
                resource_id=tenant.identity.id,
                occurred_at=tenant.created_at,
                detail={"slug": tenant.slug},
            )
        return tenant

    def tenant(self, identifier: str) -> Tenant:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM tenant WHERE tenant_id=? OR slug=? LIMIT 1",
                (identifier, identifier),
            ).fetchone()
        if row is None:
            raise ControlPlaneError(f"unknown tenant: {identifier}")
        return self._tenant_from_json(str(row["record_json"]))

    def list_tenants(self) -> tuple[Tenant, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM tenant ORDER BY slug"
            ).fetchall()
        return tuple(self._tenant_from_json(str(row["record_json"])) for row in rows)

    def mount_graph(self, mount: GraphMount, *, actor: str = "system") -> GraphMount:
        self.tenant(mount.tenant_id)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT created_at FROM graph_mount WHERE tenant_id=? AND name=?",
                (mount.tenant_id, mount.name),
            ).fetchone()
            if existing is not None and str(existing["created_at"]) != mount.created_at:
                mount = GraphMount.create(
                    tenant_id=mount.tenant_id,
                    name=mount.name,
                    store_root=mount.store_root,
                    created_at=str(existing["created_at"]),
                    updated_at=mount.updated_at,
                )
            connection.execute(
                "INSERT INTO graph_mount(tenant_id, name, store_root, created_at, updated_at, "
                "record_json) VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(tenant_id, name) DO UPDATE SET "
                "store_root=excluded.store_root, updated_at=excluded.updated_at, "
                "record_json=excluded.record_json",
                (
                    mount.tenant_id,
                    mount.name,
                    mount.store_root,
                    mount.created_at,
                    mount.updated_at,
                    _record_json(mount),
                ),
            )
            self._append_audit(
                connection,
                tenant_id=mount.tenant_id,
                actor=actor,
                action="graph.mounted",
                resource_id=mount.identity.id,
                occurred_at=mount.updated_at,
                detail={"name": mount.name, "store_root": mount.store_root},
            )
        return mount

    def graph_mount(self, tenant_id: str, name: str = "default") -> GraphMount:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM graph_mount WHERE tenant_id=? AND name=?",
                (tenant_id, name),
            ).fetchone()
        if row is None:
            raise ControlPlaneError(f"tenant has no {name!r} graph mount")
        return self._mount_from_json(str(row["record_json"]))

    def list_graph_mounts(self, tenant_id: str) -> tuple[GraphMount, ...]:
        self.tenant(tenant_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM graph_mount WHERE tenant_id=? ORDER BY name",
                (tenant_id,),
            ).fetchall()
        return tuple(self._mount_from_json(str(row["record_json"])) for row in rows)

    def issue_api_key(
        self,
        tenant_id: str,
        *,
        scopes: Iterable[str],
        created_at: str | None = None,
        actor: str = "system",
    ) -> IssuedApiKey:
        tenant = self.tenant(tenant_id)
        if tenant.state is not TenantState.ACTIVE:
            raise ControlPlaneError("cannot issue a key for a suspended tenant")
        effective_created_at = created_at or utc_now()
        _timestamp(effective_created_at)
        normalized_scopes = _validate_scopes(scopes)
        key_id = secrets.token_hex(12)
        secret = secrets.token_urlsafe(32)
        token = f"tcg_{key_id}_{secret}"
        salt = secrets.token_bytes(24)
        verifier = hashlib.pbkdf2_hmac(
            "sha256", token.encode("utf-8"), salt, _PBKDF2_ITERATIONS
        )
        prefix = f"tcg_{key_id}_"
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO api_key(key_id, tenant_id, token_prefix, salt, verifier, "
                "iterations, scopes_json, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    key_id,
                    tenant.identity.id,
                    prefix,
                    salt,
                    verifier,
                    _PBKDF2_ITERATIONS,
                    json.dumps(normalized_scopes, separators=(",", ":")),
                    effective_created_at,
                ),
            )
            self._append_audit(
                connection,
                tenant_id=tenant.identity.id,
                actor=actor,
                action="api_key.issued",
                resource_id=key_id,
                occurred_at=effective_created_at,
                detail={"prefix": prefix, "scopes": normalized_scopes},
            )
        return IssuedApiKey(
            key_id,
            tenant.identity.id,
            token,
            prefix,
            normalized_scopes,
            effective_created_at,
        )

    def authenticate(self, token: str, *, used_at: str | None = None) -> ApiPrincipal:
        match = _KEY_RE.fullmatch(token)
        if match is None:
            raise AuthenticationError("invalid API credential")
        key_id = match.group(1)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT k.*, t.state AS tenant_state FROM api_key k "
                "JOIN tenant t ON t.tenant_id=k.tenant_id WHERE k.key_id=?",
                (key_id,),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise AuthenticationError("invalid API credential")
        verifier = hashlib.pbkdf2_hmac(
            "sha256",
            token.encode("utf-8"),
            bytes(row["salt"]),
            int(row["iterations"]),
        )
        if not hmac.compare_digest(verifier, bytes(row["verifier"])):
            raise AuthenticationError("invalid API credential")
        if str(row["tenant_state"]) != TenantState.ACTIVE.value:
            raise AuthenticationError("invalid API credential")
        effective_used_at = used_at or utc_now()
        _timestamp(effective_used_at)
        with self._connect() as connection:
            connection.execute(
                "UPDATE api_key SET last_used_at=? WHERE key_id=?",
                (effective_used_at, key_id),
            )
        return ApiPrincipal(
            str(row["tenant_id"]),
            key_id,
            tuple(json.loads(str(row["scopes_json"]))),
        )

    def require(self, principal: ApiPrincipal, scope: str) -> None:
        if not principal.allows(scope):
            raise AuthorizationError(f"credential lacks required scope: {scope}")

    def revoke_api_key(
        self,
        key_id: str,
        *,
        actor: str,
        revoked_at: str | None = None,
    ) -> None:
        effective_revoked_at = revoked_at or utc_now()
        _timestamp(effective_revoked_at)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT tenant_id, revoked_at FROM api_key WHERE key_id=?", (key_id,)
            ).fetchone()
            if row is None:
                raise ControlPlaneError(f"unknown API key: {key_id}")
            if row["revoked_at"] is not None:
                return
            connection.execute(
                "UPDATE api_key SET revoked_at=? WHERE key_id=?",
                (effective_revoked_at, key_id),
            )
            self._append_audit(
                connection,
                tenant_id=str(row["tenant_id"]),
                actor=actor,
                action="api_key.revoked",
                resource_id=key_id,
                occurred_at=effective_revoked_at,
                detail={},
            )

    def put_job_payload(
        self,
        tenant_id: str,
        payload: Mapping[str, Any],
        *,
        created_at: str | None = None,
    ) -> str:
        self.tenant(tenant_id)
        primitive = to_primitive(dict(payload))
        if not isinstance(primitive, dict):  # pragma: no cover - defensive
            raise ControlPlaneError("job payload must be an object")
        content = canonical_json_bytes(primitive)
        payload_ref = sha256_digest(content)
        effective_created_at = created_at or utc_now()
        _timestamp(effective_created_at)
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO job_payload(tenant_id, payload_ref, payload_json, "
                "created_at) VALUES(?, ?, ?, ?)",
                (tenant_id, payload_ref, content.decode("utf-8"), effective_created_at),
            )
        return payload_ref

    def job_payload(self, tenant_id: str, payload_ref: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM job_payload WHERE tenant_id=? AND payload_ref=?",
                (tenant_id, payload_ref),
            ).fetchone()
        if row is None:
            raise ControlPlaneError("unknown tenant-scoped job payload")
        payload = json.loads(str(row["payload_json"]))
        if not isinstance(payload, dict):  # pragma: no cover - database corruption guard
            raise ControlPlaneError("stored job payload is not an object")
        return payload

    def audit_events(self, tenant_id: str, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 1000:
            raise ControlPlaneError("audit limit must be between 1 and 1000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT sequence, event_id, actor, action, resource_id, occurred_at, "
                "detail_json, previous_event_id FROM audit_event WHERE tenant_id=? "
                "ORDER BY sequence DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return tuple(
            {
                "sequence": int(row["sequence"]),
                "event_id": str(row["event_id"]),
                "actor": str(row["actor"]),
                "action": str(row["action"]),
                "resource_id": str(row["resource_id"]),
                "occurred_at": str(row["occurred_at"]),
                "detail": json.loads(str(row["detail_json"])),
                "previous_event_id": row["previous_event_id"],
            }
            for row in rows
        )

    def tenant_metrics(self, tenant_id: str) -> dict[str, Any]:
        """Return a bounded tenant snapshot without exposing record payloads."""

        self.tenant(tenant_id)
        with self._connect() as connection:
            jobs = {
                str(row["state"]): int(row["count"])
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS count FROM worker_job "
                    "WHERE tenant_id=? GROUP BY state",
                    (tenant_id,),
                ).fetchall()
            }
            candidates = {
                str(row["current_state"]): int(row["count"])
                for row in connection.execute(
                    "SELECT current_state, COUNT(*) AS count FROM candidate_submission "
                    "WHERE tenant_id=? GROUP BY current_state",
                    (tenant_id,),
                ).fetchall()
            }
            counts = {}
            for key, table in (
                ("graph_mounts", "graph_mount"),
                ("primitive_handles", "primitive_handle"),
                ("primitive_revisions", "primitive_revision"),
                ("released_primitives", "primitive_release"),
                ("primitive_release_revocations", "primitive_release_revocation"),
                ("candidate_submissions", "candidate_submission"),
                ("prompt_sessions", "prompt_session"),
                ("usage_receipts", "usage_event"),
                ("audit_events", "audit_event"),
            ):
                counts[key] = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE tenant_id=?",  # noqa: S608 - fixed allowlist
                        (tenant_id,),
                    ).fetchone()[0]
                )
            counts["active_released_primitives"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM primitive_release r WHERE r.tenant_id=? "
                    "AND NOT EXISTS (SELECT 1 FROM primitive_release_revocation v "
                    "WHERE v.tenant_id=r.tenant_id AND v.release_id=r.release_id)",
                    (tenant_id,),
                ).fetchone()[0]
            )
            counts["open_prompt_sessions"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM prompt_session WHERE tenant_id=? "
                    "AND closed_at IS NULL",
                    (tenant_id,),
                ).fetchone()[0]
            )
        return {
            "format_version": "1.0.0",
            "tenant_id": tenant_id,
            "generated_at": utc_now(),
            "counts": counts,
            "jobs_by_state": {
                state.value: jobs.get(state.value, 0) for state in JobState
            },
            "candidates_by_state": candidates,
        }

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        resource_id: str,
        occurred_at: str,
        detail: Mapping[str, Any],
    ) -> None:
        _timestamp(occurred_at)
        previous = connection.execute(
            "SELECT event_id FROM audit_event WHERE tenant_id=? ORDER BY sequence DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
        previous_event_id = str(previous["event_id"]) if previous is not None else None
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM audit_event"
            ).fetchone()[0]
        )
        primitive_detail = to_primitive(dict(detail))
        event_id = sha256_digest(
            canonical_json_bytes(
                {
                    "sequence": sequence,
                    "tenant_id": tenant_id,
                    "actor": actor,
                    "action": action,
                    "resource_id": resource_id,
                    "occurred_at": occurred_at,
                    "detail": primitive_detail,
                    "previous_event_id": previous_event_id,
                }
            )
        )
        connection.execute(
            "INSERT INTO audit_event(sequence, event_id, tenant_id, actor, action, "
            "resource_id, occurred_at, detail_json, previous_event_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                event_id,
                tenant_id,
                actor,
                action,
                resource_id,
                occurred_at,
                json.dumps(primitive_detail, sort_keys=True, separators=(",", ":")),
                previous_event_id,
            ),
        )

    @staticmethod
    def _tenant_from_json(value: str) -> Tenant:
        data = json.loads(value)
        return Tenant(
            _identity(data["identity"]),
            str(data["format_version"]),
            str(data["slug"]),
            str(data["display_name"]),
            TenantState(data["state"]),
            str(data["created_at"]),
        )

    @staticmethod
    def _mount_from_json(value: str) -> GraphMount:
        data = json.loads(value)
        return GraphMount(
            _identity(data["identity"]),
            str(data["format_version"]),
            str(data["tenant_id"]),
            str(data["name"]),
            str(data["store_root"]),
            str(data["created_at"]),
            str(data["updated_at"]),
        )


class SQLiteWorkerQueue:
    """Persistent multi-tenant queue preserving :mod:`workers` semantics."""

    def __init__(self, control: SQLiteControlPlane):
        self.control = control

    def enqueue(self, tenant_id: str, job: WorkerJob) -> WorkerJob:
        self.control.tenant(tenant_id)
        with self.control._transaction() as connection:
            existing = connection.execute(
                "SELECT record_json FROM worker_job WHERE tenant_id=? AND queue_name=? "
                "AND idempotency_key=?",
                (tenant_id, job.queue, job.idempotency_key),
            ).fetchone()
            if existing is not None:
                current = self._job_from_json(str(existing["record_json"]))
                if current != job:
                    raise WorkerQueueError("an idempotency key cannot describe two jobs")
                return current
            connection.execute(
                "INSERT INTO worker_job(tenant_id, job_id, queue_name, kind, "
                "idempotency_key, priority, created_at, state, attempts, "
                "required_capabilities_json, record_json) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
                (
                    tenant_id,
                    job.identity.id,
                    job.queue,
                    job.kind.value,
                    job.idempotency_key,
                    job.priority,
                    job.created_at,
                    JobState.PENDING.value,
                    json.dumps(job.required_capabilities, separators=(",", ":")),
                    _record_json(job),
                ),
            )
            self._append_event(
                connection,
                tenant_id=tenant_id,
                job=job,
                kind=WorkerEventKind.ENQUEUED,
                attempt=0,
                occurred_at=job.created_at,
                detail="job accepted under its tenant and queue-scoped idempotency key",
            )
        return job

    def get(self, tenant_id: str, job_id: str) -> StoredJob:
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT record_json, state, attempts, cancellation_requested_at "
                "FROM worker_job WHERE tenant_id=? AND job_id=?",
                (tenant_id, job_id),
            ).fetchone()
            lease_row = connection.execute(
                "SELECT record_json FROM worker_lease WHERE tenant_id=? AND job_id=?",
                (tenant_id, job_id),
            ).fetchone()
        if row is None:
            raise WorkerQueueError(f"unknown job: {job_id}")
        return StoredJob(
            tenant_id,
            self._job_from_json(str(row["record_json"])),
            JobState(row["state"]),
            int(row["attempts"]),
            (
                self._lease_from_json(str(lease_row["record_json"]))
                if lease_row is not None
                else None
            ),
            (
                str(row["cancellation_requested_at"])
                if row["cancellation_requested_at"] is not None
                else None
            ),
        )

    def find_by_idempotency(
        self, tenant_id: str, *, queue: str, idempotency_key: str
    ) -> StoredJob | None:
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT job_id FROM worker_job WHERE tenant_id=? AND queue_name=? "
                "AND idempotency_key=?",
                (tenant_id, queue, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        return self.get(tenant_id, str(row["job_id"]))

    def list(
        self,
        tenant_id: str,
        *,
        queue: str | None = None,
        state: JobState | None = None,
        limit: int = 100,
    ) -> tuple[StoredJob, ...]:
        if not 1 <= limit <= 1000:
            raise WorkerQueueError("job limit must be between 1 and 1000")
        clauses = ["tenant_id=?"]
        parameters: list[Any] = [tenant_id]
        if queue is not None:
            clauses.append("queue_name=?")
            parameters.append(queue)
        if state is not None:
            clauses.append("state=?")
            parameters.append(state.value)
        parameters.append(limit)
        with self.control._connect() as connection:
            rows = connection.execute(
                "SELECT job_id FROM worker_job WHERE " + " AND ".join(clauses)
                + " ORDER BY created_at DESC, job_id LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(self.get(tenant_id, str(row["job_id"])) for row in rows)

    def events(self, tenant_id: str, job_id: str) -> tuple[WorkerEvent, ...]:
        self.get(tenant_id, job_id)
        with self.control._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM worker_event WHERE tenant_id=? AND job_id=? "
                "ORDER BY sequence",
                (tenant_id, job_id),
            ).fetchall()
        return tuple(self._event_from_json(str(row["record_json"])) for row in rows)

    def claim(
        self,
        *,
        queue: str,
        worker_id: str,
        leased_at: str,
        expires_at: str,
        lease_nonce: str,
        capabilities: Iterable[str] = (),
        kinds: Iterable[JobKind] | None = None,
    ) -> LeasedJob | None:
        worker_capabilities = set(capabilities)
        allowed_kinds = set(kinds) if kinds is not None else set(JobKind)
        with self.control._transaction() as connection:
            self._requeue_expired_in_transaction(
                connection, occurred_at=leased_at, actor=worker_id
            )
            rows = connection.execute(
                "SELECT tenant_id, record_json, attempts FROM worker_job "
                "WHERE queue_name=? AND state=? "
                "ORDER BY priority DESC, created_at, job_id",
                (queue, JobState.PENDING.value),
            ).fetchall()
            selected: tuple[str, WorkerJob, int] | None = None
            for row in rows:
                job = self._job_from_json(str(row["record_json"]))
                if job.kind not in allowed_kinds:
                    continue
                if not set(job.required_capabilities).issubset(worker_capabilities):
                    continue
                selected = (str(row["tenant_id"]), job, int(row["attempts"]))
                break
            if selected is None:
                return None
            tenant_id, job, attempts = selected
            lease = WorkerLease.create(
                job_id=job.identity.id,
                attempt=attempts + 1,
                worker_id=worker_id,
                leased_at=leased_at,
                expires_at=expires_at,
                lease_nonce=lease_nonce,
            )
            connection.execute(
                "UPDATE worker_job SET state=?, attempts=? WHERE tenant_id=? AND job_id=?",
                (JobState.LEASED.value, lease.attempt, tenant_id, job.identity.id),
            )
            connection.execute(
                "INSERT INTO worker_lease(tenant_id, job_id, lease_id, attempt, worker_id, "
                "expires_at, record_json) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    job.identity.id,
                    lease.identity.id,
                    lease.attempt,
                    worker_id,
                    expires_at,
                    _record_json(lease),
                ),
            )
            self._append_event(
                connection,
                tenant_id=tenant_id,
                job=job,
                kind=WorkerEventKind.LEASED,
                attempt=lease.attempt,
                occurred_at=leased_at,
                detail="worker acquired an exclusive time-bounded lease",
                worker_id=worker_id,
                lease=lease,
            )
        return LeasedJob(tenant_id, job, lease)

    def heartbeat(
        self,
        leased: LeasedJob,
        *,
        occurred_at: str,
        expires_at: str,
        lease_nonce: str,
    ) -> LeasedJob:
        with self.control._transaction() as connection:
            self._validate_active_lease(connection, leased, occurred_at)
            replacement = WorkerLease.create(
                job_id=leased.job.identity.id,
                attempt=leased.lease.attempt,
                worker_id=leased.lease.worker_id,
                leased_at=occurred_at,
                expires_at=expires_at,
                lease_nonce=lease_nonce,
            )
            connection.execute(
                "UPDATE worker_lease SET lease_id=?, expires_at=?, record_json=? "
                "WHERE tenant_id=? AND job_id=?",
                (
                    replacement.identity.id,
                    replacement.expires_at,
                    _record_json(replacement),
                    leased.tenant_id,
                    leased.job.identity.id,
                ),
            )
            self._append_event(
                connection,
                tenant_id=leased.tenant_id,
                job=leased.job,
                kind=WorkerEventKind.HEARTBEAT,
                attempt=replacement.attempt,
                occurred_at=occurred_at,
                detail="worker renewed its exclusive time-bounded lease",
                worker_id=replacement.worker_id,
                lease=replacement,
            )
        return LeasedJob(leased.tenant_id, leased.job, replacement)

    def request_cancel(
        self,
        tenant_id: str,
        job_id: str,
        *,
        occurred_at: str,
        actor: str,
    ) -> WorkerEvent:
        _timestamp(occurred_at)
        if not actor.strip():
            raise WorkerQueueError("cancellation actor is required")
        with self.control._transaction() as connection:
            row = connection.execute(
                "SELECT record_json, state, attempts, cancellation_requested_at "
                "FROM worker_job WHERE tenant_id=? AND job_id=?",
                (tenant_id, job_id),
            ).fetchone()
            if row is None:
                raise WorkerQueueError(f"unknown job: {job_id}")
            job = self._job_from_json(str(row["record_json"]))
            state = JobState(str(row["state"]))
            if state is JobState.CANCELLED:
                existing = connection.execute(
                    "SELECT record_json FROM worker_event WHERE tenant_id=? AND job_id=? "
                    "AND event_kind=? ORDER BY sequence DESC LIMIT 1",
                    (tenant_id, job_id, WorkerEventKind.CANCELLED.value),
                ).fetchone()
                assert existing is not None
                return self._event_from_json(str(existing["record_json"]))
            if state in {JobState.SUCCEEDED, JobState.DEAD_LETTER}:
                raise WorkerQueueError("a terminal worker job cannot be cancelled")
            if state is JobState.PENDING:
                connection.execute(
                    "UPDATE worker_job SET state=?, cancellation_requested_at=?, "
                    "cancellation_actor=? WHERE tenant_id=? AND job_id=?",
                    (
                        JobState.CANCELLED.value,
                        occurred_at,
                        actor.strip(),
                        tenant_id,
                        job_id,
                    ),
                )
                return self._append_event(
                    connection,
                    tenant_id=tenant_id,
                    job=job,
                    kind=WorkerEventKind.CANCELLED,
                    attempt=int(row["attempts"]),
                    occurred_at=occurred_at,
                    detail=f"{actor.strip()} cancelled the pending job before execution",
                )
            if row["cancellation_requested_at"] is not None:
                existing = connection.execute(
                    "SELECT record_json FROM worker_event WHERE tenant_id=? AND job_id=? "
                    "AND event_kind=? ORDER BY sequence DESC LIMIT 1",
                    (tenant_id, job_id, WorkerEventKind.CANCELLATION_REQUESTED.value),
                ).fetchone()
                assert existing is not None
                return self._event_from_json(str(existing["record_json"]))
            lease_row = connection.execute(
                "SELECT record_json FROM worker_lease WHERE tenant_id=? AND job_id=?",
                (tenant_id, job_id),
            ).fetchone()
            if lease_row is None:  # pragma: no cover - transactional corruption guard
                raise WorkerQueueError("leased job has no active lease")
            lease = self._lease_from_json(str(lease_row["record_json"]))
            connection.execute(
                "UPDATE worker_job SET cancellation_requested_at=?, cancellation_actor=? "
                "WHERE tenant_id=? AND job_id=?",
                (occurred_at, actor.strip(), tenant_id, job_id),
            )
            return self._append_event(
                connection,
                tenant_id=tenant_id,
                job=job,
                kind=WorkerEventKind.CANCELLATION_REQUESTED,
                attempt=lease.attempt,
                occurred_at=occurred_at,
                detail=f"{actor.strip()} requested cooperative cancellation",
                worker_id=lease.worker_id,
                lease=lease,
            )

    def cancellation_requested(self, leased: LeasedJob) -> bool:
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT l.record_json, j.state, j.cancellation_requested_at "
                "FROM worker_lease l JOIN worker_job j "
                "ON j.tenant_id=l.tenant_id AND j.job_id=l.job_id "
                "WHERE l.tenant_id=? AND l.job_id=?",
                (leased.tenant_id, leased.job.identity.id),
            ).fetchone()
        if row is None or self._lease_from_json(str(row["record_json"])) != leased.lease:
            raise WorkerQueueError("stale or unknown worker lease")
        return row["cancellation_requested_at"] is not None

    def acknowledge_cancel(
        self, leased: LeasedJob, *, occurred_at: str
    ) -> WorkerEvent:
        with self.control._transaction() as connection:
            self._validate_active_lease(
                connection, leased, occurred_at, allow_cancellation=True
            )
            row = connection.execute(
                "SELECT cancellation_requested_at FROM worker_job "
                "WHERE tenant_id=? AND job_id=?",
                (leased.tenant_id, leased.job.identity.id),
            ).fetchone()
            if row is None or row["cancellation_requested_at"] is None:
                raise WorkerQueueError("worker job has no cancellation request")
            connection.execute(
                "UPDATE worker_job SET state=? WHERE tenant_id=? AND job_id=?",
                (JobState.CANCELLED.value, leased.tenant_id, leased.job.identity.id),
            )
            connection.execute(
                "DELETE FROM worker_lease WHERE tenant_id=? AND job_id=?",
                (leased.tenant_id, leased.job.identity.id),
            )
            return self._append_event(
                connection,
                tenant_id=leased.tenant_id,
                job=leased.job,
                kind=WorkerEventKind.CANCELLED,
                attempt=leased.lease.attempt,
                occurred_at=occurred_at,
                detail="worker acknowledged cooperative cancellation",
                worker_id=leased.lease.worker_id,
                lease=leased.lease,
            )

    def complete(
        self,
        leased: LeasedJob,
        *,
        occurred_at: str,
        output_refs: Iterable[str],
        metrics: Mapping[str, Any] | None = None,
    ) -> WorkerEvent:
        outputs = tuple(output_refs)
        if not outputs:
            raise WorkerQueueError("successful attempts must name at least one output receipt")
        with self.control._transaction() as connection:
            self._validate_active_lease(connection, leased, occurred_at)
            connection.execute(
                "UPDATE worker_job SET state=? WHERE tenant_id=? AND job_id=?",
                (JobState.SUCCEEDED.value, leased.tenant_id, leased.job.identity.id),
            )
            connection.execute(
                "DELETE FROM worker_lease WHERE tenant_id=? AND job_id=?",
                (leased.tenant_id, leased.job.identity.id),
            )
            return self._append_event(
                connection,
                tenant_id=leased.tenant_id,
                job=leased.job,
                kind=WorkerEventKind.SUCCEEDED,
                attempt=leased.lease.attempt,
                occurred_at=occurred_at,
                detail="worker completed the leased job",
                worker_id=leased.lease.worker_id,
                lease=leased.lease,
                output_refs=outputs,
                metrics=metrics,
            )

    def fail(
        self,
        leased: LeasedJob,
        *,
        occurred_at: str,
        detail: str,
        retryable: bool,
        output_refs: Iterable[str] = (),
        metrics: Mapping[str, Any] | None = None,
    ) -> WorkerEvent:
        with self.control._transaction() as connection:
            self._validate_active_lease(connection, leased, occurred_at)
            can_retry = retryable and leased.lease.attempt < leased.job.max_attempts
            state = JobState.PENDING if can_retry else JobState.DEAD_LETTER
            connection.execute(
                "UPDATE worker_job SET state=? WHERE tenant_id=? AND job_id=?",
                (state.value, leased.tenant_id, leased.job.identity.id),
            )
            connection.execute(
                "DELETE FROM worker_lease WHERE tenant_id=? AND job_id=?",
                (leased.tenant_id, leased.job.identity.id),
            )
            return self._append_event(
                connection,
                tenant_id=leased.tenant_id,
                job=leased.job,
                kind=(
                    WorkerEventKind.FAILED_RETRYABLE
                    if can_retry
                    else WorkerEventKind.DEAD_LETTERED
                ),
                attempt=leased.lease.attempt,
                occurred_at=occurred_at,
                detail=detail,
                worker_id=leased.lease.worker_id,
                lease=leased.lease,
                output_refs=output_refs,
                metrics=metrics,
            )

    def requeue_expired(self, *, occurred_at: str, actor: str) -> tuple[WorkerEvent, ...]:
        with self.control._transaction() as connection:
            return self._requeue_expired_in_transaction(
                connection, occurred_at=occurred_at, actor=actor
            )

    def _requeue_expired_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        occurred_at: str,
        actor: str,
    ) -> tuple[WorkerEvent, ...]:
        now = _timestamp(occurred_at)
        rows = connection.execute(
            "SELECT l.tenant_id, l.record_json AS lease_json, j.record_json AS job_json, "
            "j.cancellation_requested_at "
            "FROM worker_lease l JOIN worker_job j "
            "ON j.tenant_id=l.tenant_id AND j.job_id=l.job_id ORDER BY l.job_id"
        ).fetchall()
        events: list[WorkerEvent] = []
        for row in rows:
            lease = self._lease_from_json(str(row["lease_json"]))
            if _timestamp(lease.expires_at) >= now:
                continue
            job = self._job_from_json(str(row["job_json"]))
            tenant_id = str(row["tenant_id"])
            cancellation_requested = row["cancellation_requested_at"] is not None
            can_retry = lease.attempt < job.max_attempts
            state = (
                JobState.CANCELLED
                if cancellation_requested
                else (JobState.PENDING if can_retry else JobState.DEAD_LETTER)
            )
            connection.execute(
                "UPDATE worker_job SET state=? WHERE tenant_id=? AND job_id=?",
                (state.value, tenant_id, job.identity.id),
            )
            connection.execute(
                "DELETE FROM worker_lease WHERE tenant_id=? AND job_id=?",
                (tenant_id, job.identity.id),
            )
            events.append(
                self._append_event(
                    connection,
                    tenant_id=tenant_id,
                    job=job,
                    kind=(
                        WorkerEventKind.CANCELLED
                        if cancellation_requested
                        else (
                            WorkerEventKind.LEASE_EXPIRED
                            if can_retry
                            else WorkerEventKind.DEAD_LETTERED
                        )
                    ),
                    attempt=lease.attempt,
                    occurred_at=occurred_at,
                    detail=(
                        f"{actor} finalized cancellation after the lease expired"
                        if cancellation_requested
                        else f"{actor} reclaimed an expired worker lease"
                    ),
                    worker_id=lease.worker_id,
                    lease=lease,
                )
            )
        return tuple(events)

    def _validate_active_lease(
        self,
        connection: sqlite3.Connection,
        leased: LeasedJob,
        occurred_at: str,
        *,
        allow_cancellation: bool = False,
    ) -> None:
        row = connection.execute(
            "SELECT l.record_json, j.state, j.cancellation_requested_at "
            "FROM worker_lease l JOIN worker_job j "
            "ON j.tenant_id=l.tenant_id AND j.job_id=l.job_id "
            "WHERE l.tenant_id=? AND l.job_id=?",
            (leased.tenant_id, leased.job.identity.id),
        ).fetchone()
        if row is None or JobState(row["state"]) is not JobState.LEASED:
            raise WorkerQueueError("stale or unknown worker lease")
        active = self._lease_from_json(str(row["record_json"]))
        if active != leased.lease:
            raise WorkerQueueError("stale or unknown worker lease")
        if _timestamp(occurred_at) > _timestamp(active.expires_at):
            raise WorkerQueueError("worker lease expired before completion")
        if row["cancellation_requested_at"] is not None and not allow_cancellation:
            raise WorkerQueueError("worker job cancellation has been requested")

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        tenant_id: str,
        job: WorkerJob,
        kind: WorkerEventKind,
        attempt: int,
        occurred_at: str,
        detail: str,
        worker_id: str | None = None,
        lease: WorkerLease | None = None,
        output_refs: Iterable[str] = (),
        metrics: Mapping[str, Any] | None = None,
    ) -> WorkerEvent:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM worker_event"
            ).fetchone()[0]
        )
        event = WorkerEvent.create(
            sequence=sequence,
            job_id=job.identity.id,
            attempt=attempt,
            event_kind=kind,
            worker_id=worker_id,
            occurred_at=occurred_at,
            lease_id=lease.identity.id if lease is not None else None,
            output_refs=output_refs,
            metrics=metrics,
            detail=detail,
        )
        connection.execute(
            "INSERT INTO worker_event(sequence, event_id, tenant_id, job_id, event_kind, "
            "occurred_at, record_json) VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                event.identity.id,
                tenant_id,
                job.identity.id,
                kind.value,
                occurred_at,
                _record_json(event),
            ),
        )
        return event

    @staticmethod
    def _job_from_json(value: str) -> WorkerJob:
        data = json.loads(value)
        return WorkerJob(
            _identity(data["identity"]),
            str(data["format_version"]),
            str(data["queue"]),
            JobKind(data["kind"]),
            str(data["subject_id"]),
            str(data["payload_ref"]),
            str(data["idempotency_key"]),
            int(data["priority"]),
            int(data["max_attempts"]),
            str(data["created_at"]),
            tuple(data["required_capabilities"]),
        )

    @staticmethod
    def _lease_from_json(value: str) -> WorkerLease:
        data = json.loads(value)
        return WorkerLease(
            _identity(data["identity"]),
            str(data["job_id"]),
            int(data["attempt"]),
            str(data["worker_id"]),
            str(data["lease_token"]),
            str(data["leased_at"]),
            str(data["expires_at"]),
        )

    @staticmethod
    def _event_from_json(value: str) -> WorkerEvent:
        data = json.loads(value)
        return WorkerEvent(
            _identity(data["identity"]),
            int(data["sequence"]),
            str(data["job_id"]),
            int(data["attempt"]),
            WorkerEventKind(data["event_kind"]),
            data.get("worker_id"),
            str(data["occurred_at"]),
            data.get("lease_id"),
            tuple(data["output_refs"]),
            data["metrics"],
            str(data["detail"]),
        )
