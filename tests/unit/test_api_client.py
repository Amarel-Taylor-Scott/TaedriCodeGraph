from __future__ import annotations

import json
import base64
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping

from taedri_codegraph.api_client import (
    APIResponseError,
    TaedriClient,
    UrllibTransport,
)


class FakeTransport:
    def __init__(self, status: int = 200, payload: object | None = None):
        self.status = status
        self.payload = {"items": []} if payload is None else payload
        self.calls: list[tuple[str, str, Mapping[str, str], bytes | None]] = []

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
        self.calls.append((method, url, headers, body))
        return self.status, json.dumps(self.payload).encode("utf-8")


class APIClientTests(unittest.TestCase):
    def test_search_encodes_graph_filters_and_redacts_token(self) -> None:
        transport = FakeTransport(payload={"items": [{"native_name": "normalize"}]})
        client = TaedriClient(
            "https://api.example.test/base/",
            "tcg_secret_fixture",
            graph="all",
            transport=transport,
        )
        result = client.search(
            "normalize address",
            entity_kind="function",
            facet_filters={"license": "MIT", "runtime": "python"},
        )
        self.assertEqual(result["items"][0]["native_name"], "normalize")
        _, url, headers, _ = transport.calls[0]
        self.assertIn("/base/v1/search?", url)
        self.assertIn("graph=all", url)
        self.assertIn("filter=license%3DMIT", url)
        self.assertIn("semantic=true", url)
        self.assertIn("structural=true", url)
        self.assertIn("maximum_seed_expansions=3", url)
        self.assertEqual(headers["Authorization"], "Bearer tcg_secret_fixture")
        self.assertNotIn("tcg_secret_fixture", repr(client))

    def test_search_encodes_explicit_adaptive_lane_policies(self) -> None:
        transport = FakeTransport()
        client = TaedriClient(
            "https://api.example.test", "secret", transport=transport
        )
        client.search(
            "normalize address",
            mode="adaptive",
            allow_semantic=False,
            allow_structural=False,
            maximum_seed_expansions=0,
        )
        url = transport.calls[0][1]
        self.assertIn("semantic=false", url)
        self.assertIn("structural=false", url)
        self.assertIn("maximum_seed_expansions=0", url)

    def test_structured_api_error_does_not_leak_token(self) -> None:
        transport = FakeTransport(
            status=403,
            payload={"error": {"code": "forbidden", "message": "missing scope"}},
        )
        client = TaedriClient(
            "https://api.example.test", "highly-secret", transport=transport
        )
        with self.assertRaises(APIResponseError) as captured:
            client.me()
        self.assertEqual(captured.exception.status, 403)
        self.assertNotIn("highly-secret", str(captured.exception))

    def test_base_url_rejects_embedded_credentials(self) -> None:
        with self.assertRaisesRegex(Exception, "without credentials"):
            TaedriClient("https://user:password@example.test", "token")

    def test_credentialed_base_url_rejects_non_loopback_plaintext_http(self) -> None:
        with self.assertRaisesRegex(Exception, "HTTPS or a loopback"):
            TaedriClient("http://untrusted.example.test", "token")
        client = TaedriClient(
            "http://127.0.0.1:8000", "token", transport=FakeTransport()
        )
        self.assertIn("127.0.0.1", repr(client))

    def test_transport_does_not_forward_authorization_across_redirects(self) -> None:
        observed: list[str | None] = []

        class DestinationHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                observed.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"destination")

            do_POST = do_GET

            def log_message(self, format, *args):  # noqa: A002, ANN001
                return

        destination = ThreadingHTTPServer(("127.0.0.1", 0), DestinationHandler)
        destination_url = (
            f"http://127.0.0.1:{destination.server_address[1]}/destination"
        )

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.send_response(302)
                self.send_header("Location", destination_url)
                self.end_headers()

            def log_message(self, format, *args):  # noqa: A002, ANN001
                return

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        threads = [
            threading.Thread(target=server.serve_forever, daemon=True)
            for server in (destination, redirect)
        ]
        for thread in threads:
            thread.start()
        try:
            status, _ = UrllibTransport().request(
                "POST",
                f"http://127.0.0.1:{redirect.server_address[1]}/start",
                {"Authorization": "Bearer do-not-forward"},
                b"{}",
                timeout_seconds=2,
                max_response_bytes=1024,
            )
            self.assertEqual(status, 302)
            self.assertEqual(observed, [])
        finally:
            for server in (redirect, destination):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)

    def test_usage_and_limit_methods_keep_policy_fields_explicit(self) -> None:
        transport = FakeTransport(payload={"items": []})
        client = TaedriClient(
            "https://api.example.test", "secret", transport=transport
        )
        client.usage(metric="api.request", limit=25)
        self.assertIn("/v1/usage?", transport.calls[0][1])
        self.assertIn("metric=api.request", transport.calls[0][1])
        client.set_limit(
            metric="api.request",
            window_seconds=60,
            hard_limit=100,
            reason="approved trial",
            effective_at="2026-07-16T12:00:00Z",
        )
        method, url, _, body = transport.calls[1]
        self.assertEqual((method, url), ("POST", "https://api.example.test/v1/limits"))
        assert body is not None
        request = json.loads(body)
        self.assertEqual(request["hard_limit"], 100)
        self.assertEqual(request["reason"], "approved trial")

    def test_primitive_and_portal_methods_keep_refs_and_redirects_explicit(self) -> None:
        transport = FakeTransport(payload={"items": []})
        client = TaedriClient(
            "https://api.example.test", "secret", transport=transport
        )
        client.primitive_pack(
            "acme.tools",
            "parse address",
            roles=("source", "contract"),
            have_digests=("sha256:abc",),
            include_history=True,
        )
        url = transport.calls[0][1]
        self.assertIn("/v1/primitives/acme.tools/parse%20address/pack?", url)
        self.assertIn("role=source", url)
        self.assertIn("have=sha256%3Aabc", url)
        client.create_checkout(
            plan_ref="taedri.plan.team@1.0.0",
            return_url="https://portal.example.test/account",
        )
        self.assertEqual(transport.calls[1][0], "POST")
        body = json.loads(transport.calls[1][3] or b"{}")
        self.assertEqual(body["plan_ref"], "taedri.plan.team@1.0.0")

    def test_pack_decoder_rejects_declared_size_mismatch(self) -> None:
        content = base64.b64encode(b"pack").decode("ascii")
        with self.assertRaisesRegex(Exception, "size"):
            TaedriClient._pack_bytes(
                {"content_base64": content, "encoded_size_bytes": 999}
            )


if __name__ == "__main__":
    unittest.main()
