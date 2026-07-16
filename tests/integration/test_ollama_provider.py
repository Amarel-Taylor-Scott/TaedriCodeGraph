from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from taedri_codegraph.model_providers import (
    ChatMessage,
    ModelProviderError,
    OllamaChatProvider,
)


class FakeOllamaHandler(BaseHTTPRequestHandler):
    last_request: dict[str, object] | None = None
    last_authorization: str | None = None
    fail = False

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        type(self).last_request = json.loads(self.rfile.read(length))
        type(self).last_authorization = self.headers.get("Authorization")
        if type(self).fail:
            self.send_response(503)
            body = json.dumps({"error": "model unavailable"}).encode("utf-8")
        else:
            self.send_response(200)
            body = json.dumps(
                {
                    "model": "qwen-test:1b",
                    "created_at": "2026-07-16T18:00:00Z",
                    "message": {
                        "role": "assistant",
                        "content": "def normalize(value):\n    return value.strip()",
                    },
                    "done": True,
                    "done_reason": "stop",
                    "total_duration": 9_000_000,
                    "load_duration": 1_000_000,
                    "prompt_eval_count": 23,
                    "prompt_eval_duration": 2_000_000,
                    "eval_count": 11,
                    "eval_duration": 6_000_000,
                }
            ).encode("utf-8")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class OllamaProviderIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeOllamaHandler.fail = False
        FakeOllamaHandler.last_request = None
        FakeOllamaHandler.last_authorization = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_native_chat_request_and_usage_receipt_over_real_socket(self) -> None:
        provider = OllamaChatProvider(self.url, bearer_token="ollama-secret")
        result = provider.chat(
            "qwen-test:1b",
            (
                ChatMessage("system", "Return only Python source."),
                ChatMessage("user", "Write a text normalizer."),
            ),
            seed=41,
            temperature="0",
            max_completion_tokens=200,
            keep_alive="5m",
        )
        self.assertIn("def normalize", result.content)
        self.assertEqual(result.receipt.prompt_tokens, 23)
        self.assertEqual(result.receipt.completion_tokens, 11)
        self.assertEqual(result.receipt.total_duration_ns, 9_000_000)
        self.assertEqual(result.receipt.usage_source, "ollama-native-response")
        self.assertNotIn("ollama-secret", json.dumps(result.receipt.to_dict()))
        self.assertNotIn("ollama-secret", repr(provider))
        self.assertEqual(FakeOllamaHandler.last_authorization, "Bearer ollama-secret")
        request = FakeOllamaHandler.last_request or {}
        self.assertIs(request["stream"], False)
        self.assertEqual(request["options"]["seed"], 41)
        self.assertEqual(request["options"]["num_predict"], 200)

    def test_provider_error_is_bounded_and_secret_free(self) -> None:
        FakeOllamaHandler.fail = True
        provider = OllamaChatProvider(self.url, bearer_token="never-leak")
        with self.assertRaises(ModelProviderError) as captured:
            provider.chat("qwen-test:1b", (ChatMessage("user", "hello"),))
        self.assertIn("503", str(captured.exception))
        self.assertNotIn("never-leak", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
