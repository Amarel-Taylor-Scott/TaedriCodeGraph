"""The compact `tcg` command-line surface for the first vertical slice."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Sequence

from .analyzers import PythonSyntaxAnalyzer
from .artifacts import analyze_wheel
from .storage import GraphStore
from .sources import PolyglotInventoryAnalyzer


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _env_csv(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    if value.casefold() in {"1", "true", "yes", "on"}:
        return True
    if value.casefold() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


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
    backup = epoch_subcommands.add_parser(
        "backup", help="mirror a validated published epoch into immutable objects"
    )
    backup.add_argument("--epoch")
    backup.add_argument("--store", type=Path, default=Path(".tcg"))
    backup.add_argument("--objects", type=Path, required=True)
    backup.add_argument("--prefix", default="")
    restore = epoch_subcommands.add_parser(
        "restore", help="restore an immutable epoch from an object backup manifest"
    )
    restore.add_argument("manifest_digest")
    restore.add_argument("--store", type=Path, default=Path(".tcg"))
    restore.add_argument("--objects", type=Path, required=True)
    restore.add_argument("--prefix", default="")
    restore.add_argument("--publish", action="store_true")

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

    primitive = subcommands.add_parser(
        "primitive", help="validate or release one complete repository-native primitive"
    )
    primitive_subcommands = primitive.add_subparsers(
        dest="primitive_command", required=True
    )
    primitive_validate = primitive_subcommands.add_parser(
        "validate", help="validate every release artifact, edge, port, digest, and policy field"
    )
    primitive_validate.add_argument("directory", type=Path)
    primitive_release = primitive_subcommands.add_parser(
        "release-local",
        help="stage, execute, release, search, and pack one trusted-source primitive",
    )
    primitive_release.add_argument("directory", type=Path)
    primitive_release.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    primitive_release.add_argument("--tenant", required=True)
    primitive_release.add_argument("--actor")
    primitive_release.add_argument(
        "--verifier-id", default="taedri.verifier.local-cli-v1"
    )
    primitive_release.add_argument("--authorizer-id", required=True)
    primitive_release.add_argument("--expected-revision-id")
    primitive_release.add_argument(
        "--allow-trusted-code-execution",
        action="store_true",
        help="required acknowledgement: the local verifier is not a hostile-code sandbox",
    )

    mcp = subcommands.add_parser("mcp", help="serve graph tools over MCP stdio")
    mcp.add_argument("--store", type=Path, default=Path(".tcg"))
    mcp.add_argument("--epoch")
    mcp.add_argument(
        "--api-url",
        default=os.environ.get("TAEDRI_API_URL"),
        help="authenticated remote API base URL; uses the local store when omitted",
    )
    mcp.add_argument(
        "--token-env",
        default="TAEDRI_API_TOKEN",
        help="environment variable holding the API token (never pass a token as an argument)",
    )
    mcp.add_argument("--graph", default=os.environ.get("TAEDRI_GRAPH", "default"))
    mcp.add_argument(
        "--session-id",
        default=os.environ.get("TAEDRI_PROMPT_SESSION_ID"),
        help="existing remote prompt session for fail-closed digest-only tool receipts",
    )

    serve = subcommands.add_parser(
        "serve", help="serve authenticated tenant-scoped graph and job APIs"
    )
    serve.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    serve.add_argument("--host", default=os.environ.get("TAEDRI_HOST", "127.0.0.1"))
    serve.add_argument(
        "--port", type=int, default=int(os.environ.get("TAEDRI_PORT", "8000"))
    )
    serve.add_argument(
        "--cors-origin",
        action="append",
        default=_env_csv("TAEDRI_CORS_ORIGINS"),
        help="allowed browser origin (repeatable; never defaults to wildcard)",
    )
    serve.add_argument(
        "--production",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("TAEDRI_PRODUCTION_SERVER"),
        help="run under the optional Gunicorn process manager",
    )
    serve.add_argument(
        "--workers", type=int, default=int(os.environ.get("TAEDRI_WEB_WORKERS", "2"))
    )
    serve.add_argument(
        "--threads", type=int, default=int(os.environ.get("TAEDRI_WEB_THREADS", "4"))
    )
    serve.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("TAEDRI_WEB_TIMEOUT_SECONDS", "120")),
    )
    serve.add_argument(
        "--api-requests-per-minute",
        type=int,
        default=int(os.environ.get("TAEDRI_API_REQUESTS_PER_MINUTE", "600")),
    )

    admin = subcommands.add_parser("admin", help="operate the local SaaS control plane")
    admin_subcommands = admin.add_subparsers(dest="admin_command", required=True)
    bootstrap = admin_subcommands.add_parser(
        "bootstrap", help="create a tenant, graph mount, and one API key"
    )
    bootstrap.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    bootstrap.add_argument("--tenant", required=True, help="lowercase tenant slug")
    bootstrap.add_argument("--name", required=True, help="tenant display name")
    bootstrap.add_argument("--graph-store", required=True, type=Path)
    bootstrap.add_argument(
        "--scope",
        action="append",
        default=[],
        help="API scope; defaults to graph/source/jobs/audit access",
    )
    status = admin_subcommands.add_parser("status", help="inspect control-plane readiness")
    status.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    revoke = admin_subcommands.add_parser("revoke-key", help="revoke an API key by ID")
    revoke.add_argument("key_id")
    revoke.add_argument("--actor", required=True)
    revoke.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    mount = admin_subcommands.add_parser(
        "mount", help="create or update a tenant graph mount"
    )
    mount.add_argument("--tenant", required=True)
    mount.add_argument("--name", required=True)
    mount.add_argument("--graph-store", required=True, type=Path)
    mount.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    list_mounts = admin_subcommands.add_parser(
        "list-mounts", help="list tenant graph mounts"
    )
    list_mounts.add_argument("--tenant", required=True)
    list_mounts.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )

    worker = subcommands.add_parser("worker", help="run persistent source-analysis jobs")
    worker_subcommands = worker.add_subparsers(dest="worker_command", required=True)
    worker_run = worker_subcommands.add_parser("run")
    worker_run.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    worker_run.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ.get("TAEDRI_SOURCE_ROOT", ".")),
    )
    worker_run.add_argument(
        "--worker-id",
        default=os.environ.get("TAEDRI_WORKER_ID", socket.gethostname()),
    )
    worker_run.add_argument("--queue", default=os.environ.get("TAEDRI_QUEUE", "default"))
    worker_run.add_argument(
        "--capability",
        action="append",
        default=[],
        help="worker capability (defaults to safe built-in analyzers)",
    )
    worker_run.add_argument("--lease-seconds", type=int, default=900)
    worker_run.add_argument("--poll-seconds", type=float, default=2.0)
    worker_run.add_argument("--once", action="store_true")
    worker_run.add_argument(
        "--allow-network-acquisition",
        action="store_true",
        default=_env_bool("TAEDRI_ALLOW_NETWORK_ACQUISITION"),
        help="allow exact-host PyPI/GitHub acquisition jobs with byte and digest limits",
    )

    poc = subcommands.add_parser(
        "poc", help="run API and worker together in one explicitly single-node process"
    )
    poc.add_argument(
        "--control",
        type=Path,
        default=Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite")),
    )
    poc.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ.get("TAEDRI_SOURCE_ROOT", ".")),
    )
    poc.add_argument("--host", default=os.environ.get("TAEDRI_HOST", "127.0.0.1"))
    poc.add_argument("--port", type=int, default=int(os.environ.get("TAEDRI_PORT", "8000")))
    poc.add_argument("--worker-id", default=os.environ.get("TAEDRI_WORKER_ID", socket.gethostname()))
    poc.add_argument("--queue", default=os.environ.get("TAEDRI_QUEUE", "default"))
    poc.add_argument("--poll-seconds", type=float, default=2.0)
    poc.add_argument(
        "--allow-network-acquisition",
        action="store_true",
        default=_env_bool("TAEDRI_ALLOW_NETWORK_ACQUISITION"),
    )
    poc.add_argument(
        "--cors-origin",
        action="append",
        default=_env_csv("TAEDRI_CORS_ORIGINS"),
    )

    components = subcommands.add_parser(
        "components",
        help=(
            "validate component inventory evidence; this does not authorize a "
            "product release"
        ),
    )
    components.add_argument("--root", type=Path, default=Path("."))

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
        elif args.epoch_command == "backup":
            from .object_store import FilesystemObjectStore, backup_epoch

            backup_manifest, object_ref = backup_epoch(
                store,
                FilesystemObjectStore(args.objects, prefix=args.prefix),
                args.epoch,
            )
            _print({"backup": backup_manifest, "manifest_object": object_ref})
        elif args.epoch_command == "restore":
            from .object_store import (
                FilesystemObjectStore,
                epoch_backup_from_dict,
                restore_epoch,
            )

            objects = FilesystemObjectStore(args.objects, prefix=args.prefix)
            value = json.loads(objects.get_bytes(args.manifest_digest))
            _print(
                {
                    "restored": restore_epoch(
                        store,
                        objects,
                        epoch_backup_from_dict(value),
                        publish=args.publish,
                    ),
                    "published": args.publish,
                }
            )
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
    if args.command == "primitive":
        from .primitives.bundle import inspect_primitive_directory

        inspected = inspect_primitive_directory(args.directory)
        if args.primitive_command == "validate":
            _print(
                {
                    "status": "release-grade",
                    "directory": str(args.directory),
                    "namespace": inspected.bundle.namespace,
                    "name": inspected.bundle.name,
                    "tree_id": inspected.tree_id,
                    "file_count": len(inspected.bundle.files),
                    "required_role_count": len(
                        {item.role for item in inspected.bundle.files}
                    ),
                    "artifacts": inspected.artifacts.to_dict(),
                    "code_executed": False,
                }
            )
            return 0
        if not args.allow_trusted_code_execution:
            raise ValueError(
                "release-local requires --allow-trusted-code-execution; use an isolated verifier for untrusted code"
            )
        from .primitive_repository import SQLitePrimitiveRepository
        from .primitives.acceptance import LocalPythonPrimitiveVerifier
        from .saas import SQLiteControlPlane, utc_now

        control = SQLiteControlPlane(args.control)
        tenant = control.tenant(args.tenant)
        repository = SQLitePrimitiveRepository(control)
        staged_at = utc_now()
        staged = repository.stage(
            tenant.identity.id,
            namespace=inspected.bundle.namespace,
            name=inspected.bundle.name,
            files=inspected.bundle.files,
            contract_path=inspected.bundle.contract_path,
            ref_kind=inspected.bundle.ref_kind,
            ref_name=inspected.bundle.ref_name,
            expected_revision_id=args.expected_revision_id,
            actor=args.actor or inspected.artifacts.implementation_producer_id,
            created_at=staged_at,
            message=inspected.bundle.message,
        )
        accepted = LocalPythonPrimitiveVerifier(
            repository,
            verifier_id=args.verifier_id,
        ).verify_and_release(
            tenant.identity.id,
            staged.revision.identity.id,
            ref_kind=inspected.bundle.ref_kind,
            ref_name=inspected.bundle.ref_name,
            authorizer_id=args.authorizer_id,
            policy_decision_id=inspected.bundle.policy_decision_id,
            verified_at=utc_now(),
            assurance_level=inspected.bundle.assurance_level,
        )
        pack, encoded = repository.pack(
            tenant.identity.id,
            inspected.bundle.namespace,
            inspected.bundle.name,
            ref_kind=inspected.bundle.ref_kind,
            ref_name=inspected.bundle.ref_name,
        )
        matches = repository.list(
            tenant.identity.id,
            query=inspected.bundle.name,
        )
        _print(
            {
                "status": "released",
                "tenant_id": tenant.identity.id,
                "primitive_id": accepted.released.release.primitive_id,
                "revision_id": accepted.released.release.revision_id,
                "release_id": accepted.released.release.identity.id,
                "acceptance_receipt_id": accepted.acceptance.identity.id,
                "assurance_level": accepted.released.release.assurance_level.value,
                "executed_case_count": accepted.executed_case_count,
                "proofs": [item.value for item in accepted.released.release.proofs],
                "interface_id": inspected.artifacts.interface_id,
                "interface_edges": inspected.artifacts.interface_edge_count,
                "interface_ports": inspected.artifacts.interface_port_count,
                "capability_groups": inspected.artifacts.capability_group_count,
                "search_result_count": len(matches),
                "pack_id": pack.identity.id,
                "pack_bytes": len(encoded),
            }
        )
        return 0
    if args.command == "mcp":
        from .mcp_server import run_server

        run_server(
            args.store,
            args.epoch,
            api_url=args.api_url,
            token_env=args.token_env,
            graph=args.graph,
            session_id=args.session_id,
        )
        return 0
    if args.command == "serve":
        if args.production:
            from .production_server import run_production_server

            run_production_server(
                control_db=args.control,
                host=args.host,
                port=args.port,
                cors_origins=args.cors_origin,
                workers=args.workers,
                threads=args.threads,
                timeout_seconds=args.timeout_seconds,
                api_request_limit_per_minute=args.api_requests_per_minute,
            )
        else:
            from .http_api import run_http_server

            run_http_server(
                control_db=args.control,
                host=args.host,
                port=args.port,
                cors_origins=args.cors_origin,
            )
        return 0
    if args.command == "admin":
        from .saas import GraphMount, SQLiteControlPlane, Tenant, utc_now

        control = SQLiteControlPlane(args.control)
        if args.admin_command == "bootstrap":
            created_at = utc_now()
            tenant = control.create_tenant(
                Tenant.create(
                    slug=args.tenant,
                    display_name=args.name,
                    created_at=created_at,
                ),
                actor="bootstrap",
            )
            graph_root = args.graph_store.expanduser().resolve()
            control.mount_graph(
                GraphMount.create(
                    tenant_id=tenant.identity.id,
                    name="default",
                    store_root=graph_root,
                    created_at=created_at,
                ),
                actor="bootstrap",
            )
            scopes = args.scope or [
                "graph:read",
                "source:read",
                "jobs:read",
                "jobs:write",
                "ingestion:write",
                "registry:read",
                "registry:write",
                "sessions:read",
                "sessions:write",
                "usage:read",
                "usage:write",
                "metrics:read",
                "audit:read",
                "billing:read",
                "billing:write",
            ]
            issued = control.issue_api_key(
                tenant.identity.id,
                scopes=scopes,
                actor="bootstrap",
            )
            _print(
                {
                    "tenant": tenant,
                    "graph_store": str(graph_root),
                    "api_key": issued,
                    "warning": "the API token is returned once; store it outside the repository",
                }
            )
        elif args.admin_command == "revoke-key":
            control.revoke_api_key(args.key_id, actor=args.actor)
            _print({"revoked": args.key_id})
        elif args.admin_command == "mount":
            tenant = control.tenant(args.tenant)
            now = utc_now()
            graph_root = args.graph_store.expanduser().resolve()
            mounted = control.mount_graph(
                GraphMount.create(
                    tenant_id=tenant.identity.id,
                    name=args.name,
                    store_root=graph_root,
                    created_at=now,
                ),
                actor="admin-cli",
            )
            _print({"mount": mounted})
        elif args.admin_command == "list-mounts":
            tenant = control.tenant(args.tenant)
            _print({"mounts": control.list_graph_mounts(tenant.identity.id)})
        else:
            _print(
                {
                    "integrity": control.integrity_check(),
                    "tenants": control.list_tenants(),
                }
            )
        return 0
    if args.command == "worker" and args.worker_command == "run":
        from .job_runner import JobRunner
        from .saas import SQLiteControlPlane

        runner = JobRunner(
            SQLiteControlPlane(args.control),
            source_root=args.source_root,
            worker_id=args.worker_id,
            queue=args.queue,
            capabilities=args.capability or None,
            lease_seconds=args.lease_seconds,
            allow_network_acquisition=args.allow_network_acquisition,
            github_token=os.environ.get("TAEDRI_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        )
        if args.once:
            _print(runner.run_once())
        else:
            runner.run_forever(poll_seconds=args.poll_seconds)
        return 0
    if args.command == "poc":
        import threading

        from .http_api import run_http_server
        from .job_runner import JobRunner
        from .saas import SQLiteControlPlane

        runner = JobRunner(
            SQLiteControlPlane(args.control),
            source_root=args.source_root,
            worker_id=args.worker_id,
            queue=args.queue,
            allow_network_acquisition=args.allow_network_acquisition,
            github_token=os.environ.get("TAEDRI_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        )
        worker_thread = threading.Thread(
            target=runner.run_forever,
            kwargs={"poll_seconds": args.poll_seconds},
            name="taedri-poc-worker",
            daemon=True,
        )
        worker_thread.start()
        run_http_server(
            control_db=args.control,
            host=args.host,
            port=args.port,
            cors_origins=args.cors_origin,
        )
        return 0
    if args.command == "components":
        from .readiness import load_component_readiness

        _print(load_component_readiness(args.root))
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
