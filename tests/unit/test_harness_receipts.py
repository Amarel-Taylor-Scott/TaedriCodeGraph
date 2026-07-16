from __future__ import annotations

import unittest
from typing import Any

from taedri_codegraph.api_client import APIResponseError
from taedri_codegraph.harness_receipts import RemoteSessionRecorder


class FakeSessionClient:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = [{"event_kind": "session_started"}]
        self.conflict_once = False

    def session(self, session_id: str) -> dict[str, Any]:
        return {"event_count": len(self.events)}

    def record_session_event(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]:
        if self.conflict_once:
            self.conflict_once = False
            self.events.append({"event_kind": "external_event"})
            raise APIResponseError(409, "session_conflict", "sequence changed")
        self.events.append(event)
        return {
            "event": {
                "identity": {
                    "id": f"uceg:v1:prompt_session_event:{len(self.events)}"
                }
            }
        }


class RemoteSessionRecorderTests(unittest.TestCase):
    def test_search_records_only_digests_and_retries_one_sequence_conflict(self) -> None:
        client = FakeSessionClient()
        client.conflict_once = True
        recorder = RemoteSessionRecorder(client, "uceg:v1:prompt_session:test")  # type: ignore[arg-type]
        refs = recorder.record_search(
            "private normalize intent",
            {"items": [{"entity_id": "entity-a"}], "count": 1},
            tool_name="search_code",
        )
        self.assertEqual(len(refs), 2)
        captured, searched = client.events[-2:]
        self.assertEqual(captured["event_kind"], "request_captured")
        self.assertEqual(searched["event_kind"], "search_receipt")
        serialized = repr(client.events)
        self.assertNotIn("private normalize intent", serialized)
        self.assertIn("sha256:", serialized)


if __name__ == "__main__":
    unittest.main()
