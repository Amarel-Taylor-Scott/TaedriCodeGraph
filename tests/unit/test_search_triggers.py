from __future__ import annotations

import unittest

from taedri_codegraph.discovery.triggers import (
    SearchTriggerSignal,
    TriggerKind,
    TriggeredPrimitiveClient,
    default_trigger_router,
    intent_digest,
)
from taedri_codegraph.primitives.search import (
    PrimitiveSearchResponse,
    SearchStageReceipt,
    SearchStrategy,
    primitive_search_request_digest,
    primitive_search_result_digest,
)


class _Search:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        query_digest = primitive_search_request_digest(request)
        rows = []
        stage = SearchStageReceipt.create(
            query_digest=query_digest,
            stage="exact",
            lanes=("exact",),
            executed=True,
            candidate_count=0,
            new_candidate_count=0,
            duration_ms=0,
            stop_reason=None,
            retriever_identity="taedri.search.exact@1.0.0",
            result_digest=primitive_search_result_digest(
                rows, retriever_identity="taedri.search.exact@1.0.0"
            ),
        )
        return PrimitiveSearchResponse.create(
            query_digest=query_digest,
            strategy=request.strategy,
            items=rows,
            stages=(stage,),
            escalated=False,
            stop_reason="fixture",
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

    def test_confidence_gated_tiers_fail_closed_when_confidence_is_unknown(self) -> None:
        router = default_trigger_router()
        for kind in (
            TriggerKind.REPEATED_BOILERPLATE,
            TriggerKind.CLASSIFIER_SUGGESTION,
            TriggerKind.MODEL_SUGGESTION,
        ):
            with self.subTest(kind=kind.value):
                decision = router.decide(_signal(kind))
                self.assertFalse(decision.should_search)
                self.assertTrue(
                    any(
                        item.reason == "confidence_unknown"
                        for item in decision.receipts
                    )
                )

    def test_confidence_gated_tiers_accept_only_at_or_above_their_floor(self) -> None:
        cases = (
            (TriggerKind.REPEATED_BOILERPLATE, 600_000),
            (TriggerKind.CLASSIFIER_SUGGESTION, 750_000),
            (TriggerKind.MODEL_SUGGESTION, 850_000),
        )
        for kind, threshold in cases:
            with self.subTest(kind=kind.value):
                below = default_trigger_router().decide(
                    _signal(kind, confidence_ppm=threshold - 1)
                )
                at_floor = default_trigger_router().decide(
                    _signal(kind, confidence_ppm=threshold)
                )
                self.assertFalse(below.should_search)
                self.assertTrue(at_floor.should_search)

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
