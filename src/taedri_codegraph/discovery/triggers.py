"""Privacy-aware, tiered decisions for when a coding client should search primitives."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

from ..canonical import canonical_json_bytes, sha256_digest, to_primitive
from ..contracts import RecordMixin
from ..primitives.search import (
    PrimitiveSearchRequest,
    PrimitiveSearchResponse,
    SearchStrategy,
)

_KEY = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
_FORBIDDEN_CAPTURE_KEYS = frozenset(
    {
        "prompt",
        "prompts",
        "message",
        "messages",
        "source",
        "source_body",
        "source_text",
        "code",
        "query_text",
        "authorization",
        "token",
    }
)


class TriggerKind(str, Enum):
    USER_EXPLICIT = "user_explicit"
    TOOL_EXPLICIT = "tool_explicit"
    MISSING_SYMBOL = "missing_symbol"
    DEPENDENCY_FAILURE = "dependency_failure"
    REPEATED_BOILERPLATE = "repeated_boilerplate"
    CONTEXT_PRESSURE = "context_pressure"
    PRE_EDIT = "pre_edit"
    CLASSIFIER_SUGGESTION = "classifier_suggestion"
    MODEL_SUGGESTION = "model_suggestion"


class TriggerTier(str, Enum):
    USER = "user"
    DETERMINISTIC = "deterministic"
    CLASSIFIER = "classifier"
    MODEL = "model"


_TIER_ORDER = {
    TriggerTier.USER: 0,
    TriggerTier.DETERMINISTIC: 1,
    TriggerTier.CLASSIFIER: 2,
    TriggerTier.MODEL: 3,
}


@dataclass(frozen=True, slots=True)
class SearchTriggerSignal(RecordMixin):
    event_id: str
    session_id: str
    kind: TriggerKind
    intent_digest: str
    occurred_at: str
    language: str | None = None
    labels: tuple[str, ...] = ()
    confidence_ppm: int | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id or not self.session_id or not self.occurred_at:
            raise ValueError("trigger event, session, and occurrence time are required")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.intent_digest):
            raise ValueError("trigger intent must be represented by a sha256 digest")
        if self.confidence_ppm is not None and not 0 <= self.confidence_ppm <= 1_000_000:
            raise ValueError("trigger confidence must be 0..1,000,000 ppm")
        primitive = to_primitive(dict(self.attributes))
        _reject_sensitive_keys(primitive)
        object.__setattr__(self, "labels", tuple(sorted(set(self.labels))))
        object.__setattr__(self, "attributes", MappingProxyType(primitive))


@dataclass(frozen=True, slots=True)
class TriggerRuleDefinition(RecordMixin):
    key: str
    version: str
    tier: TriggerTier
    kinds: tuple[TriggerKind, ...]
    priority: int
    strategy: SearchStrategy
    result_limit: int
    minimum_candidates: int
    disclosure_level: str = "selection"
    minimum_confidence_ppm: int = 0
    cooldown_ms: int = 0
    required_labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key) or not re.fullmatch(
            r"[0-9]+(?:\.[0-9]+){0,2}", self.version
        ):
            raise ValueError("trigger rule key or version is invalid")
        if not self.kinds:
            raise ValueError("trigger rule requires at least one signal kind")
        if not 0 <= self.priority <= 10_000:
            raise ValueError("trigger rule priority is invalid")
        if not 1 <= self.result_limit <= 1000:
            raise ValueError("trigger result limit is invalid")
        if not 1 <= self.minimum_candidates <= 1000:
            raise ValueError("trigger minimum candidate count is invalid")
        if not 0 <= self.minimum_confidence_ppm <= 1_000_000:
            raise ValueError("trigger confidence threshold is invalid")
        if self.cooldown_ms < 0:
            raise ValueError("trigger cooldown cannot be negative")
        if self.disclosure_level not in {"handle", "selection", "contract", "implementation"}:
            raise ValueError("trigger disclosure level is invalid")
        object.__setattr__(self, "required_labels", tuple(sorted(set(self.required_labels))))

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"


@dataclass(frozen=True, slots=True)
class TriggerRuleReceipt(RecordMixin):
    rule_ref: str
    tier: TriggerTier
    outcome: str
    reason: str


@dataclass(frozen=True, slots=True)
class SearchTriggerDecision(RecordMixin):
    should_search: bool
    intent_digest: str
    selected_rule_ref: str | None
    strategy: SearchStrategy | None
    result_limit: int
    minimum_candidates: int
    disclosure_level: str
    receipts: tuple[TriggerRuleReceipt, ...]
    reason: str


Matcher = Callable[[SearchTriggerSignal], bool]


class SearchTriggerRouter:
    """Chooses the first matching control tier and never lets a model override it."""

    def __init__(self, *, monotonic_ms: Callable[[], int] | None = None) -> None:
        self._rules: dict[str, tuple[TriggerRuleDefinition, Matcher]] = {}
        self._last_fired: dict[tuple[str, str], int] = {}
        self._monotonic_ms = monotonic_ms or (lambda: time.monotonic_ns() // 1_000_000)

    def register(self, definition: TriggerRuleDefinition, matcher: Matcher) -> None:
        if definition.ref in self._rules:
            raise ValueError(f"trigger rule already registered: {definition.ref}")
        self._rules[definition.ref] = (definition, matcher)

    def decide(self, signal: SearchTriggerSignal) -> SearchTriggerDecision:
        now = self._monotonic_ms()
        receipts: list[TriggerRuleReceipt] = []
        ordered = sorted(
            self._rules.values(),
            key=lambda item: (
                _TIER_ORDER[item[0].tier],
                -item[0].priority,
                item[0].ref,
            ),
        )
        for tier in TriggerTier:
            matched: list[TriggerRuleDefinition] = []
            for definition, matcher in ordered:
                if definition.tier is not tier:
                    continue
                if signal.kind not in definition.kinds:
                    receipts.append(
                        TriggerRuleReceipt(definition.ref, tier, "skipped", "kind")
                    )
                    continue
                confidence = signal.confidence_ppm
                if definition.minimum_confidence_ppm > 0 and confidence is None:
                    receipts.append(
                        TriggerRuleReceipt(
                            definition.ref,
                            tier,
                            "skipped",
                            "confidence_unknown",
                        )
                    )
                    continue
                if confidence is not None and confidence < definition.minimum_confidence_ppm:
                    receipts.append(
                        TriggerRuleReceipt(definition.ref, tier, "skipped", "confidence")
                    )
                    continue
                if not set(definition.required_labels).issubset(signal.labels):
                    receipts.append(
                        TriggerRuleReceipt(definition.ref, tier, "skipped", "labels")
                    )
                    continue
                last = self._last_fired.get((signal.session_id, definition.ref))
                if (
                    tier is not TriggerTier.USER
                    and last is not None
                    and now - last < definition.cooldown_ms
                ):
                    receipts.append(
                        TriggerRuleReceipt(definition.ref, tier, "skipped", "cooldown")
                    )
                    continue
                if not matcher(signal):
                    receipts.append(
                        TriggerRuleReceipt(definition.ref, tier, "skipped", "predicate")
                    )
                    continue
                matched.append(definition)
                receipts.append(
                    TriggerRuleReceipt(definition.ref, tier, "matched", "rule_matched")
                )
            if matched:
                selected = sorted(matched, key=lambda item: (-item.priority, item.ref))[0]
                self._last_fired[(signal.session_id, selected.ref)] = now
                return SearchTriggerDecision(
                    True,
                    signal.intent_digest,
                    selected.ref,
                    selected.strategy,
                    selected.result_limit,
                    selected.minimum_candidates,
                    selected.disclosure_level,
                    tuple(receipts),
                    f"matched_{tier.value}_tier",
                )
        return SearchTriggerDecision(
            False,
            signal.intent_digest,
            None,
            None,
            0,
            0,
            "handle",
            tuple(receipts),
            "no_rule_matched",
        )


class PrimitiveSearchClient(Protocol):
    def search(self, request: PrimitiveSearchRequest) -> PrimitiveSearchResponse: ...


@dataclass(frozen=True, slots=True)
class TriggeredSearchResult(RecordMixin):
    decision: SearchTriggerDecision
    response: PrimitiveSearchResponse | None


class TriggeredPrimitiveClient:
    def __init__(self, router: SearchTriggerRouter, search: PrimitiveSearchClient) -> None:
        self.router = router
        self.search_service = search

    def handle(self, signal: SearchTriggerSignal, *, current_intent: str) -> TriggeredSearchResult:
        if intent_digest(current_intent) != signal.intent_digest:
            raise ValueError("current intent does not match the trigger digest")
        decision = self.router.decide(signal)
        if not decision.should_search:
            return TriggeredSearchResult(decision, None)
        response = self.search_service.search(
            PrimitiveSearchRequest(
                current_intent,
                decision.strategy or SearchStrategy.AUTO,
                limit=decision.result_limit,
                minimum_candidates=decision.minimum_candidates,
                entity_kind=(
                    str(signal.attributes["entity_kind"])
                    if "entity_kind" in signal.attributes
                    else None
                ),
            )
        )
        return TriggeredSearchResult(decision, response)


def default_trigger_router(
    *, monotonic_ms: Callable[[], int] | None = None
) -> SearchTriggerRouter:
    router = SearchTriggerRouter(monotonic_ms=monotonic_ms)
    router.register(
        TriggerRuleDefinition(
            "taedri.trigger.explicit",
            "1.0.0",
            TriggerTier.USER,
            (TriggerKind.USER_EXPLICIT, TriggerKind.TOOL_EXPLICIT),
            10_000,
            SearchStrategy.DEEP,
            20,
            8,
            "contract",
        ),
        lambda _signal: True,
    )
    router.register(
        TriggerRuleDefinition(
            "taedri.trigger.missing_dependency",
            "1.0.0",
            TriggerTier.DETERMINISTIC,
            (TriggerKind.MISSING_SYMBOL, TriggerKind.DEPENDENCY_FAILURE),
            9000,
            SearchStrategy.BALANCED,
            15,
            6,
            "selection",
            cooldown_ms=5_000,
        ),
        lambda signal: bool(signal.language),
    )
    router.register(
        TriggerRuleDefinition(
            "taedri.trigger.reuse_pressure",
            "1.0.0",
            TriggerTier.DETERMINISTIC,
            (
                TriggerKind.REPEATED_BOILERPLATE,
                TriggerKind.CONTEXT_PRESSURE,
                TriggerKind.PRE_EDIT,
            ),
            8000,
            SearchStrategy.AUTO,
            12,
            6,
            "selection",
            minimum_confidence_ppm=600_000,
            cooldown_ms=15_000,
        ),
        lambda _signal: True,
    )
    router.register(
        TriggerRuleDefinition(
            "taedri.trigger.classifier",
            "1.0.0",
            TriggerTier.CLASSIFIER,
            (TriggerKind.CLASSIFIER_SUGGESTION,),
            5000,
            SearchStrategy.AUTO,
            10,
            5,
            "selection",
            minimum_confidence_ppm=750_000,
            cooldown_ms=30_000,
        ),
        lambda _signal: True,
    )
    router.register(
        TriggerRuleDefinition(
            "taedri.trigger.model_router",
            "1.0.0",
            TriggerTier.MODEL,
            (TriggerKind.MODEL_SUGGESTION,),
            1000,
            SearchStrategy.AUTO,
            10,
            5,
            "selection",
            minimum_confidence_ppm=850_000,
            cooldown_ms=60_000,
        ),
        lambda _signal: True,
    )
    return router


def intent_digest(value: str) -> str:
    if not value.strip():
        raise ValueError("search intent cannot be empty")
    return sha256_digest(canonical_json_bytes({"intent": value}))


def _reject_sensitive_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in _FORBIDDEN_CAPTURE_KEYS:
                raise ValueError(f"trigger attributes cannot capture {key}")
            _reject_sensitive_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive_keys(item)
