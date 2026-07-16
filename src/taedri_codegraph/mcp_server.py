"""Optional MCP surface for coding agents and editor harnesses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import GraphStore


def create_server(store: str | Path = ".tcg", epoch: str | None = None) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - optional integration dependency
        raise RuntimeError("install taedri-codegraph[agents] to run the MCP server") from exc

    graph_store = GraphStore(store)
    server = FastMCP(
        "Taedri CodeGraph",
        instructions=(
            "Search before requesting source. Use search_code for candidate selection, "
            "then get_code_context(include_source=true) only for selected entities. "
            "Retrieval similarity is not compatibility or correctness evidence."
        ),
    )

    def index():
        return graph_store.index(epoch)

    @server.tool()
    def search_code(
        query: str,
        limit: int = 10,
        entity_kind: str | None = None,
        facet_filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Explainable exact, lexical, blocking, and vector search over code entities."""

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

        return index().context(
            query,
            limit=limit,
            include_source=include_source,
            facets=facet_filters,
        )

    @server.tool()
    def get_entity(identifier: str) -> dict[str, Any]:
        """Resolve an exact entity ID or qualified name."""

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

        entity = index().resolve_entity(identifier)
        if entity is None:
            raise ValueError(f"entity not found: {identifier}")
        return index().neighbors(
            entity["identity"]["id"], direction=direction, predicate=predicate, limit=limit
        )

    @server.tool()
    def list_representations(identifier: str, limit: int = 100) -> list[dict[str, Any]]:
        """List parallel representation variants with producer and generation receipts."""

        entity = index().resolve_entity(identifier)
        if entity is None:
            raise ValueError(f"entity not found: {identifier}")
        return index().representations("entity", entity["identity"]["id"], limit=limit)

    @server.tool()
    def find_structural_candidates(
        identifier: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Find LSH-band candidates; results are nominations, not equivalence proof."""

        return index().structurally_similar(identifier, limit=limit)

    @server.tool()
    def search_metadata(
        representation_key: str | None = None,
        text: str | None = None,
        subject_kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Search license, artifact, label, metric, and other representation variants."""

        return index().search_representations(
            representation_key=representation_key,
            text=text,
            subject_kind=subject_kind,
            limit=limit,
        )

    @server.resource("taedri://entity/{identifier}")
    def entity_resource(identifier: str) -> dict[str, Any]:
        entity = index().resolve_entity(identifier)
        if entity is None:
            raise ValueError(f"entity not found: {identifier}")
        return entity

    return server


def run_server(store: str | Path = ".tcg", epoch: str | None = None) -> None:
    create_server(store, epoch).run(transport="stdio")
