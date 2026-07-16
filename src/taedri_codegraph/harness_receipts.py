"""Fail-closed prompt-session instrumentation for remote agent tools."""

from __future__ import annotations

import threading
from typing import Any, Mapping

from .api_client import APIResponseError, TaedriClient
from .canonical import canonical_json_bytes, sha256_digest
from .saas import utc_now


class HarnessReceiptError(RuntimeError):
    """Raised when configured harness evidence cannot be appended safely."""


class RemoteSessionRecorder:
    """Append digest-only request/search receipts with sequence compare-and-swap."""

    def __init__(self, client: TaedriClient, session_id: str):
        if not session_id:
            raise HarnessReceiptError("prompt session ID is required")
        self.client = client
        self.session_id = session_id
        self._lock = threading.Lock()

    def record_search(
        self, query: str, response: Mapping[str, Any], *, tool_name: str
    ) -> tuple[str, str]:
        if not query or not tool_name:
            raise HarnessReceiptError("search query and tool name are required")
        query_ref = sha256_digest(query.encode("utf-8"))
        response_ref = sha256_digest(canonical_json_bytes(response))
        with self._lock:
            captured = self._append(
                "request_captured",
                input_refs=[query_ref],
                output_refs=[],
                attributes={
                    "capture": "digest_only",
                    "tool": tool_name,
                    "query_digest": query_ref,
                },
            )
            searched = self._append(
                "search_receipt",
                input_refs=[query_ref],
                output_refs=[response_ref],
                attributes={
                    "tool": tool_name,
                    "response_digest": response_ref,
                    "result_count": int(response.get("count", len(response.get("items", [])))),
                },
            )
        return (
            str(captured["event"]["identity"]["id"]),
            str(searched["event"]["identity"]["id"]),
        )

    def _append(
        self,
        event_kind: str,
        *,
        input_refs: list[str],
        output_refs: list[str],
        attributes: Mapping[str, Any],
    ) -> dict[str, Any]:
        for attempt in range(2):
            state = self.client.session(self.session_id)
            expected_sequence = int(state["event_count"]) + 1
            try:
                return self.client.record_session_event(
                    self.session_id,
                    {
                        "event_kind": event_kind,
                        "expected_sequence": expected_sequence,
                        "occurred_at": utc_now(),
                        "input_refs": input_refs,
                        "output_refs": output_refs,
                        "attributes": dict(attributes),
                    },
                )
            except APIResponseError as exc:
                if exc.status == 409 and attempt == 0:
                    continue
                raise HarnessReceiptError(
                    f"prompt-session receipt failed: {exc.code}"
                ) from exc
        raise HarnessReceiptError("prompt-session receipt sequence did not converge")
