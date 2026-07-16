"""Durable tenant-scoped prompt-session receipts for coding harnesses."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .canonical import canonical_json_bytes
from .contracts import RecordMixin
from .saas import SQLiteControlPlane
from .sessions import (
    HarnessRef,
    PromptPrivacyMode,
    PromptSession,
    PromptSessionError,
    PromptSessionEvent,
    PromptSessionLedger,
    SessionEventKind,
)


class SessionRepositoryError(ValueError):
    """Raised when stored session state cannot be validated or replayed."""


class SessionRepositoryConflict(SessionRepositoryError):
    """Raised when an append compare-and-swap sequence is stale or divergent."""


class SQLitePromptSessionRepository:
    """Append-only session repository that reuses the privacy state machine."""

    def __init__(self, control: SQLiteControlPlane):
        self.control = control

    def start(self, session: PromptSession, *, actor: str) -> PromptSessionEvent:
        self.control.tenant(session.tenant_id)
        with self.control._transaction() as connection:
            existing = connection.execute(
                "SELECT record_json FROM prompt_session WHERE tenant_id=? AND session_id=?",
                (session.tenant_id, session.identity.id),
            ).fetchone()
            if existing is not None:
                if str(existing["record_json"]) != _json(session):
                    raise SessionRepositoryError("prompt session identity collision")
                event = connection.execute(
                    "SELECT record_json FROM prompt_session_event "
                    "WHERE tenant_id=? AND session_id=? AND sequence=1",
                    (session.tenant_id, session.identity.id),
                ).fetchone()
                if event is None:
                    raise SessionRepositoryError("stored session is missing its start event")
                return _event(json.loads(str(event["record_json"])))
            ledger = PromptSessionLedger()
            event = ledger.start(session, actor=actor)
            connection.execute(
                "INSERT INTO prompt_session(tenant_id, session_id, workspace_id, "
                "privacy_mode, started_at, closed_at, record_json) "
                "VALUES(?, ?, ?, ?, ?, NULL, ?)",
                (
                    session.tenant_id,
                    session.identity.id,
                    session.workspace_id,
                    session.privacy_mode.value,
                    session.started_at,
                    _json(session),
                ),
            )
            self._insert_event(connection, session.tenant_id, event)
            self.control._append_audit(
                connection,
                tenant_id=session.tenant_id,
                actor=actor,
                action="prompt_session.started",
                resource_id=session.identity.id,
                occurred_at=session.started_at,
                detail={
                    "event_id": event.identity.id,
                    "privacy_mode": session.privacy_mode.value,
                },
            )
        return event

    def record(
        self,
        tenant_id: str,
        session_id: str,
        event_kind: SessionEventKind,
        *,
        actor: str,
        occurred_at: str,
        input_refs: Iterable[str] = (),
        output_refs: Iterable[str] = (),
        attributes: Mapping[str, Any] | None = None,
        expected_sequence: int | None = None,
    ) -> PromptSessionEvent:
        self.control.tenant(tenant_id)
        with self.control._transaction() as connection:
            ledger = self._load(tenant_id, session_id, connection)
            history = ledger.history(session_id)
            inputs = tuple(input_refs)
            outputs = tuple(output_refs)
            attribute_values = dict(attributes or {})
            if expected_sequence is not None:
                if expected_sequence <= 0:
                    raise SessionRepositoryError("expected session sequence must be positive")
                if expected_sequence <= len(history):
                    desired = PromptSessionEvent.create(
                        session_id=session_id,
                        sequence=expected_sequence,
                        event_kind=event_kind,
                        actor=actor,
                        occurred_at=occurred_at,
                        input_refs=inputs,
                        output_refs=outputs,
                        attributes=attribute_values,
                    )
                    stored = history[expected_sequence - 1]
                    if desired == stored:
                        return stored
                    raise SessionRepositoryConflict(
                        "session sequence already contains a different event"
                    )
                if expected_sequence != len(history) + 1:
                    raise SessionRepositoryConflict(
                        f"session append expected sequence {len(history) + 1}"
                    )
            event = ledger.record(
                session_id,
                event_kind,
                actor=actor,
                occurred_at=occurred_at,
                input_refs=inputs,
                output_refs=outputs,
                attributes=attribute_values,
            )
            self._insert_event(connection, tenant_id, event)
            if event_kind is SessionEventKind.SESSION_CLOSED:
                connection.execute(
                    "UPDATE prompt_session SET closed_at=? "
                    "WHERE tenant_id=? AND session_id=?",
                    (occurred_at, tenant_id, session_id),
                )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action=f"prompt_session.{event_kind.value}",
                resource_id=session_id,
                occurred_at=occurred_at,
                detail={
                    "event_id": event.identity.id,
                    "sequence": event.sequence,
                    "input_ref_count": len(event.input_refs),
                    "output_ref_count": len(event.output_refs),
                },
            )
        return event

    def get(self, tenant_id: str, session_id: str) -> dict[str, Any]:
        self.control.tenant(tenant_id)
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT record_json, closed_at FROM prompt_session "
                "WHERE tenant_id=? AND session_id=?",
                (tenant_id, session_id),
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown prompt session: {session_id}")
            events = [
                json.loads(str(event["record_json"]))
                for event in connection.execute(
                    "SELECT record_json FROM prompt_session_event "
                    "WHERE tenant_id=? AND session_id=? ORDER BY sequence",
                    (tenant_id, session_id),
                )
            ]
        return {
            "session": json.loads(str(row["record_json"])),
            "closed_at": str(row["closed_at"]) if row["closed_at"] is not None else None,
            "events": events,
            "event_count": len(events),
        }

    def list(
        self,
        tenant_id: str,
        *,
        workspace_id: str | None = None,
        limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        self.control.tenant(tenant_id)
        if not 1 <= limit <= 1000:
            raise SessionRepositoryError("session list limit must be 1..1000")
        statement = (
            "SELECT record_json, closed_at FROM prompt_session WHERE tenant_id=?"
        )
        parameters: list[Any] = [tenant_id]
        if workspace_id is not None:
            statement += " AND workspace_id=?"
            parameters.append(workspace_id)
        statement += " ORDER BY started_at DESC, session_id LIMIT ?"
        parameters.append(limit)
        with self.control._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return tuple(
            {
                "session": json.loads(str(row["record_json"])),
                "closed_at": (
                    str(row["closed_at"]) if row["closed_at"] is not None else None
                ),
            }
            for row in rows
        )

    def _load(self, tenant_id: str, session_id: str, connection: Any) -> PromptSessionLedger:
        row = connection.execute(
            "SELECT record_json FROM prompt_session WHERE tenant_id=? AND session_id=?",
            (tenant_id, session_id),
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown prompt session: {session_id}")
        session = _session(json.loads(str(row["record_json"])))
        events = tuple(
            _event(json.loads(str(item["record_json"])))
            for item in connection.execute(
                "SELECT record_json FROM prompt_session_event "
                "WHERE tenant_id=? AND session_id=? ORDER BY sequence",
                (tenant_id, session_id),
            )
        )
        if not events:
            raise SessionRepositoryError("prompt session has no start event")
        ledger = PromptSessionLedger()
        if ledger.start(session, actor=events[0].actor) != events[0]:
            raise SessionRepositoryError("prompt session start event failed validation")
        for stored in events[1:]:
            replayed = ledger.record(
                session_id,
                stored.event_kind,
                actor=stored.actor,
                occurred_at=stored.occurred_at,
                input_refs=stored.input_refs,
                output_refs=stored.output_refs,
                attributes=stored.attributes,
            )
            if replayed != stored:
                raise SessionRepositoryError("prompt session event failed replay validation")
        return ledger

    @staticmethod
    def _insert_event(connection: Any, tenant_id: str, event: PromptSessionEvent) -> None:
        connection.execute(
            "INSERT INTO prompt_session_event(tenant_id, session_id, sequence, event_id, "
            "event_kind, occurred_at, record_json) VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                tenant_id,
                event.session_id,
                event.sequence,
                event.identity.id,
                event.event_kind.value,
                event.occurred_at,
                _json(event),
            ),
        )


def _json(value: RecordMixin) -> str:
    return canonical_json_bytes(value.to_dict()).decode("utf-8")


def _session(value: Mapping[str, Any]) -> PromptSession:
    try:
        harness_value = _mapping(value.get("harness"), "session harness")
        result = PromptSession.create(
            tenant_id=str(value.get("tenant_id", "")),
            workspace_id=str(value.get("workspace_id", "")),
            repository_snapshot_id=str(value.get("repository_snapshot_id", "")),
            harness=HarnessRef(
                str(harness_value.get("id", "")),
                str(harness_value.get("version", "")),
                str(harness_value.get("config_digest", "")),
                str(harness_value.get("interface", "")),
            ),
            policy_digest=str(value.get("policy_digest", "")),
            privacy_mode=PromptPrivacyMode(str(value.get("privacy_mode", ""))),
            started_at=str(value.get("started_at", "")),
        )
    except (PromptSessionError, ValueError, TypeError) as exc:
        raise SessionRepositoryError("stored prompt session is invalid") from exc
    if result.to_dict() != dict(value):
        raise SessionRepositoryError("stored prompt session identity is invalid")
    return result


def _event(value: Mapping[str, Any]) -> PromptSessionEvent:
    try:
        attributes = _mapping(value.get("attributes"), "session event attributes")
        result = PromptSessionEvent.create(
            session_id=str(value.get("session_id", "")),
            sequence=int(value.get("sequence", 0)),
            event_kind=SessionEventKind(str(value.get("event_kind", ""))),
            actor=str(value.get("actor", "")),
            occurred_at=str(value.get("occurred_at", "")),
            input_refs=_strings(value.get("input_refs")),
            output_refs=_strings(value.get("output_refs")),
            attributes=attributes,
        )
    except (PromptSessionError, ValueError, TypeError) as exc:
        raise SessionRepositoryError("stored prompt session event is invalid") from exc
    if result.to_dict() != dict(value):
        raise SessionRepositoryError("stored prompt session event identity is invalid")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionRepositoryError(f"{label} must be an object")
    return value


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SessionRepositoryError("stored reference list is invalid")
    return tuple(value)
