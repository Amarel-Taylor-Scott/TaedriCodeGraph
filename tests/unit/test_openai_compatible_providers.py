from __future__ import annotations

import json
import unittest

from taedri_codegraph.model_providers import (
    ChatMessage,
    MistralChatProvider,
    ModelProviderError,
    OllamaChatProvider,
    OpenAICompatibleChatProvider,
    OpenRouterChatProvider,
)


class _Transport:
    def __init__(self, status: int, value: object) -> None:
        self.status = status
        self.content = json.dumps(value).encode("utf-8")
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        method,
        url,
        headers,
        body,
        *,
        timeout_seconds,
        max_response_bytes,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": json.loads(body),
                "timeout_seconds": timeout_seconds,
                "max_response_bytes": max_response_bytes,
            }
        )
        return self.status, self.content


def _response(model: str = "vendor/model") -> dict[str, object]:
    return {
        "id": "chatcmpl-fixture",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "bounded answer"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21},
    }


class OpenAICompatibleProviderTests(unittest.TestCase):
    def test_openrouter_parses_native_usage_without_retaining_token(self) -> None:
        transport = _Transport(200, _response("openrouter/test-model"))
        provider = OpenRouterChatProvider(
            "https://openrouter.example/api/v1",
            api_token="openrouter-secret",
            timeout_seconds=12,
            max_response_bytes=4096,
            transport=transport,
        )
        result = provider.chat(
            "openrouter/test-model",
            (ChatMessage("user", "say hello"),),
            seed=7,
            temperature="0.25",
            max_completion_tokens=30,
        )
        self.assertEqual(result.content, "bounded answer")
        self.assertEqual(result.receipt.provider_id, "openrouter")
        self.assertEqual(result.receipt.provider_api, "openrouter-chat-completions-v1")
        self.assertEqual(result.receipt.usage_source, "openrouter-native-response")
        self.assertEqual(result.receipt.prompt_tokens, 17)
        self.assertEqual(result.receipt.completion_tokens, 4)
        call = transport.calls[0]
        self.assertEqual(
            call["url"], "https://openrouter.example/api/v1/chat/completions"
        )
        self.assertEqual(call["headers"]["Authorization"], "Bearer openrouter-secret")
        self.assertEqual(call["body"]["seed"], 7)
        self.assertEqual(call["body"]["max_tokens"], 30)
        self.assertEqual(call["timeout_seconds"], 12)
        self.assertEqual(call["max_response_bytes"], 4096)
        serialized = json.dumps(result.receipt.to_dict())
        self.assertNotIn("openrouter-secret", serialized)
        self.assertNotIn("openrouter-secret", repr(provider))

    def test_mistral_uses_provider_seed_field_and_native_receipt(self) -> None:
        transport = _Transport(200, _response("mistral-small-test"))
        provider = MistralChatProvider(
            "https://mistral.example/v1",
            api_token="mistral-secret",
            transport=transport,
        )
        result = provider.chat(
            "mistral-small-test",
            (ChatMessage("system", "Be concise."), ChatMessage("user", "hello")),
            seed=11,
        )
        self.assertEqual(result.receipt.provider_id, "mistral")
        self.assertEqual(result.receipt.usage_source, "mistral-native-response")
        self.assertEqual(transport.calls[0]["body"]["random_seed"], 11)
        self.assertNotIn("seed", transport.calls[0]["body"])
        self.assertNotIn("mistral-secret", json.dumps(result.receipt.to_dict()))
        self.assertNotIn("mistral-secret", repr(provider))

    def test_generic_adapter_allows_an_unauthenticated_local_endpoint(self) -> None:
        transport = _Transport(200, _response("local-compatible"))
        provider = OpenAICompatibleChatProvider(
            "http://127.0.0.1:9000/v1", transport=transport
        )
        result = provider.chat(
            "local-compatible", (ChatMessage("user", "hello"),)
        )
        self.assertEqual(result.receipt.provider_id, "openai-compatible")
        self.assertNotIn("Authorization", transport.calls[0]["headers"])

    def test_providers_reject_non_loopback_plaintext_http_origins(self) -> None:
        with self.assertRaisesRegex(ModelProviderError, "HTTPS or a loopback"):
            MistralChatProvider(
                "http://untrusted.example/v1", api_token="sensitive"
            )
        with self.assertRaisesRegex(ModelProviderError, "HTTPS or a loopback"):
            OpenRouterChatProvider(
                "http://untrusted.example/v1", api_token="sensitive"
            )
        with self.assertRaisesRegex(ModelProviderError, "HTTPS or a loopback"):
            OpenAICompatibleChatProvider("http://untrusted.example/v1")
        with self.assertRaisesRegex(ModelProviderError, "HTTPS or a loopback"):
            OllamaChatProvider(
                "http://untrusted.example", bearer_token="sensitive"
            )

    def test_provider_error_does_not_echo_remote_body_or_token(self) -> None:
        secret = "never-echo-this-token"
        transport = _Transport(
            429,
            {
                "error": {
                    "message": f"request rejected for Bearer {secret}",
                    "prompt": "private request text",
                }
            },
        )
        provider = OpenRouterChatProvider(
            "https://openrouter.example/api/v1",
            api_token=secret,
            transport=transport,
        )
        with self.assertRaises(ModelProviderError) as captured:
            provider.chat("provider/model", (ChatMessage("user", "private"),))
        message = str(captured.exception)
        self.assertIn("429", message)
        self.assertNotIn(secret, message)
        self.assertNotIn("private request text", message)


if __name__ == "__main__":
    unittest.main()
