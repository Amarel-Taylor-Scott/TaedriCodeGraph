from __future__ import annotations

import json
from typing import Iterable

from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest
from taedri_codegraph.model_providers import (
    ChatMessage,
    ChatResult,
    ModelUsageReceipt,
)


class SemanticFakeChatProvider:
    """A transport-free teacher fake; it still consumes the real prompt schema."""

    def __init__(
        self,
        *,
        forced_name: str | None = None,
        forced_content: str | None = None,
    ) -> None:
        self.forced_name = forced_name
        self.forced_content = forced_content
        self.calls: list[tuple[ChatMessage, ...]] = []

    def chat(
        self,
        model: str,
        messages: Iterable[ChatMessage],
        *,
        seed: int | None = None,
        temperature: str | None = None,
        max_completion_tokens: int | None = None,
    ) -> ChatResult:
        prepared = tuple(messages)
        self.calls.append(prepared)
        request = json.loads(prepared[-1].content)
        cards = request["primitive_cards"]
        target = self.forced_name or _target_name(request["task_request"])
        selected = next(
            (item["route_handle"] for item in cards if item["name"] == target),
            None,
        )
        if self.forced_content is not None:
            content = self.forced_content
        elif selected is None:
            content = json.dumps(
                {
                    "selected_route_handle": None,
                    "reason_code": "no_suitable_candidate",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        else:
            content = json.dumps(
                {
                    "selected_route_handle": selected,
                    "reason_code": "capability_match",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        provider_request = {
            "model": model,
            "messages": [item.to_dict() for item in prepared],
            "seed": seed,
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
        }
        request_bytes = canonical_json_bytes(provider_request)
        response_value = {"model": model, "content": content}
        receipt = ModelUsageReceipt.create(
            provider_id="fake",
            provider_api="fake-chat-v1",
            usage_source="fake-native-response",
            endpoint_origin="https://fake.invalid",
            model_requested=model,
            model_reported=model,
            request_digest=sha256_digest(request_bytes),
            response_digest=sha256_digest(canonical_json_bytes(response_value)),
            content_digest=sha256_digest(content.encode("utf-8")),
            started_at="2026-07-16T00:00:00.000Z",
            completed_at="2026-07-16T00:00:00.001Z",
            wall_ms=1,
            prompt_tokens=max(1, len(request_bytes) // 4),
            completion_tokens=max(1, len(content.encode("utf-8")) // 4),
            total_duration_ns=None,
            load_duration_ns=None,
            prompt_eval_duration_ns=None,
            eval_duration_ns=None,
            finish_reason="stop",
        )
        return ChatResult(content, receipt)


def _target_name(request: str) -> str:
    lowered = request.casefold()
    rules = (
        ("outer spacing", "collapse-whitespace"),
        ("table headers", "normalize-column-name"),
        ("first-seen order", "stable-deduplicate"),
        ("upload batches", "chunk-sequence"),
        ("nested json event", "flatten-record"),
        ("arithmetic mean", "numeric-mean"),
        ("conventional median", "numeric-median"),
        ("minimum becomes zero", "minmax-scale"),
        ("population variance", "zscore-standardize"),
    )
    for phrase, name in rules:
        if phrase in lowered:
            return name
    return "no-such-primitive"

