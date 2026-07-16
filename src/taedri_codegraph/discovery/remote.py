"""Authenticated API adapter for the privacy-aware trigger client."""

from __future__ import annotations

from typing import Any, Mapping

from ..api_client import APIClientError, TaedriClient
from ..primitives.search import (
    PrimitiveSearchRequest,
    PrimitiveSearchResponse,
    SearchStageReceipt,
    SearchStrategy,
)


class RemotePrimitiveSearchClient:
    """Make :class:`TaedriClient` satisfy the trigger router's search protocol."""

    def __init__(self, client: TaedriClient) -> None:
        self.client = client

    def search(self, request: PrimitiveSearchRequest) -> PrimitiveSearchResponse:
        response = self.client.search(
            request.query,
            mode="adaptive",
            strategy=request.strategy.value,
            minimum_candidates=request.minimum_candidates,
            limit=request.limit,
            entity_kind=request.entity_kind,
            facet_filters=request.facets,
        )
        raw_waterfall = response.get("search_waterfall")
        if not isinstance(raw_waterfall, Mapping):
            raise APIClientError("adaptive search response has no waterfall receipt")
        raw_items = response.get("items")
        raw_stages = raw_waterfall.get("stages")
        if not isinstance(raw_items, list) or not isinstance(raw_stages, list):
            raise APIClientError("adaptive search response is malformed")
        items: list[Mapping[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, Mapping):
                raise APIClientError("adaptive search item is not an object")
            items.append(dict(item))
        stages: list[SearchStageReceipt] = []
        for raw in raw_stages:
            if not isinstance(raw, Mapping):
                raise APIClientError("adaptive search stage is not an object")
            try:
                stages.append(
                    SearchStageReceipt(
                        str(raw["stage"]),
                        tuple(str(item) for item in raw["lanes"]),
                        bool(raw["executed"]),
                        int(raw["candidate_count"]),
                        int(raw["new_candidate_count"]),
                        int(raw["duration_ms"]),
                        (
                            str(raw["stop_reason"])
                            if raw.get("stop_reason") is not None
                            else None
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise APIClientError("adaptive search stage is malformed") from exc
        try:
            return PrimitiveSearchResponse(
                str(raw_waterfall["query_digest"]),
                SearchStrategy(str(raw_waterfall["strategy"])),
                tuple(items),
                tuple(stages),
                bool(raw_waterfall["escalated"]),
                str(raw_waterfall["stop_reason"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise APIClientError("adaptive search waterfall is malformed") from exc
