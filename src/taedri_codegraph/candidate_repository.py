"""Durable, tenant-scoped candidate intake and review workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import canonical_json_bytes
from .contracts import ProducerRef, RecordMixin
from .intake import (
    CandidateIntakeError,
    CandidateIntakeLedger,
    CandidateOrigin,
    CandidateState,
    CandidateStateEvent,
    CandidateSubmission,
    CandidateVisibility,
    LicenseEvidenceState,
)
from .saas import SQLiteControlPlane


class CandidateRepositoryError(ValueError):
    """Raised when persisted intake records conflict or cannot be decoded."""


@dataclass(frozen=True, slots=True)
class ImportedCandidateLedger(RecordMixin):
    submissions_created: int
    events_created: int
    submissions_unchanged: int
    submission_ids: tuple[str, ...]


class SQLiteCandidateRepository:
    """Append-only candidate state adapter using domain transitions as policy."""

    def __init__(self, control: SQLiteControlPlane):
        self.control = control

    def import_ledger(
        self,
        tenant_id: str,
        ledger: CandidateIntakeLedger,
        *,
        actor: str,
        imported_at: str,
        resource_id: str,
    ) -> ImportedCandidateLedger:
        self.control.tenant(tenant_id)
        if not actor or not imported_at or not resource_id:
            raise CandidateRepositoryError("candidate import provenance is required")
        created_submissions = 0
        unchanged_submissions = 0
        created_events = 0
        with self.control._transaction() as connection:
            for submission_id in sorted(ledger.submissions):
                submission = ledger.submissions[submission_id]
                history = ledger.history(submission_id)
                record_json = _json(submission)
                existing = connection.execute(
                    "SELECT record_json FROM candidate_submission "
                    "WHERE tenant_id=? AND submission_id=?",
                    (tenant_id, submission_id),
                ).fetchone()
                if existing is None:
                    connection.execute(
                        "INSERT INTO candidate_submission(tenant_id, submission_id, "
                        "primitive_id, revision_id, current_state, visibility, "
                        "license_evidence_state, submitted_at, record_json) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            tenant_id,
                            submission_id,
                            submission.primitive_id,
                            submission.revision_id,
                            history[-1].to_state.value,
                            submission.visibility.value,
                            submission.license_evidence_state.value,
                            submission.submitted_at,
                            record_json,
                        ),
                    )
                    created_submissions += 1
                elif str(existing["record_json"]) != record_json:
                    raise CandidateRepositoryError(
                        f"candidate submission identity collision: {submission_id}"
                    )
                else:
                    unchanged_submissions += 1
                stored = tuple(
                    str(row["record_json"])
                    for row in connection.execute(
                        "SELECT record_json FROM candidate_state_event "
                        "WHERE tenant_id=? AND submission_id=? ORDER BY sequence",
                        (tenant_id, submission_id),
                    )
                )
                incoming = tuple(_json(event) for event in history)
                shared = min(len(stored), len(incoming))
                if stored[:shared] != incoming[:shared]:
                    raise CandidateRepositoryError(
                        f"candidate event history diverged: {submission_id}"
                    )
                for event, encoded in zip(
                    history[len(stored) :], incoming[len(stored) :], strict=True
                ):
                    connection.execute(
                        "INSERT INTO candidate_state_event(tenant_id, submission_id, "
                        "sequence, event_id, to_state, occurred_at, record_json) "
                        "VALUES(?, ?, ?, ?, ?, ?, ?)",
                        (
                            tenant_id,
                            submission_id,
                            event.sequence,
                            event.identity.id,
                            event.to_state.value,
                            event.occurred_at,
                            encoded,
                        ),
                    )
                    created_events += 1
                if len(incoming) >= len(stored):
                    connection.execute(
                        "UPDATE candidate_submission SET current_state=? "
                        "WHERE tenant_id=? AND submission_id=?",
                        (history[-1].to_state.value, tenant_id, submission_id),
                    )
            result = ImportedCandidateLedger(
                created_submissions,
                created_events,
                unchanged_submissions,
                tuple(sorted(ledger.submissions)),
            )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action="candidate.ledger.imported",
                resource_id=resource_id,
                occurred_at=imported_at,
                detail=result.to_dict(),
            )
        return result

    def transition(
        self,
        tenant_id: str,
        submission_id: str,
        to_state: CandidateState,
        *,
        actor: str,
        occurred_at: str,
        reason: str,
        evidence_ids: Iterable[str] = (),
        policy_decision_id: str | None = None,
    ) -> CandidateStateEvent:
        self.control.tenant(tenant_id)
        with self.control._transaction() as connection:
            ledger = self._load_one(tenant_id, submission_id, connection)
            event = ledger.transition(
                submission_id,
                to_state,
                actor=actor,
                occurred_at=occurred_at,
                reason=reason,
                evidence_ids=evidence_ids,
                policy_decision_id=policy_decision_id,
            )
            connection.execute(
                "INSERT INTO candidate_state_event(tenant_id, submission_id, sequence, "
                "event_id, to_state, occurred_at, record_json) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant_id,
                    submission_id,
                    event.sequence,
                    event.identity.id,
                    event.to_state.value,
                    event.occurred_at,
                    _json(event),
                ),
            )
            connection.execute(
                "UPDATE candidate_submission SET current_state=? "
                "WHERE tenant_id=? AND submission_id=?",
                (event.to_state.value, tenant_id, submission_id),
            )
            self.control._append_audit(
                connection,
                tenant_id=tenant_id,
                actor=actor,
                action=f"candidate.{to_state.value}",
                resource_id=submission_id,
                occurred_at=occurred_at,
                detail={
                    "event_id": event.identity.id,
                    "reason": reason,
                    "policy_decision_id": policy_decision_id,
                },
            )
        return event

    def list(
        self,
        tenant_id: str,
        *,
        state: CandidateState | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        self.control.tenant(tenant_id)
        if not 1 <= limit <= 1000:
            raise CandidateRepositoryError("candidate list limit must be 1..1000")
        clauses = ["s.tenant_id=?"]
        parameters: list[Any] = [tenant_id]
        if state is not None:
            clauses.append("s.current_state=?")
            parameters.append(state.value)
        if query:
            clauses.append("(h.namespace LIKE ? OR h.name LIKE ?)")
            pattern = f"%{query}%"
            parameters.extend((pattern, pattern))
        parameters.append(limit)
        statement = (
            "SELECT s.record_json, s.current_state, h.namespace, h.name "
            "FROM candidate_submission s JOIN primitive_handle h "
            "ON h.tenant_id=s.tenant_id AND h.primitive_id=s.primitive_id WHERE "
            + " AND ".join(clauses)
            + " ORDER BY s.submitted_at DESC, s.submission_id LIMIT ?"
        )
        with self.control._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return tuple(
            {
                "submission": json.loads(str(row["record_json"])),
                "current_state": str(row["current_state"]),
                "namespace": str(row["namespace"]),
                "name": str(row["name"]),
            }
            for row in rows
        )

    def get(self, tenant_id: str, submission_id: str) -> dict[str, Any]:
        self.control.tenant(tenant_id)
        with self.control._connect() as connection:
            row = connection.execute(
                "SELECT record_json, current_state FROM candidate_submission "
                "WHERE tenant_id=? AND submission_id=?",
                (tenant_id, submission_id),
            ).fetchone()
            if row is None:
                raise LookupError(f"unknown candidate submission: {submission_id}")
            history = [
                json.loads(str(event["record_json"]))
                for event in connection.execute(
                    "SELECT record_json FROM candidate_state_event "
                    "WHERE tenant_id=? AND submission_id=? ORDER BY sequence",
                    (tenant_id, submission_id),
                )
            ]
        return {
            "submission": json.loads(str(row["record_json"])),
            "current_state": str(row["current_state"]),
            "history": history,
        }

    def _load_one(
        self, tenant_id: str, submission_id: str, connection: Any
    ) -> CandidateIntakeLedger:
        row = connection.execute(
            "SELECT record_json FROM candidate_submission "
            "WHERE tenant_id=? AND submission_id=?",
            (tenant_id, submission_id),
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown candidate submission: {submission_id}")
        submission = _submission(json.loads(str(row["record_json"])))
        events = tuple(
            _event(json.loads(str(item["record_json"])))
            for item in connection.execute(
                "SELECT record_json FROM candidate_state_event "
                "WHERE tenant_id=? AND submission_id=? ORDER BY sequence",
                (tenant_id, submission_id),
            )
        )
        if not events:
            raise CandidateRepositoryError("candidate submission has no initial event")
        ledger = CandidateIntakeLedger()
        if ledger.submit(submission) != events[0]:
            raise CandidateRepositoryError("candidate initial event failed validation")
        for stored in events[1:]:
            replayed = ledger.transition(
                submission_id,
                stored.to_state,
                actor=stored.actor,
                occurred_at=stored.occurred_at,
                reason=stored.reason,
                evidence_ids=stored.evidence_ids,
                policy_decision_id=stored.policy_decision_id,
            )
            if replayed != stored:
                raise CandidateRepositoryError("candidate event failed replay validation")
        return ledger


def _json(value: RecordMixin) -> str:
    return canonical_json_bytes(value.to_dict()).decode("utf-8")


def _producer(value: Mapping[str, Any]) -> ProducerRef:
    return ProducerRef(
        str(value.get("id", "")),
        str(value.get("version", "")),
        str(value.get("config_digest", "")),
    )


def _submission(value: Mapping[str, Any]) -> CandidateSubmission:
    try:
        result = CandidateSubmission.create(
            primitive_id=str(value.get("primitive_id", "")),
            revision_id=str(value.get("revision_id", "")),
            origin=CandidateOrigin(str(value.get("origin", ""))),
            producer=_producer(_mapping(value.get("producer"), "candidate producer")),
            submitted_by=str(value.get("submitted_by", "")),
            submitted_at=str(value.get("submitted_at", "")),
            source_uri=str(value.get("source_uri", "")),
            source_revision=_optional_string(value.get("source_revision")),
            license_expression=_optional_string(value.get("license_expression")),
            license_evidence_state=LicenseEvidenceState(
                str(value.get("license_evidence_state", ""))
            ),
            visibility=CandidateVisibility(str(value.get("visibility", ""))),
            production_run_id=str(value.get("production_run_id", "")),
            evidence_ids=_strings(value.get("evidence_ids")),
        )
    except (CandidateIntakeError, ValueError, TypeError) as exc:
        raise CandidateRepositoryError("stored candidate submission is invalid") from exc
    if result.to_dict() != dict(value):
        raise CandidateRepositoryError("stored candidate submission identity is invalid")
    return result


def _event(value: Mapping[str, Any]) -> CandidateStateEvent:
    try:
        from_state_value = value.get("from_state")
        result = CandidateStateEvent.create(
            submission_id=str(value.get("submission_id", "")),
            sequence=int(value.get("sequence", 0)),
            from_state=(
                CandidateState(str(from_state_value))
                if from_state_value is not None
                else None
            ),
            to_state=CandidateState(str(value.get("to_state", ""))),
            actor=str(value.get("actor", "")),
            occurred_at=str(value.get("occurred_at", "")),
            reason=str(value.get("reason", "")),
            evidence_ids=_strings(value.get("evidence_ids")),
            policy_decision_id=_optional_string(value.get("policy_decision_id")),
        )
    except (CandidateIntakeError, ValueError, TypeError) as exc:
        raise CandidateRepositoryError("stored candidate event is invalid") from exc
    if result.to_dict() != dict(value):
        raise CandidateRepositoryError("stored candidate event identity is invalid")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateRepositoryError(f"{label} must be an object")
    return value


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CandidateRepositoryError("stored string list is invalid")
    return tuple(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CandidateRepositoryError("stored optional string is invalid")
    return value
