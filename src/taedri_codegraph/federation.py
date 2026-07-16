"""Bounded multi-epoch retrieval for a tenant with several graph mounts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .query import GraphIndex


@dataclass(frozen=True, slots=True)
class MountedGraphIndex:
    name: str
    epoch_id: str
    index: GraphIndex


class FederatedGraphIndex:
    """Fuse a bounded set of immutable serving indexes with explicit receipts.

    This is the correct small-tenant implementation. A materialized shared projection
    replaces it after the measured mount-count/latency gate, without changing entity IDs
    or source epochs.
    """

    def __init__(self, mounts: Iterable[MountedGraphIndex]):
        values = tuple(sorted(mounts, key=lambda item: item.name))
        if not values:
            raise ValueError("federated retrieval requires at least one published graph")
        if len({item.name for item in values}) != len(values):
            raise ValueError("federated graph mount names must be unique")
        self.mounts = values
        self._by_name = {item.name: item for item in values}

    @property
    def epochs(self) -> dict[str, str]:
        return {item.name: item.epoch_id for item in self.mounts}

    def hybrid_search(
        self,
        text: str,
        *,
        entity_kind: str | None = None,
        facets: Mapping[str, str] | None = None,
        lanes: Iterable[str] = ("exact", "lexical", "blocking", "vector"),
        limit: int = 20,
        explain: bool = True,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("federated result limit must be between 1 and 1000")
        per_mount = min(1000, max(limit * 5, 50))
        ranked: dict[tuple[str, str], dict[str, Any]] = {}
        for mounted in self.mounts:
            results = mounted.index.hybrid_search(
                text,
                entity_kind=entity_kind,
                facets=facets,
                lanes=lanes,
                limit=per_mount,
                explain=explain,
            )
            for rank, result in enumerate(results, start=1):
                ranked[(mounted.name, str(result["entity_id"]))] = {
                    "result": result,
                    "mount": mounted,
                    "rank": rank,
                    "rrf_score": 1.0 / (60 + rank),
                }
        return self._ordered(ranked, limit=limit, explain=explain, mode="hybrid")

    def search_entities(
        self,
        text: str,
        *,
        entity_kind: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("federated result limit must be between 1 and 1000")
        per_mount = min(1000, max(limit * 5, 50))
        ranked: dict[tuple[str, str], dict[str, Any]] = {}
        for mounted in self.mounts:
            results = mounted.index.search_entities(
                text, entity_kind=entity_kind, limit=per_mount
            )
            for rank, result in enumerate(results, start=1):
                ranked[(mounted.name, str(result["entity_id"]))] = {
                    "result": result,
                    "mount": mounted,
                    "rank": rank,
                    "rrf_score": 1.0 / (60 + rank),
                }
        return self._ordered(ranked, limit=limit, explain=True, mode="lexical")

    def context(
        self,
        query: str,
        *,
        limit: int = 5,
        include_source: bool = False,
        facets: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        matches = self.hybrid_search(query, facets=facets, limit=limit, explain=True)
        useful_keys = {
            "uceg.description.source.docstring",
            "uceg.description.deterministic.synopsis",
            "uceg.aspect.python.signature",
            "uceg.aspect.python.annotation",
            "uceg.label.entity_kind",
            "uceg.label.language",
        }
        items: list[dict[str, Any]] = []
        for match in matches:
            mounted = self._by_name[str(match["graph_mount"])]
            entity_id = str(match["entity_id"])
            representations = mounted.index.representations("entity", entity_id, limit=200)
            items.append(
                {
                    "match": match,
                    "representations": [
                        item
                        for item in representations
                        if item["representation_key"] in useful_keys
                    ],
                    "source": mounted.index.source_for_entity(
                        entity_id, include_text=include_source
                    ),
                    "neighbors": mounted.index.neighbors(
                        entity_id, direction="both", limit=12
                    ),
                }
            )
        return {
            "query": query,
            "disclosure_level": "implementation" if include_source else "selection",
            "result_count": len(items),
            "graph_mounts": self.epochs,
            "items": items,
        }

    def _ordered(
        self,
        ranked: Mapping[tuple[str, str], Mapping[str, Any]],
        *,
        limit: int,
        explain: bool,
        mode: str,
    ) -> list[dict[str, Any]]:
        ordered = sorted(
            ranked.values(),
            key=lambda item: (
                -float(item["rrf_score"]),
                -float(item["result"].get("score", 0.0)),
                str(item["result"].get("qualified_name", "")),
                item["mount"].name,
            ),
        )[:limit]
        output: list[dict[str, Any]] = []
        for item in ordered:
            mounted = item["mount"]
            result = dict(item["result"])
            result["graph_mount"] = mounted.name
            result["epoch_id"] = mounted.epoch_id
            if explain:
                result["federation_receipt"] = {
                    "method": "mount_reciprocal_rank@60",
                    "mode": mode,
                    "mount_rank": item["rank"],
                    "mount_count": len(self.mounts),
                    "searched_epochs": self.epochs,
                    "score": round(float(item["rrf_score"]), 8),
                    "warning": "federated retrieval nominates candidates; it is not compatibility proof",
                }
            output.append(result)
        return output
