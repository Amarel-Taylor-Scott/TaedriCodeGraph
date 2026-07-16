"""Privacy-aware prompt-session and coding-harness receipt contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from .canonical import to_primitive
from .contracts import RecordMixin
from .identity import IdentityRecord


class PromptSessionError(ValueError):
    """Raised when a harness records an invalid or privacy-breaking event."""


class PromptPrivacyMode(str, Enum):
    DIGEST_ONLY = "digest_only"
    ENCRYPTED_REFERENCE = "encrypted_reference"
    EXPLICIT_CAPTURE = "explicit_capture"


class SessionEventKind(str, Enum):
    SESSION_STARTED = "session_started"
    REQUEST_CAPTURED = "request_captured"
    SEARCH_RECEIPT = "search_receipt"
    CANDIDATE_SELECTED = "candidate_selected"
    MATERIALIZATION_RECEIPT = "materialization_receipt"
    MODEL_ATTEMPT = "model_attempt"
    VERIFICATION_RECEIPT = "verification_receipt"
    RESULT_ACCEPTED = "result_accepted"
    ABSTAINED = "abstained"
    SESSION_CLOSED = "session_closed"


@dataclass(frozen=True, slots=True)
class HarnessRef(RecordMixin):
    id: str
    version: str
    config_digest: str
    interface: str

    def __post_init__(self) -> None:
        if not self.id or not self.version or not self.interface:
            raise PromptSessionError("harness identity, version, and interface are required")
        if not self.config_digest.startswith("sha256:"):
            raise PromptSessionError("harness configuration must be content addressed")


@dataclass(frozen=True, slots=True)
class PromptSession(RecordMixin):
    identity: IdentityRecord
    format_version: str
    tenant_id: str
    workspace_id: str
    repository_snapshot_id: str
    harness: HarnessRef
    policy_digest: str
    privacy_mode: PromptPrivacyMode
    started_at: str

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        workspace_id: str,
        repository_snapshot_id: str,
        harness: HarnessRef,
        policy_digest: str,
        privacy_mode: PromptPrivacyMode,
        started_at: str,
    ) -> "PromptSession":
        if not all(
            (
                tenant_id,
                workspace_id,
                repository_snapshot_id,
                policy_digest,
                started_at,
            )
        ):
            raise PromptSessionError("session scope and policy fields are required")
        if not policy_digest.startswith("sha256:"):
            raise PromptSessionError("session policy must be content addressed")
        key = {
            "format_version": "1.0.0",
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "repository_snapshot_id": repository_snapshot_id,
            "harness": harness.to_dict(),
            "policy_digest": policy_digest,
            "privacy_mode": privacy_mode.value,
            "started_at": started_at,
        }
        return cls(
            IdentityRecord.create("prompt_session", key),
            "1.0.0",
            tenant_id,
            workspace_id,
            repository_snapshot_id,
            harness,
            policy_digest,
            privacy_mode,
            started_at,
        )


@dataclass(frozen=True, slots=True)
class PromptSessionEvent(RecordMixin):
    identity: IdentityRecord
    session_id: str
    sequence: int
    event_kind: SessionEventKind
    actor: str
    occurred_at: str
    input_refs: tuple[str, ...]
    output_refs: tuple[str, ...]
    attributes: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        sequence: int,
        event_kind: SessionEventKind,
        actor: str,
        occurred_at: str,
        input_refs: Iterable[str] = (),
        output_refs: Iterable[str] = (),
        attributes: Mapping[str, Any] | None = None,
    ) -> "PromptSessionEvent":
        if sequence <= 0 or not all((session_id, actor, occurred_at)):
            raise PromptSessionError("session event identity and provenance are required")
        inputs = tuple(input_refs)
        outputs = tuple(output_refs)
        attribute_values = to_primitive(dict(attributes or {}))
        if not isinstance(attribute_values, dict):  # pragma: no cover - defensive
            raise PromptSessionError("session attributes must be a mapping")
        key = {
            "session_id": session_id,
            "sequence": sequence,
            "event_kind": event_kind.value,
            "actor": actor,
            "occurred_at": occurred_at,
            "input_refs": inputs,
            "output_refs": outputs,
            "attributes": attribute_values,
        }
        return cls(
            IdentityRecord.create("prompt_session_event", key),
            session_id,
            sequence,
            event_kind,
            actor,
            occurred_at,
            inputs,
            outputs,
            attribute_values,
        )


class PromptSessionLedger:
    """Append-only harness audit stream with a small conformance state machine."""

    _PROHIBITED_DIGEST_ONLY_KEYS = frozenset(
        {"prompt", "prompt_text", "raw_prompt", "message_text", "source_body"}
    )

    def __init__(self) -> None:
        self.sessions: dict[str, PromptSession] = {}
        self.events: list[PromptSessionEvent] = []

    def start(self, session: PromptSession, *, actor: str) -> PromptSessionEvent:
        existing = self.sessions.get(session.identity.id)
        if existing is not None:
            if existing != session:  # pragma: no cover - digest collision guard
                raise PromptSessionError("session identity collision")
            return self.history(session.identity.id)[0]
        self.sessions[session.identity.id] = session
        return self._append(
            session,
            SessionEventKind.SESSION_STARTED,
            actor=actor,
            occurred_at=session.started_at,
            output_refs=(session.identity.id,),
            attributes={"privacy_mode": session.privacy_mode.value},
        )

    def history(self, session_id: str) -> tuple[PromptSessionEvent, ...]:
        if session_id not in self.sessions:
            raise PromptSessionError(f"unknown session: {session_id}")
        return tuple(event for event in self.events if event.session_id == session_id)

    def record(
        self,
        session_id: str,
        event_kind: SessionEventKind,
        *,
        actor: str,
        occurred_at: str,
        input_refs: Iterable[str] = (),
        output_refs: Iterable[str] = (),
        attributes: Mapping[str, Any] | None = None,
    ) -> PromptSessionEvent:
        session = self.sessions.get(session_id)
        if session is None:
            raise PromptSessionError(f"unknown session: {session_id}")
        inputs = tuple(input_refs)
        outputs = tuple(output_refs)
        values = dict(attributes or {})
        history = self.history(session_id)
        kinds = [event.event_kind for event in history]
        if kinds[-1] is SessionEventKind.SESSION_CLOSED:
            raise PromptSessionError("a closed session is immutable")
        if event_kind is SessionEventKind.SESSION_STARTED:
            raise PromptSessionError("session_started is created by start()")
        if event_kind is SessionEventKind.REQUEST_CAPTURED:
            if not inputs:
                raise PromptSessionError("request capture requires a digest or secure content reference")
        elif event_kind is SessionEventKind.SEARCH_RECEIPT:
            self._require(kinds, SessionEventKind.REQUEST_CAPTURED, event_kind)
            self._require_outputs(outputs, event_kind)
        elif event_kind is SessionEventKind.CANDIDATE_SELECTED:
            self._require(kinds, SessionEventKind.SEARCH_RECEIPT, event_kind)
            self._require_outputs(outputs, event_kind)
        elif event_kind is SessionEventKind.MATERIALIZATION_RECEIPT:
            self._require(kinds, SessionEventKind.CANDIDATE_SELECTED, event_kind)
            self._require_outputs(outputs, event_kind)
        elif event_kind is SessionEventKind.MODEL_ATTEMPT:
            self._require(kinds, SessionEventKind.REQUEST_CAPTURED, event_kind)
            self._require_outputs(outputs, event_kind)
        elif event_kind is SessionEventKind.VERIFICATION_RECEIPT:
            self._require(kinds, SessionEventKind.MODEL_ATTEMPT, event_kind)
            self._require_outputs(outputs, event_kind)
            if values.get("outcome") not in {"passed", "failed", "error", "unknown"}:
                raise PromptSessionError(
                    "verification receipts require an explicit passed/failed/error/unknown outcome"
                )
        elif event_kind is SessionEventKind.RESULT_ACCEPTED:
            self._require(kinds, SessionEventKind.VERIFICATION_RECEIPT, event_kind)
            self._require_outputs(outputs, event_kind)
            latest_verification = next(
                event
                for event in reversed(history)
                if event.event_kind is SessionEventKind.VERIFICATION_RECEIPT
            )
            if latest_verification.attributes.get("outcome") != "passed":
                raise PromptSessionError("only a passed verification can precede acceptance")
            if not isinstance(values.get("policy_decision_ref"), str):
                raise PromptSessionError("accepted results require a policy decision reference")
        elif event_kind is SessionEventKind.ABSTAINED:
            self._require(kinds, SessionEventKind.REQUEST_CAPTURED, event_kind)
            if not isinstance(values.get("reason_code"), str):
                raise PromptSessionError("abstention requires a reason_code")
        elif event_kind is SessionEventKind.SESSION_CLOSED:
            if not any(
                kind in {SessionEventKind.RESULT_ACCEPTED, SessionEventKind.ABSTAINED}
                for kind in kinds
            ):
                raise PromptSessionError("a session closes only after acceptance or abstention")
        return self._append(
            session,
            event_kind,
            actor=actor,
            occurred_at=occurred_at,
            input_refs=inputs,
            output_refs=outputs,
            attributes=values,
        )

    def _append(
        self,
        session: PromptSession,
        event_kind: SessionEventKind,
        *,
        actor: str,
        occurred_at: str,
        input_refs: Iterable[str] = (),
        output_refs: Iterable[str] = (),
        attributes: Mapping[str, Any] | None = None,
    ) -> PromptSessionEvent:
        values = dict(attributes or {})
        if (
            session.privacy_mode is PromptPrivacyMode.DIGEST_ONLY
            and self._contains_prohibited_key(values)
        ):
            raise PromptSessionError(
                "digest-only sessions cannot persist raw prompts, messages, or source bodies"
            )
        event = PromptSessionEvent.create(
            session_id=session.identity.id,
            sequence=len(self.history(session.identity.id)) + 1,
            event_kind=event_kind,
            actor=actor,
            occurred_at=occurred_at,
            input_refs=input_refs,
            output_refs=output_refs,
            attributes=values,
        )
        self.events.append(event)
        return event

    @classmethod
    def _contains_prohibited_key(cls, value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                str(key).lower() in cls._PROHIBITED_DIGEST_ONLY_KEYS
                or cls._contains_prohibited_key(item)
                for key, item in value.items()
            )
        if isinstance(value, list | tuple):
            return any(cls._contains_prohibited_key(item) for item in value)
        return False

    @staticmethod
    def _require(
        kinds: Iterable[SessionEventKind],
        required: SessionEventKind,
        requested: SessionEventKind,
    ) -> None:
        if required not in kinds:
            raise PromptSessionError(
                f"{requested.value} requires an earlier {required.value} event"
            )

    @staticmethod
    def _require_outputs(outputs: tuple[str, ...], event_kind: SessionEventKind) -> None:
        if not outputs:
            raise PromptSessionError(f"{event_kind.value} requires at least one output receipt")
