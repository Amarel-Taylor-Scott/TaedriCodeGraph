from __future__ import annotations

import unittest
from dataclasses import replace

from taedri_codegraph.primitives.search import (
    PrimitiveSearchRequest,
    PrimitiveSearchService,
    SearchStrategy,
    primitive_search_request_digest,
    primitive_search_result_digest,
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


class _SemanticSearch:
    retriever_identity = "taedri.test.semantic-embedding@2.1.0"

    def __init__(self) -> None:
        self.calls = []

    def __call__(self, request, *, limit):
        self.calls.append((request.query, limit))
        return [
            {
                "entity_id": "entity:meaning",
                "qualified_name": "pkg.meaning",
                "description": "model-backed semantic result",
            }
        ]


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
        self.assertEqual(
            [stage.stage for stage in response.stages],
            ["exact", "sparse", "lexical_hash_vector", "semantic", "structural"],
        )
        lexical_hash = response.stages[2]
        self.assertTrue(lexical_hash.executed)
        self.assertEqual(
            lexical_hash.retriever_identity, "uceg.embedding.lexical_hash64@1.0.0"
        )
        self.assertTrue(lexical_hash.result_digest.startswith("sha256:"))
        semantic = response.stages[3]
        self.assertFalse(semantic.executed)
        self.assertEqual(semantic.stop_reason, "semantic_retriever_unavailable")
        self.assertEqual(
            semantic.retriever_identity, "taedri.search.semantic-callback@1.0.0"
        )
        self.assertTrue(
            semantic.receipt_id.startswith("uceg:v1:primitive_search_stage_receipt:")
        )

    def test_lexical_hash_and_true_semantic_lanes_coexist(self) -> None:
        index = _Index()
        semantic_search = _SemanticSearch()
        response = PrimitiveSearchService(
            index, semantic_search=semantic_search
        ).search(
            PrimitiveSearchRequest(
                "parse by meaning",
                SearchStrategy.BALANCED,
                limit=10,
                minimum_candidates=1,
                allow_structural=False,
            )
        )
        self.assertIn(("vector",), index.calls)
        self.assertEqual(semantic_search.calls, [("parse by meaning", 50)])
        stages = {stage.stage: stage for stage in response.stages}
        lexical_hash = stages["lexical_hash_vector"]
        semantic = stages["semantic"]
        self.assertTrue(lexical_hash.executed)
        self.assertTrue(semantic.executed)
        self.assertEqual(lexical_hash.lanes, ("vector",))
        self.assertEqual(semantic.lanes, ("semantic",))
        self.assertNotEqual(
            lexical_hash.retriever_identity, semantic.retriever_identity
        )
        self.assertEqual(
            semantic.retriever_identity, _SemanticSearch.retriever_identity
        )
        self.assertNotEqual(lexical_hash.receipt_id, semantic.receipt_id)
        self.assertTrue(
            any(item["entity_id"] == "entity:tokenize" for item in response.items)
        )
        self.assertTrue(
            any(item["entity_id"] == "entity:meaning" for item in response.items)
        )

    def test_semantic_receipt_identity_is_content_derived_without_raw_query(self) -> None:
        semantic_search = _SemanticSearch()
        service = PrimitiveSearchService(_Index(), semantic_search=semantic_search)
        first = service.search(
            PrimitiveSearchRequest(
                "first private query",
                SearchStrategy.BALANCED,
                minimum_candidates=1,
                allow_structural=False,
            )
        )
        repeated = service.search(
            PrimitiveSearchRequest(
                "first private query",
                SearchStrategy.BALANCED,
                minimum_candidates=1,
                allow_structural=False,
            )
        )
        different_query = service.search(
            PrimitiveSearchRequest(
                "second private query",
                SearchStrategy.BALANCED,
                minimum_candidates=1,
                allow_structural=False,
            )
        )
        first_receipt = first.stages[3]
        repeated_receipt = repeated.stages[3]
        different_receipt = different_query.stages[3]
        self.assertEqual(first_receipt.result_digest, repeated_receipt.result_digest)
        self.assertEqual(first_receipt.result_digest, different_receipt.result_digest)
        self.assertNotEqual(first_receipt.receipt_id, different_receipt.receipt_id)
        self.assertNotIn("private query", str(first_receipt))

    def test_semantic_can_be_disabled_without_disabling_lexical_hash_vector(self) -> None:
        index = _Index()
        semantic_search = _SemanticSearch()
        response = PrimitiveSearchService(
            index, semantic_search=semantic_search
        ).search(
            PrimitiveSearchRequest(
                "parse by meaning",
                SearchStrategy.BALANCED,
                minimum_candidates=1,
                allow_semantic=False,
                allow_structural=False,
            )
        )
        self.assertIn(("vector",), index.calls)
        self.assertEqual(semantic_search.calls, [])
        semantic = response.stages[3]
        self.assertFalse(semantic.executed)
        self.assertEqual(semantic.stop_reason, "policy")

    def test_semantic_retriever_identity_must_be_versioned(self) -> None:
        semantic_search = _SemanticSearch()
        semantic_search.retriever_identity = "unversioned-semantic-space"
        with self.assertRaisesRegex(ValueError, "explicitly versioned"):
            PrimitiveSearchService(_Index(), semantic_search=semantic_search)

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

    def test_request_digest_binds_strategy_limits_facets_and_lane_policies(self) -> None:
        request = PrimitiveSearchRequest(
            "parse address",
            SearchStrategy.AUTO,
            limit=20,
            minimum_candidates=8,
            entity_kind="function",
            facets={"runtime": "python"},
            allow_semantic=True,
            allow_structural=True,
            maximum_seed_expansions=3,
        )
        base_digest = primitive_search_request_digest(request)
        variants = (
            replace(request, query="parse postal address"),
            replace(request, strategy=SearchStrategy.DEEP),
            replace(request, limit=21),
            replace(request, minimum_candidates=9),
            replace(request, entity_kind="method"),
            replace(request, facets={"runtime": "javascript"}),
            replace(request, allow_semantic=False),
            replace(request, allow_structural=False),
            replace(request, maximum_seed_expansions=4),
        )
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(
                    primitive_search_request_digest(variant), base_digest
                )

    def test_result_digest_binds_order_scores_and_retriever_version(self) -> None:
        rows = [
            {"entity_id": "entity:first", "score": 0.75},
            {"entity_id": "entity:second", "score": 0.5},
        ]
        identity = "taedri.test.retriever@1.0.0"
        base_digest = primitive_search_result_digest(
            rows, retriever_identity=identity
        )
        self.assertNotEqual(
            base_digest,
            primitive_search_result_digest(
                list(reversed(rows)), retriever_identity=identity
            ),
        )
        self.assertNotEqual(
            base_digest,
            primitive_search_result_digest(
                [dict(rows[0], score=0.76), rows[1]],
                retriever_identity=identity,
            ),
        )
        self.assertNotEqual(
            base_digest,
            primitive_search_result_digest(
                rows, retriever_identity="taedri.test.retriever@1.0.1"
            ),
        )


if __name__ == "__main__":
    unittest.main()
