from __future__ import annotations

import unittest

from taedri_codegraph.primitives.search import (
    PrimitiveSearchRequest,
    PrimitiveSearchService,
    SearchStrategy,
)


class _Index:
    def __init__(self) -> None:
        self.calls = []

    def hybrid_search(self, text, **kwargs):
        lanes = tuple(kwargs["lanes"])
        self.calls.append(lanes)
        if lanes == ("exact",):
            return [
                {
                    "entity_id": "entity:exact",
                    "qualified_name": "pkg.parse",
                    "description": "parse address",
                }
            ]
        if lanes == ("lexical", "blocking"):
            return [
                {"entity_id": "entity:exact", "qualified_name": "pkg.parse"},
                {"entity_id": "entity:tag", "qualified_name": "pkg.tag"},
            ]
        if lanes == ("vector",):
            return [
                {"entity_id": "entity:tokenize", "qualified_name": "pkg.tokenize"}
            ]
        raise AssertionError(lanes)

    def structurally_similar(self, identifier, *, limit=50):
        self.calls.append(("structural", identifier))
        return [{"entity_id": "entity:helper", "qualified_name": "pkg.helper"}]


class PrimitiveSearchServiceTests(unittest.TestCase):
    def test_auto_waterfall_escalates_when_candidates_are_insufficient(self) -> None:
        index = _Index()
        response = PrimitiveSearchService(index).search(
            PrimitiveSearchRequest(
                "parse an address",
                SearchStrategy.AUTO,
                limit=5,
                minimum_candidates=4,
            )
        )
        self.assertEqual(response.stop_reason, "candidate_budget_satisfied")
        self.assertTrue(response.escalated)
        self.assertEqual(len(response.items), 4)
        self.assertIn(("vector",), index.calls)
        self.assertTrue(any(call[0] == "structural" for call in index.calls if len(call) > 1))
        self.assertNotIn("parse an address", response.query_digest)

    def test_fast_strategy_stops_after_exact_when_threshold_is_met(self) -> None:
        index = _Index()
        response = PrimitiveSearchService(index).search(
            PrimitiveSearchRequest(
                "pkg.parse",
                SearchStrategy.FAST,
                limit=3,
                minimum_candidates=1,
            )
        )
        self.assertEqual(index.calls, [("exact",)])
        self.assertEqual(response.items[0]["entity_id"], "entity:exact")
        self.assertFalse(response.escalated)


if __name__ == "__main__":
    unittest.main()
