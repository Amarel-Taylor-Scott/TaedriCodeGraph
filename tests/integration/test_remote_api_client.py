from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

from taedri_codegraph.analyzers import PythonSyntaxAnalyzer
from taedri_codegraph.api_client import APIResponseError, TaedriClient
from taedri_codegraph.http_api import ApiConfig, TaedriAPI, ThreadingWSGIServer
from taedri_codegraph.harness_receipts import RemoteSessionRecorder
from taedri_codegraph.saas import GraphMount, SQLiteControlPlane, Tenant
from taedri_codegraph.storage import GraphStore


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class RemoteAPIClientIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        source = root / "source"
        source.mkdir()
        (source / "address.py").write_text(
            "def normalize_address(value: str) -> str:\n"
            "    return ' '.join(value.split())\n\n"
            + "".join(
                f"def normalize_variant_{number}(value: str) -> str:\n"
                f"    return normalize_address(value)\n\n"
                for number in range(6)
            ),
            "utf-8",
        )
        analyzer = PythonSyntaxAnalyzer()
        bundle = analyzer.analyze(source, package_name="fixture", release="1.0")
        graph = GraphStore(root / "graph")
        epoch_id = graph.write_candidate(bundle, analyzer.registry)
        graph.publish_epoch(epoch_id)

        control_path = root / "control.sqlite"
        control = SQLiteControlPlane(control_path)
        tenant = control.create_tenant(
            Tenant.create(
                slug="remote-client",
                display_name="Remote client",
                created_at="2026-07-16T15:00:00Z",
            )
        )
        control.mount_graph(
            GraphMount.create(
                tenant_id=tenant.identity.id,
                name="default",
                store_root=(root / "graph").resolve(),
                created_at="2026-07-16T15:00:01Z",
            )
        )
        self.key = control.issue_api_key(
            tenant.identity.id,
            scopes=("graph:read", "source:read", "sessions:read", "sessions:write"),
        )
        self.server = make_server(
            "127.0.0.1",
            0,
            TaedriAPI(ApiConfig(control_path)),
            server_class=ThreadingWSGIServer,
            handler_class=QuietHandler,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def test_client_search_context_metadata_and_graph_tools_over_real_socket(self) -> None:
        client = TaedriClient(self.base_url, self.key.token)
        self.assertEqual(client.me()["tenant_id"], self.key.tenant_id)
        search = client.search("normalize address", limit=5)
        self.assertEqual(search["items"][0]["native_name"], "normalize_address")
        context = client.context("normalize address", limit=1, include_source=True)
        self.assertIn(
            "def normalize_address", context["items"][0]["source"]["source_text"]
        )
        identifier = search["items"][0]["entity_id"]
        self.assertEqual(client.entity(identifier)["identity"]["id"], identifier)
        self.assertIn("items", client.neighbors(identifier))
        self.assertIn("items", client.structurally_similar(identifier))
        metadata = client.search_metadata(text="normalize", limit=20)
        self.assertGreater(metadata["count"], 0)
        started = client.start_session(
            {
                "workspace_id": "remote-sdk-test",
                "repository_snapshot_id": "uceg:v1:package_snapshot:fixture",
                "harness": {
                    "id": "taedri.remote-sdk-test",
                    "version": "1.0.0",
                    "config_digest": "sha256:" + "a" * 64,
                    "interface": "python-sdk",
                },
                "policy_digest": "sha256:" + "b" * 64,
                "privacy_mode": "digest_only",
                "started_at": "2026-07-16T15:01:00Z",
            }
        )
        session_id = started["session"]["identity"]["id"]
        client.record_session_event(
            session_id,
            {
                "event_kind": "request_captured",
                "expected_sequence": 2,
                "occurred_at": "2026-07-16T15:01:01Z",
                "input_refs": ["sha256:" + "c" * 64],
                "attributes": {"capture": "digest_only"},
            },
        )
        self.assertEqual(client.session(session_id)["event_count"], 2)
        receipt_refs = RemoteSessionRecorder(client, session_id).record_search(
            "normalize address", search, tool_name="search_code"
        )
        self.assertEqual(len(receipt_refs), 2)
        recorded = client.session(session_id)
        self.assertEqual(recorded["event_count"], 4)
        self.assertEqual(recorded["events"][-1]["event_kind"], "search_receipt")

    def test_search_cursor_is_epoch_bound_and_pages_without_overlap(self) -> None:
        client = TaedriClient(self.base_url, self.key.token)
        first = client.search("normalize", limit=2)
        cursor = first["pagination"]["next_cursor"]
        self.assertIsInstance(cursor, str)
        second = client.search("normalize", limit=2, cursor=cursor)
        first_ids = {item["entity_id"] for item in first["items"]}
        second_ids = {item["entity_id"] for item in second["items"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertEqual(second["pagination"]["offset"], 2)
        with self.assertRaises(APIResponseError) as captured:
            client.search("different", limit=2, cursor=cursor)
        self.assertEqual(captured.exception.code, "invalid_cursor")

    def test_client_preserves_structured_authentication_failure(self) -> None:
        with self.assertRaises(APIResponseError) as captured:
            TaedriClient(self.base_url, "wrong-token").me()
        self.assertEqual(captured.exception.status, 401)
        self.assertEqual(captured.exception.code, "authentication_required")


if __name__ == "__main__":
    unittest.main()
