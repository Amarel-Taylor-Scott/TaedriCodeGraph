from __future__ import annotations

import json
import unittest
from typing import Mapping

from taedri_codegraph.api_client import TaedriClient
from taedri_codegraph.discovery import (
    RemotePrimitiveSearchClient,
    SearchTriggerSignal,
    TriggerKind,
    TriggeredPrimitiveClient,
    default_trigger_router,
    intent_digest,
)


class _Transport:
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> tuple[int, bytes]:
        payload = {
            "items": [{"entity_id": "uceg:v1:entity:fixture"}],
            "search_waterfall": {
                "query_digest": intent_digest("parse address"),
                "strategy": "deep",
                "stages": [
                    {
                        "stage": "exact",
                        "lanes": ["exact"],
                        "executed": True,
                        "candidate_count": 1,
                        "new_candidate_count": 1,
                        "duration_ms": 0,
                        "stop_reason": None,
                    }
                ],
                "escalated": False,
                "stop_reason": "candidate_budget_satisfied",
            },
        }
        self.url = url
        return 200, json.dumps(payload).encode("utf-8")


class RemoteTriggerClientTests(unittest.TestCase):
    def test_explicit_trigger_runs_remote_adaptive_search_without_raw_intent_receipt(self) -> None:
        transport = _Transport()
        remote = RemotePrimitiveSearchClient(
            TaedriClient("https://api.example.test", "secret", transport=transport)
        )
        client = TriggeredPrimitiveClient(default_trigger_router(), remote)
        signal = SearchTriggerSignal(
            "event-1",
            "session-1",
            TriggerKind.USER_EXPLICIT,
            intent_digest("parse address"),
            "2026-07-16T19:00:00Z",
        )
        result = client.handle(signal, current_intent="parse address")
        self.assertTrue(result.decision.should_search)
        self.assertEqual(result.response.items[0]["entity_id"], "uceg:v1:entity:fixture")
        self.assertIn("mode=adaptive", transport.url)
        self.assertIn("strategy=deep", transport.url)
        self.assertNotIn("secret", transport.url)


if __name__ == "__main__":
    unittest.main()
