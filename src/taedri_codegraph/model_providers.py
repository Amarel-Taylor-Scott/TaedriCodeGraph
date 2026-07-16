"""Model-provider adapters with bounded I/O and evidence-bearing usage receipts."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit

from .api_client import APIClientError, APITransport, UrllibTransport
from .canonical import canonical_json_bytes, sha256_digest
from .contracts import RecordMixin
from .identity import IdentityRecord


class ModelProviderError(RuntimeError):
    """Raised when a model runtime response is unavailable or fails validation."""


@dataclass(frozen=True, slots=True)
class ChatMessage(RecordMixin):
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ModelProviderError(f"unsupported chat role: {self.role!r}")
        if not self.content:
            raise ModelProviderError("chat message content cannot be empty")


@dataclass(frozen=True, slots=True)
class ModelUsageReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    provider_id: str
    provider_api: str
    endpoint_origin: str
    model_requested: str
    model_reported: str
    request_digest: str
    response_digest: str
    content_digest: str
    started_at: str
    completed_at: str
    wall_ms: int
    prompt_tokens: int
    completion_tokens: int
    total_duration_ns: int | None
    load_duration_ns: int | None
    prompt_eval_duration_ns: int | None
    eval_duration_ns: int | None
    finish_reason: str | None
    usage_source: str

    @classmethod
    def create(
        cls,
        *,
        endpoint_origin: str,
        model_requested: str,
        model_reported: str,
        request_digest: str,
        response_digest: str,
        content_digest: str,
        started_at: str,
        completed_at: str,
        wall_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        total_duration_ns: int | None,
        load_duration_ns: int | None,
        prompt_eval_duration_ns: int | None,
        eval_duration_ns: int | None,
        finish_reason: str | None,
    ) -> "ModelUsageReceipt":
        if min(wall_ms, prompt_tokens, completion_tokens) < 0:
            raise ModelProviderError("model usage counters cannot be negative")
        key = {
            "format_version": "1.0.0",
            "provider_id": "ollama",
            "provider_api": "ollama-native-chat-v1",
            "endpoint_origin": endpoint_origin,
            "model_requested": model_requested,
            "model_reported": model_reported,
            "request_digest": request_digest,
            "response_digest": response_digest,
            "content_digest": content_digest,
            "started_at": started_at,
            "completed_at": completed_at,
            "wall_ms": wall_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_duration_ns": total_duration_ns,
            "load_duration_ns": load_duration_ns,
            "prompt_eval_duration_ns": prompt_eval_duration_ns,
            "eval_duration_ns": eval_duration_ns,
            "finish_reason": finish_reason,
            "usage_source": "ollama-native-response",
        }
        return cls(
            IdentityRecord.create("model_usage_receipt", key),
            "1.0.0",
            "ollama",
            "ollama-native-chat-v1",
            endpoint_origin,
            model_requested,
            model_reported,
            request_digest,
            response_digest,
            content_digest,
            started_at,
            completed_at,
            wall_ms,
            prompt_tokens,
            completion_tokens,
            total_duration_ns,
            load_duration_ns,
            prompt_eval_duration_ns,
            eval_duration_ns,
            finish_reason,
            "ollama-native-response",
        )


@dataclass(frozen=True, slots=True)
class ChatResult:
    content: str
    receipt: ModelUsageReceipt


class OllamaChatProvider:
    """Ollama native `/api/chat` adapter; streaming is disabled for exact receipts."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        *,
        bearer_token: str | None = None,
        timeout_seconds: float = 300,
        max_response_bytes: int = 16 * 1024 * 1024,
        transport: APITransport | None = None,
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ModelProviderError("Ollama URL must be an http(s) origin without credentials")
        if bearer_token is not None and (
            not bearer_token or any(character in bearer_token for character in "\r\n")
        ):
            raise ModelProviderError("Ollama bearer token is invalid")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ModelProviderError("provider timeout and response limit must be positive")
        self.origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        self._bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.transport = transport or UrllibTransport()

    def __repr__(self) -> str:
        token = "<configured>" if self._bearer_token is not None else "<none>"
        return f"OllamaChatProvider(origin={self.origin!r}, bearer_token={token})"

    def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        *,
        seed: int | None = None,
        temperature: str | None = None,
        max_completion_tokens: int | None = None,
        keep_alive: str | int | None = None,
    ) -> ChatResult:
        prepared = tuple(messages)
        if not model or not prepared:
            raise ModelProviderError("model and at least one chat message are required")
        options: dict[str, Any] = {}
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise ModelProviderError("model seed must be an integer")
            options["seed"] = seed
        if temperature is not None:
            try:
                parsed_temperature = float(temperature)
            except ValueError as exc:
                raise ModelProviderError("temperature must be a decimal string") from exc
            if not math.isfinite(parsed_temperature) or not 0 <= parsed_temperature <= 2:
                raise ModelProviderError("temperature must be between 0 and 2")
            options["temperature"] = parsed_temperature
        if max_completion_tokens is not None:
            if (
                isinstance(max_completion_tokens, bool)
                or not isinstance(max_completion_tokens, int)
                or max_completion_tokens <= 0
            ):
                raise ModelProviderError("completion token limit must be positive")
            options["num_predict"] = max_completion_tokens
        request_value: dict[str, Any] = {
            "model": model,
            "messages": [message.to_dict() for message in prepared],
            "stream": False,
        }
        if options:
            request_value["options"] = options
        if keep_alive is not None:
            request_value["keep_alive"] = keep_alive
        request_bytes = canonical_json_bytes(request_value)
        request_digest = sha256_digest(request_bytes)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._bearer_token is not None:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        started_at = _now()
        started = time.perf_counter_ns()
        try:
            status, content = self.transport.request(
                "POST",
                self.origin + "/api/chat",
                headers,
                request_bytes,
                timeout_seconds=self.timeout_seconds,
                max_response_bytes=self.max_response_bytes,
            )
        except APIClientError as exc:
            raise ModelProviderError(str(exc)) from exc
        completed = time.perf_counter_ns()
        completed_at = _now()
        try:
            value = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelProviderError("Ollama returned invalid JSON") from exc
        if not isinstance(value, Mapping):
            raise ModelProviderError("Ollama response must be an object")
        if not 200 <= status < 300:
            message = str(value.get("error") or "provider request failed")
            raise ModelProviderError(f"Ollama returned HTTP {status}: {message}")
        message = value.get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
            raise ModelProviderError("Ollama response is missing assistant content")
        assistant_content = str(message["content"])
        if not assistant_content:
            raise ModelProviderError("Ollama returned empty assistant content")
        model_reported = str(value.get("model") or "")
        if not model_reported:
            raise ModelProviderError("Ollama response is missing the model identity")
        receipt = ModelUsageReceipt.create(
            endpoint_origin=self.origin,
            model_requested=model,
            model_reported=model_reported,
            request_digest=request_digest,
            response_digest=sha256_digest(canonical_json_bytes(value)),
            content_digest=sha256_digest(assistant_content.encode("utf-8")),
            started_at=started_at,
            completed_at=completed_at,
            wall_ms=(completed - started) // 1_000_000,
            prompt_tokens=_counter(value, "prompt_eval_count"),
            completion_tokens=_counter(value, "eval_count"),
            total_duration_ns=_optional_counter(value, "total_duration"),
            load_duration_ns=_optional_counter(value, "load_duration"),
            prompt_eval_duration_ns=_optional_counter(value, "prompt_eval_duration"),
            eval_duration_ns=_optional_counter(value, "eval_duration"),
            finish_reason=_optional_text(value.get("done_reason")),
        )
        return ChatResult(assistant_content, receipt)


def _counter(value: Mapping[str, Any], name: str) -> int:
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise ModelProviderError(f"Ollama response has invalid {name}")
    return item


def _optional_counter(value: Mapping[str, Any], name: str) -> int | None:
    item = value.get(name)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise ModelProviderError(f"Ollama response has invalid {name}")
    return item


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ModelProviderError("Ollama finish reason is invalid")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
