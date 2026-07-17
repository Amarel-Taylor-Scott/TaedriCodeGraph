from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.http_api import ApiConfig, TaedriAPI
from taedri_codegraph.job_runner import JobRunner
from taedri_codegraph.primitive_capsules import decode_primitive_pack
from taedri_codegraph.primitives.bundle import load_primitive_directory
from taedri_codegraph.portal import SubscriptionState
from taedri_codegraph.saas import GraphMount, SQLiteControlPlane, Tenant, utc_now
from tests.primitive_fixtures import runtime_native_bundle
from tests.unit.test_acquisition import FakeTransport, github_archive_bytes, valid_wheel_bytes


class WSGIClient:
    def __init__(self, application: TaedriAPI):
        self.application = application

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: Mapping[str, Any] | None = None,
        origin: str | None = None,
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        route, separator, query = path.partition("?")
        content = json.dumps(body).encode("utf-8") if body is not None else b""
        environ: dict[str, Any] = {
            "REQUEST_METHOD": method,
            "PATH_INFO": route,
            "QUERY_STRING": query if separator else "",
            "CONTENT_LENGTH": str(len(content)),
            "CONTENT_TYPE": "application/json" if body is not None else "",
            "wsgi.input": io.BytesIO(content),
        }
        if token is not None:
            environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        if origin is not None:
            environ["HTTP_ORIGIN"] = origin
        response: dict[str, Any] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            response["status"] = status
            response["headers"] = dict(headers)

        raw = b"".join(self.application(environ, start_response))
        return response["status"], json.loads(raw), response["headers"]


class SaaSHTTPWorkerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        package = self.sources / "customer-package"
        package.mkdir(parents=True)
        (package / "address.py").write_text(
            "def normalize_address(value: str) -> str:\n"
            "    return ' '.join(value.lower().split())\n",
            encoding="utf-8",
        )
        self.control_path = self.root / "control.sqlite"
        self.control = SQLiteControlPlane(self.control_path)
        now = utc_now()
        self.tenant = self.control.create_tenant(
            Tenant.create(slug="customer", display_name="Customer", created_at=now)
        )
        self.control.mount_graph(
            GraphMount.create(
                tenant_id=self.tenant.identity.id,
                name="default",
                store_root=(self.root / "graph").resolve(),
                created_at=now,
            )
        )
        self.issued = self.control.issue_api_key(
            self.tenant.identity.id,
            scopes=(
                "graph:read",
                "source:read",
                "jobs:read",
                "jobs:write",
                "ingestion:write",
                "audit:read",
                "registry:read",
                "registry:write",
                "sessions:read",
                "sessions:write",
                "usage:read",
                "usage:write",
                "metrics:read",
            ),
        )
        self.graph_only = self.control.issue_api_key(
            self.tenant.identity.id, scopes=("graph:read",)
        )
        self.job_only = self.control.issue_api_key(
            self.tenant.identity.id, scopes=("jobs:write", "jobs:read")
        )
        self.registry_read_only = self.control.issue_api_key(
            self.tenant.identity.id, scopes=("registry:read",)
        )
        self.client = WSGIClient(
            TaedriAPI(
                ApiConfig(
                    self.control_path,
                    cors_origins=("http://localhost:8080",),
                )
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_authenticated_job_to_published_search_end_to_end(self) -> None:
        status, health, _ = self.client.request("GET", "/healthz")
        self.assertEqual(status, "200 OK")
        self.assertEqual(health["status"], "ok")

        status, error, _ = self.client.request("GET", "/v1/search?q=address")
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(error["error"]["code"], "authentication_required")

        job_body = {
            "kind": "extract",
            "subject_id": "customer-package@working-tree",
            "idempotency_key": "customer-package@working-tree:python-v1",
            "required_capabilities": ["python-ast"],
            "payload": {
                "operation": "analyze_python_path",
                "relative_path": "customer-package",
                "package_name": "customer_package",
                "release": "working-tree",
                "publish": True,
            },
        }
        status, accepted, _ = self.client.request(
            "POST", "/v1/jobs", token=self.issued.token, body=job_body
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(accepted["state"], "pending")
        job_id = accepted["job"]["identity"]["id"]

        status, replayed, _ = self.client.request(
            "POST", "/v1/jobs", token=self.issued.token, body=job_body
        )
        self.assertEqual(status, "202 Accepted")
        self.assertEqual(replayed["job"]["identity"]["id"], job_id)

        result = JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="integration-worker",
        ).run_once()
        self.assertTrue(result.claimed)
        self.assertEqual(result.event.event_kind.value, "succeeded")

        status, stored, _ = self.client.request(
            "GET", f"/v1/jobs/{job_id}", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(stored["state"], "succeeded")
        self.assertEqual([event["event_kind"] for event in stored["events"]], [
            "enqueued",
            "leased",
            "succeeded",
        ])

        status, search, _ = self.client.request(
            "GET",
            "/v1/search?" + urlencode({"q": "normalize address", "limit": 5}),
            token=self.issued.token,
        )
        self.assertEqual(status, "200 OK")
        self.assertTrue(search["epoch_id"].startswith("uceg:v1:graph_epoch:"))
        self.assertEqual(search["items"][0]["native_name"], "normalize_address")
        self.assertIn("query_receipt", search["items"][0])

        status, adaptive, _ = self.client.request(
            "GET",
            "/v1/search?" + urlencode(
                {
                    "q": "normalize address",
                    "limit": 5,
                    "mode": "adaptive",
                    "strategy": "auto",
                    "minimum_candidates": 3,
                }
            ),
            token=self.issued.token,
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(adaptive["search_waterfall"]["strategy"], "auto")
        self.assertEqual(
            [stage["stage"] for stage in adaptive["search_waterfall"]["stages"]],
            ["exact", "sparse", "lexical_hash_vector", "semantic", "structural"],
        )

    def test_usage_limits_are_versioned_and_api_admission_is_enforced(self) -> None:
        status, revision, _ = self.client.request(
            "POST",
            "/v1/limits",
            token=self.issued.token,
            body={
                "metric": "search.request",
                "window_seconds": 3600,
                "hard_limit": 25,
                "reason": "integration allocation",
            },
        )
        self.assertEqual(status, "201 Created")
        self.assertEqual(revision["metric"], "search.request")

        status, limits, _ = self.client.request(
            "GET", "/v1/limits?metric=search.request", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(limits["items"][0]["identity"]["id"], revision["identity"]["id"])

        status, usage, _ = self.client.request(
            "GET", "/v1/usage?metric=api.request", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertGreaterEqual(usage["count"], 3)
        self.assertEqual(usage["summary"][0]["metric"], "api.request")

        status, metrics, _ = self.client.request(
            "GET", "/v1/metrics", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(metrics["tenant_id"], self.tenant.identity.id)
        self.assertGreaterEqual(metrics["counts"]["usage_receipts"], 4)

        limited_client = WSGIClient(
            TaedriAPI(
                ApiConfig(
                    self.control_path,
                    api_request_limit_per_minute=2,
                )
            )
        )
        limited_tenant = self.control.create_tenant(
            Tenant.create(
                slug="limited",
                display_name="Limited",
                created_at=utc_now(),
            )
        )
        fresh_key = self.control.issue_api_key(
            limited_tenant.identity.id, scopes=("graph:read",)
        )
        limited_client.application.metering.set_limit(
            limited_tenant.identity.id,
            metric="api.request",
            window_seconds=60,
            hard_limit=2,
            actor="integration-test",
            reason="bounded admission test",
        )
        responses = [
            limited_client.request("GET", "/v1/me", token=fresh_key.token)
            for _ in range(3)
        ]
        self.assertEqual([item[0] for item in responses[:2]], ["200 OK", "200 OK"])
        self.assertEqual(responses[2][0], "429 Too Many Requests")
        self.assertEqual(responses[2][1]["error"]["code"], "quota_exceeded")
        self.assertEqual(responses[2][2]["Retry-After"], "60")

    def test_source_disclosure_requires_a_separate_scope(self) -> None:
        job_body = {
            "kind": "extract",
            "subject_id": "customer-package",
            "idempotency_key": "source-scope-fixture",
            "required_capabilities": ["python-ast"],
            "payload": {
                "operation": "analyze_python_path",
                "relative_path": "customer-package",
                "package_name": "customer_package",
            },
        }
        self.client.request("POST", "/v1/jobs", token=self.issued.token, body=job_body)
        JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="scope-worker",
        ).run_once()

        status, _, _ = self.client.request(
            "GET",
            "/v1/context?q=normalize+address&source=true",
            token=self.graph_only.token,
        )
        self.assertEqual(status, "403 Forbidden")
        status, context, _ = self.client.request(
            "GET",
            "/v1/context?q=normalize+address&source=true",
            token=self.issued.token,
        )
        self.assertEqual(status, "200 OK")
        self.assertIn("source", context["items"][0])

    def test_pending_job_can_be_cancelled_idempotently_before_worker_claim(self) -> None:
        body = {
            "kind": "extract",
            "subject_id": "customer-package@cancelled",
            "idempotency_key": "customer-package:cancelled",
            "required_capabilities": ["python-ast"],
            "payload": {
                "operation": "analyze_python_path",
                "relative_path": "customer-package",
                "package_name": "customer_package",
            },
        }
        status, accepted, _ = self.client.request(
            "POST", "/v1/jobs", token=self.issued.token, body=body
        )
        self.assertEqual(status, "202 Accepted")
        job_id = accepted["job"]["identity"]["id"]
        status, cancelled, _ = self.client.request(
            "POST", f"/v1/jobs/{job_id}/cancel", token=self.issued.token, body={}
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual(cancelled["cancellation_event"]["event_kind"], "cancelled")
        status, replayed, _ = self.client.request(
            "POST", f"/v1/jobs/{job_id}/cancel", token=self.issued.token, body={}
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(
            replayed["cancellation_event"]["identity"]["id"],
            cancelled["cancellation_event"]["identity"]["id"],
        )
        result = JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="cancel-worker",
        ).run_once()
        self.assertFalse(result.claimed)

    def test_cors_is_explicit_not_wildcard(self) -> None:
        status, _, headers = self.client.request(
            "GET", "/healthz", origin="http://localhost:8080"
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(
            headers["Access-Control-Allow-Origin"], "http://localhost:8080"
        )
        status, _, headers = self.client.request(
            "GET", "/healthz", origin="https://untrusted.example"
        )
        self.assertEqual(status, "200 OK")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_public_plans_and_tenant_subscription_portal_are_scope_separated(self) -> None:
        status, plans, _ = self.client.request("GET", "/v1/public/plans")
        self.assertEqual(status, "200 OK")
        self.assertEqual(plans["count"], 3)
        self.assertTrue(
            all(item["provider_price_ref"] is None for item in plans["items"])
        )

        status, _, _ = self.client.request(
            "GET", "/v1/portal/subscription", token=self.issued.token
        )
        self.assertEqual(status, "403 Forbidden")
        billing = self.control.issue_api_key(
            self.tenant.identity.id, scopes=("billing:read", "billing:write")
        )
        self.client.application.subscriptions.apply_event(
            self.tenant.identity.id,
            plan_ref="taedri.plan.team@1.0.0",
            state=SubscriptionState.ACTIVE,
            provider="fixture",
            provider_customer_ref="customer-portal",
            provider_subscription_ref="subscription-portal",
            effective_at="2026-07-16T12:30:00Z",
            source_event_id="provider-event-portal",
            source_event_digest="sha256:" + "9" * 64,
            actor="fixture-webhook",
        )
        status, account, _ = self.client.request(
            "GET", "/v1/portal/subscription", token=billing.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(account["subscription"]["state"], "active")
        self.assertTrue(
            account["entitlements"]["entitlements"][
                "taedri.entitlement.source_disclosure"
            ]
        )
        status, error, _ = self.client.request(
            "POST",
            "/v1/portal/checkout",
            token=billing.token,
            body={
                "plan_ref": "taedri.plan.team@1.0.0",
                "return_url": "http://localhost:8080/account",
            },
        )
        self.assertEqual(status, "503 Service Unavailable")
        self.assertEqual(error["error"]["code"], "billing_unavailable")

    def test_pypi_acquisition_job_is_scoped_persistent_and_searchable(self) -> None:
        job_body = {
            "kind": "acquire",
            "subject_id": "pypi:demo-pkg==1.0",
            "idempotency_key": "pypi:demo-pkg==1.0:wheel:python-v1",
            "required_capabilities": ["pypi-acquire", "python-ast"],
            "payload": {
                "operation": "ingest_pypi_wheel",
                "package": "demo-pkg",
                "version": "1.0",
                "publish": True,
            },
        }
        status, denied, _ = self.client.request(
            "POST", "/v1/jobs", token=self.job_only.token, body=job_body
        )
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("ingestion:write", denied["error"]["message"])

        status, accepted, _ = self.client.request(
            "POST", "/v1/jobs", token=self.issued.token, body=job_body
        )
        self.assertEqual(status, "202 Accepted")
        transport = FakeTransport(valid_wheel_bytes(), github_archive_bytes())
        result = JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="pypi-worker",
            allow_network_acquisition=True,
            acquisition_transport=transport,
        ).run_once()
        self.assertTrue(result.claimed)
        self.assertEqual(result.event.event_kind.value, "succeeded")
        self.assertEqual(result.event.metrics["artifact_bytes"], len(valid_wheel_bytes()))
        self.assertTrue(any(ref.startswith("sha256:") for ref in result.event.output_refs))

        status, search, _ = self.client.request(
            "GET", "/v1/search?q=normalize&limit=5", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(search["items"][0]["native_name"], "normalize")

    def test_job_operation_requires_matching_capabilities(self) -> None:
        status, error, _ = self.client.request(
            "POST",
            "/v1/jobs",
            token=self.issued.token,
            body={
                "kind": "acquire",
                "subject_id": "pypi:demo-pkg==1.0",
                "idempotency_key": "missing-capability",
                "required_capabilities": [],
                "payload": {
                    "operation": "ingest_pypi_wheel",
                    "package": "demo-pkg",
                    "version": "1.0",
                },
            },
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertEqual(error["error"]["code"], "missing_capability")

    def test_multiple_package_graphs_are_federated_with_mount_and_epoch_receipts(self) -> None:
        second = self.sources / "document-package"
        second.mkdir()
        (second / "document.py").write_text(
            "def parse_document(value: str) -> str:\n    return value.strip()\n",
            "utf-8",
        )
        self.control.mount_graph(
            GraphMount.create(
                tenant_id=self.tenant.identity.id,
                name="documents",
                store_root=(self.root / "document-graph").resolve(),
                created_at=utc_now(),
            )
        )
        jobs = [
            {
                "kind": "extract",
                "subject_id": "customer-package",
                "idempotency_key": "federation-address",
                "required_capabilities": ["python-ast"],
                "payload": {
                    "operation": "analyze_python_path",
                    "relative_path": "customer-package",
                    "package_name": "customer_package",
                    "graph": "default",
                },
            },
            {
                "kind": "extract",
                "subject_id": "document-package",
                "idempotency_key": "federation-document",
                "required_capabilities": ["python-ast"],
                "payload": {
                    "operation": "analyze_python_path",
                    "relative_path": "document-package",
                    "package_name": "document_package",
                    "graph": "documents",
                },
            },
        ]
        for body in jobs:
            status, _, _ = self.client.request(
                "POST", "/v1/jobs", token=self.issued.token, body=body
            )
            self.assertEqual(status, "202 Accepted")
        runner = JobRunner(
            self.control, source_root=self.sources, worker_id="federated-worker"
        )
        self.assertTrue(runner.run_once().claimed)
        self.assertTrue(runner.run_once().claimed)

        status, graphs, _ = self.client.request(
            "GET", "/v1/graphs", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(graphs["count"], 2)
        self.assertTrue(all(item["ready"] for item in graphs["items"]))

        status, search, _ = self.client.request(
            "GET", "/v1/search?q=value&graph=all&limit=20", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(set(search["epochs"]), {"default", "documents"})
        self.assertEqual(
            {item["graph_mount"] for item in search["items"]},
            {"default", "documents"},
        )
        self.assertTrue(
            all("federation_receipt" in item for item in search["items"])
        )

    @staticmethod
    def _primitive_body() -> dict[str, Any]:
        root = Path(__file__).resolve().parents[2]
        bundle = runtime_native_bundle(
            load_primitive_directory(root / "examples/primitives/normalize-text")
        )
        return {
            "namespace": bundle.namespace,
            "name": bundle.name,
            "contract_path": bundle.contract_path,
            "message": bundle.message,
            "policy_decision_id": bundle.policy_decision_id,
            "assurance_level": bundle.assurance_level.value,
            "files": [
                {
                    "path": item.path,
                    "role": item.role.value,
                    "media_type": item.media_type,
                    "content_base64": base64.b64encode(item.content).decode("ascii"),
                    "mode": item.mode,
                }
                for item in bundle.files
            ],
        }

    def test_primitive_registry_http_publish_resolve_pack_fork_and_restart(self) -> None:
        body = self._primitive_body()
        status, denied, _ = self.client.request(
            "POST", "/v1/primitives", token=self.registry_read_only.token, body=body
        )
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("registry:write", denied["error"]["message"])

        status, staged, _ = self.client.request(
            "POST", "/v1/primitives", token=self.issued.token, body=body
        )
        self.assertEqual(status, "202 Accepted")
        self.assertFalse(staged["publicly_queryable"])
        revision_id = staged["staged"]["revision"]["identity"]["id"]

        status, hidden, _ = self.client.request(
            "GET", "/v1/primitives?q=normalize", token=self.registry_read_only.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(hidden["count"], 0)

        verified = JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="primitive-release-worker",
            capabilities=("primitive-release-v1",),
        ).run_once()
        self.assertTrue(verified.claimed)
        self.assertEqual(verified.event.event_kind.value, "succeeded")
        self.assertEqual(verified.event.metrics["released_primitives"], 1)

        status, conflict, _ = self.client.request(
            "POST", "/v1/primitives", token=self.issued.token, body=body
        )
        self.assertEqual(status, "409 Conflict")
        self.assertEqual(conflict["error"]["code"], "registry_conflict")

        restarted = WSGIClient(TaedriAPI(ApiConfig(self.control_path)))
        status, record, _ = restarted.request(
            "GET", "/v1/primitives/taedri.core/normalize-text", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(record["revision"]["identity"]["id"], revision_id)

        status, packed, _ = restarted.request(
            "GET",
            "/v1/primitives/taedri.core/normalize-text/pack?role=source",
            token=self.registry_read_only.token,
        )
        self.assertEqual(status, "200 OK")
        manifest, payloads = decode_primitive_pack(
            base64.b64decode(packed["content_base64"], validate=True)
        )
        self.assertEqual(manifest["identity"]["id"], packed["pack"]["identity"]["id"])
        self.assertEqual(len(payloads), 1)
        self.assertIn(b"def normalize", next(iter(payloads.values())))

        status, forked, _ = restarted.request(
            "POST",
            "/v1/primitives/taedri.core/normalize-text/fork",
            token=self.issued.token,
            body={
                "target_namespace": "research",
                "target_name": "normalize-text",
                "message": "fork for an experiment",
            },
        )
        self.assertEqual(status, "201 Created")
        self.assertEqual(
            forked["forked"]["revision"]["upstream_revision_id"], revision_id
        )
        status, items, _ = restarted.request(
            "GET", "/v1/primitives?q=normalize", token=self.registry_read_only.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(items["count"], 1)
        status, _, _ = restarted.request(
            "GET", "/v1/primitives/research/normalize-text", token=self.issued.token
        )
        self.assertEqual(status, "404 Not Found")

    def test_primitive_registry_is_tenant_isolated_at_http_boundary(self) -> None:
        status, _, _ = self.client.request(
            "POST",
            "/v1/primitives",
            token=self.issued.token,
            body=self._primitive_body(),
        )
        self.assertEqual(status, "202 Accepted")
        verified = JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="tenant-release-worker",
            capabilities=("primitive-release-v1",),
        ).run_once()
        self.assertEqual(verified.event.event_kind.value, "succeeded")
        other = self.control.create_tenant(
            Tenant.create(slug="registry-other", display_name="Other", created_at=utc_now())
        )
        other_key = self.control.issue_api_key(
            other.identity.id, scopes=("registry:read",)
        )
        status, items, _ = self.client.request(
            "GET", "/v1/primitives", token=other_key.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(items["count"], 0)
        status, error, _ = self.client.request(
            "GET", "/v1/primitives/taedri.core/normalize-text", token=other_key.token
        )
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(error["error"]["code"], "not_found")

    def test_released_primitive_revocation_removes_every_public_serving_path(self) -> None:
        status, _, _ = self.client.request(
            "POST", "/v1/primitives", token=self.issued.token, body=self._primitive_body()
        )
        self.assertEqual(status, "202 Accepted")
        verified = JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="revocation-release-worker",
            capabilities=("primitive-release-v1",),
        ).run_once()
        self.assertEqual(verified.event.event_kind.value, "succeeded")
        status, revoked, _ = self.client.request(
            "POST",
            "/v1/primitives/taedri.core/normalize-text/revoke",
            token=self.issued.token,
            body={
                "reason": "integration revocation exercise",
                "policy_decision_id": "policy:integration-revoke-v1",
            },
        )
        self.assertEqual(status, "201 Created")
        self.assertTrue(
            revoked["revocation"]["identity"]["id"].startswith(
                "uceg:v1:primitive_release_revocation:"
            )
        )
        status, items, _ = self.client.request(
            "GET", "/v1/primitives?q=normalize", token=self.registry_read_only.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(items["count"], 0)
        status, _, _ = self.client.request(
            "GET",
            "/v1/primitives/taedri.core/normalize-text/pack",
            token=self.registry_read_only.token,
        )
        self.assertEqual(status, "404 Not Found")

    def test_factory_job_generates_reviewable_downloadable_candidates(self) -> None:
        body = {
            "kind": "extract",
            "subject_id": "customer-package@working-tree:function-candidates",
            "idempotency_key": "customer-package:candidates:v1",
            "required_capabilities": ["python-ast", "primitive-factory-v1"],
            "payload": {
                "operation": "generate_primitive_candidates",
                "relative_path": "customer-package",
                "package_name": "customer_package",
                "namespace": "customer.candidates",
                "source_uri": "mounted:customer-package",
                "source_revision": "working-tree",
                "candidate_limit": 100,
            },
        }
        status, accepted, _ = self.client.request(
            "POST", "/v1/jobs", token=self.issued.token, body=body
        )
        self.assertEqual(status, "202 Accepted")
        result = JobRunner(
            self.control,
            source_root=self.sources,
            worker_id="primitive-factory-worker",
        ).run_once()
        self.assertTrue(result.claimed)
        self.assertEqual(result.event.event_kind.value, "succeeded")
        self.assertEqual(result.event.metrics["candidate_count"], 1)

        status, candidates, _ = self.client.request(
            "GET",
            "/v1/candidates?state=indexed_candidate&q=normalize",
            token=self.registry_read_only.token,
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(candidates["count"], 1)
        submission_id = candidates["items"][0]["submission"]["identity"]["id"]

        status, packed, _ = self.client.request(
            "GET",
            f"/v1/candidates/{submission_id}/pack?role=source,contract",
            token=self.registry_read_only.token,
        )
        self.assertEqual(status, "200 OK")
        _, payloads = decode_primitive_pack(
            base64.b64decode(packed["content_base64"], validate=True)
        )
        self.assertGreaterEqual(len(payloads), 2)

        status, reviewed, _ = self.client.request(
            "POST",
            f"/v1/candidates/{submission_id}/transition",
            token=self.issued.token,
            body={
                "to_state": "curated_candidate",
                "reason": "independent contract and syntax checks passed",
                "evidence_ids": ["verify:integration"],
                "policy_decision_id": "policy:private-candidate-v1",
            },
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(reviewed["candidate"]["current_state"], "curated_candidate")
        status, public_primitives, _ = self.client.request(
            "GET", "/v1/primitives?q=normalize", token=self.registry_read_only.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(public_primitives["count"], 0)

    def test_prompt_session_api_is_private_idempotent_and_restart_safe(self) -> None:
        started_at = "2026-07-16T17:00:00Z"
        body = {
            "workspace_id": "workspace-integration",
            "repository_snapshot_id": "uceg:v1:package_snapshot:integration",
            "harness": {
                "id": "taedri.integration-harness",
                "version": "1.0.0",
                "config_digest": sha256_digest(b"integration-harness"),
                "interface": "mcp",
            },
            "policy_digest": sha256_digest(b"integration-policy"),
            "privacy_mode": "digest_only",
            "started_at": started_at,
        }
        status, denied, _ = self.client.request(
            "POST", "/v1/sessions", token=self.registry_read_only.token, body=body
        )
        self.assertEqual(status, "403 Forbidden")
        self.assertIn("sessions:write", denied["error"]["message"])

        status, started, _ = self.client.request(
            "POST", "/v1/sessions", token=self.issued.token, body=body
        )
        self.assertEqual(status, "201 Created")
        session_id = started["session"]["identity"]["id"]
        request_event = {
            "event_kind": "request_captured",
            "expected_sequence": 2,
            "occurred_at": "2026-07-16T17:00:01Z",
            "input_refs": [sha256_digest(b"find an address normalizer")],
            "attributes": {"capture": "digest_only"},
        }
        status, first, _ = self.client.request(
            "POST",
            f"/v1/sessions/{session_id}/events",
            token=self.issued.token,
            body=request_event,
        )
        self.assertEqual(status, "201 Created")
        status, replayed, _ = self.client.request(
            "POST",
            f"/v1/sessions/{session_id}/events",
            token=self.issued.token,
            body=request_event,
        )
        self.assertEqual(status, "201 Created")
        self.assertEqual(
            replayed["event"]["identity"]["id"], first["event"]["identity"]["id"]
        )
        self.assertEqual(replayed["session"]["event_count"], 2)

        prohibited = dict(request_event)
        prohibited["expected_sequence"] = 3
        prohibited["occurred_at"] = "2026-07-16T17:00:02Z"
        prohibited["attributes"] = {"nested": {"raw_prompt": "must not persist"}}
        status, error, _ = self.client.request(
            "POST",
            f"/v1/sessions/{session_id}/events",
            token=self.issued.token,
            body=prohibited,
        )
        self.assertEqual(status, "400 Bad Request")
        self.assertIn("digest-only", error["error"]["message"])

        for sequence, kind, attributes in (
            (3, "abstained", {"reason_code": "no_verified_candidate"}),
            (4, "session_closed", {}),
        ):
            status, _, _ = self.client.request(
                "POST",
                f"/v1/sessions/{session_id}/events",
                token=self.issued.token,
                body={
                    "event_kind": kind,
                    "expected_sequence": sequence,
                    "occurred_at": f"2026-07-16T17:00:0{sequence}Z",
                    "attributes": attributes,
                },
            )
            self.assertEqual(status, "201 Created")
        restarted = WSGIClient(TaedriAPI(ApiConfig(self.control_path)))
        status, stored, _ = restarted.request(
            "GET", f"/v1/sessions/{session_id}", token=self.issued.token
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(stored["event_count"], 4)
        self.assertEqual(stored["closed_at"], "2026-07-16T17:00:04Z")


if __name__ == "__main__":
    unittest.main()
