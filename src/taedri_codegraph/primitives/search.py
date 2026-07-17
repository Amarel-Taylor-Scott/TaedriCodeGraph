"""Adaptive multi-lane primitive candidate retrieval with explicit escalation receipts."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol

from ..canonical import canonical_json_bytes, sha256_digest
from ..contracts import RecordMixin


_RETRIEVER_IDENTITY = re.compile(
    r"^[a-z][a-z0-9_.-]+@[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$"
)
_SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_STAGE_RECEIPT_ID = re.compile(
    r"^uceg:v1:primitive_search_stage_receipt:[0-9a-f]{64}$"
)
_SEARCH_REQUEST_FORMAT = "taedri.primitive-search-request@1.0.0"
_SEARCH_RESULTS_FORMAT = "taedri.primitive-search-results@1.0.0"
_SEARCH_RESPONSE_FORMAT = "taedri.primitive-search-response@1.0.0"
_EXACT_RETRIEVER = "taedri.search.exact@1.0.0"
_SPARSE_RETRIEVER = "taedri.search.lexical-blocking@1.0.0"
_LEXICAL_HASH_RETRIEVER = "uceg.embedding.lexical_hash64@1.0.0"
_SEMANTIC_CALLBACK_INTERFACE = "taedri.search.semantic-callback@1.0.0"
_STRUCTURAL_RETRIEVER = "taedri.search.structural@1.0.0"


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
        if not isinstance(self.query, str):
            raise TypeError("primitive search query must be a string")
        if not self.query.strip():
            raise ValueError("primitive search query is required")
        if not isinstance(self.strategy, SearchStrategy):
            raise TypeError("primitive search strategy must be a SearchStrategy")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("primitive search limit must be an integer")
        if not 1 <= self.limit <= 1000:
            raise ValueError("primitive search limit must be 1..1000")
        if isinstance(self.minimum_candidates, bool) or not isinstance(
            self.minimum_candidates, int
        ):
            raise TypeError("minimum candidates must be an integer")
        if not 1 <= self.minimum_candidates <= 1000:
            raise ValueError("minimum candidates must be 1..1000")
        if self.entity_kind is not None and (
            not isinstance(self.entity_kind, str) or not self.entity_kind
        ):
            raise TypeError("entity kind must be a non-empty string when supplied")
        if self.facets is not None:
            if not isinstance(self.facets, Mapping):
                raise TypeError("primitive search facets must be a mapping")
            normalized_facets: dict[str, str] = {}
            for key, value in self.facets.items():
                if not isinstance(key, str) or not key:
                    raise TypeError(
                        "primitive search facet keys must be non-empty strings"
                    )
                if not isinstance(value, str):
                    raise TypeError("primitive search facet values must be strings")
                normalized_facets[key] = value
            object.__setattr__(
                self,
                "facets",
                MappingProxyType(dict(sorted(normalized_facets.items()))),
            )
        if not isinstance(self.allow_semantic, bool) or not isinstance(
            self.allow_structural, bool
        ):
            raise TypeError("primitive search lane policies must be booleans")
        if isinstance(self.maximum_seed_expansions, bool) or not isinstance(
            self.maximum_seed_expansions, int
        ):
            raise TypeError("structural seed limit must be an integer")
        if not 0 <= self.maximum_seed_expansions <= 20:
            raise ValueError("structural seed limit must be 0..20")


def primitive_search_request_digest(request: PrimitiveSearchRequest) -> str:
    """Bind every retrieval choice that can change a search execution."""

    return sha256_digest(
        canonical_json_bytes(
            {
                "format": _SEARCH_REQUEST_FORMAT,
                "query": request.query,
                "strategy": request.strategy.value,
                "limit": request.limit,
                "minimum_candidates": request.minimum_candidates,
                "entity_kind": request.entity_kind,
                "facets": dict(request.facets or {}),
                "allow_semantic": request.allow_semantic,
                "allow_structural": request.allow_structural,
                "maximum_seed_expansions": request.maximum_seed_expansions,
            }
        )
    )


class SemanticSearchCallback(Protocol):
    """Optional semantic retriever with an explicit model/index-space identity."""

    retriever_identity: str

    def __call__(
        self, request: PrimitiveSearchRequest, *, limit: int
    ) -> Iterable[Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class SearchStageReceipt(RecordMixin):
    stage: str
    lanes: tuple[str, ...]
    executed: bool
    candidate_count: int
    new_candidate_count: int
    duration_ms: int
    stop_reason: str | None
    retriever_identity: str
    result_digest: str | None
    receipt_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.stage, str) or not self.stage:
            raise ValueError("search-stage name is required")
        if not isinstance(self.lanes, tuple) or not self.lanes or any(
            not isinstance(item, str) or not item for item in self.lanes
        ):
            raise TypeError("search-stage lanes must be non-empty strings")
        if not isinstance(self.executed, bool):
            raise TypeError("search-stage executed must be a boolean")
        for field_name, value in (
            ("candidate_count", self.candidate_count),
            ("new_candidate_count", self.new_candidate_count),
            ("duration_ms", self.duration_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"search-stage {field_name} must be an integer")
            if value < 0:
                raise ValueError(f"search-stage {field_name} cannot be negative")
        if self.new_candidate_count > self.candidate_count:
            raise ValueError("new candidate count cannot exceed candidate count")
        if self.executed:
            if self.stop_reason is not None:
                raise ValueError("executed search stages cannot have a stop reason")
            if self.result_digest is None:
                raise ValueError("executed search stages require a result digest")
        else:
            if not isinstance(self.stop_reason, str) or not self.stop_reason:
                raise ValueError("skipped search stages require a stop reason")
            if self.candidate_count or self.new_candidate_count:
                raise ValueError("skipped search stages cannot report candidates")
            if self.result_digest is not None:
                raise ValueError("skipped search stages cannot have a result digest")
        if not isinstance(self.retriever_identity, str):
            raise TypeError("search-stage retriever identity is required")
        _validate_retriever_identity(self.retriever_identity)
        if self.result_digest is not None and not _SHA256_DIGEST.fullmatch(
            self.result_digest
        ):
            raise ValueError("search-stage result digest must be SHA-256")
        if not isinstance(self.receipt_id, str) or not _STAGE_RECEIPT_ID.fullmatch(
            self.receipt_id
        ):
            raise ValueError("search-stage receipt ID is malformed")

    @classmethod
    def create(
        cls,
        *,
        query_digest: str,
        stage: str,
        lanes: tuple[str, ...],
        executed: bool,
        candidate_count: int,
        new_candidate_count: int,
        duration_ms: int,
        stop_reason: str | None,
        retriever_identity: str,
        result_digest: str | None = None,
    ) -> "SearchStageReceipt":
        if not _SHA256_DIGEST.fullmatch(query_digest):
            raise ValueError("search request digest must be SHA-256")
        _validate_retriever_identity(retriever_identity)
        if result_digest is not None and not _SHA256_DIGEST.fullmatch(result_digest):
            raise ValueError("search-stage result digest must be SHA-256")
        receipt_key = {
            "query_digest": query_digest,
            "stage": stage,
            "lanes": lanes,
            "executed": executed,
            "candidate_count": candidate_count,
            "new_candidate_count": new_candidate_count,
            "duration_ms": duration_ms,
            "stop_reason": stop_reason,
            "retriever_identity": retriever_identity,
            "result_digest": result_digest,
        }
        receipt_id = (
            "uceg:v1:primitive_search_stage_receipt:"
            + sha256_digest(canonical_json_bytes(receipt_key)).removeprefix("sha256:")
        )
        return cls(
            stage,
            lanes,
            executed,
            candidate_count,
            new_candidate_count,
            duration_ms,
            stop_reason,
            retriever_identity,
            result_digest,
            receipt_id,
        )

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any], *, query_digest: str
    ) -> "SearchStageReceipt":
        """Strictly decode and content-check one wire receipt."""

        required = {
            "stage",
            "lanes",
            "executed",
            "candidate_count",
            "new_candidate_count",
            "duration_ms",
            "stop_reason",
            "retriever_identity",
            "result_digest",
            "receipt_id",
        }
        if set(value) != required:
            raise ValueError("search-stage receipt fields are incomplete or unknown")
        stage = value["stage"]
        lanes = value["lanes"]
        executed = value["executed"]
        candidate_count = value["candidate_count"]
        new_candidate_count = value["new_candidate_count"]
        duration_ms = value["duration_ms"]
        stop_reason = value["stop_reason"]
        retriever_identity = value["retriever_identity"]
        result_digest = value["result_digest"]
        receipt_id = value["receipt_id"]
        if not isinstance(stage, str):
            raise TypeError("search-stage name must be a string")
        if not isinstance(lanes, list) or any(
            not isinstance(item, str) for item in lanes
        ):
            raise TypeError("search-stage lanes must be a string array")
        if not isinstance(executed, bool):
            raise TypeError("search-stage executed must be a boolean")
        for field_name, field_value in (
            ("candidate_count", candidate_count),
            ("new_candidate_count", new_candidate_count),
            ("duration_ms", duration_ms),
        ):
            if isinstance(field_value, bool) or not isinstance(field_value, int):
                raise TypeError(f"search-stage {field_name} must be an integer")
        if stop_reason is not None and not isinstance(stop_reason, str):
            raise TypeError("search-stage stop reason must be a string or null")
        if not isinstance(retriever_identity, str):
            raise TypeError("search-stage retriever identity must be a string")
        if result_digest is not None and not isinstance(result_digest, str):
            raise TypeError("search-stage result digest must be a string or null")
        if not isinstance(receipt_id, str):
            raise TypeError("search-stage receipt ID must be a string")
        decoded = cls.create(
            query_digest=query_digest,
            stage=stage,
            lanes=tuple(lanes),
            executed=executed,
            candidate_count=candidate_count,
            new_candidate_count=new_candidate_count,
            duration_ms=duration_ms,
            stop_reason=stop_reason,
            retriever_identity=retriever_identity,
            result_digest=result_digest,
        )
        if decoded.receipt_id != receipt_id:
            raise ValueError("search-stage receipt ID does not match its content")
        return decoded


@dataclass(frozen=True, slots=True)
class PrimitiveSearchResponse(RecordMixin):
    query_digest: str
    strategy: SearchStrategy
    items: tuple[Mapping[str, Any], ...]
    stages: tuple[SearchStageReceipt, ...]
    escalated: bool
    stop_reason: str
    response_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.query_digest, str) or not _SHA256_DIGEST.fullmatch(
            self.query_digest
        ):
            raise ValueError("primitive search response digest must be SHA-256")
        if not isinstance(self.strategy, SearchStrategy):
            raise TypeError("primitive search response strategy is invalid")
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, Mapping) for item in self.items
        ):
            raise TypeError("primitive search response items must be mappings")
        if not isinstance(self.stages, tuple) or any(
            not isinstance(item, SearchStageReceipt) for item in self.stages
        ):
            raise TypeError("primitive search response stages are invalid")
        if not self.stages:
            raise ValueError("primitive search response stages cannot be empty")
        stage_names = tuple(item.stage for item in self.stages)
        if len(stage_names) != len(set(stage_names)):
            raise ValueError("primitive search response stages must be unique")
        receipt_ids = tuple(item.receipt_id for item in self.stages)
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError("primitive search response stage receipts must be unique")
        if not isinstance(self.escalated, bool):
            raise TypeError("primitive search response escalated must be a boolean")
        if not isinstance(self.stop_reason, str) or not self.stop_reason:
            raise ValueError("primitive search response stop reason is required")
        if not isinstance(self.response_digest, str) or not _SHA256_DIGEST.fullmatch(
            self.response_digest
        ):
            raise ValueError("primitive search aggregate response digest is invalid")
        expected = primitive_search_response_digest(
            query_digest=self.query_digest,
            strategy=self.strategy,
            items=self.items,
            stages=self.stages,
            escalated=self.escalated,
            stop_reason=self.stop_reason,
        )
        if expected != self.response_digest:
            raise ValueError(
                "primitive search aggregate response digest does not match its content"
            )

    @classmethod
    def create(
        cls,
        *,
        query_digest: str,
        strategy: SearchStrategy,
        items: Iterable[Mapping[str, Any]],
        stages: Iterable[SearchStageReceipt],
        escalated: bool,
        stop_reason: str,
    ) -> "PrimitiveSearchResponse":
        item_values = tuple(dict(item) for item in items)
        stage_values = tuple(stages)
        response_digest = primitive_search_response_digest(
            query_digest=query_digest,
            strategy=strategy,
            items=item_values,
            stages=stage_values,
            escalated=escalated,
            stop_reason=stop_reason,
        )
        return cls(
            query_digest,
            strategy,
            item_values,
            stage_values,
            escalated,
            stop_reason,
            response_digest,
        )


class PrimitiveSearchService:
    """Runs cheap/high-precision retrieval before optional broader mechanisms."""

    def __init__(
        self,
        index: SearchIndex,
        *,
        semantic_search: SemanticSearchCallback | None = None,
    ) -> None:
        self.index = index
        self.semantic_search = semantic_search
        if semantic_search is not None:
            _validate_retriever_identity(semantic_search.retriever_identity)

    def search(
        self,
        request: PrimitiveSearchRequest,
        *,
        result_limit: int | None = None,
    ) -> PrimitiveSearchResponse:
        query_digest = primitive_search_request_digest(request)
        aggregate: dict[str, dict[str, Any]] = {}
        receipts: list[SearchStageReceipt] = []
        stage_number = 0

        response_limit = request.limit if result_limit is None else result_limit
        if isinstance(response_limit, bool) or not isinstance(response_limit, int):
            raise TypeError("primitive search result limit must be an integer")
        if not request.limit <= response_limit <= 1000:
            raise ValueError(
                "primitive search result limit must be request.limit..1000"
            )
        retrieval_limit = max(response_limit * 5, request.minimum_candidates)

        def merge_rows(stage: str, rows: list[dict[str, Any]]) -> int:
            before = len(aggregate)
            for rank, row in enumerate(rows, start=1):
                identifier = _candidate_identifier(row)
                if identifier is None:
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
            return len(aggregate) - before

        def run_index_lanes(
            stage: str,
            lanes: tuple[str, ...],
            should_run: bool,
            *,
            retriever_identity: str,
            skip_reason: str = "policy_or_sufficient_candidates",
        ) -> None:
            nonlocal stage_number
            stage_number += 1
            if not should_run:
                receipts.append(
                    SearchStageReceipt.create(
                        query_digest=query_digest,
                        stage=stage,
                        lanes=lanes,
                        executed=False,
                        candidate_count=0,
                        new_candidate_count=0,
                        duration_ms=0,
                        stop_reason=skip_reason,
                        retriever_identity=retriever_identity,
                    )
                )
                return
            started = time.monotonic_ns()
            rows = [
                dict(row)
                for row in self.index.hybrid_search(
                    request.query,
                    entity_kind=request.entity_kind,
                    facets=request.facets,
                    lanes=lanes,
                    limit=retrieval_limit,
                    explain=True,
                )
            ]
            new_candidate_count = merge_rows(stage, rows)
            receipts.append(
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage=stage,
                    lanes=lanes,
                    executed=True,
                    candidate_count=len(rows),
                    new_candidate_count=new_candidate_count,
                    duration_ms=max(
                        0, (time.monotonic_ns() - started) // 1_000_000
                    ),
                    stop_reason=None,
                    retriever_identity=retriever_identity,
                    result_digest=primitive_search_result_digest(
                        rows, retriever_identity=retriever_identity
                    ),
                )
            )

        run_index_lanes(
            "exact", ("exact",), True, retriever_identity=_EXACT_RETRIEVER
        )
        exact_sufficient = len(aggregate) >= request.minimum_candidates
        run_sparse = request.strategy is not SearchStrategy.FAST or not exact_sufficient
        run_index_lanes(
            "sparse",
            ("lexical", "blocking"),
            run_sparse,
            retriever_identity=_SPARSE_RETRIEVER,
        )

        current_sufficient = len(aggregate) >= request.minimum_candidates
        ambiguous = self._ambiguous(aggregate)
        run_lexical_hash_vector = (
            request.strategy in {SearchStrategy.BALANCED, SearchStrategy.DEEP}
            or (
                request.strategy is SearchStrategy.AUTO
                and (not current_sufficient or ambiguous)
            )
        )
        run_index_lanes(
            "lexical_hash_vector",
            ("vector",),
            run_lexical_hash_vector,
            retriever_identity=_LEXICAL_HASH_RETRIEVER,
        )

        current_sufficient = len(aggregate) >= request.minimum_candidates
        semantic_warranted = (
            request.strategy in {SearchStrategy.BALANCED, SearchStrategy.DEEP}
            or (
                request.strategy is SearchStrategy.AUTO
                and (not current_sufficient or self._ambiguous(aggregate))
            )
        )
        semantic_identity = (
            self.semantic_search.retriever_identity
            if self.semantic_search is not None
            else _SEMANTIC_CALLBACK_INTERFACE
        )
        stage_number += 1
        if not request.allow_semantic:
            receipts.append(
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage="semantic",
                    lanes=("semantic",),
                    executed=False,
                    candidate_count=0,
                    new_candidate_count=0,
                    duration_ms=0,
                    stop_reason="policy",
                    retriever_identity=semantic_identity,
                )
            )
        elif not semantic_warranted:
            receipts.append(
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage="semantic",
                    lanes=("semantic",),
                    executed=False,
                    candidate_count=0,
                    new_candidate_count=0,
                    duration_ms=0,
                    stop_reason="sufficient_candidates",
                    retriever_identity=semantic_identity,
                )
            )
        elif self.semantic_search is None:
            receipts.append(
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage="semantic",
                    lanes=("semantic",),
                    executed=False,
                    candidate_count=0,
                    new_candidate_count=0,
                    duration_ms=0,
                    stop_reason="semantic_retriever_unavailable",
                    retriever_identity=semantic_identity,
                )
            )
        else:
            started = time.monotonic_ns()
            rows = [
                dict(row)
                for row in self.semantic_search(request, limit=retrieval_limit)
            ]
            new_candidate_count = merge_rows("semantic", rows)
            receipts.append(
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage="semantic",
                    lanes=("semantic",),
                    executed=True,
                    candidate_count=len(rows),
                    new_candidate_count=new_candidate_count,
                    duration_ms=max(
                        0, (time.monotonic_ns() - started) // 1_000_000
                    ),
                    stop_reason=None,
                    retriever_identity=semantic_identity,
                    result_digest=primitive_search_result_digest(
                        rows, retriever_identity=semantic_identity
                    ),
                )
            )

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
            structural_rows: list[dict[str, Any]] = []
            for seed in seeds:
                identifier = str(seed.get("entity_id") or seed.get("qualified_name") or "")
                if not identifier:
                    continue
                rows = self.index.structurally_similar(
                    identifier,
                    limit=max(response_limit * 2, request.minimum_candidates),
                )
                row_count += len(rows)
                for rank, row in enumerate(rows, start=1):
                    structural_rows.append(dict(row))
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
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage="structural",
                    lanes=("simhash", "minhash", "graph"),
                    executed=True,
                    candidate_count=row_count,
                    new_candidate_count=len(aggregate) - before,
                    duration_ms=max(
                        0, (time.monotonic_ns() - started) // 1_000_000
                    ),
                    stop_reason=None,
                    retriever_identity=_STRUCTURAL_RETRIEVER,
                    result_digest=primitive_search_result_digest(
                        structural_rows, retriever_identity=_STRUCTURAL_RETRIEVER
                    ),
                )
            )
        else:
            receipts.append(
                SearchStageReceipt.create(
                    query_digest=query_digest,
                    stage="structural",
                    lanes=("simhash", "minhash", "graph"),
                    executed=False,
                    candidate_count=0,
                    new_candidate_count=0,
                    duration_ms=0,
                    stop_reason="policy_or_sufficient_candidates",
                    retriever_identity=_STRUCTURAL_RETRIEVER,
                )
            )

        ordered = self._ordered(aggregate)[:response_limit]
        stop_reason = (
            "candidate_budget_satisfied"
            if len(aggregate) >= request.minimum_candidates
            else "waterfall_exhausted"
        )
        return PrimitiveSearchResponse.create(
            query_digest=query_digest,
            strategy=request.strategy,
            items=ordered,
            stages=receipts,
            escalated=sum(1 for item in receipts if item.executed) > 2,
            stop_reason=stop_reason,
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


def _candidate_identifier(row: Mapping[str, Any]) -> str | None:
    identity = row.get("identity")
    nested_id = identity.get("id") if isinstance(identity, Mapping) else None
    identifier = row.get("entity_id") or nested_id
    if identifier is None:
        return None
    normalized = str(identifier)
    return normalized if normalized and normalized != "None" else None


def primitive_search_result_digest(
    rows: Iterable[Mapping[str, Any]], *, retriever_identity: str
) -> str:
    """Bind retriever version plus every returned candidate's rank and scores."""

    _validate_retriever_identity(retriever_identity)
    candidates: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        scores = {
            key: _stable_score_value(value)
            for key, value in sorted(row.items())
            if isinstance(key, str)
            and (
                key == "score"
                or key.endswith("_score")
                or key in {"distance", "similarity", "raw_lane_scores"}
            )
        }
        candidates.append(
            {
                "rank": rank,
                "candidate_id": _candidate_identifier(row),
                "scores": scores,
            }
        )
    return sha256_digest(
        canonical_json_bytes(
            {
                "format": _SEARCH_RESULTS_FORMAT,
                "retriever_identity": retriever_identity,
                "candidates": candidates,
            }
        )
    )


def primitive_search_response_digest(
    *,
    query_digest: str,
    strategy: SearchStrategy,
    items: Iterable[Mapping[str, Any]],
    stages: Iterable[SearchStageReceipt],
    escalated: bool,
    stop_reason: str,
) -> str:
    """Bind the complete ordered response, not only stage-local candidate IDs."""

    if not isinstance(query_digest, str) or not _SHA256_DIGEST.fullmatch(
        query_digest
    ):
        raise ValueError("primitive search response query digest must be SHA-256")
    if not isinstance(strategy, SearchStrategy):
        raise TypeError("primitive search response strategy is invalid")
    if not isinstance(escalated, bool):
        raise TypeError("primitive search response escalated must be a boolean")
    if not isinstance(stop_reason, str) or not stop_reason:
        raise ValueError("primitive search response stop reason is required")
    item_values = []
    for item in items:
        if not isinstance(item, Mapping):
            raise TypeError("primitive search response item is not a mapping")
        item_values.append(dict(item))
    stage_values = []
    for stage in stages:
        if not isinstance(stage, SearchStageReceipt):
            raise TypeError("primitive search response stage is invalid")
        stage_values.append(stage.to_dict())
    return sha256_digest(
        canonical_json_bytes(
            {
                "format": _SEARCH_RESPONSE_FORMAT,
                "query_digest": query_digest,
                "strategy": strategy.value,
                "items": item_values,
                "stages": stage_values,
                "escalated": escalated,
                "stop_reason": stop_reason,
            }
        )
    )


def _stable_score_value(value: Any) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("search result scores must be finite")
        return {"binary64": value.hex()}
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            if not isinstance(key, str):
                raise TypeError("search result score mappings require string keys")
            normalized[key] = _stable_score_value(item)
        return normalized
    if isinstance(value, tuple | list):
        return [_stable_score_value(item) for item in value]
    raise TypeError("search result score values must be JSON-compatible scalars")


def _validate_retriever_identity(value: str) -> None:
    if not _RETRIEVER_IDENTITY.fullmatch(value):
        raise ValueError(
            "retriever identity must be a normalized, explicitly versioned reference"
        )
