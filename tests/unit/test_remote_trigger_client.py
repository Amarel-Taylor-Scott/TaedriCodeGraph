from __future__ import annotations

import json
import unittest
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

from taedri_codegraph.api_client import APIClientError, TaedriClient
from taedri_codegraph.discovery import (
    RemotePrimitiveSearchClient,
    SearchTriggerSignal,
    TriggerKind,
    TriggeredPrimitiveClient,
    default_trigger_router,
    intent_digest,
)
from taedri_codegraph.primitives.search import (
    PrimitiveSearchRequest,
    SearchStageReceipt,
    SearchStrategy,
    primitive_search_request_digest,
    primitive_search_response_digest,
    primitive_search_result_digest,
)


class _Transport:
    def __init__(self, *, tamper: str | None = None) -> None:
        self.tamper = tamper

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
        parameters = parse_qs(urlsplit(url).query)
        filters = {}
        for value in parameters.get("filter", []):
            key, _, item = value.partition("=")
            filters[key] = item
        request = PrimitiveSearchRequest(
            parameters["q"][0],
            SearchStrategy(parameters["strategy"][0]),
            limit=int(parameters["limit"][0]),
            minimum_candidates=int(parameters["minimum_candidates"][0]),
            entity_kind=(parameters.get("kind") or [None])[0],
            facets=filters,
            allow_semantic=parameters["semantic"][0] == "true",
            allow_structural=parameters["structural"][0] == "true",
            maximum_seed_expansions=int(
                parameters["maximum_seed_expansions"][0]
            ),
        )
        items = [{"entity_id": "uceg:v1:entity:fixture", "score": 1.0}]
        query_digest = primitive_search_request_digest(request)
        insufficient_or_ambiguous = True
        stage_specs = (
            ("exact", ("exact",), "taedri.search.exact@1.0.0", True),
            (
                "sparse",
                ("lexical", "blocking"),
                "taedri.search.lexical-blocking@1.0.0",
                request.strategy is not SearchStrategy.FAST
                or insufficient_or_ambiguous,
            ),
            (
                "lexical_hash_vector",
                ("vector",),
                "uceg.embedding.lexical_hash64@1.0.0",
                request.strategy in {SearchStrategy.BALANCED, SearchStrategy.DEEP}
                or (
                    request.strategy is SearchStrategy.AUTO
                    and insufficient_or_ambiguous
                ),
            ),
            (
                "semantic",
                ("semantic",),
                "taedri.search.semantic-callback@1.0.0",
                request.allow_semantic
                and (
                    request.strategy in {
                        SearchStrategy.BALANCED,
                        SearchStrategy.DEEP,
                    }
                    or (
                        request.strategy is SearchStrategy.AUTO
                        and insufficient_or_ambiguous
                    )
                ),
            ),
            (
                "structural",
                ("simhash", "minhash", "graph"),
                "taedri.search.structural@1.0.0",
                request.allow_structural
                and request.maximum_seed_expansions > 0
                and (
                    request.strategy is SearchStrategy.DEEP
                    or (
                        request.strategy is SearchStrategy.AUTO
                        and insufficient_or_ambiguous
                    )
                ),
            ),
        )
        receipts = []
        for index, (name, lanes, retriever, executed) in enumerate(stage_specs):
            receipts.append(
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage=name,
                    lanes=lanes,
                    executed=executed,
                    candidate_count=1 if executed else 0,
                    new_candidate_count=1 if executed and index == 0 else 0,
                    duration_ms=0,
                    stop_reason=None if executed else "policy_or_sufficient_candidates",
                    retriever_identity=retriever,
                    result_digest=(
                        primitive_search_result_digest(
                            items, retriever_identity=retriever
                        )
                        if executed
                        else None
                    ),
                )
            )
        escalated = sum(stage.executed for stage in receipts) > 2
        response_digest = primitive_search_response_digest(
            query_digest=query_digest,
            strategy=request.strategy,
            items=items,
            stages=receipts,
            escalated=escalated,
            stop_reason="candidate_budget_satisfied",
        )
        stages = [stage.to_dict() for stage in receipts]
        payload = {
            "items": items,
            "search_waterfall": {
                "query_digest": query_digest,
                "strategy": request.strategy.value,
                "stages": stages,
                "escalated": escalated,
                "stop_reason": "candidate_budget_satisfied",
                "response_digest": response_digest,
            },
        }
        if self.tamper == "request_digest":
            payload["search_waterfall"]["query_digest"] = "sha256:" + "0" * 64
        elif self.tamper == "receipt_id":
            receipt_id = str(stages[0]["receipt_id"])
            replacement = "1" if receipt_id.endswith("0") else "0"
            stages[0]["receipt_id"] = receipt_id[:-1] + replacement
        elif self.tamper == "string_boolean":
            stages[0]["executed"] = "false"
        elif self.tamper == "duration":
            stages[0]["duration_ms"] = 1
        elif self.tamper == "item_substitution":
            items[0]["entity_id"] = "uceg:v1:entity:substituted"
        elif self.tamper == "zero_stages":
            payload["search_waterfall"]["stages"] = []
        elif self.tamper == "cloned_stage":
            payload["search_waterfall"]["stages"] = [
                stages[0],
                stages[0],
                *stages[2:],
            ]
        elif self.tamper == "escalation":
            payload["search_waterfall"]["escalated"] = not escalated
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
        self.assertIn("semantic=true", transport.url)
        self.assertIn("structural=true", transport.url)
        self.assertIn("maximum_seed_expansions=3", transport.url)
        self.assertNotIn("secret", transport.url)

    def test_remote_search_forwards_nondefault_lane_policies(self) -> None:
        transport = _Transport()
        remote = RemotePrimitiveSearchClient(
            TaedriClient("https://api.example.test", "secret", transport=transport)
        )
        response = remote.search(
            PrimitiveSearchRequest(
                "parse address",
                SearchStrategy.DEEP,
                allow_semantic=False,
                allow_structural=False,
                maximum_seed_expansions=0,
            )
        )
        self.assertEqual(response.strategy, SearchStrategy.DEEP)
        self.assertIn("semantic=false", transport.url)
        self.assertIn("structural=false", transport.url)
        self.assertIn("maximum_seed_expansions=0", transport.url)

    def test_remote_search_rejects_tampered_or_coercive_receipts(self) -> None:
        for tamper in (
            "request_digest",
            "receipt_id",
            "string_boolean",
            "duration",
            "item_substitution",
            "zero_stages",
            "cloned_stage",
            "escalation",
        ):
            with self.subTest(tamper=tamper):
                remote = RemotePrimitiveSearchClient(
                    TaedriClient(
                        "https://api.example.test",
                        "secret",
                        transport=_Transport(tamper=tamper),
                    )
                )
                with self.assertRaises(APIClientError):
                    remote.search(
                        PrimitiveSearchRequest(
                            "parse address", SearchStrategy.DEEP
                        )
                    )


if __name__ == "__main__":
    unittest.main()
