"""The compact `tcg` command-line surface for the first vertical slice."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .analyzers import PythonSyntaxAnalyzer
from .storage import GraphStore


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

    search = subcommands.add_parser("search", help="exact and fielded lexical entity search")
    search.add_argument("query")
    search.add_argument("--kind")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--store", type=Path, default=Path(".tcg"))
    search.add_argument("--epoch")

    entity = subcommands.add_parser("entity", help="entity operations")
    entity_subcommands = entity.add_subparsers(dest="entity_command", required=True)
    show = entity_subcommands.add_parser("show")
    show.add_argument("identifier")
    show.add_argument("--store", type=Path, default=Path(".tcg"))
    show.add_argument("--epoch")

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
        _print(index.search_entities(args.query, entity_kind=args.kind, limit=args.limit))
        return 0
    if args.command == "entity" and args.entity_command == "show":
        index = GraphStore(args.store).index(args.epoch)
        record = index.resolve_entity(args.identifier)
        if record is None:
            raise LookupError(f"entity not found: {args.identifier}")
        _print(record)
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (FileNotFoundError, ValueError, LookupError) as exc:
        parser.exit(2, f"tcg: error: {exc}\n")
    return 2  # pragma: no cover
