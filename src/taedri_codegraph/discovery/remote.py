"""Authenticated API adapter for the privacy-aware trigger client."""

from __future__ import annotations

from typing import Any, Mapping

from ..api_client import APIClientError, TaedriClient
from ..primitives.search import (
    PrimitiveSearchRequest,
    PrimitiveSearchResponse,
    SearchStageReceipt,
    SearchStrategy,
    primitive_search_request_digest,
)


_EXPECTED_STAGE_CONTRACT = (
    ("exact", ("exact",)),
    ("sparse", ("lexical", "blocking")),
    ("lexical_hash_vector", ("vector",)),
    ("semantic", ("semantic",)),
    ("structural", ("simhash", "minhash", "graph")),
)


def _validate_stage_contract(
    request: PrimitiveSearchRequest,
    stages: tuple[SearchStageReceipt, ...],
    *,
    escalated: bool,
) -> None:
    observed = tuple((stage.stage, stage.lanes) for stage in stages)
    if observed != _EXPECTED_STAGE_CONTRACT:
        raise ValueError(
            "adaptive search stages do not match the exact ordered contract"
        )
    if len({stage.receipt_id for stage in stages}) != len(stages):
        raise ValueError("adaptive search cloned a stage receipt")
    by_name = {stage.stage: stage for stage in stages}
    if not by_name["exact"].executed:
        raise ValueError("adaptive search exact stage must execute")
    if request.strategy is not SearchStrategy.FAST and not by_name["sparse"].executed:
        raise ValueError("adaptive search omitted its required sparse stage")
    if request.strategy in {SearchStrategy.BALANCED, SearchStrategy.DEEP} and not by_name[
        "lexical_hash_vector"
    ].executed:
        raise ValueError("adaptive search omitted its required lexical-vector stage")
    if request.strategy is SearchStrategy.FAST and any(
        by_name[name].executed
        for name in ("lexical_hash_vector", "semantic", "structural")
    ):
        raise ValueError("fast search executed a disallowed escalation stage")
    if request.strategy is SearchStrategy.BALANCED and by_name["structural"].executed:
        raise ValueError("balanced search executed a disallowed structural stage")
    if not request.allow_semantic and by_name["semantic"].executed:
        raise ValueError("search executed semantic retrieval contrary to policy")
    structural_required = (
        request.strategy is SearchStrategy.DEEP
        and request.allow_structural
        and request.maximum_seed_expansions > 0
    )
    if structural_required != by_name["structural"].executed and (
        request.strategy is SearchStrategy.DEEP
        or not request.allow_structural
        or request.maximum_seed_expansions == 0
    ):
        raise ValueError("search structural execution disagrees with request policy")
    expected_escalated = sum(stage.executed for stage in stages) > 2
    if escalated is not expected_escalated:
        raise ValueError("adaptive search escalation flag disagrees with its stages")


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
            allow_semantic=request.allow_semantic,
            allow_structural=request.allow_structural,
            maximum_seed_expansions=request.maximum_seed_expansions,
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
        expected_digest = primitive_search_request_digest(request)
        for raw in raw_stages:
            if not isinstance(raw, Mapping):
                raise APIClientError("adaptive search stage is not an object")
            try:
                stages.append(
                    SearchStageReceipt.from_dict(
                        raw, query_digest=expected_digest
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise APIClientError("adaptive search stage is malformed") from exc
        try:
            raw_query_digest = raw_waterfall["query_digest"]
            raw_strategy = raw_waterfall["strategy"]
            raw_escalated = raw_waterfall["escalated"]
            raw_stop_reason = raw_waterfall["stop_reason"]
            raw_response_digest = raw_waterfall["response_digest"]
            if not isinstance(raw_query_digest, str):
                raise TypeError("query digest is not a string")
            if raw_query_digest != expected_digest:
                raise ValueError("query digest does not match the requested search")
            if not isinstance(raw_strategy, str):
                raise TypeError("strategy is not a string")
            strategy = SearchStrategy(raw_strategy)
            if strategy is not request.strategy:
                raise ValueError("response strategy does not match the requested search")
            if not isinstance(raw_escalated, bool):
                raise TypeError("escalated is not a boolean")
            if not isinstance(raw_stop_reason, str) or not raw_stop_reason:
                raise TypeError("stop reason is not a non-empty string")
            if not isinstance(raw_response_digest, str):
                raise TypeError("aggregate response digest is not a string")
            stage_values = tuple(stages)
            _validate_stage_contract(
                request,
                stage_values,
                escalated=raw_escalated,
            )
            decoded = PrimitiveSearchResponse.create(
                query_digest=raw_query_digest,
                strategy=strategy,
                items=items,
                stages=stage_values,
                escalated=raw_escalated,
                stop_reason=raw_stop_reason,
            )
            if decoded.response_digest != raw_response_digest:
                raise ValueError(
                    "aggregate response digest does not match returned items and stages"
                )
            return decoded
        except (KeyError, TypeError, ValueError) as exc:
            raise APIClientError("adaptive search waterfall is malformed") from exc
