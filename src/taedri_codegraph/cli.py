"""The compact `tcg` command-line surface for the first vertical slice."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .analyzers import PythonSyntaxAnalyzer
from .artifacts import analyze_wheel
from .storage import GraphStore
from .sources import PolyglotInventoryAnalyzer


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tcg",
        description="Build and query evidence-backed graphs over existing code.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    analyze = subcommands.add_parser("analyze", help="analyze source without executing it")
    analyze_subcommands = analyze.add_subparsers(dest="analyze_command", required=True)
    path = analyze_subcommands.add_parser("path", help="analyze a local Python source tree")
    path.add_argument("root", type=Path)
    path.add_argument("--store", type=Path, default=Path(".tcg"))
    path.add_argument("--package")
    path.add_argument("--release")
    path.add_argument("--publish", action="store_true")
    wheel = analyze_subcommands.add_parser(
        "wheel", help="verify and analyze a wheel without importing or executing it"
    )
    wheel.add_argument("artifact", type=Path)
    wheel.add_argument("--store", type=Path, default=Path(".tcg"))
    wheel.add_argument("--publish", action="store_true")
    inventory = analyze_subcommands.add_parser(
        "inventory", help="inventory a local polyglot source tree without executing it"
    )
    inventory.add_argument("root", type=Path)
    inventory.add_argument("--store", type=Path, default=Path(".tcg"))
    inventory.add_argument("--package")
    inventory.add_argument("--release")
    inventory.add_argument("--source-uri")
    inventory.add_argument("--publish", action="store_true")

    epoch = subcommands.add_parser("epoch", help="validate and publish immutable epochs")
    epoch_subcommands = epoch.add_subparsers(dest="epoch_command", required=True)
    validate = epoch_subcommands.add_parser("validate")
    validate.add_argument("epoch_id", nargs="?")
    validate.add_argument("--store", type=Path, default=Path(".tcg"))
    publish = epoch_subcommands.add_parser("publish")
    publish.add_argument("epoch_id")
    publish.add_argument("--store", type=Path, default=Path(".tcg"))
    listing = epoch_subcommands.add_parser("list")
    listing.add_argument("--store", type=Path, default=Path(".tcg"))

    search = subcommands.add_parser("search", help="explainable hybrid entity search")
    search.add_argument("query")
    search.add_argument("--kind")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--store", type=Path, default=Path(".tcg"))
    search.add_argument("--epoch")
    search.add_argument("--mode", choices=("hybrid", "lexical"), default="hybrid")
    search.add_argument(
        "--filter", action="append", default=[], metavar="KEY=VALUE", help="facet filter"
    )
    search.add_argument(
        "--lane",
        action="append",
        choices=("exact", "lexical", "blocking", "vector"),
        help="restrict hybrid retrieval lanes (repeatable)",
    )
    search.add_argument("--no-explain", action="store_true")

    context = subcommands.add_parser(
        "context", help="progressively disclose selected implementation context for an agent"
    )
    context.add_argument("query")
    context.add_argument("--limit", type=int, default=5)
    context.add_argument("--source", action="store_true", help="include bounded source bodies")
    context.add_argument("--filter", action="append", default=[], metavar="KEY=VALUE")
    context.add_argument("--store", type=Path, default=Path(".tcg"))
    context.add_argument("--epoch")

    representation = subcommands.add_parser(
        "representation", help="inspect representation variants and provenance receipts"
    )
    representation_subcommands = representation.add_subparsers(
        dest="representation_command", required=True
    )
    representation_list = representation_subcommands.add_parser("list")
    representation_list.add_argument("identifier")
    representation_list.add_argument(
        "--subject-kind", choices=("entity", "snapshot", "file", "relation"), default="entity"
    )
    representation_list.add_argument("--limit", type=int, default=100)
    representation_list.add_argument("--store", type=Path, default=Path(".tcg"))
    representation_list.add_argument("--epoch")
    representation_search = representation_subcommands.add_parser("search")
    representation_search.add_argument("text", nargs="?")
    representation_search.add_argument("--key")
    representation_search.add_argument("--subject-kind")
    representation_search.add_argument("--limit", type=int, default=100)
    representation_search.add_argument("--store", type=Path, default=Path(".tcg"))
    representation_search.add_argument("--epoch")

    mcp = subcommands.add_parser("mcp", help="serve graph tools over MCP stdio")
    mcp.add_argument("--store", type=Path, default=Path(".tcg"))
    mcp.add_argument("--epoch")

    entity = subcommands.add_parser("entity", help="entity operations")
    entity_subcommands = entity.add_subparsers(dest="entity_command", required=True)
    show = entity_subcommands.add_parser("show")
    show.add_argument("identifier")
    show.add_argument("--store", type=Path, default=Path(".tcg"))
    show.add_argument("--epoch")
    similar = entity_subcommands.add_parser("similar")
    similar.add_argument("identifier")
    similar.add_argument("--limit", type=int, default=50)
    similar.add_argument("--store", type=Path, default=Path(".tcg"))
    similar.add_argument("--epoch")

    edge = subcommands.add_parser("edge", help="first-class relation operations")
    edge_subcommands = edge.add_subparsers(dest="edge_command", required=True)
    edge_search = edge_subcommands.add_parser("search")
    edge_search.add_argument("text", nargs="?")
    edge_search.add_argument("--predicate")
    edge_search.add_argument("--limit", type=int, default=50)
    edge_search.add_argument("--store", type=Path, default=Path(".tcg"))
    edge_search.add_argument("--epoch")
    neighbors = edge_subcommands.add_parser("neighbors")
    neighbors.add_argument("entity")
    neighbors.add_argument("--direction", choices=("in", "out", "both"), default="both")
    neighbors.add_argument("--predicate")
    neighbors.add_argument("--limit", type=int, default=100)
    neighbors.add_argument("--store", type=Path, default=Path(".tcg"))
    neighbors.add_argument("--epoch")
    edge_show = edge_subcommands.add_parser("show")
    edge_show.add_argument("assertion_id")
    edge_show.add_argument("--store", type=Path, default=Path(".tcg"))
    edge_show.add_argument("--epoch")
    return parser


def run(args: argparse.Namespace) -> int:
    if args.command == "analyze" and args.analyze_command == "path":
        analyzer = PythonSyntaxAnalyzer()
        bundle = analyzer.analyze(
            args.root,
            package_name=args.package,
            release=args.release,
        )
        store = GraphStore(args.store)
        epoch_id = store.write_candidate(bundle, analyzer.registry)
        published = False
        if args.publish:
            store.publish_epoch(epoch_id)
            published = True
        _print({"epoch_id": epoch_id, "published": published, **bundle.summary()})
        return 0
    if args.command == "analyze" and args.analyze_command == "wheel":
        analyzer = PythonSyntaxAnalyzer()
        bundle, inspection = analyze_wheel(args.artifact, analyzer)
        store = GraphStore(args.store)
        epoch_id = store.write_candidate(bundle, analyzer.registry)
        published = False
        if args.publish:
            store.publish_epoch(epoch_id)
            published = True
        _print(
            {
                "epoch_id": epoch_id,
                "published": published,
                "artifact": inspection.to_dict(),
                **bundle.summary(),
            }
        )
        return 0
    if args.command == "analyze" and args.analyze_command == "inventory":
        analyzer = PolyglotInventoryAnalyzer()
        bundle = analyzer.analyze(
            args.root,
            package_name=args.package,
            release=args.release,
            source_uri=args.source_uri,
        )
        store = GraphStore(args.store)
        epoch_id = store.write_candidate(bundle)
        published = False
        if args.publish:
            store.publish_epoch(epoch_id)
            published = True
        _print({"epoch_id": epoch_id, "published": published, **bundle.summary()})
        return 0
    if args.command == "epoch":
        store = GraphStore(args.store)
        if args.epoch_command == "validate":
            epoch_id = args.epoch_id or store.current_epoch_id()
            _print(store.validate_epoch(epoch_id))
        elif args.epoch_command == "publish":
            _print({"published": store.publish_epoch(args.epoch_id)})
        else:
            _print(store.list_epochs())
        return 0
    if args.command == "search":
        index = GraphStore(args.store).index(args.epoch)
        if args.mode == "lexical":
            results = index.search_entities(args.query, entity_kind=args.kind, limit=args.limit)
        else:
            results = index.hybrid_search(
                args.query,
                entity_kind=args.kind,
                facets=_parse_filters(args.filter),
                lanes=args.lane or ("exact", "lexical", "blocking", "vector"),
                limit=args.limit,
                explain=not args.no_explain,
            )
        _print(results)
        return 0
    if args.command == "context":
        index = GraphStore(args.store).index(args.epoch)
        _print(
            index.context(
                args.query,
                limit=args.limit,
                include_source=args.source,
                facets=_parse_filters(args.filter),
            )
        )
        return 0
    if args.command == "representation" and args.representation_command == "list":
        index = GraphStore(args.store).index(args.epoch)
        if args.subject_kind == "entity":
            entity = index.resolve_entity(args.identifier)
            if entity is None:
                raise LookupError(f"entity not found: {args.identifier}")
            subject_id = entity["identity"]["id"]
        elif args.subject_kind == "snapshot" and args.identifier == "current":
            subject_id = index.metadata()["snapshot_id"]
        else:
            subject_id = args.identifier
        _print(index.representations(args.subject_kind, subject_id, limit=args.limit))
        return 0
    if args.command == "representation" and args.representation_command == "search":
        index = GraphStore(args.store).index(args.epoch)
        _print(
            index.search_representations(
                representation_key=args.key,
                text=args.text,
                subject_kind=args.subject_kind,
                limit=args.limit,
            )
        )
        return 0
    if args.command == "mcp":
        from .mcp_server import run_server

        run_server(args.store, args.epoch)
        return 0
    if args.command == "entity" and args.entity_command == "show":
        index = GraphStore(args.store).index(args.epoch)
        record = index.resolve_entity(args.identifier)
        if record is None:
            raise LookupError(f"entity not found: {args.identifier}")
        _print(record)
        return 0
    if args.command == "entity" and args.entity_command == "similar":
        index = GraphStore(args.store).index(args.epoch)
        _print(index.structurally_similar(args.identifier, limit=args.limit))
        return 0
    if args.command == "edge":
        index = GraphStore(args.store).index(args.epoch)
        if args.edge_command == "search":
            _print(index.search_edges(predicate=args.predicate, text=args.text, limit=args.limit))
        elif args.edge_command == "show":
            record = index.edge_record(args.assertion_id)
            if record is None:
                raise LookupError(f"edge assertion not found: {args.assertion_id}")
            _print(record)
        else:
            entity = index.resolve_entity(args.entity)
            if entity is None:
                raise LookupError(f"entity not found: {args.entity}")
            entity_id = entity["identity"]["id"]
            _print(
                index.neighbors(
                    entity_id,
                    direction=args.direction,
                    predicate=args.predicate,
                    limit=args.limit,
                )
            )
        return 0
    raise RuntimeError("unhandled CLI command")


def _parse_filters(values: Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key or not item:
            raise ValueError(f"facet filter must be KEY=VALUE: {value!r}")
        result[key] = item
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (FileNotFoundError, ValueError, LookupError) as exc:
        parser.exit(2, f"tcg: error: {exc}\n")
    return 2  # pragma: no cover
