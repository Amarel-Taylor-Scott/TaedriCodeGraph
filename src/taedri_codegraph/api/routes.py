"""Single declarative inventory for public and tenant-scoped API operations."""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import RecordMixin


@dataclass(frozen=True, slots=True)
class RouteSpec(RecordMixin):
    method: str
    path: str
    operation_id: str
    summary: str
    success_status: int
    authenticated: bool = True
    required_scope: str | None = None
    request_schema: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        method = self.method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("route method is unsupported")
        if not self.path.startswith("/") or not self.operation_id or not self.summary:
            raise ValueError("route path, operation ID, and summary are required")
        if not 200 <= self.success_status <= 299:
            raise ValueError("route success status must be 2xx")
        if not self.authenticated and self.required_scope is not None:
            raise ValueError("public route cannot require a tenant scope")
        object.__setattr__(self, "method", method)


_ROUTES = (
    RouteSpec("GET", "/healthz", "health", "Process liveness", 200, False, tags=("operations",)),
    RouteSpec("GET", "/readyz", "readiness", "Dependency readiness", 200, False, tags=("operations",)),
    RouteSpec("GET", "/v1/public/plans", "listPublicPlans", "List public plan catalog for the portal POC", 200, False, tags=("portal",)),
    RouteSpec("GET", "/v1/me", "getPrincipal", "Get current API principal", 200, tags=("identity",)),
    RouteSpec("GET", "/v1/graphs", "listGraphs", "List tenant graph mounts", 200, True, "graph:read", tags=("graph",)),
    RouteSpec("GET", "/v1/epochs", "listEpochs", "List immutable graph epochs", 200, True, "graph:read", tags=("graph",)),
    RouteSpec("GET", "/v1/search", "search", "Run explainable adaptive or hybrid search", 200, True, "graph:read", tags=("retrieval",)),
    RouteSpec("GET", "/v1/context", "getContext", "Resolve progressive code context", 200, True, "graph:read", tags=("retrieval",)),
    RouteSpec("GET", "/v1/representations", "listRepresentations", "Search typed representation variants", 200, True, "graph:read", tags=("retrieval",)),
    RouteSpec("GET", "/v1/edges", "searchEdges", "Search graph edges", 200, True, "graph:read", tags=("graph",)),
    RouteSpec("GET", "/v1/edges/{assertion_id}", "getEdge", "Get one edge assertion", 200, True, "graph:read", tags=("graph",)),
    RouteSpec("GET", "/v1/entities/{identifier}", "getEntity", "Get one graph entity", 200, True, "graph:read", tags=("graph",)),
    RouteSpec("GET", "/v1/entities/{identifier}/neighbors", "getNeighbors", "Traverse bounded graph neighbors", 200, True, "graph:read", tags=("graph",)),
    RouteSpec("GET", "/v1/entities/{identifier}/similar", "getSimilar", "Get structural similarity candidates", 200, True, "graph:read", tags=("retrieval",)),
    RouteSpec("GET", "/v1/jobs", "listJobs", "List worker jobs", 200, True, "jobs:read", tags=("workers",)),
    RouteSpec("POST", "/v1/jobs", "submitJob", "Submit an idempotent worker job", 202, True, "jobs:write", "job-submission.v1.schema.json", ("workers",)),
    RouteSpec("GET", "/v1/jobs/{job_id}", "getJob", "Get worker job and event history", 200, True, "jobs:read", tags=("workers",)),
    RouteSpec("POST", "/v1/jobs/{job_id}/cancel", "cancelJob", "Request cooperative job cancellation", 200, True, "jobs:write", tags=("workers",)),
    RouteSpec("GET", "/v1/candidates", "listCandidates", "List generated primitive candidates", 200, True, "registry:read", tags=("registry",)),
    RouteSpec("GET", "/v1/candidates/{submission_id}", "getCandidate", "Get candidate history", 200, True, "registry:read", tags=("registry",)),
    RouteSpec("GET", "/v1/candidates/{submission_id}/pack", "getCandidatePack", "Download a selective candidate pack", 200, True, "registry:read", tags=("registry",)),
    RouteSpec("POST", "/v1/candidates/{submission_id}/transition", "transitionCandidate", "Append a candidate review state", 200, True, "registry:write", tags=("registry",)),
    RouteSpec("GET", "/v1/sessions", "listSessions", "List prompt sessions", 200, True, "sessions:read", tags=("sessions",)),
    RouteSpec("POST", "/v1/sessions", "startSession", "Start a prompt session", 201, True, "sessions:write", "prompt-session-start.v1.schema.json", ("sessions",)),
    RouteSpec("GET", "/v1/sessions/{session_id}", "getSession", "Get a prompt session ledger", 200, True, "sessions:read", tags=("sessions",)),
    RouteSpec("POST", "/v1/sessions/{session_id}/events", "appendSessionEvent", "Append a prompt-session receipt", 201, True, "sessions:write", "prompt-session-append.v1.schema.json", ("sessions",)),
    RouteSpec("GET", "/v1/primitives", "listPrimitives", "List primitive handles and refs", 200, True, "registry:read", tags=("registry",)),
    RouteSpec("POST", "/v1/primitives", "stagePrimitive", "Stage a complete primitive and enqueue executable release verification", 202, True, "registry:write", "primitive-stage.v1.schema.json", ("registry",)),
    RouteSpec("GET", "/v1/primitives/{namespace}/{name}", "getPrimitive", "Resolve a primitive ref", 200, True, "registry:read", tags=("registry",)),
    RouteSpec("GET", "/v1/primitives/{namespace}/{name}/pack", "getPrimitivePack", "Download a selective thin primitive pack", 200, True, "registry:read", tags=("registry",)),
    RouteSpec("POST", "/v1/primitives/{namespace}/{name}/fork", "forkPrimitive", "Fork a primitive revision", 201, True, "registry:write", tags=("registry",)),
    RouteSpec("POST", "/v1/primitives/{namespace}/{name}/revoke", "revokePrimitive", "Append a release revocation and remove it from serving", 201, True, "registry:write", tags=("registry",)),
    RouteSpec("GET", "/v1/usage", "listUsage", "List immutable usage receipts", 200, True, "usage:read", tags=("operations",)),
    RouteSpec("GET", "/v1/metrics", "getMetrics", "Get tenant operational metrics", 200, True, "metrics:read", tags=("operations",)),
    RouteSpec("GET", "/v1/limits", "listLimits", "List quota policy revisions", 200, True, "usage:read", tags=("operations",)),
    RouteSpec("POST", "/v1/limits", "setLimit", "Append a quota policy revision", 201, True, "usage:write", tags=("operations",)),
    RouteSpec("GET", "/v1/audit", "listAudit", "List tenant audit events", 200, True, "audit:read", tags=("operations",)),
    RouteSpec("GET", "/v1/portal/subscription", "getSubscription", "Get current subscription and entitlements", 200, True, "billing:read", tags=("portal",)),
    RouteSpec("GET", "/v1/portal/entitlements", "getEntitlements", "Get active feature entitlements", 200, True, "billing:read", tags=("portal",)),
    RouteSpec("POST", "/v1/portal/checkout", "createCheckout", "Create a provider checkout redirect", 201, True, "billing:write", tags=("portal",)),
    RouteSpec("POST", "/v1/portal/billing-session", "createBillingPortal", "Create a provider account-management redirect", 201, True, "billing:write", tags=("portal",)),
)


def route_catalog() -> tuple[RouteSpec, ...]:
    keys = [(item.method, item.path) for item in _ROUTES]
    if len(keys) != len(set(keys)):  # pragma: no cover - import-time contract guard
        raise RuntimeError("duplicate API route declaration")
    return _ROUTES
