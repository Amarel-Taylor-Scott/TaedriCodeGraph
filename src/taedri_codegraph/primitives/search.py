"""Adaptive multi-lane primitive candidate retrieval with explicit escalation receipts."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from ..canonical import canonical_json_bytes, sha256_digest
from ..contracts import RecordMixin


class SearchStrategy(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP = "deep"
    AUTO = "auto"


class SearchIndex(Protocol):
    def hybrid_search(
        self,
        text: str,
        *,
        entity_kind: str | None = None,
        facets: Mapping[str, str] | None = None,
        lanes: tuple[str, ...] = (),
        limit: int = 20,
        explain: bool = True,
    ) -> list[dict[str, Any]]: ...

    def structurally_similar(
        self, identifier: str, *, limit: int = 50
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class PrimitiveSearchRequest(RecordMixin):
    query: str
    strategy: SearchStrategy = SearchStrategy.AUTO
    limit: int = 20
    minimum_candidates: int = 8
    entity_kind: str | None = None
    facets: Mapping[str, str] | None = None
    allow_semantic: bool = True
    allow_structural: bool = True
    maximum_seed_expansions: int = 3

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("primitive search query is required")
        if not 1 <= self.limit <= 1000:
            raise ValueError("primitive search limit must be 1..1000")
        if not 1 <= self.minimum_candidates <= 1000:
            raise ValueError("minimum candidates must be 1..1000")
        if not 0 <= self.maximum_seed_expansions <= 20:
            raise ValueError("structural seed limit must be 0..20")


@dataclass(frozen=True, slots=True)
class SearchStageReceipt(RecordMixin):
    stage: str
    lanes: tuple[str, ...]
    executed: bool
    candidate_count: int
    new_candidate_count: int
    duration_ms: int
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class PrimitiveSearchResponse(RecordMixin):
    query_digest: str
    strategy: SearchStrategy
    items: tuple[Mapping[str, Any], ...]
    stages: tuple[SearchStageReceipt, ...]
    escalated: bool
    stop_reason: str


class PrimitiveSearchService:
    """Runs cheap/high-precision retrieval before optional broader mechanisms."""

    def __init__(self, index: SearchIndex) -> None:
        self.index = index

    def search(self, request: PrimitiveSearchRequest) -> PrimitiveSearchResponse:
        query_digest = sha256_digest(canonical_json_bytes({"query": request.query}))
        aggregate: dict[str, dict[str, Any]] = {}
        receipts: list[SearchStageReceipt] = []
        stage_number = 0

        def run_lanes(stage: str, lanes: tuple[str, ...], should_run: bool) -> None:
            nonlocal stage_number
            stage_number += 1
            if not should_run:
                receipts.append(SearchStageReceipt(stage, lanes, False, 0, 0, 0, "policy"))
                return
            started = time.monotonic_ns()
            rows = self.index.hybrid_search(
                request.query,
                entity_kind=request.entity_kind,
                facets=request.facets,
                lanes=lanes,
                limit=max(request.limit * 5, request.minimum_candidates),
                explain=True,
            )
            before = len(aggregate)
            for rank, row in enumerate(rows, start=1):
                identifier = str(row.get("entity_id") or row.get("identity", {}).get("id"))
                if not identifier or identifier == "None":
                    continue
                item = aggregate.setdefault(
                    identifier,
                    {
                        "record": dict(row),
                        "waterfall_score": 0.0,
                        "waterfall_stages": [],
                    },
                )
                item["waterfall_score"] += (5 - min(stage_number, 4)) / (60 + rank)
                item["waterfall_stages"].append(stage)
                if len(str(row.get("description", ""))) > len(
                    str(item["record"].get("description", ""))
                ):
                    item["record"] = dict(row)
            receipts.append(
                SearchStageReceipt(
                    stage,
                    lanes,
                    True,
                    len(rows),
                    len(aggregate) - before,
                    max(0, (time.monotonic_ns() - started) // 1_000_000),
                    None,
                )
            )

        run_lanes("exact", ("exact",), True)
        exact_sufficient = len(aggregate) >= request.minimum_candidates
        run_sparse = request.strategy is not SearchStrategy.FAST or not exact_sufficient
        run_lanes("sparse", ("lexical", "blocking"), run_sparse)

        current_sufficient = len(aggregate) >= request.minimum_candidates
        ambiguous = self._ambiguous(aggregate)
        run_semantic = request.allow_semantic and (
            request.strategy in {SearchStrategy.BALANCED, SearchStrategy.DEEP}
            or (
                request.strategy is SearchStrategy.AUTO
                and (not current_sufficient or ambiguous)
            )
        )
        run_lanes("semantic", ("vector",), run_semantic)

        current_sufficient = len(aggregate) >= request.minimum_candidates
        run_structural = request.allow_structural and (
            request.strategy is SearchStrategy.DEEP
            or (
                request.strategy is SearchStrategy.AUTO
                and (not current_sufficient or self._ambiguous(aggregate))
            )
        )
        if run_structural and request.maximum_seed_expansions:
            started = time.monotonic_ns()
            before = len(aggregate)
            seeds = self._ordered(aggregate)[: request.maximum_seed_expansions]
            row_count = 0
            for seed in seeds:
                identifier = str(seed.get("entity_id") or seed.get("qualified_name") or "")
                if not identifier:
                    continue
                rows = self.index.structurally_similar(
                    identifier, limit=max(request.limit * 2, request.minimum_candidates)
                )
                row_count += len(rows)
                for rank, row in enumerate(rows, start=1):
                    entity_id = str(
                        row.get("entity_id") or row.get("identity", {}).get("id")
                    )
                    if not entity_id or entity_id == "None":
                        continue
                    item = aggregate.setdefault(
                        entity_id,
                        {
                            "record": dict(row),
                            "waterfall_score": 0.0,
                            "waterfall_stages": [],
                        },
                    )
                    item["waterfall_score"] += 1 / (60 + rank)
                    item["waterfall_stages"].append("structural")
            receipts.append(
                SearchStageReceipt(
                    "structural",
                    ("simhash", "minhash", "graph"),
                    True,
                    row_count,
                    len(aggregate) - before,
                    max(0, (time.monotonic_ns() - started) // 1_000_000),
                    None,
                )
            )
        else:
            receipts.append(
                SearchStageReceipt(
                    "structural",
                    ("simhash", "minhash", "graph"),
                    False,
                    0,
                    0,
                    0,
                    "policy_or_sufficient_candidates",
                )
            )

        ordered = self._ordered(aggregate)[: request.limit]
        stop_reason = (
            "candidate_budget_satisfied"
            if len(aggregate) >= request.minimum_candidates
            else "waterfall_exhausted"
        )
        return PrimitiveSearchResponse(
            query_digest,
            request.strategy,
            tuple(ordered),
            tuple(receipts),
            sum(1 for item in receipts if item.executed) > 2,
            stop_reason,
        )

    @staticmethod
    def _ambiguous(aggregate: Mapping[str, Mapping[str, Any]]) -> bool:
        scores = sorted(
            (float(item["waterfall_score"]) for item in aggregate.values()), reverse=True
        )
        if len(scores) < 2:
            return True
        return scores[0] - scores[1] < 0.002

    @staticmethod
    def _ordered(aggregate: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for item in aggregate.values():
            row = dict(item["record"])
            row["waterfall_score"] = round(float(item["waterfall_score"]), 8)
            row["waterfall_stages"] = tuple(dict.fromkeys(item["waterfall_stages"]))
            rows.append(row)
        return sorted(
            rows,
            key=lambda row: (
                -float(row["waterfall_score"]),
                str(row.get("qualified_name") or row.get("entity_id") or ""),
            ),
        )
