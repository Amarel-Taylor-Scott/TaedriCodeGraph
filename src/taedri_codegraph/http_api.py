"""Dependency-free authenticated HTTP API over published Taedri graph epochs."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qs, unquote
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .api import build_openapi
from .canonical import to_primitive
from .candidate_repository import SQLiteCandidateRepository
from .intake import CandidateState
from .metering import QuotaExceeded, SQLiteMeteringRepository
from .pagination import CursorError, decode_cursor, encode_cursor
from .pipelines import platform_pipeline_catalog
from .primitive_capsules import CapsuleRole, RefKind
from .primitive_repository import (
    PrimitiveFileInput,
    PrimitiveRepositoryConflict,
    SQLitePrimitiveRepository,
)
from .primitives.search import (
    PrimitiveSearchRequest,
    PrimitiveSearchService,
    SearchStrategy,
)
from .portal import (
    BillingGateway,
    BillingUnavailable,
    PortalService,
    SubscriptionRepository,
    default_plan_catalog,
)
from .session_repository import (
    SessionRepositoryConflict,
    SQLitePromptSessionRepository,
)
from .sessions import HarnessRef, PromptPrivacyMode, PromptSession, SessionEventKind
from .saas import (
    ApiPrincipal,
    AuthenticationError,
    AuthorizationError,
    ControlPlaneError,
    SQLiteControlPlane,
    SQLiteWorkerQueue,
    utc_now,
)
from .storage import GraphStore
from .workers import JobKind, JobState, WorkerJob, WorkerQueueError


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ApiConfig:
    control_db: Path
    cors_origins: tuple[str, ...] = ()
    max_body_bytes: int = 1_048_576
    max_federated_graphs: int = 32
    api_request_limit_per_minute: int = 600
    billing_gateway: BillingGateway | None = None
    portal_return_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_body_bytes <= 0:
            raise ValueError("API body limit must be positive")
        if not 1 <= self.max_federated_graphs <= 1000:
            raise ValueError("federated graph limit must be between 1 and 1000")
        if not 1 <= self.api_request_limit_per_minute <= 1_000_000:
            raise ValueError("API request limit must be between 1 and 1,000,000")


class ApiError(ValueError):
    def __init__(self, status: str, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class TaedriAPI:
    """Small WSGI surface with tenant isolation and progressive disclosure."""

    def __init__(self, config: ApiConfig):
        self.config = config
        self.control = SQLiteControlPlane(config.control_db)
        self.jobs = SQLiteWorkerQueue(self.control)
        self.primitives = SQLitePrimitiveRepository(self.control)
        self.candidates = SQLiteCandidateRepository(self.control)
        self.sessions = SQLitePromptSessionRepository(self.control)
        self.metering = SQLiteMeteringRepository(self.control)
        self.plan_catalog = default_plan_catalog()
        self.subscriptions = SubscriptionRepository(self.control, self.plan_catalog)
        self.portal = PortalService(
            self.subscriptions,
            gateway=config.billing_gateway,
            allowed_return_origins=(config.portal_return_origins or config.cors_origins),
        )
        self.pipeline_catalog = platform_pipeline_catalog()

    def __call__(
        self,
        environ: Mapping[str, Any],
        start_response: Callable[[str, list[tuple[str, str]]], Any],
    ) -> Iterable[bytes]:
        started = time.monotonic()
        request_id = str(environ.get("HTTP_X_REQUEST_ID") or uuid.uuid4())
        if len(request_id) > 128 or any(ord(character) < 32 for character in request_id):
            request_id = str(uuid.uuid4())
        admission_id = str(uuid.uuid4())
        origin = str(environ.get("HTTP_ORIGIN") or "")
        try:
            status, payload, extra_headers = self._dispatch(
                environ, admission_id=admission_id, request_id=request_id
            )
        except ApiError as exc:
            status = exc.status
            payload = {"error": {"code": exc.code, "message": exc.message}}
            extra_headers = []
        except AuthenticationError:
            status = "401 Unauthorized"
            payload = {
                "error": {"code": "authentication_required", "message": "invalid credential"}
            }
            extra_headers = [("WWW-Authenticate", 'Bearer realm="taedri"')]
        except AuthorizationError as exc:
            status = "403 Forbidden"
            payload = {"error": {"code": "forbidden", "message": str(exc)}}
            extra_headers = []
        except PrimitiveRepositoryConflict as exc:
            status = "409 Conflict"
            payload = {"error": {"code": "registry_conflict", "message": str(exc)}}
            extra_headers = []
        except SessionRepositoryConflict as exc:
            status = "409 Conflict"
            payload = {"error": {"code": "session_conflict", "message": str(exc)}}
            extra_headers = []
        except QuotaExceeded as exc:
            status = "429 Too Many Requests"
            payload = {
                "error": {
                    "code": "quota_exceeded",
                    "message": str(exc),
                    "metric": exc.metric,
                    "hard_limit": exc.hard_limit,
                    "used": exc.used,
                    "requested": exc.requested,
                    "window_start": exc.window_start,
                    "window_end": exc.window_end,
                }
            }
            extra_headers = [("Retry-After", "60")]
        except BillingUnavailable as exc:
            status = "503 Service Unavailable"
            payload = {"error": {"code": "billing_unavailable", "message": str(exc)}}
            extra_headers = []
        except (ControlPlaneError, WorkerQueueError, ValueError) as exc:
            status = "400 Bad Request"
            payload = {"error": {"code": "invalid_request", "message": str(exc)}}
            extra_headers = []
        except LookupError as exc:
            status = "404 Not Found"
            payload = {"error": {"code": "not_found", "message": str(exc)}}
            extra_headers = []
        except FileNotFoundError as exc:
            status = "409 Conflict"
            payload = {"error": {"code": "graph_not_ready", "message": str(exc)}}
            extra_headers = []
        except Exception:
            LOGGER.exception("unhandled API error request_id=%s", request_id)
            status = "500 Internal Server Error"
            payload = {
                "error": {
                    "code": "internal_error",
                    "message": "request failed; consult the server log with the request ID",
                }
            }
            extra_headers = []

        primitive = to_primitive(payload)
        body = (
            b""
            if status.startswith("204 ")
            else json.dumps(
                primitive, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        )
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Request-ID", request_id),
        ]
        if origin and origin in self.config.cors_origins:
            headers.extend(
                [("Access-Control-Allow-Origin", origin), ("Vary", "Origin")]
            )
        headers.extend(extra_headers)
        duration_ms = (time.monotonic() - started) * 1000
        LOGGER.info(
            "request completed request_id=%s method=%s path=%s status=%s duration_ms=%.3f",
            request_id,
            str(environ.get("REQUEST_METHOD") or "GET").upper(),
            str(environ.get("PATH_INFO") or "/"),
            status.split(" ", 1)[0],
            duration_ms,
        )
        start_response(status, headers)
        return [body]

    def _dispatch(
        self,
        environ: Mapping[str, Any],
        *,
        admission_id: str,
        request_id: str,
    ) -> tuple[str, Mapping[str, Any], list[tuple[str, str]]]:
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        path = str(environ.get("PATH_INFO") or "/")
        query = parse_qs(str(environ.get("QUERY_STRING") or ""), keep_blank_values=True)

        if method == "OPTIONS":
            return self._preflight(environ)
        if method == "GET" and path == "/healthz":
            return "200 OK", {"status": "ok", "service": "taedri-codegraph"}, []
        if method == "GET" and path == "/readyz":
            integrity = self.control.integrity_check()
            if integrity != "ok":
                raise ApiError("503 Service Unavailable", "not_ready", "control store failed")
            return (
                "200 OK",
                {
                    "status": "ready",
                    "control_store": integrity,
                    "tenant_count": len(self.control.list_tenants()),
                },
                [],
            )
        if method == "GET" and path in {"/openapi.json", "/v1/openapi.json"}:
            return "200 OK", self._openapi(), []
        if method == "GET" and path == "/v1/public/plans":
            return "200 OK", self.portal.public_plans(), []

        principal = self._principal(environ)
        self.metering.consume(
            principal.tenant_id,
            metric="api.request",
            quantity=1,
            idempotency_key=admission_id,
            resource_id=request_id,
            dimensions={"method": method, "path": path, "key_id": principal.key_id},
            fallback_window_seconds=60,
            fallback_hard_limit=self.config.api_request_limit_per_minute,
        )
        if method == "GET" and path == "/v1/me":
            return (
                "200 OK",
                {
                    "tenant_id": principal.tenant_id,
                    "key_id": principal.key_id,
                    "scopes": principal.scopes,
                },
                [],
            )
        if method == "GET" and path == "/v1/epochs":
            self.control.require(principal, "graph:read")
            store = self._store(principal, self._optional(query, "graph") or "default")
            return "200 OK", store.list_epochs(), []
        if method == "GET" and path == "/v1/graphs":
            self.control.require(principal, "graph:read")
            return "200 OK", self._graphs(principal), []
        if method == "GET" and path == "/v1/search":
            return "200 OK", self._search(principal, query), []
        if method == "GET" and path == "/v1/context":
            return "200 OK", self._context(principal, query), []
        if method == "GET" and path == "/v1/representations":
            return "200 OK", self._representations(principal, query), []
        if method == "GET" and path == "/v1/edges":
            return "200 OK", self._edges(principal, query), []
        if path.startswith("/v1/edges/") and method == "GET":
            return (
                "200 OK",
                self._edge(principal, unquote(path[len("/v1/edges/") :]), query),
                [],
            )
        if path.startswith("/v1/entities/") and method == "GET":
            tail = path[len("/v1/entities/") :]
            if tail.endswith("/neighbors"):
                identifier = unquote(tail[: -len("/neighbors")])
                return "200 OK", self._neighbors(principal, identifier, query), []
            if tail.endswith("/similar"):
                identifier = unquote(tail[: -len("/similar")])
                return "200 OK", self._structurally_similar(principal, identifier, query), []
            return "200 OK", self._entity(principal, unquote(tail), query), []
        if path == "/v1/jobs" and method == "POST":
            return "202 Accepted", self._submit_job(principal, environ), []
        if path == "/v1/jobs" and method == "GET":
            return "200 OK", self._list_jobs(principal, query), []
        if path.startswith("/v1/jobs/") and path.endswith("/cancel") and method == "POST":
            job_id = unquote(path[len("/v1/jobs/") : -len("/cancel")])
            return "200 OK", self._cancel_job(principal, job_id), []
        if path.startswith("/v1/jobs/") and method == "GET":
            return "200 OK", self._job(principal, unquote(path[len("/v1/jobs/") :])), []
        if path == "/v1/candidates" and method == "GET":
            return "200 OK", self._list_candidates(principal, query), []
        if path.startswith("/v1/candidates/"):
            return self._candidate_route(
                principal,
                method,
                path[len("/v1/candidates/") :],
                query,
                environ,
            )
        if path == "/v1/sessions" and method == "POST":
            return "201 Created", self._start_session(principal, environ), []
        if path == "/v1/sessions" and method == "GET":
            return "200 OK", self._list_sessions(principal, query), []
        if path.startswith("/v1/sessions/"):
            return self._session_route(
                principal,
                method,
                path[len("/v1/sessions/") :],
                environ,
            )
        if path == "/v1/primitives" and method == "POST":
            return "202 Accepted", self._stage_primitive(principal, environ), []
        if path == "/v1/primitives" and method == "GET":
            return "200 OK", self._list_primitives(principal, query), []
        if path.startswith("/v1/primitives/"):
            return self._primitive_route(
                principal,
                method,
                path[len("/v1/primitives/") :],
                query,
                environ,
            )
        if path == "/v1/usage" and method == "GET":
            return "200 OK", self._usage(principal, query), []
        if path == "/v1/metrics" and method == "GET":
            self.control.require(principal, "metrics:read")
            return "200 OK", self.control.tenant_metrics(principal.tenant_id), []
        if path == "/v1/limits" and method == "GET":
            return "200 OK", self._limits(principal, query), []
        if path == "/v1/limits" and method == "POST":
            return "201 Created", self._set_limit(principal, environ), []
        if path == "/v1/portal/subscription" and method == "GET":
            self.control.require(principal, "billing:read")
            return "200 OK", self.portal.subscription(principal.tenant_id), []
        if path == "/v1/portal/entitlements" and method == "GET":
            self.control.require(principal, "billing:read")
            return (
                "200 OK",
                self.subscriptions.entitlements(principal.tenant_id).to_dict(),
                [],
            )
        if path == "/v1/portal/checkout" and method == "POST":
            self.control.require(principal, "billing:write")
            body = self._json_body(environ)
            session = self.portal.checkout(
                principal.tenant_id,
                plan_ref=self._body_string(body, "plan_ref"),
                return_url=self._body_string(body, "return_url"),
            )
            return "201 Created", session.to_dict(), []
        if path == "/v1/portal/billing-session" and method == "POST":
            self.control.require(principal, "billing:write")
            body = self._json_body(environ)
            session = self.portal.billing_portal(
                principal.tenant_id,
                return_url=self._body_string(body, "return_url"),
            )
            return "201 Created", session.to_dict(), []
        if path == "/v1/audit" and method == "GET":
            self.control.require(principal, "audit:read")
            limit = self._limit(query, default=100)
            return (
                "200 OK",
                {"items": self.control.audit_events(principal.tenant_id, limit=limit)},
                [],
            )
        raise ApiError("404 Not Found", "route_not_found", "route not found")

    def _principal(self, environ: Mapping[str, Any]) -> ApiPrincipal:
        header = str(environ.get("HTTP_AUTHORIZATION") or "")
        scheme, separator, token = header.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            raise AuthenticationError("invalid API credential")
        return self.control.authenticate(token)

    def _store(self, principal: ApiPrincipal, name: str = "default") -> GraphStore:
        mount = self.control.graph_mount(principal.tenant_id, name)
        return GraphStore(mount.store_root)

    def _index(self, principal: ApiPrincipal, query: Mapping[str, list[str]]):
        epoch = self._optional(query, "epoch")
        graph = self._optional(query, "graph") or "default"
        if graph == "all":
            raise ApiError(
                "400 Bad Request",
                "federation_not_supported",
                "this route requires one graph mount rather than graph=all",
            )
        return self._store(principal, graph).index(epoch)

    def _federated_index(self, principal: ApiPrincipal):
        from .federation import FederatedGraphIndex, MountedGraphIndex

        mounts = self.control.list_graph_mounts(principal.tenant_id)
        if len(mounts) > self.config.max_federated_graphs:
            raise ApiError(
                "422 Unprocessable Entity",
                "federation_limit",
                "tenant exceeds the bounded federation limit; build a materialized serving projection",
            )
        indexes = []
        for mount in mounts:
            store = GraphStore(mount.store_root)
            try:
                epoch_id = store.current_epoch_id()
                indexes.append(
                    MountedGraphIndex(mount.name, epoch_id, store.index(epoch_id))
                )
            except FileNotFoundError:
                continue
        if not indexes:
            raise FileNotFoundError("no graph mount has a published epoch")
        return FederatedGraphIndex(indexes)

    def _graphs(self, principal: ApiPrincipal) -> Mapping[str, Any]:
        items = []
        for mount in self.control.list_graph_mounts(principal.tenant_id):
            store = GraphStore(mount.store_root)
            epochs = store.list_epochs()
            items.append(
                {"mount": mount, "epochs": epochs, "ready": bool(epochs["current"])}
            )
        return {"items": items, "count": len(items)}

    def _search(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        text = self._required(query, "q")
        limit = self._limit(query, default=20)
        entity_kind = self._optional(query, "kind")
        mode = self._optional(query, "mode") or "hybrid"
        graph = self._optional(query, "graph") or "default"
        if graph == "all":
            index = self._federated_index(principal)
            epoch_scope: Any = index.epochs
        else:
            store = self._store(principal, graph)
            epoch_scope = self._optional(query, "epoch") or store.current_epoch_id()
            index = store.index(epoch_scope)
        facet_filters = self._filters(query.get("filter", []))
        lanes: tuple[str, ...] = ()
        if mode == "hybrid":
            lane_values = query.get("lane", [])
            lanes = tuple(
                item
                for value in lane_values
                for item in value.split(",")
                if item
            ) or ("exact", "lexical", "blocking", "vector")
        strategy_value = self._optional(query, "strategy") or "auto"
        try:
            strategy = SearchStrategy(strategy_value)
        except ValueError as exc:
            raise ApiError(
                "400 Bad Request",
                "invalid_strategy",
                "strategy must be fast, balanced, deep, or auto",
            ) from exc
        minimum_candidates_value = self._optional(query, "minimum_candidates")
        try:
            minimum_candidates = (
                int(minimum_candidates_value) if minimum_candidates_value else 8
            )
        except ValueError as exc:
            raise ApiError(
                "400 Bad Request",
                "invalid_minimum_candidates",
                "minimum_candidates must be an integer",
            ) from exc
        if not 1 <= minimum_candidates <= 1000:
            raise ApiError(
                "400 Bad Request",
                "invalid_minimum_candidates",
                "minimum_candidates must be between 1 and 1000",
            )
        cursor_scope = {
            "route": "search",
            "query": text,
            "entity_kind": entity_kind,
            "mode": mode,
            "graph": graph,
            "epoch": epoch_scope,
            "facets": facet_filters,
            "lanes": lanes,
            "strategy": strategy.value,
            "minimum_candidates": minimum_candidates,
        }
        cursor_value = self._optional(query, "cursor")
        try:
            offset = decode_cursor(cursor_value, cursor_scope) if cursor_value else 0
        except CursorError as exc:
            raise ApiError("400 Bad Request", "invalid_cursor", str(exc)) from exc
        if offset >= 1000:
            raise ApiError(
                "400 Bad Request", "cursor_depth_exceeded", "search cursor depth is bounded to 1000"
            )
        fetch_limit = min(1000, offset + limit + 1)
        waterfall = None
        if mode == "lexical":
            candidates = index.search_entities(
                text, entity_kind=entity_kind, limit=fetch_limit
            )
        elif mode == "hybrid":
            candidates = index.hybrid_search(
                text,
                entity_kind=entity_kind,
                facets=facet_filters,
                lanes=lanes,
                limit=fetch_limit,
                explain=self._boolean(query, "explain", default=True),
            )
        elif mode == "adaptive":
            if graph == "all":
                raise ApiError(
                    "400 Bad Request",
                    "adaptive_federation_not_supported",
                    "adaptive structural expansion currently requires one graph mount",
                )
            waterfall = PrimitiveSearchService(index).search(
                PrimitiveSearchRequest(
                    text,
                    strategy,
                    limit=fetch_limit,
                    minimum_candidates=minimum_candidates,
                    entity_kind=entity_kind,
                    facets=facet_filters,
                    allow_semantic=self._boolean(query, "semantic", default=True),
                    allow_structural=self._boolean(query, "structural", default=True),
                )
            )
            candidates = list(waterfall.items)
        else:
            raise ApiError(
                "400 Bad Request",
                "invalid_mode",
                "mode must be lexical, hybrid, or adaptive",
            )
        items = candidates[offset : offset + limit]
        has_more = len(candidates) > offset + limit
        next_cursor = (
            encode_cursor(cursor_scope, offset + limit) if has_more else None
        )
        response: dict[str, Any] = {
            "items": items,
            "count": len(items),
            "graph": graph,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "next_cursor": next_cursor,
                "maximum_depth": 1000,
            },
        }
        if graph == "all":
            response["epochs"] = index.epochs
        else:
            response["epoch_id"] = epoch_scope
        if waterfall is not None:
            response["search_waterfall"] = {
                "query_digest": waterfall.query_digest,
                "strategy": waterfall.strategy.value,
                "stages": [item.to_dict() for item in waterfall.stages],
                "escalated": waterfall.escalated,
                "stop_reason": waterfall.stop_reason,
            }
        return response

    def _context(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        include_source = self._boolean(query, "source", default=False)
        if include_source:
            self.control.require(principal, "source:read")
        graph = self._optional(query, "graph") or "default"
        index = (
            self._federated_index(principal)
            if graph == "all"
            else self._index(principal, query)
        )
        result = index.context(
            self._required(query, "q"),
            limit=self._limit(query, default=5),
            include_source=include_source,
            facets=self._filters(query.get("filter", [])),
        )
        result["graph"] = graph
        return result

    def _entity(
        self,
        principal: ApiPrincipal,
        identifier: str,
        query: Mapping[str, list[str]],
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        record = self._index(principal, query).resolve_entity(identifier)
        if record is None:
            raise LookupError(f"entity not found: {identifier}")
        return record

    def _neighbors(
        self,
        principal: ApiPrincipal,
        identifier: str,
        query: Mapping[str, list[str]],
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        index = self._index(principal, query)
        entity = index.resolve_entity(identifier)
        if entity is None:
            raise LookupError(f"entity not found: {identifier}")
        items = index.neighbors(
            entity["identity"]["id"],
            direction=self._optional(query, "direction") or "both",
            predicate=self._optional(query, "predicate"),
            limit=self._limit(query, default=100),
        )
        return {"entity": entity, "items": items, "count": len(items)}

    def _structurally_similar(
        self,
        principal: ApiPrincipal,
        identifier: str,
        query: Mapping[str, list[str]],
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        items = self._index(principal, query).structurally_similar(
            identifier, limit=self._limit(query, default=50)
        )
        return {"items": items, "count": len(items)}

    def _edges(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        items = self._index(principal, query).search_edges(
            predicate=self._optional(query, "predicate"),
            text=self._optional(query, "q"),
            limit=self._limit(query, default=50),
        )
        return {"items": items, "count": len(items)}

    def _edge(
        self,
        principal: ApiPrincipal,
        assertion_id: str,
        query: Mapping[str, list[str]],
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        record = self._index(principal, query).edge_record(assertion_id)
        if record is None:
            raise LookupError(f"edge assertion not found: {assertion_id}")
        return record

    def _representations(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "graph:read")
        index = self._index(principal, query)
        identifier = self._optional(query, "subject")
        subject_kind = self._optional(query, "subject_kind") or "entity"
        if identifier is None:
            representation_key = self._optional(query, "key")
            text = self._optional(query, "q")
            if representation_key is None and text is None:
                raise ApiError(
                    "400 Bad Request",
                    "missing_parameter",
                    "subject or a metadata key/text query is required",
                )
            items = index.search_representations(
                representation_key=representation_key,
                text=text,
                subject_kind=self._optional(query, "subject_kind"),
                limit=self._limit(query, default=100),
            )
            return {"items": items, "count": len(items)}
        if subject_kind == "entity":
            entity = index.resolve_entity(identifier)
            if entity is None:
                raise LookupError(f"entity not found: {identifier}")
            subject_id = entity["identity"]["id"]
        elif subject_kind == "snapshot" and identifier == "current":
            subject_id = index.metadata()["snapshot_id"]
        else:
            subject_id = identifier
        items = index.representations(
            subject_kind, subject_id, limit=self._limit(query, default=100)
        )
        return {"items": items, "count": len(items), "subject_id": subject_id}

    def _submit_job(
        self, principal: ApiPrincipal, environ: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "jobs:write")
        body = self._json_body(environ)
        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise ApiError("400 Bad Request", "invalid_payload", "payload must be an object")
        try:
            kind = JobKind(str(body.get("kind", "extract")))
        except ValueError as exc:
            raise ApiError("400 Bad Request", "invalid_job_kind", "unsupported job kind") from exc
        if kind not in {JobKind.ACQUIRE, JobKind.EXTRACT, JobKind.INDEX}:
            raise ApiError(
                "400 Bad Request",
                "unsupported_job_kind",
                "network submissions currently support acquire, extract, and index jobs",
            )
        operation = payload.get("operation")
        try:
            contract = self.pipeline_catalog.operation(operation)
        except ValueError as exc:
            raise ApiError("400 Bad Request", "unsupported_operation", "unsupported job operation")
        if kind not in contract.allowed_kinds:
            raise ApiError("400 Bad Request", "kind_operation_mismatch", "job kind does not match its operation")
        if kind is JobKind.ACQUIRE:
            self.control.require(principal, "ingestion:write")
        if operation == "generate_primitive_candidates":
            self.control.require(principal, "registry:write")
        idempotency_key = body.get("idempotency_key")
        subject_id = body.get("subject_id")
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ApiError(
                "400 Bad Request", "missing_idempotency_key", "idempotency_key is required"
            )
        if not isinstance(subject_id, str) or not subject_id:
            raise ApiError("400 Bad Request", "missing_subject", "subject_id is required")
        queue_name = str(body.get("queue") or "default")
        capabilities = self._string_list(body.get("required_capabilities", []))
        try:
            required = set(contract.capabilities_for(payload))
        except ValueError as exc:
            raise ApiError("400 Bad Request", "invalid_operation_payload", str(exc)) from exc
        missing_capabilities = sorted(required - set(capabilities))
        if missing_capabilities:
            raise ApiError(
                "400 Bad Request",
                "missing_capability",
                "required_capabilities must include: " + ", ".join(missing_capabilities),
            )
        priority = int(body.get("priority", 50))
        max_attempts = int(body.get("max_attempts", 3))
        created_at = utc_now()
        payload_ref = self.control.put_job_payload(
            principal.tenant_id, payload, created_at=created_at
        )
        existing = self.jobs.find_by_idempotency(
            principal.tenant_id,
            queue=queue_name,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            previous = existing.job
            if (
                previous.kind is not kind
                or previous.subject_id != subject_id
                or previous.payload_ref != payload_ref
                or previous.priority != priority
                or previous.max_attempts != max_attempts
                or previous.required_capabilities != tuple(sorted(set(capabilities)))
            ):
                raise ApiError(
                    "409 Conflict",
                    "idempotency_conflict",
                    "idempotency key already describes a different job",
                )
            return self._stored_job(existing)
        job = WorkerJob.create(
            queue=queue_name,
            kind=kind,
            subject_id=subject_id,
            payload_ref=payload_ref,
            idempotency_key=idempotency_key,
            created_at=created_at,
            priority=priority,
            max_attempts=max_attempts,
            required_capabilities=capabilities,
        )
        accepted = self.jobs.enqueue(principal.tenant_id, job)
        return self._stored_job(self.jobs.get(principal.tenant_id, accepted.identity.id))

    def _list_jobs(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "jobs:read")
        state_value = self._optional(query, "state")
        state = JobState(state_value) if state_value else None
        items = self.jobs.list(
            principal.tenant_id,
            queue=self._optional(query, "queue"),
            state=state,
            limit=self._limit(query, default=100),
        )
        return {"items": [self._stored_job(item) for item in items], "count": len(items)}

    def _job(self, principal: ApiPrincipal, job_id: str) -> Mapping[str, Any]:
        self.control.require(principal, "jobs:read")
        stored = self.jobs.get(principal.tenant_id, job_id)
        result = self._stored_job(stored)
        result["events"] = self.jobs.events(principal.tenant_id, job_id)
        return result

    def _cancel_job(
        self, principal: ApiPrincipal, job_id: str
    ) -> Mapping[str, Any]:
        self.control.require(principal, "jobs:write")
        if not job_id:
            raise ApiError("400 Bad Request", "missing_job", "job ID is required")
        event = self.jobs.request_cancel(
            principal.tenant_id,
            job_id,
            occurred_at=utc_now(),
            actor=f"api-key:{principal.key_id}",
        )
        result = self._stored_job(self.jobs.get(principal.tenant_id, job_id))
        result["cancellation_event"] = event
        return result

    def _list_candidates(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "registry:read")
        state_value = self._optional(query, "state")
        try:
            state = CandidateState(state_value) if state_value else None
        except ValueError as exc:
            raise ApiError(
                "400 Bad Request", "invalid_candidate_state", "candidate state is invalid"
            ) from exc
        items = self.candidates.list(
            principal.tenant_id,
            state=state,
            query=self._optional(query, "q"),
            limit=self._limit(query, default=100),
        )
        return {"items": items, "count": len(items)}

    def _start_session(
        self, principal: ApiPrincipal, environ: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "sessions:write")
        body = self._json_body(environ)
        harness_value = body.get("harness")
        if not isinstance(harness_value, dict):
            raise ApiError("400 Bad Request", "invalid_harness", "harness must be an object")
        try:
            privacy_mode = PromptPrivacyMode(self._body_string(body, "privacy_mode"))
            harness = HarnessRef(
                self._body_string(harness_value, "id"),
                self._body_string(harness_value, "version"),
                self._body_string(harness_value, "config_digest"),
                self._body_string(harness_value, "interface"),
            )
        except ValueError as exc:
            raise ApiError(
                "400 Bad Request", "invalid_session", "session harness or privacy mode is invalid"
            ) from exc
        session = PromptSession.create(
            tenant_id=principal.tenant_id,
            workspace_id=self._body_string(body, "workspace_id"),
            repository_snapshot_id=self._body_string(body, "repository_snapshot_id"),
            harness=harness,
            policy_digest=self._body_string(body, "policy_digest"),
            privacy_mode=privacy_mode,
            started_at=self._body_string(body, "started_at"),
        )
        event = self.sessions.start(session, actor=f"api-key:{principal.key_id}")
        return {"session": session, "event": event}

    def _list_sessions(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "sessions:read")
        items = self.sessions.list(
            principal.tenant_id,
            workspace_id=self._optional(query, "workspace"),
            limit=self._limit(query, default=100),
        )
        return {"items": items, "count": len(items)}

    def _session_route(
        self,
        principal: ApiPrincipal,
        method: str,
        tail: str,
        environ: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any], list[tuple[str, str]]]:
        parts = [unquote(item) for item in tail.split("/") if item]
        if len(parts) not in {1, 2}:
            raise ApiError("404 Not Found", "route_not_found", "session route not found")
        session_id = parts[0]
        action = parts[1] if len(parts) == 2 else None
        if method == "GET" and action is None:
            self.control.require(principal, "sessions:read")
            return "200 OK", self.sessions.get(principal.tenant_id, session_id), []
        if method == "POST" and action == "events":
            self.control.require(principal, "sessions:write")
            body = self._json_body(environ)
            try:
                event_kind = SessionEventKind(self._body_string(body, "event_kind"))
            except ValueError as exc:
                raise ApiError(
                    "400 Bad Request", "invalid_session_event", "session event kind is invalid"
                ) from exc
            if event_kind is SessionEventKind.SESSION_STARTED:
                raise ApiError(
                    "400 Bad Request",
                    "invalid_session_event",
                    "session_started is created by the session start endpoint",
                )
            expected = body.get("expected_sequence")
            if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 1:
                raise ApiError(
                    "400 Bad Request",
                    "invalid_expected_sequence",
                    "expected_sequence must be an integer greater than 1",
                )
            attributes = body.get("attributes", {})
            if not isinstance(attributes, dict):
                raise ApiError(
                    "400 Bad Request", "invalid_attributes", "attributes must be an object"
                )
            event = self.sessions.record(
                principal.tenant_id,
                session_id,
                event_kind,
                actor=f"api-key:{principal.key_id}",
                occurred_at=self._body_string(body, "occurred_at"),
                input_refs=self._string_list(body.get("input_refs", [])),
                output_refs=self._string_list(body.get("output_refs", [])),
                attributes=attributes,
                expected_sequence=expected,
            )
            return (
                "201 Created",
                {
                    "event": event,
                    "session": self.sessions.get(principal.tenant_id, session_id),
                },
                [],
            )
        raise ApiError("404 Not Found", "route_not_found", "session route not found")

    def _candidate_route(
        self,
        principal: ApiPrincipal,
        method: str,
        tail: str,
        query: Mapping[str, list[str]],
        environ: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any], list[tuple[str, str]]]:
        parts = [unquote(item) for item in tail.split("/") if item]
        if len(parts) not in {1, 2}:
            raise ApiError("404 Not Found", "route_not_found", "candidate route not found")
        submission_id = parts[0]
        action = parts[1] if len(parts) == 2 else None
        if method == "GET" and action is None:
            self.control.require(principal, "registry:read")
            return "200 OK", self.candidates.get(principal.tenant_id, submission_id), []
        if method == "GET" and action == "pack":
            self.control.require(principal, "registry:read")
            candidate = self.candidates.get(principal.tenant_id, submission_id)
            role_values = tuple(
                item
                for value in query.get("role", [])
                for item in value.split(",")
                if item
            )
            try:
                roles = tuple(CapsuleRole(item) for item in role_values) or None
            except ValueError as exc:
                raise ApiError(
                    "400 Bad Request", "invalid_pack_role", "pack role is invalid"
                ) from exc
            revision_id = str(candidate["submission"]["revision_id"])
            pack, encoded = self.primitives.pack_revision(
                principal.tenant_id,
                revision_id,
                include_roles=roles,
                have_digests=query.get("have", []),
                include_history=self._boolean(query, "history", default=False),
            )
            return (
                "200 OK",
                {
                    "submission_id": submission_id,
                    "pack": pack,
                    "encoding": "base64",
                    "media_type": "application/vnd.taedri.primitive-pack",
                    "encoded_size_bytes": len(encoded),
                    "content_base64": base64.b64encode(encoded).decode("ascii"),
                },
                [],
            )
        if method == "POST" and action == "transition":
            self.control.require(principal, "registry:write")
            body = self._json_body(environ)
            try:
                state = CandidateState(self._body_string(body, "to_state"))
            except ValueError as exc:
                raise ApiError(
                    "400 Bad Request", "invalid_candidate_state", "candidate state is invalid"
                ) from exc
            if state not in {
                CandidateState.CURATED_CANDIDATE,
                CandidateState.REJECTED,
                CandidateState.REVOKED,
            }:
                raise ApiError(
                    "400 Bad Request",
                    "invalid_review_transition",
                    "review API only accepts curated_candidate, rejected, or revoked; release requires the executable primitive gate",
                )
            event = self.candidates.transition(
                principal.tenant_id,
                submission_id,
                state,
                actor=f"api-key:{principal.key_id}",
                occurred_at=utc_now(),
                reason=self._body_string(body, "reason"),
                evidence_ids=self._string_list(body.get("evidence_ids", [])),
                policy_decision_id=self._optional_body_string(
                    body, "policy_decision_id"
                ),
            )
            return (
                "200 OK",
                {
                    "event": event,
                    "candidate": self.candidates.get(
                        principal.tenant_id, submission_id
                    ),
                },
                [],
            )
        raise ApiError("404 Not Found", "route_not_found", "candidate route not found")

    def _stage_primitive(
        self, principal: ApiPrincipal, environ: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "registry:write")
        body = self._json_body(environ)
        namespace = self._body_string(body, "namespace")
        name = self._body_string(body, "name")
        contract_path = self._body_string(body, "contract_path")
        ref_name = str(body.get("ref_name") or "main")
        try:
            ref_kind = RefKind(str(body.get("ref_kind") or "branch"))
        except ValueError as exc:
            raise ApiError(
                "400 Bad Request", "invalid_ref_kind", "ref_kind must be branch or tag"
            ) from exc
        expected = body.get("expected_revision_id")
        if expected is not None and (not isinstance(expected, str) or not expected):
            raise ApiError(
                "400 Bad Request",
                "invalid_expected_revision",
                "expected_revision_id must be null or a non-empty string",
            )
        parent_value = body.get("parent_revision_ids")
        parents = None if parent_value is None else self._string_list(parent_value)
        files_value = body.get("files")
        if not isinstance(files_value, list):
            raise ApiError("400 Bad Request", "invalid_files", "files must be a list")
        files: list[PrimitiveFileInput] = []
        for index, value in enumerate(files_value):
            if not isinstance(value, dict):
                raise ApiError(
                    "400 Bad Request", "invalid_file", f"files[{index}] must be an object"
                )
            try:
                role = CapsuleRole(str(value.get("role", "")))
            except ValueError as exc:
                raise ApiError(
                    "400 Bad Request", "invalid_file_role", f"files[{index}] has an invalid role"
                ) from exc
            encoded = value.get("content_base64")
            if not isinstance(encoded, str) or not encoded:
                raise ApiError(
                    "400 Bad Request",
                    "invalid_file_content",
                    f"files[{index}].content_base64 is required",
                )
            try:
                content = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ApiError(
                    "400 Bad Request",
                    "invalid_file_content",
                    f"files[{index}] is not valid base64",
                ) from exc
            files.append(
                PrimitiveFileInput(
                    self._body_string(value, "path"),
                    role,
                    self._body_string(value, "media_type"),
                    content,
                    str(value.get("mode") or "100644"),
                )
            )
        evidence = self._string_list(body.get("evidence_ids", []))
        policy_decision_id = self._body_string(body, "policy_decision_id")
        assurance_level = str(body.get("assurance_level") or "bootstrap")
        if assurance_level not in {"bootstrap", "standard", "high_assurance"}:
            raise ApiError(
                "400 Bad Request",
                "invalid_assurance_level",
                "assurance_level must be bootstrap, standard, or high_assurance",
            )
        staged = self.primitives.stage(
            principal.tenant_id,
            namespace=namespace,
            name=name,
            files=files,
            contract_path=contract_path,
            ref_kind=ref_kind,
            ref_name=ref_name,
            expected_revision_id=expected,
            actor=f"api-key:{principal.key_id}",
            created_at=utc_now(),
            message=self._body_string(body, "message"),
            graph_epoch_id=self._optional_body_string(body, "graph_epoch_id"),
            parent_revision_ids=parents,
            generation_run_id=self._optional_body_string(body, "generation_run_id"),
            evidence_ids=evidence,
        )
        verification_payload = {
            "operation": "verify_primitive_release",
            "revision_id": staged.revision.identity.id,
            "ref_kind": ref_kind.value,
            "ref_name": ref_name,
            "authorizer_id": f"api-key:{principal.key_id}",
            "policy_decision_id": policy_decision_id,
            "assurance_level": assurance_level,
        }
        created_at = utc_now()
        payload_ref = self.control.put_job_payload(
            principal.tenant_id, verification_payload, created_at=created_at
        )
        job = WorkerJob.create(
            queue="default",
            kind=JobKind.VERIFY,
            subject_id=staged.revision.identity.id,
            payload_ref=payload_ref,
            idempotency_key="primitive-release:" + staged.revision.identity.id,
            created_at=created_at,
            priority=90,
            max_attempts=1,
            required_capabilities=("primitive-release-v1",),
        )
        accepted = self.jobs.enqueue(principal.tenant_id, job)
        return {
            "staged": staged,
            "publicly_queryable": False,
            "verification_job": self._stored_job(
                self.jobs.get(principal.tenant_id, accepted.identity.id)
            ),
        }

    def _list_primitives(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "registry:read")
        items = self.primitives.list(
            principal.tenant_id,
            query=self._optional(query, "q"),
            limit=self._limit(query, default=100),
        )
        return {"items": items, "count": len(items)}

    def _primitive_route(
        self,
        principal: ApiPrincipal,
        method: str,
        tail: str,
        query: Mapping[str, list[str]],
        environ: Mapping[str, Any],
    ) -> tuple[str, Mapping[str, Any], list[tuple[str, str]]]:
        parts = [unquote(item) for item in tail.split("/") if item]
        if len(parts) not in {2, 3}:
            raise ApiError("404 Not Found", "route_not_found", "primitive route not found")
        namespace, name = parts[:2]
        action = parts[2] if len(parts) == 3 else None
        if method == "GET" and action is None:
            self.control.require(principal, "registry:read")
            return (
                "200 OK",
                self.primitives.get(
                    principal.tenant_id,
                    namespace,
                    name,
                    ref_kind=self._ref_kind(query),
                    ref_name=self._optional(query, "ref") or "main",
                ),
                [],
            )
        if method == "GET" and action == "pack":
            self.control.require(principal, "registry:read")
            role_values = tuple(
                item
                for value in query.get("role", [])
                for item in value.split(",")
                if item
            )
            try:
                roles = tuple(CapsuleRole(item) for item in role_values) or None
            except ValueError as exc:
                raise ApiError(
                    "400 Bad Request", "invalid_pack_role", "pack role is invalid"
                ) from exc
            pack, encoded = self.primitives.pack(
                principal.tenant_id,
                namespace,
                name,
                ref_kind=self._ref_kind(query),
                ref_name=self._optional(query, "ref") or "main",
                include_roles=roles,
                have_digests=query.get("have", []),
                include_history=self._boolean(query, "history", default=False),
            )
            return (
                "200 OK",
                {
                    "pack": pack,
                    "encoding": "base64",
                    "media_type": "application/vnd.taedri.primitive-pack",
                    "encoded_size_bytes": len(encoded),
                    "content_base64": base64.b64encode(encoded).decode("ascii"),
                },
                [],
            )
        if method == "POST" and action == "fork":
            self.control.require(principal, "registry:write")
            body = self._json_body(environ)
            source = self.primitives.get(
                principal.tenant_id,
                namespace,
                name,
                ref_kind=self._ref_kind(query),
                ref_name=self._optional(query, "ref") or "main",
            )
            forked = self.primitives.fork(
                principal.tenant_id,
                source_revision_id=source["revision"].identity.id,
                target_namespace=self._body_string(body, "target_namespace"),
                target_name=self._body_string(body, "target_name"),
                branch_name=str(body.get("branch_name") or "main"),
                actor=f"api-key:{principal.key_id}",
                created_at=utc_now(),
                message=self._body_string(body, "message"),
            )
            return "201 Created", {"forked": forked}, []
        if method == "POST" and action == "revoke":
            self.control.require(principal, "registry:write")
            body = self._json_body(environ)
            source = self.primitives.get(
                principal.tenant_id,
                namespace,
                name,
                ref_kind=self._ref_kind(query),
                ref_name=self._optional(query, "ref") or "main",
            )
            release = source.get("release")
            if not isinstance(release, Mapping):
                raise ApiError(
                    "409 Conflict", "release_missing", "primitive has no active release"
                )
            identity = release.get("identity")
            if not isinstance(identity, Mapping):
                raise ApiError(
                    "409 Conflict", "release_invalid", "active release identity is invalid"
                )
            revoked = self.primitives.revoke(
                principal.tenant_id,
                release_id=str(identity.get("id") or ""),
                actor=f"api-key:{principal.key_id}",
                policy_decision_id=self._body_string(body, "policy_decision_id"),
                reason=self._body_string(body, "reason"),
                revoked_at=utc_now(),
            )
            return "201 Created", {"revocation": revoked}, []
        raise ApiError("404 Not Found", "route_not_found", "primitive route not found")

    def _usage(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "usage:read")
        metric = self._optional(query, "metric")
        receipts = self.metering.receipts(
            principal.tenant_id,
            metric=metric,
            limit=self._limit(query, default=100),
        )
        return {
            "items": receipts,
            "count": len(receipts),
            "summary": self.metering.summary(principal.tenant_id),
        }

    def _limits(
        self, principal: ApiPrincipal, query: Mapping[str, list[str]]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "usage:read")
        revisions = self.metering.limit_history(
            principal.tenant_id,
            metric=self._optional(query, "metric"),
            limit=self._limit(query, default=100),
        )
        return {"items": revisions, "count": len(revisions)}

    def _set_limit(
        self, principal: ApiPrincipal, environ: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self.control.require(principal, "usage:write")
        body = self._json_body(environ)
        metric = self._body_string(body, "metric")
        reason = self._body_string(body, "reason")
        try:
            window_seconds = int(body["window_seconds"])
            hard_limit = int(body["hard_limit"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(
                "400 Bad Request",
                "invalid_limit",
                "window_seconds and hard_limit must be integers",
            ) from exc
        revision = self.metering.set_limit(
            principal.tenant_id,
            metric=metric,
            window_seconds=window_seconds,
            hard_limit=hard_limit,
            effective_at=self._optional_body_string(body, "effective_at"),
            actor=f"api-key:{principal.key_id}",
            reason=reason,
        )
        return revision.to_dict()

    @staticmethod
    def _ref_kind(query: Mapping[str, list[str]]) -> RefKind:
        value = TaedriAPI._optional(query, "ref_kind") or "branch"
        try:
            return RefKind(value)
        except ValueError as exc:
            raise ApiError(
                "400 Bad Request", "invalid_ref_kind", "ref_kind must be branch or tag"
            ) from exc

    @staticmethod
    def _body_string(value: Mapping[str, Any], name: str) -> str:
        item = value.get(name)
        if not isinstance(item, str) or not item:
            raise ApiError("400 Bad Request", "missing_field", f"{name} is required")
        return item

    @staticmethod
    def _optional_body_string(value: Mapping[str, Any], name: str) -> str | None:
        item = value.get(name)
        if item is None:
            return None
        if not isinstance(item, str) or not item:
            raise ApiError("400 Bad Request", "invalid_field", f"{name} must be a string")
        return item

    @staticmethod
    def _stored_job(stored: Any) -> dict[str, Any]:
        return {
            "tenant_id": stored.tenant_id,
            "job": stored.job,
            "state": stored.state.value,
            "attempts": stored.attempts,
            "active_lease": stored.active_lease,
            "cancellation_requested_at": stored.cancellation_requested_at,
        }

    def _json_body(self, environ: Mapping[str, Any]) -> dict[str, Any]:
        content_type = str(environ.get("CONTENT_TYPE") or "").split(";", 1)[0]
        if content_type != "application/json":
            raise ApiError(
                "415 Unsupported Media Type",
                "content_type",
                "request body must use application/json",
            )
        raw_length = str(environ.get("CONTENT_LENGTH") or "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ApiError("400 Bad Request", "content_length", "invalid content length") from exc
        if length <= 0 or length > self.config.max_body_bytes:
            raise ApiError(
                "413 Payload Too Large",
                "body_size",
                "request body is empty or exceeds the configured limit",
            )
        stream = environ.get("wsgi.input")
        if stream is None or not hasattr(stream, "read"):
            raise ApiError("400 Bad Request", "body_missing", "request body is unavailable")
        try:
            payload = json.loads(stream.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError("400 Bad Request", "invalid_json", "request body is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ApiError("400 Bad Request", "invalid_json", "request body must be an object")
        return payload

    def _preflight(
        self, environ: Mapping[str, Any]
    ) -> tuple[str, Mapping[str, Any], list[tuple[str, str]]]:
        origin = str(environ.get("HTTP_ORIGIN") or "")
        if not origin or origin not in self.config.cors_origins:
            raise ApiError("403 Forbidden", "cors_denied", "origin is not allowed")
        return (
            "204 No Content",
            {},
            [
                ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
                ("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Request-ID"),
                ("Access-Control-Max-Age", "600"),
            ],
        )

    @staticmethod
    def _required(query: Mapping[str, list[str]], name: str) -> str:
        value = TaedriAPI._optional(query, name)
        if value is None or not value:
            raise ApiError("400 Bad Request", "missing_parameter", f"{name} is required")
        return value

    @staticmethod
    def _optional(query: Mapping[str, list[str]], name: str) -> str | None:
        values = query.get(name)
        if not values:
            return None
        if len(values) != 1:
            raise ApiError(
                "400 Bad Request", "duplicate_parameter", f"{name} must appear once"
            )
        return values[0]

    @staticmethod
    def _limit(query: Mapping[str, list[str]], *, default: int) -> int:
        value = TaedriAPI._optional(query, "limit")
        try:
            limit = default if value is None else int(value)
        except ValueError as exc:
            raise ApiError("400 Bad Request", "invalid_limit", "limit must be an integer") from exc
        if not 1 <= limit <= 1000:
            raise ApiError("400 Bad Request", "invalid_limit", "limit must be 1..1000")
        return limit

    @staticmethod
    def _boolean(
        query: Mapping[str, list[str]], name: str, *, default: bool
    ) -> bool:
        value = TaedriAPI._optional(query, name)
        if value is None:
            return default
        if value.lower() in {"1", "true", "yes"}:
            return True
        if value.lower() in {"0", "false", "no"}:
            return False
        raise ApiError("400 Bad Request", "invalid_boolean", f"{name} must be true or false")

    @staticmethod
    def _filters(values: Iterable[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for value in values:
            key, separator, item = value.partition("=")
            if not separator or not key or not item:
                raise ApiError(
                    "400 Bad Request", "invalid_filter", "filters must use KEY=VALUE"
                )
            result[key] = item
        return result

    @staticmethod
    def _string_list(value: Any) -> tuple[str, ...]:
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            raise ApiError(
                "400 Bad Request", "invalid_string_list", "value must be a list of strings"
            )
        return tuple(value)

    @staticmethod
    def _openapi() -> Mapping[str, Any]:
        return build_openapi()


def create_app() -> TaedriAPI:
    control_db = Path(os.environ.get("TAEDRI_CONTROL_DB", ".tcg/control.sqlite"))
    origins = tuple(
        item.strip()
        for item in os.environ.get("TAEDRI_CORS_ORIGINS", "").split(",")
        if item.strip()
    )
    max_body = int(os.environ.get("TAEDRI_MAX_BODY_BYTES", "1048576"))
    request_limit = int(os.environ.get("TAEDRI_API_REQUESTS_PER_MINUTE", "600"))
    return TaedriAPI(
        ApiConfig(
            control_db=control_db,
            cors_origins=origins,
            max_body_bytes=max_body,
            api_request_limit_per_minute=request_limit,
        )
    )


def run_http_server(
    *,
    control_db: str | Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    cors_origins: Iterable[str] = (),
) -> None:
    if not 1 <= port <= 65_535:
        raise ValueError("HTTP port must be between 1 and 65535")
    application = TaedriAPI(
        ApiConfig(Path(control_db), tuple(sorted(set(cors_origins))))
    )
    with make_server(
        host,
        port,
        application,
        server_class=ThreadingWSGIServer,
        handler_class=WSGIRequestHandler,
    ) as server:
        LOGGER.info("Taedri API listening on http://%s:%s", host, port)
        server.serve_forever()
