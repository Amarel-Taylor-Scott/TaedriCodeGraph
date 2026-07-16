"""Optional MCP surface for coding agents and editor harnesses."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .api_client import TaedriClient
from .harness_receipts import RemoteSessionRecorder
from .primitives.search import (
    PrimitiveSearchRequest,
    PrimitiveSearchService,
    SearchStrategy,
)
from .storage import GraphStore


def create_server(
    store: str | Path = ".tcg",
    epoch: str | None = None,
    *,
    api_url: str | None = None,
    token_env: str = "TAEDRI_API_TOKEN",
    graph: str = "default",
    session_id: str | None = None,
    api_client: TaedriClient | None = None,
) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - optional integration dependency
        raise RuntimeError("install taedri-codegraph[agents] to run the MCP server") from exc

    if api_client is not None and api_url is not None:
        raise ValueError("pass an API client or API URL, not both")
    remote = api_client
    if api_url is not None:
        token = os.environ.get(token_env)
        if not token:
            raise RuntimeError(
                f"authenticated remote MCP requires a token in {token_env}"
            )
        remote = TaedriClient(api_url, token, graph=graph)
    if session_id is not None and remote is None:
        raise ValueError("prompt-session recording requires authenticated remote mode")
    recorder = (
        RemoteSessionRecorder(remote, session_id)
        if remote is not None and session_id is not None
        else None
    )
    graph_store = None if remote is not None else GraphStore(store)
    server = FastMCP(
        "Taedri CodeGraph",
        instructions=(
            "Search before requesting source. Use search_code for candidate selection, "
            "or search_primitives when adaptive escalation receipts are needed. "
            "then get_code_context(include_source=true) only for selected entities. "
            "Retrieval similarity is not compatibility or correctness evidence. "
            "Never print or return the configured bearer token."
        ),
    )

    def index():
        if graph_store is None:  # pragma: no cover - guarded by each remote branch
            raise RuntimeError("local graph index is unavailable in remote mode")
        return graph_store.index(epoch)

    @server.tool()
    def search_code(
        query: str,
        limit: int = 10,
        entity_kind: str | None = None,
        facet_filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Explainable exact, lexical, blocking, and vector search over code entities."""

        if remote is not None:
            response = remote.search(
                query,
                entity_kind=entity_kind,
                facet_filters=facet_filters,
                limit=limit,
            )
            if recorder is not None:
                recorder.record_search(query, response, tool_name="search_code")
            return response["items"]
        return index().hybrid_search(
            query,
            entity_kind=entity_kind,
            facets=facet_filters,
            limit=limit,
            explain=True,
        )

    @server.tool()
    def get_code_context(
        query: str,
        limit: int = 5,
        include_source: bool = False,
        facet_filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return progressively disclosed descriptions, contracts, graph links, and source."""

        if remote is not None:
            response = remote.context(
                query,
                limit=limit,
                include_source=include_source,
                facet_filters=facet_filters,
            )
            if recorder is not None:
                recorder.record_search(query, response, tool_name="get_code_context")
            return response
        return index().context(
            query,
            limit=limit,
            include_source=include_source,
            facets=facet_filters,
        )

    @server.tool()
    def search_primitives(
        query: str,
        strategy: str = "auto",
        limit: int = 10,
        minimum_candidates: int = 8,
        entity_kind: str | None = None,
        facet_filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Adaptive exact→sparse→semantic→structural search with escalation receipts."""

        try:
            selected_strategy = SearchStrategy(strategy)
        except ValueError as exc:
            raise ValueError("strategy must be fast, balanced, deep, or auto") from exc
        if remote is not None:
            response = remote.search(
                query,
                mode="adaptive",
                strategy=selected_strategy.value,
                minimum_candidates=minimum_candidates,
                entity_kind=entity_kind,
                facet_filters=facet_filters,
                limit=limit,
            )
            if recorder is not None:
                recorder.record_search(query, response, tool_name="search_primitives")
            return response
        response = PrimitiveSearchService(index()).search(
            PrimitiveSearchRequest(
                query,
                selected_strategy,
                limit=limit,
                minimum_candidates=minimum_candidates,
                entity_kind=entity_kind,
                facets=facet_filters,
            )
        )
        return response.to_dict()

    @server.tool()
    def get_entity(identifier: str) -> dict[str, Any]:
        """Resolve an exact entity ID or qualified name."""

        if remote is not None:
            return remote.entity(identifier)
        entity = index().resolve_entity(identifier)
        if entity is None:
            raise ValueError(f"entity not found: {identifier}")
        return entity

    @server.tool()
    def get_neighbors(
        identifier: str,
        direction: str = "both",
        predicate: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Traverse evidence-bearing incoming or outgoing graph assertions."""

        if remote is not None:
            return remote.neighbors(
                identifier, direction=direction, predicate=predicate, limit=limit
            )["items"]
        entity = index().resolve_entity(identifier)
        if entity is None:
            raise ValueError(f"entity not found: {identifier}")
        return index().neighbors(
            entity["identity"]["id"], direction=direction, predicate=predicate, limit=limit
        )

    @server.tool()
    def list_representations(identifier: str, limit: int = 100) -> list[dict[str, Any]]:
        """List parallel representation variants with producer and generation receipts."""

        if remote is not None:
            return remote.representations(identifier, limit=limit)["items"]
        entity = index().resolve_entity(identifier)
        if entity is None:
            raise ValueError(f"entity not found: {identifier}")
        return index().representations("entity", entity["identity"]["id"], limit=limit)

    @server.tool()
    def find_structural_candidates(
        identifier: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Find LSH-band candidates; results are nominations, not equivalence proof."""

        if remote is not None:
            return remote.structurally_similar(identifier, limit=limit)["items"]
        return index().structurally_similar(identifier, limit=limit)

    @server.tool()
    def search_metadata(
        representation_key: str | None = None,
        text: str | None = None,
        subject_kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search license, artifact, label, metric, and other representation variants."""

        if remote is not None:
            return remote.search_metadata(
                representation_key=representation_key,
                text=text,
                subject_kind=subject_kind,
                limit=limit,
            )["items"]
        return index().search_representations(
            representation_key=representation_key,
            text=text,
            subject_kind=subject_kind,
            limit=limit,
        )

    @server.resource("taedri://entity/{identifier}")
    def entity_resource(identifier: str) -> dict[str, Any]:
        if remote is not None:
            return remote.entity(identifier)
        entity = index().resolve_entity(identifier)
        if entity is None:
            raise ValueError(f"entity not found: {identifier}")
        return entity

    return server


def run_server(
    store: str | Path = ".tcg",
    epoch: str | None = None,
    *,
    api_url: str | None = None,
    token_env: str = "TAEDRI_API_TOKEN",
    graph: str = "default",
    session_id: str | None = None,
) -> None:
    create_server(
        store,
        epoch,
        api_url=api_url,
        token_env=token_env,
        graph=graph,
        session_id=session_id,
    ).run(transport="stdio")
