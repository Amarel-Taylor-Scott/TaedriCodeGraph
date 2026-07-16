"""Append-only intake and promotion policy for generated primitive candidates.

The registry stores immutable content and revision history.  This module deliberately
keeps workflow state outside those identities: the same revision can be received,
quarantined, indexed, rejected, promoted, or revoked without rewriting its capsule.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .contracts import ProducerRef, RecordMixin
from .identity import IdentityRecord


class CandidateIntakeError(ValueError):
    """Raised when a submission or state transition violates intake policy."""


class CandidateOrigin(str, Enum):
    EXTRACTED = "extracted"
    GENERATED = "generated"
    IMPORTED = "imported"
    HUMAN_AUTHORED = "human_authored"


class CandidateState(str, Enum):
    RECEIVED = "received"
    QUARANTINED = "quarantined"
    STRUCTURALLY_VALID = "structurally_valid"
    INDEXED_CANDIDATE = "indexed_candidate"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    REVOKED = "revoked"


class LicenseEvidenceState(str, Enum):
    UNKNOWN = "unknown"
    DECLARED = "declared"
    VERIFIED = "verified"
    CONFLICTING = "conflicting"


class CandidateVisibility(str, Enum):
    PRIVATE = "private"
    ORGANIZATION = "organization"
    PUBLIC = "public"


_ALLOWED_TRANSITIONS: dict[CandidateState, frozenset[CandidateState]] = {
    CandidateState.RECEIVED: frozenset(
        {CandidateState.QUARANTINED, CandidateState.REJECTED}
    ),
    CandidateState.QUARANTINED: frozenset(
        {CandidateState.STRUCTURALLY_VALID, CandidateState.REJECTED}
    ),
    CandidateState.STRUCTURALLY_VALID: frozenset(
        {CandidateState.INDEXED_CANDIDATE, CandidateState.REJECTED}
    ),
    CandidateState.INDEXED_CANDIDATE: frozenset(
        {CandidateState.PROMOTED, CandidateState.REJECTED}
    ),
    CandidateState.PROMOTED: frozenset({CandidateState.REVOKED}),
    CandidateState.REJECTED: frozenset(),
    CandidateState.REVOKED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class CandidateSubmission(RecordMixin):
    identity: IdentityRecord
    format_version: str
    primitive_id: str
    revision_id: str
    origin: CandidateOrigin
    producer: ProducerRef
    submitted_by: str
    submitted_at: str
    source_uri: str
    source_revision: str | None
    license_expression: str | None
    license_evidence_state: LicenseEvidenceState
    visibility: CandidateVisibility
    production_run_id: str
    evidence_ids: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        primitive_id: str,
        revision_id: str,
        origin: CandidateOrigin,
        producer: ProducerRef,
        submitted_by: str,
        submitted_at: str,
        source_uri: str,
        production_run_id: str,
        source_revision: str | None = None,
        license_expression: str | None = None,
        license_evidence_state: LicenseEvidenceState = LicenseEvidenceState.UNKNOWN,
        visibility: CandidateVisibility = CandidateVisibility.PRIVATE,
        evidence_ids: Iterable[str] = (),
    ) -> "CandidateSubmission":
        if not all(
            (primitive_id, revision_id, submitted_by, submitted_at, source_uri, production_run_id)
        ):
            raise CandidateIntakeError("submission identity and provenance fields are required")
        if license_evidence_state is LicenseEvidenceState.VERIFIED and not license_expression:
            raise CandidateIntakeError("a verified license requires an expression")
        evidence = tuple(sorted(set(evidence_ids)))
        key = {
            "format_version": "1.0.0",
            "primitive_id": primitive_id,
            "revision_id": revision_id,
            "origin": origin.value,
            "producer": producer.to_dict(),
            "submitted_by": submitted_by,
            "submitted_at": submitted_at,
            "source_uri": source_uri,
            "source_revision": source_revision,
            "license_expression": license_expression,
            "license_evidence_state": license_evidence_state.value,
            "visibility": visibility.value,
            "production_run_id": production_run_id,
            "evidence_ids": evidence,
        }
        return cls(
            IdentityRecord.create("candidate_submission", key),
            "1.0.0",
            primitive_id,
            revision_id,
            origin,
            producer,
            submitted_by,
            submitted_at,
            source_uri,
            source_revision,
            license_expression,
            license_evidence_state,
            visibility,
            production_run_id,
            evidence,
        )


@dataclass(frozen=True, slots=True)
class CandidateStateEvent(RecordMixin):
    identity: IdentityRecord
    submission_id: str
    sequence: int
    from_state: CandidateState | None
    to_state: CandidateState
    actor: str
    occurred_at: str
    reason: str
    evidence_ids: tuple[str, ...]
    policy_decision_id: str | None

    @classmethod
    def create(
        cls,
        *,
        submission_id: str,
        sequence: int,
        from_state: CandidateState | None,
        to_state: CandidateState,
        actor: str,
        occurred_at: str,
        reason: str,
        evidence_ids: Iterable[str] = (),
        policy_decision_id: str | None = None,
    ) -> "CandidateStateEvent":
        if sequence <= 0 or not all((submission_id, actor, occurred_at, reason)):
            raise CandidateIntakeError("state event sequence and provenance are required")
        evidence = tuple(sorted(set(evidence_ids)))
        key = {
            "submission_id": submission_id,
            "sequence": sequence,
            "from_state": from_state.value if from_state is not None else None,
            "to_state": to_state.value,
            "actor": actor,
            "occurred_at": occurred_at,
            "reason": reason,
            "evidence_ids": evidence,
            "policy_decision_id": policy_decision_id,
        }
        return cls(
            IdentityRecord.create("candidate_state_event", key),
            submission_id,
            sequence,
            from_state,
            to_state,
            actor,
            occurred_at,
            reason,
            evidence,
            policy_decision_id,
        )


class CandidateIntakeLedger:
    """In-memory conformance implementation for a transactional intake adapter."""

    def __init__(self) -> None:
        self.submissions: dict[str, CandidateSubmission] = {}
        self.events: list[CandidateStateEvent] = []
        self._states: dict[str, CandidateState] = {}

    def submit(self, submission: CandidateSubmission) -> CandidateStateEvent:
        existing = self.submissions.get(submission.identity.id)
        if existing is not None:
            if existing != submission:  # pragma: no cover - identity collision guard
                raise CandidateIntakeError("submission identity collision")
            return self.history(submission.identity.id)[0]
        self.submissions[submission.identity.id] = submission
        event = CandidateStateEvent.create(
            submission_id=submission.identity.id,
            sequence=1,
            from_state=None,
            to_state=CandidateState.RECEIVED,
            actor=submission.submitted_by,
            occurred_at=submission.submitted_at,
            reason="candidate submitted to the immutable intake ledger",
            evidence_ids=submission.evidence_ids,
        )
        self.events.append(event)
        self._states[submission.identity.id] = CandidateState.RECEIVED
        return event

    def state(self, submission_id: str) -> CandidateState:
        try:
            return self._states[submission_id]
        except KeyError as exc:
            raise CandidateIntakeError(f"unknown submission: {submission_id}") from exc

    def history(self, submission_id: str) -> tuple[CandidateStateEvent, ...]:
        if submission_id not in self.submissions:
            raise CandidateIntakeError(f"unknown submission: {submission_id}")
        return tuple(event for event in self.events if event.submission_id == submission_id)

    def transition(
        self,
        submission_id: str,
        to_state: CandidateState,
        *,
        actor: str,
        occurred_at: str,
        reason: str,
        evidence_ids: Iterable[str] = (),
        policy_decision_id: str | None = None,
    ) -> CandidateStateEvent:
        submission = self.submissions.get(submission_id)
        if submission is None:
            raise CandidateIntakeError(f"unknown submission: {submission_id}")
        current = self._states[submission_id]
        if to_state not in _ALLOWED_TRANSITIONS[current]:
            raise CandidateIntakeError(
                f"invalid candidate transition: {current.value} -> {to_state.value}"
            )
        evidence = tuple(sorted(set(evidence_ids)))
        if to_state is CandidateState.PROMOTED:
            if not policy_decision_id or not evidence:
                raise CandidateIntakeError(
                    "promotion requires a policy decision and independent verification evidence"
                )
            if actor in {submission.submitted_by, submission.producer.id}:
                raise CandidateIntakeError(
                    "the submitting producer cannot promote its own candidate"
                )
            if (
                submission.visibility is CandidateVisibility.PUBLIC
                and submission.license_evidence_state is not LicenseEvidenceState.VERIFIED
            ):
                raise CandidateIntakeError(
                    "public promotion requires verified license evidence"
                )
        sequence = len(self.history(submission_id)) + 1
        event = CandidateStateEvent.create(
            submission_id=submission_id,
            sequence=sequence,
            from_state=current,
            to_state=to_state,
            actor=actor,
            occurred_at=occurred_at,
            reason=reason,
            evidence_ids=evidence,
            policy_decision_id=policy_decision_id,
        )
        self.events.append(event)
        self._states[submission_id] = to_state
        return event

