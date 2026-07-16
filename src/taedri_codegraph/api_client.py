"""Dependency-free authenticated client for agents, hooks, and thin SDKs."""

from __future__ import annotations

import base64
import binascii
import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .primitives.digestion import (
    BlobCache,
    DigestionPolicy,
    DigestionReceipt,
    PrimitiveDigester,
)


class APIClientError(RuntimeError):
    """Base client error that never includes the bearer credential."""


class APIResponseError(APIClientError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"Taedri API returned {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class APITransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> tuple[int, bytes]: ...


@dataclass(frozen=True, slots=True)
class UrllibTransport:
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> tuple[int, bytes]:
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                content = response.read(max_response_bytes + 1)
                status = int(response.status)
        except HTTPError as exc:
            content = exc.read(max_response_bytes + 1)
            status = int(exc.code)
        except (URLError, TimeoutError, socket.timeout, OSError) as exc:
            raise APIClientError(f"Taedri API transport failed: {type(exc).__name__}") from exc
        if len(content) > max_response_bytes:
            raise APIClientError("Taedri API response exceeded the configured byte limit")
        return status, content


class TaedriClient:
    """Small stable SDK surface suitable for MCP and coding-harness adapters."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        graph: str = "default",
        timeout_seconds: float = 30,
        max_response_bytes: int = 32 * 1024 * 1024,
        transport: APITransport | None = None,
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise APIClientError("API base URL must be an http(s) origin without credentials")
        if not token or any(character in token for character in "\r\n"):
            raise APIClientError("a non-empty bearer token is required")
        if not graph:
            raise APIClientError("graph mount is required")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise APIClientError("client timeout and response limit must be positive")
        path = parsed.path.rstrip("/")
        self._origin = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
        self._token = token
        self.graph = graph
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.transport = transport or UrllibTransport()

    def __repr__(self) -> str:
        return f"TaedriClient(base_url={self._origin!r}, token=<redacted>, graph={self.graph!r})"

    def me(self) -> dict[str, Any]:
        return self._get("/v1/me")

    def graphs(self) -> dict[str, Any]:
        return self._get("/v1/graphs")

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        mode: str = "hybrid",
        strategy: str = "auto",
        minimum_candidates: int = 8,
        entity_kind: str | None = None,
        facet_filters: Mapping[str, str] | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [
            ("q", query),
            ("limit", limit),
            ("graph", self.graph),
            ("mode", mode),
            ("strategy", strategy),
            ("minimum_candidates", minimum_candidates),
        ]
        if entity_kind:
            parameters.append(("kind", entity_kind))
        if cursor:
            parameters.append(("cursor", cursor))
        parameters.extend(
            ("filter", f"{key}={value}")
            for key, value in sorted((facet_filters or {}).items())
        )
        return self._get("/v1/search", parameters)

    def context(
        self,
        query: str,
        *,
        limit: int = 5,
        include_source: bool = False,
        facet_filters: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [
            ("q", query),
            ("limit", limit),
            ("graph", self.graph),
            ("source", "true" if include_source else "false"),
        ]
        parameters.extend(
            ("filter", f"{key}={value}")
            for key, value in sorted((facet_filters or {}).items())
        )
        return self._get("/v1/context", parameters)

    def entity(self, identifier: str) -> dict[str, Any]:
        return self._get(
            f"/v1/entities/{quote(identifier, safe='')}", (("graph", self.graph),)
        )

    def neighbors(
        self,
        identifier: str,
        *,
        direction: str = "both",
        predicate: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [
            ("graph", self.graph),
            ("direction", direction),
            ("limit", limit),
        ]
        if predicate:
            parameters.append(("predicate", predicate))
        return self._get(
            f"/v1/entities/{quote(identifier, safe='')}/neighbors", parameters
        )

    def structurally_similar(self, identifier: str, *, limit: int = 50) -> dict[str, Any]:
        return self._get(
            f"/v1/entities/{quote(identifier, safe='')}/similar",
            (("graph", self.graph), ("limit", limit)),
        )

    def representations(self, identifier: str, *, limit: int = 100) -> dict[str, Any]:
        return self._get(
            "/v1/representations",
            (("subject", identifier), ("graph", self.graph), ("limit", limit)),
        )

    def search_metadata(
        self,
        *,
        representation_key: str | None = None,
        text: str | None = None,
        subject_kind: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [
            ("graph", self.graph),
            ("limit", limit),
        ]
        if representation_key:
            parameters.append(("key", representation_key))
        if text:
            parameters.append(("q", text))
        if subject_kind:
            parameters.append(("subject_kind", subject_kind))
        return self._get("/v1/representations", parameters)

    def candidates(
        self, *, state: str | None = None, query: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [("limit", limit)]
        if state:
            parameters.append(("state", state))
        if query:
            parameters.append(("q", query))
        return self._get("/v1/candidates", parameters)

    def job(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/v1/jobs/{quote(job_id, safe='')}")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._post(f"/v1/jobs/{quote(job_id, safe='')}/cancel", {})

    def candidate(self, submission_id: str) -> dict[str, Any]:
        return self._get(f"/v1/candidates/{quote(submission_id, safe='')}")

    def candidate_pack(
        self,
        submission_id: str,
        *,
        roles: tuple[str, ...] = (),
        have_digests: tuple[str, ...] = (),
        include_history: bool = False,
    ) -> dict[str, Any]:
        parameters: list[tuple[str, str]] = [
            ("history", "true" if include_history else "false")
        ]
        parameters.extend(("role", role) for role in roles)
        parameters.extend(("have", digest) for digest in have_digests)
        return self._get(
            f"/v1/candidates/{quote(submission_id, safe='')}/pack", parameters
        )

    def materialize_candidate(
        self,
        submission_id: str,
        target: str | Path,
        *,
        roles: tuple[str, ...] = (),
        have_digests: tuple[str, ...] = (),
        include_history: bool = False,
        cache: BlobCache | None = None,
        policy: DigestionPolicy | None = None,
    ) -> DigestionReceipt:
        response = self.candidate_pack(
            submission_id,
            roles=roles,
            have_digests=have_digests,
            include_history=include_history,
        )
        return PrimitiveDigester(policy).materialize(
            self._pack_bytes(response), target, cache=cache
        )

    def primitives(self, *, query: str | None = None, limit: int = 100) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [("limit", limit)]
        if query:
            parameters.append(("q", query))
        return self._get("/v1/primitives", parameters)

    def primitive(
        self,
        namespace: str,
        name: str,
        *,
        ref_kind: str = "branch",
        ref_name: str = "main",
    ) -> dict[str, Any]:
        return self._get(
            self._primitive_path(namespace, name),
            (("ref_kind", ref_kind), ("ref", ref_name)),
        )

    def primitive_pack(
        self,
        namespace: str,
        name: str,
        *,
        ref_kind: str = "branch",
        ref_name: str = "main",
        roles: tuple[str, ...] = (),
        have_digests: tuple[str, ...] = (),
        include_history: bool = False,
    ) -> dict[str, Any]:
        parameters: list[tuple[str, str]] = [
            ("ref_kind", ref_kind),
            ("ref", ref_name),
            ("history", "true" if include_history else "false"),
        ]
        parameters.extend(("role", role) for role in roles)
        parameters.extend(("have", digest) for digest in have_digests)
        return self._get(self._primitive_path(namespace, name) + "/pack", parameters)

    def materialize_primitive(
        self,
        namespace: str,
        name: str,
        target: str | Path,
        *,
        ref_kind: str = "branch",
        ref_name: str = "main",
        roles: tuple[str, ...] = (),
        have_digests: tuple[str, ...] = (),
        include_history: bool = False,
        cache: BlobCache | None = None,
        policy: DigestionPolicy | None = None,
    ) -> DigestionReceipt:
        response = self.primitive_pack(
            namespace,
            name,
            ref_kind=ref_kind,
            ref_name=ref_name,
            roles=roles,
            have_digests=have_digests,
            include_history=include_history,
        )
        return PrimitiveDigester(policy).materialize(
            self._pack_bytes(response), target, cache=cache
        )

    def stage_primitive(self, capsule: Mapping[str, Any]) -> dict[str, Any]:
        """Stage a complete capsule; public serving begins only after its verify job."""

        return self._post("/v1/primitives", capsule)

    def publish_primitive(self, publication: Mapping[str, Any]) -> dict[str, Any]:
        """Compatibility alias for :meth:`stage_primitive`; it does not bypass release."""

        return self.stage_primitive(publication)

    def fork_primitive(
        self,
        namespace: str,
        name: str,
        *,
        target_namespace: str,
        target_name: str,
        message: str,
        source_ref_kind: str = "branch",
        source_ref_name: str = "main",
        branch_name: str = "main",
    ) -> dict[str, Any]:
        path = self._primitive_path(namespace, name) + "/fork"
        query = urlencode(
            (("ref_kind", source_ref_kind), ("ref", source_ref_name))
        )
        return self._post(
            path + "?" + query,
            {
                "target_namespace": target_namespace,
                "target_name": target_name,
                "branch_name": branch_name,
                "message": message,
            },
        )

    def revoke_primitive(
        self,
        namespace: str,
        name: str,
        *,
        reason: str,
        policy_decision_id: str,
        ref_kind: str = "branch",
        ref_name: str = "main",
    ) -> dict[str, Any]:
        """Append a release revocation; revoked content immediately leaves serving."""

        path = (
            f"/v1/primitives/{quote(namespace, safe='')}/{quote(name, safe='')}/revoke"
            f"?{urlencode({'ref_kind': ref_kind, 'ref': ref_name})}"
        )
        return self._post(
            path,
            {"reason": reason, "policy_decision_id": policy_decision_id},
        )

    def start_session(self, session: Mapping[str, Any]) -> dict[str, Any]:
        return self._post("/v1/sessions", session)

    def session(self, session_id: str) -> dict[str, Any]:
        return self._get(f"/v1/sessions/{quote(session_id, safe='')}")

    def record_session_event(
        self, session_id: str, event: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self._post(
            f"/v1/sessions/{quote(session_id, safe='')}/events", event
        )

    def usage(self, *, metric: str | None = None, limit: int = 100) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [("limit", limit)]
        if metric:
            parameters.append(("metric", metric))
        return self._get("/v1/usage", parameters)

    def metrics(self) -> dict[str, Any]:
        return self._get("/v1/metrics")

    def limits(self, *, metric: str | None = None, limit: int = 100) -> dict[str, Any]:
        parameters: list[tuple[str, str | int]] = [("limit", limit)]
        if metric:
            parameters.append(("metric", metric))
        return self._get("/v1/limits", parameters)

    def set_limit(
        self,
        *,
        metric: str,
        window_seconds: int,
        hard_limit: int,
        reason: str,
        effective_at: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "metric": metric,
            "window_seconds": window_seconds,
            "hard_limit": hard_limit,
            "reason": reason,
        }
        if effective_at is not None:
            body["effective_at"] = effective_at
        return self._post("/v1/limits", body)

    def subscription(self) -> dict[str, Any]:
        return self._get("/v1/portal/subscription")

    def entitlements(self) -> dict[str, Any]:
        return self._get("/v1/portal/entitlements")

    def create_checkout(self, *, plan_ref: str, return_url: str) -> dict[str, Any]:
        return self._post(
            "/v1/portal/checkout",
            {"plan_ref": plan_ref, "return_url": return_url},
        )

    def create_billing_session(self, *, return_url: str) -> dict[str, Any]:
        return self._post(
            "/v1/portal/billing-session", {"return_url": return_url}
        )

    @staticmethod
    def _primitive_path(namespace: str, name: str) -> str:
        if not namespace or not name or any(character in namespace + name for character in "\r\n"):
            raise APIClientError("primitive namespace and name are required")
        return (
            f"/v1/primitives/{quote(namespace, safe='')}/{quote(name, safe='')}"
        )

    @staticmethod
    def _pack_bytes(response: Mapping[str, Any]) -> bytes:
        content = response.get("content_base64")
        if not isinstance(content, str) or not content:
            raise APIClientError("primitive pack response has no base64 content")
        try:
            encoded = base64.b64decode(content, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise APIClientError("primitive pack response contains invalid base64") from exc
        declared = response.get("encoded_size_bytes")
        if isinstance(declared, bool) or not isinstance(declared, int) or declared != len(encoded):
            raise APIClientError("primitive pack response size does not match its declaration")
        return encoded

    def _get(
        self,
        path: str,
        parameters: Any = (),
    ) -> dict[str, Any]:
        query = urlencode(parameters, doseq=True)
        return self._request("GET", path + (f"?{query}" if query else ""), None)

    def _post(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, body)

    def _request(
        self, method: str, path: str, body: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        encoded = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "taedri-codegraph-python/0.1",
        }
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, content = self.transport.request(
            method,
            self._origin + path,
            headers,
            encoded,
            timeout_seconds=self.timeout_seconds,
            max_response_bytes=self.max_response_bytes,
        )
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise APIClientError("Taedri API returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise APIClientError("Taedri API response must be a JSON object")
        if not 200 <= status < 300:
            error = value.get("error")
            if isinstance(error, Mapping):
                code = str(error.get("code") or "request_failed")
                message = str(error.get("message") or "request failed")
            else:
                code, message = "request_failed", "request failed"
            raise APIResponseError(status, code, message)
        return value
