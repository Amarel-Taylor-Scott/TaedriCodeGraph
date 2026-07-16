from __future__ import annotations

import unittest

from taedri_codegraph.discovery.triggers import (
    SearchTriggerSignal,
    TriggerKind,
    TriggeredPrimitiveClient,
    default_trigger_router,
    intent_digest,
)
from taedri_codegraph.primitives.search import PrimitiveSearchResponse, SearchStrategy


class _Search:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return PrimitiveSearchResponse(
            intent_digest(request.query),
            request.strategy,
            (),
            (),
            False,
            "fixture",
        )


def _signal(kind, intent="reuse address parser", **kwargs):
    return SearchTriggerSignal(
        "event-1",
        "session-1",
        kind,
        intent_digest(intent),
        "2026-07-16T12:00:00Z",
        **kwargs,
    )


class SearchTriggerTests(unittest.TestCase):
    def test_explicit_user_signal_selects_deep_search(self) -> None:
        decision = default_trigger_router().decide(
            _signal(TriggerKind.USER_EXPLICIT)
        )
        self.assertTrue(decision.should_search)
        self.assertEqual(decision.strategy, SearchStrategy.DEEP)
        self.assertEqual(decision.disclosure_level, "contract")
        self.assertEqual(decision.selected_rule_ref, "taedri.trigger.explicit@1.0.0")

    def test_deterministic_signal_requires_language_and_respects_cooldown(self) -> None:
        clock = iter((1000, 2000))
        router = default_trigger_router(monotonic_ms=lambda: next(clock))
        signal = _signal(TriggerKind.MISSING_SYMBOL, language="python")
        self.assertTrue(router.decide(signal).should_search)
        second = router.decide(signal)
        self.assertFalse(second.should_search)
        self.assertTrue(any(item.reason == "cooldown" for item in second.receipts))

    def test_raw_prompt_capture_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot capture prompt"):
            _signal(TriggerKind.PRE_EDIT, attributes={"prompt": "secret"})

    def test_client_checks_intent_digest_before_search(self) -> None:
        search = _Search()
        client = TriggeredPrimitiveClient(default_trigger_router(), search)
        signal = _signal(TriggerKind.USER_EXPLICIT)
        with self.assertRaisesRegex(ValueError, "does not match"):
            client.handle(signal, current_intent="different")
        result = client.handle(signal, current_intent="reuse address parser")
        self.assertIsNotNone(result.response)
        self.assertEqual(len(search.requests), 1)


if __name__ == "__main__":
    unittest.main()
