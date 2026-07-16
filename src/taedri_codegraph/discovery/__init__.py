"""Search-trigger routing for user, application, deterministic, and model signals."""

from .triggers import (
    SearchTriggerDecision,
    SearchTriggerRouter,
    SearchTriggerSignal,
    TriggerKind,
    TriggerTier,
    TriggeredPrimitiveClient,
    default_trigger_router,
    intent_digest,
)
from .remote import RemotePrimitiveSearchClient

__all__ = [
    "SearchTriggerDecision",
    "SearchTriggerRouter",
    "SearchTriggerSignal",
    "TriggerKind",
    "TriggerTier",
    "TriggeredPrimitiveClient",
    "default_trigger_router",
    "intent_digest",
    "RemotePrimitiveSearchClient",
]
