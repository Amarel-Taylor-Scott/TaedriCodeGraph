"""Fail-closed matched-pair token-savings proofs.

This module deliberately does not infer evidence from opaque references.  A verified
proof resolves every model-attempt and verifier receipt, validates its content digest,
and requires a correctness-preserving matched pair before it can claim savings.

Token accounting uses ``exclusive_v1`` semantics: ``prompt_tokens`` already includes
the cached prompt subset, while reasoning, completion, tool, selector, retrieval,
verification, and repair tokens are mutually exclusive additions.  Consequently
cached prompt tokens are reported but never added a second time.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Protocol, runtime_checkable

from .canonical import canonical_json_bytes, sha256_digest
from .identity import IdentityRecord

if TYPE_CHECKING:
    from .model_providers import ModelUsageReceipt as ProviderModelUsageReceipt


FORMAT_VERSION = "1.0.0"
ACCOUNTING_MODE = "exclusive_v1"

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_UCEG_REF = re.compile(r"^uceg:v1:[a-z][a-z0-9_.-]*:[a-z2-7]+$")
_NAMED_REF = re.compile(r"^(?:registry|sealed):[A-Za-z0-9._:/-]+$")


class TokenSavingsError(ValueError):
    """Raised when token-savings evidence is incomplete or internally inconsistent."""


class TokenEvidenceClass(str, Enum):
    CONFORMANCE_FIXTURE = "conformance_fixture"
    REPORTED_HISTORICAL = "reported_historical"
    VERIFIED_REAL_MODEL = "verified_real_model"


class ProofArm(str, Enum):
    BASELINE = "baseline"
    REUSE = "reuse"


def _content_digest(value: Mapping[str, Any]) -> str:
    return sha256_digest(canonical_json_bytes(value))


def _require_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise TokenSavingsError(f"{field} must be an exact sha256 digest")
    return value


def _require_ref(value: object, field: str) -> str:
    if not isinstance(value, str) or not (
        _DIGEST.fullmatch(value)
        or _UCEG_REF.fullmatch(value)
        or _NAMED_REF.fullmatch(value)
    ):
        raise TokenSavingsError(f"{field} must be an exact immutable reference")
    return value


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TokenSavingsError(f"{field} must be a non-empty string")
    return value


def _require_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TokenSavingsError(f"{field} must be an integer >= {minimum}")
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise TokenSavingsError(f"{field} must be a boolean")
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise TokenSavingsError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise TokenSavingsError(f"{field} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], keys: Iterable[str], field: str) -> None:
    expected = set(keys)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise TokenSavingsError(f"{field} has invalid fields ({'; '.join(detail)})")


def _ppm(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise TokenSavingsError("baseline token total must be positive")
    magnitude = (abs(numerator) * 1_000_000) // denominator
    return -magnitude if numerator < 0 else magnitude


def _exact_ref_tuple(
    values: Iterable[str], field: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    refs = tuple(_require_ref(value, field) for value in values)
    if not allow_empty and not refs:
        raise TokenSavingsError(f"{field} must contain at least one reference")
    if refs != tuple(sorted(set(refs))):
        raise TokenSavingsError(f"{field} must be sorted and unique")
    return refs


@dataclass(frozen=True, slots=True)
class TrustedEvidenceRequest:
    """Exact runtime binding a trusted store must independently resolve."""

    subject_ref: str
    source_digest: str
    context_digest: str
    baseline_run_digest: str
    reuse_run_digest: str
    provider_receipt_refs: tuple[str, ...]
    model_usage_receipt_digests: tuple[str, ...]
    source_verifier_refs: tuple[str, ...]
    verifier_receipt_digests: tuple[str, ...]
    terminal_receipt_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_ref(self.subject_ref, "trusted_request.subject_ref")
        for name in (
            "source_digest",
            "context_digest",
            "baseline_run_digest",
            "reuse_run_digest",
        ):
            _require_digest(getattr(self, name), f"trusted_request.{name}")
        _exact_ref_tuple(
            self.provider_receipt_refs,
            "trusted_request.provider_receipt_refs",
        )
        _exact_ref_tuple(
            self.model_usage_receipt_digests,
            "trusted_request.model_usage_receipt_digests",
        )
        _exact_ref_tuple(
            self.source_verifier_refs,
            "trusted_request.source_verifier_refs",
        )
        _exact_ref_tuple(
            self.verifier_receipt_digests,
            "trusted_request.verifier_receipt_digests",
        )
        _exact_ref_tuple(
            self.terminal_receipt_refs,
            "trusted_request.terminal_receipt_refs",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_ref": self.subject_ref,
            "source_digest": self.source_digest,
            "context_digest": self.context_digest,
            "baseline_run_digest": self.baseline_run_digest,
            "reuse_run_digest": self.reuse_run_digest,
            "provider_receipt_refs": list(self.provider_receipt_refs),
            "model_usage_receipt_digests": list(
                self.model_usage_receipt_digests
            ),
            "source_verifier_refs": list(self.source_verifier_refs),
            "verifier_receipt_digests": list(self.verifier_receipt_digests),
            "terminal_receipt_refs": list(self.terminal_receipt_refs),
        }

    @property
    def binding_digest(self) -> str:
        return _content_digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class TrustedEvidenceAttestation:
    """Runtime-only, keyed trusted-store attestation.

    The attestation never carries its trust root and is never loaded from proof JSON.
    Its content digest only protects canonical representation; authority comes from
    the HMAC verified by a separately configured :class:`TrustedEvidenceTrustRoot`.
    """

    trust_domain: str
    key_id: str
    attestation_ref: str
    request: TrustedEvidenceRequest
    signature: str
    attestation_digest: str

    @classmethod
    def issue_hmac(
        cls,
        *,
        trust_domain: str,
        key_id: str,
        attestation_ref: str,
        request: TrustedEvidenceRequest,
        signing_key: bytes,
    ) -> "TrustedEvidenceAttestation":
        domain = _require_text(trust_domain, "attestation.trust_domain")
        key_reference = _require_ref(key_id, "attestation.key_id")
        reference = _require_ref(attestation_ref, "attestation.attestation_ref")
        key = _require_hmac_key(signing_key, "attestation.signing_key")
        signed_payload = {
            "format_version": FORMAT_VERSION,
            "algorithm": "hmac-sha256",
            "trust_domain": domain,
            "key_id": key_reference,
            "attestation_ref": reference,
            "request": request.to_dict(),
            "request_binding_digest": request.binding_digest,
        }
        signature = "sha256:" + hmac.new(
            key,
            canonical_json_bytes(signed_payload),
            hashlib.sha256,
        ).hexdigest()
        payload = {**signed_payload, "signature": signature}
        return cls(
            domain,
            key_reference,
            reference,
            request,
            signature,
            _content_digest(payload),
        )

    def _signed_payload(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "algorithm": "hmac-sha256",
            "trust_domain": self.trust_domain,
            "key_id": self.key_id,
            "attestation_ref": self.attestation_ref,
            "request": self.request.to_dict(),
            "request_binding_digest": self.request.binding_digest,
        }

    def validate_structure(self) -> None:
        _require_text(self.trust_domain, "attestation.trust_domain")
        _require_ref(self.key_id, "attestation.key_id")
        _require_ref(self.attestation_ref, "attestation.attestation_ref")
        _require_digest(self.signature, "attestation.signature")
        _require_digest(self.attestation_digest, "attestation.attestation_digest")
        expected = _content_digest(
            {**self._signed_payload(), "signature": self.signature}
        )
        if not hmac.compare_digest(expected, self.attestation_digest):
            raise TokenSavingsError(
                "trusted evidence attestation content digest does not match"
            )


def _require_hmac_key(value: object, field_name: str) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise TokenSavingsError(f"{field_name} must be at least 32 bytes")
    return bytes(value)


@dataclass(frozen=True, slots=True)
class TrustedEvidenceTrustRoot:
    """Configured runtime root used to authenticate evidence attestations.

    This object is injected by the embedding application.  It is deliberately not
    derivable from, or serialized into, a proof or attestation.  Verification is
    therefore relative to an operator-configured domain/key-id root, never a root
    supplied by the evidence resolver itself.
    """

    trust_domain: str
    key_id: str
    verification_key: bytes = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_text(self.trust_domain, "trusted_root.trust_domain")
        _require_ref(self.key_id, "trusted_root.key_id")
        object.__setattr__(
            self,
            "verification_key",
            _require_hmac_key(
                self.verification_key, "trusted_root.verification_key"
            ),
        )

    def verify(self, attestation: TrustedEvidenceAttestation) -> bool:
        if not isinstance(attestation, TrustedEvidenceAttestation):
            return False
        attestation.validate_structure()
        if (
            attestation.trust_domain != self.trust_domain
            or attestation.key_id != self.key_id
        ):
            return False
        expected = "sha256:" + hmac.new(
            self.verification_key,
            canonical_json_bytes(attestation._signed_payload()),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, attestation.signature)


@runtime_checkable
class TrustedEvidenceResolver(Protocol):
    """Runtime/store lookup; authority comes only from the configured trust root."""

    @property
    def trust_domain(self) -> str: ...

    @property
    def key_id(self) -> str: ...

    def resolve(
        self, request: TrustedEvidenceRequest
    ) -> TrustedEvidenceAttestation | None: ...


@dataclass(frozen=True, slots=True)
class TokenBreakdown:
    """Exclusive token categories for one model attempt and its attributable overhead."""

    prompt_tokens: int
    cached_prompt_tokens: int
    reasoning_tokens: int
    completion_tokens: int
    tool_tokens: int
    selector_tokens: int
    retrieval_tokens: int
    verification_tokens: int
    repair_tokens: int

    def __post_init__(self) -> None:
        for name in (
            "prompt_tokens",
            "cached_prompt_tokens",
            "reasoning_tokens",
            "completion_tokens",
            "tool_tokens",
            "selector_tokens",
            "retrieval_tokens",
            "verification_tokens",
            "repair_tokens",
        ):
            _require_int(getattr(self, name), name)
        if self.cached_prompt_tokens > self.prompt_tokens:
            raise TokenSavingsError("cached_prompt_tokens cannot exceed prompt_tokens")

    @property
    def uncached_prompt_tokens(self) -> int:
        return self.prompt_tokens - self.cached_prompt_tokens

    @property
    def accounted_total_tokens(self) -> int:
        # cached_prompt_tokens is a subset of prompt_tokens and is not added again.
        return (
            self.prompt_tokens
            + self.reasoning_tokens
            + self.completion_tokens
            + self.tool_tokens
            + self.selector_tokens
            + self.retrieval_tokens
            + self.verification_tokens
            + self.repair_tokens
        )

    def to_dict(self, *, include_totals: bool = False) -> dict[str, object]:
        value: dict[str, object] = {
            "accounting_mode": ACCOUNTING_MODE,
            "prompt_tokens": self.prompt_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "completion_tokens": self.completion_tokens,
            "tool_tokens": self.tool_tokens,
            "selector_tokens": self.selector_tokens,
            "retrieval_tokens": self.retrieval_tokens,
            "verification_tokens": self.verification_tokens,
            "repair_tokens": self.repair_tokens,
        }
        if include_totals:
            value["uncached_prompt_tokens"] = self.uncached_prompt_tokens
            value["accounted_total_tokens"] = self.accounted_total_tokens
        return value

    @classmethod
    def from_dict(cls, raw: object, field: str = "usage") -> "TokenBreakdown":
        value = _mapping(raw, field)
        keys = (
            "accounting_mode",
            "prompt_tokens",
            "cached_prompt_tokens",
            "reasoning_tokens",
            "completion_tokens",
            "tool_tokens",
            "selector_tokens",
            "retrieval_tokens",
            "verification_tokens",
            "repair_tokens",
        )
        _exact_keys(value, keys, field)
        if value["accounting_mode"] != ACCOUNTING_MODE:
            raise TokenSavingsError(f"{field}.accounting_mode must be {ACCOUNTING_MODE}")
        return cls(
            *(_require_int(value[name], f"{field}.{name}") for name in keys[1:])
        )

    @classmethod
    def aggregate(cls, values: Iterable["TokenBreakdown"]) -> "TokenBreakdown":
        items = tuple(values)
        return cls(
            *(sum(getattr(item, name) for item in items) for name in cls.field_names())
        )

    @staticmethod
    def field_names() -> tuple[str, ...]:
        return (
            "prompt_tokens",
            "cached_prompt_tokens",
            "reasoning_tokens",
            "completion_tokens",
            "tool_tokens",
            "selector_tokens",
            "retrieval_tokens",
            "verification_tokens",
            "repair_tokens",
        )


@dataclass(frozen=True, slots=True)
class TokenBudget:
    max_attempts: int
    max_prompt_tokens_per_attempt: int
    max_output_tokens_per_attempt: int
    max_total_tokens: int
    max_tool_calls: int
    max_wall_ms: int
    max_verifier_cpu_ms: int

    def __post_init__(self) -> None:
        _require_int(self.max_attempts, "max_attempts", minimum=1)
        _require_int(
            self.max_prompt_tokens_per_attempt,
            "max_prompt_tokens_per_attempt",
            minimum=1,
        )
        _require_int(
            self.max_output_tokens_per_attempt,
            "max_output_tokens_per_attempt",
            minimum=1,
        )
        _require_int(self.max_total_tokens, "max_total_tokens", minimum=1)
        _require_int(self.max_tool_calls, "max_tool_calls")
        _require_int(self.max_wall_ms, "max_wall_ms", minimum=1)
        _require_int(self.max_verifier_cpu_ms, "max_verifier_cpu_ms", minimum=1)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_attempts": self.max_attempts,
            "max_prompt_tokens_per_attempt": self.max_prompt_tokens_per_attempt,
            "max_output_tokens_per_attempt": self.max_output_tokens_per_attempt,
            "max_total_tokens": self.max_total_tokens,
            "max_tool_calls": self.max_tool_calls,
            "max_wall_ms": self.max_wall_ms,
            "max_verifier_cpu_ms": self.max_verifier_cpu_ms,
        }

    @classmethod
    def from_dict(cls, raw: object, field: str = "budget") -> "TokenBudget":
        value = _mapping(raw, field)
        keys = (
            "max_attempts",
            "max_prompt_tokens_per_attempt",
            "max_output_tokens_per_attempt",
            "max_total_tokens",
            "max_tool_calls",
            "max_wall_ms",
            "max_verifier_cpu_ms",
        )
        _exact_keys(value, keys, field)
        return cls(*(_require_int(value[name], f"{field}.{name}") for name in keys))


@dataclass(frozen=True, slots=True)
class MatchedRunContext:
    task_ref: str
    seed: int
    provider_id: str
    model_id: str
    model_config_digest: str
    harness_digest: str
    runtime_digest: str
    policy_digest: str
    oracle_ref: str
    snapshot_ref: str
    budget: TokenBudget

    def __post_init__(self) -> None:
        _require_ref(self.task_ref, "task_ref")
        _require_int(self.seed, "seed")
        _require_text(self.provider_id, "provider_id")
        _require_text(self.model_id, "model_id")
        for name in (
            "model_config_digest",
            "harness_digest",
            "runtime_digest",
            "policy_digest",
        ):
            _require_digest(getattr(self, name), name)
        _require_ref(self.oracle_ref, "oracle_ref")
        _require_ref(self.snapshot_ref, "snapshot_ref")

    @property
    def context_digest(self) -> str:
        return _content_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "task_ref": self.task_ref,
            "seed": self.seed,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "model_config_digest": self.model_config_digest,
            "harness_digest": self.harness_digest,
            "runtime_digest": self.runtime_digest,
            "policy_digest": self.policy_digest,
            "oracle_ref": self.oracle_ref,
            "snapshot_ref": self.snapshot_ref,
            "budget": self.budget.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: object, field: str = "context") -> "MatchedRunContext":
        value = _mapping(raw, field)
        keys = (
            "task_ref",
            "seed",
            "provider_id",
            "model_id",
            "model_config_digest",
            "harness_digest",
            "runtime_digest",
            "policy_digest",
            "oracle_ref",
            "snapshot_ref",
            "budget",
        )
        _exact_keys(value, keys, field)
        return cls(
            _require_ref(value["task_ref"], f"{field}.task_ref"),
            _require_int(value["seed"], f"{field}.seed"),
            _require_text(value["provider_id"], f"{field}.provider_id"),
            _require_text(value["model_id"], f"{field}.model_id"),
            _require_digest(
                value["model_config_digest"], f"{field}.model_config_digest"
            ),
            _require_digest(value["harness_digest"], f"{field}.harness_digest"),
            _require_digest(value["runtime_digest"], f"{field}.runtime_digest"),
            _require_digest(value["policy_digest"], f"{field}.policy_digest"),
            _require_ref(value["oracle_ref"], f"{field}.oracle_ref"),
            _require_ref(value["snapshot_ref"], f"{field}.snapshot_ref"),
            TokenBudget.from_dict(value["budget"], f"{field}.budget"),
        )


def run_spec_digest(context: MatchedRunContext, arm: ProofArm) -> str:
    return _content_digest(
        {
            "format_version": FORMAT_VERSION,
            "context_digest": context.context_digest,
            "arm": arm.value,
        }
    )


@dataclass(frozen=True, slots=True)
class ModelUsageReceipt:
    run_spec_digest: str
    attempt_index: int
    provider_id: str
    model_id: str
    model_config_digest: str
    provider_receipt_ref: str
    provider_content_digest: str
    usage_source: str
    request_digest: str
    response_digest: str
    tool_calls: int
    usage: TokenBreakdown
    receipt_digest: str

    @classmethod
    def create(
        cls,
        *,
        run_spec_digest: str,
        attempt_index: int,
        provider_id: str,
        model_id: str,
        model_config_digest: str,
        provider_receipt_ref: str,
        provider_content_digest: str,
        usage_source: str,
        request_digest: str,
        response_digest: str,
        tool_calls: int,
        usage: TokenBreakdown,
    ) -> "ModelUsageReceipt":
        spec = _require_digest(run_spec_digest, "model_usage.run_spec_digest")
        index = _require_int(attempt_index, "model_usage.attempt_index", minimum=1)
        provider = _require_text(provider_id, "model_usage.provider_id")
        model = _require_text(model_id, "model_usage.model_id")
        config = _require_digest(
            model_config_digest, "model_usage.model_config_digest"
        )
        provider_ref = _require_ref(
            provider_receipt_ref, "model_usage.provider_receipt_ref"
        )
        provider_content = _require_digest(
            provider_content_digest, "model_usage.provider_content_digest"
        )
        source = _require_text(usage_source, "model_usage.usage_source")
        request = _require_digest(request_digest, "model_usage.request_digest")
        response = _require_digest(response_digest, "model_usage.response_digest")
        calls = _require_int(tool_calls, "model_usage.tool_calls")
        if not isinstance(usage, TokenBreakdown):
            raise TokenSavingsError("model_usage.usage must be a token breakdown")
        if usage.tool_tokens > 0 and calls == 0:
            raise TokenSavingsError(
                "model usage with tool tokens must report at least one tool call"
            )
        payload = {
            "format_version": FORMAT_VERSION,
            "run_spec_digest": spec,
            "attempt_index": index,
            "provider_id": provider,
            "model_id": model,
            "model_config_digest": config,
            "provider_receipt_ref": provider_ref,
            "provider_content_digest": provider_content,
            "usage_source": source,
            "request_digest": request,
            "response_digest": response,
            "tool_calls": calls,
            "usage": usage.to_dict(),
        }
        return cls(
            spec,
            index,
            provider,
            model,
            config,
            provider_ref,
            provider_content,
            source,
            request,
            response,
            calls,
            usage,
            _content_digest(payload),
        )

    @classmethod
    def from_provider_receipt(
        cls,
        *,
        context: MatchedRunContext,
        arm: ProofArm,
        attempt_index: int,
        provider_receipt: "ProviderModelUsageReceipt",
        cached_prompt_tokens: int = 0,
        reasoning_tokens: int = 0,
        tool_tokens: int = 0,
        selector_tokens: int = 0,
        retrieval_tokens: int = 0,
        verification_tokens: int = 0,
        repair_tokens: int = 0,
        tool_calls: int = 0,
    ) -> "ModelUsageReceipt":
        """Bind an actual provider receipt into one matched-pair attempt.

        Provider prompt and completion counters are copied exactly. The additional
        counters are explicit, mutually exclusive harness-attributable categories;
        cached prompt tokens remain a reported subset of prompt tokens.
        """

        # Keep provider adapters independent of this proof subsystem while still
        # rejecting duck-typed objects that merely look like provider receipts.
        from .model_providers import ModelUsageReceipt as ProviderReceipt

        if not isinstance(provider_receipt, ProviderReceipt):
            raise TokenSavingsError(
                "provider_receipt must be a concrete model-provider usage receipt"
            )
        try:
            provider_receipt.identity.validate()
        except (TypeError, ValueError) as exc:
            raise TokenSavingsError(
                "provider_receipt has an invalid content-addressed identity"
            ) from exc
        provider_key = {
            "format_version": provider_receipt.format_version,
            "provider_id": provider_receipt.provider_id,
            "provider_api": provider_receipt.provider_api,
            "endpoint_origin": provider_receipt.endpoint_origin,
            "model_requested": provider_receipt.model_requested,
            "model_reported": provider_receipt.model_reported,
            "request_digest": provider_receipt.request_digest,
            "response_digest": provider_receipt.response_digest,
            "content_digest": provider_receipt.content_digest,
            "started_at": provider_receipt.started_at,
            "completed_at": provider_receipt.completed_at,
            "wall_ms": provider_receipt.wall_ms,
            "prompt_tokens": provider_receipt.prompt_tokens,
            "completion_tokens": provider_receipt.completion_tokens,
            "total_duration_ns": provider_receipt.total_duration_ns,
            "load_duration_ns": provider_receipt.load_duration_ns,
            "prompt_eval_duration_ns": provider_receipt.prompt_eval_duration_ns,
            "eval_duration_ns": provider_receipt.eval_duration_ns,
            "finish_reason": provider_receipt.finish_reason,
            "usage_source": provider_receipt.usage_source,
        }
        if (
            provider_receipt.identity.kind != "model_usage_receipt"
            or provider_receipt.identity.canonical_key != provider_key
        ):
            raise TokenSavingsError(
                "provider_receipt fields do not match its content-addressed identity"
            )
        if provider_receipt.provider_id != context.provider_id:
            raise TokenSavingsError(
                "provider_receipt does not match the frozen provider"
            )
        if (
            provider_receipt.model_requested != context.model_id
            or provider_receipt.model_reported != context.model_id
        ):
            raise TokenSavingsError(
                "provider_receipt does not match the exact frozen model identity"
            )
        return cls.create(
            run_spec_digest=run_spec_digest(context, arm),
            attempt_index=attempt_index,
            provider_id=provider_receipt.provider_id,
            model_id=context.model_id,
            model_config_digest=context.model_config_digest,
            provider_receipt_ref=provider_receipt.identity.id,
            provider_content_digest=provider_receipt.content_digest,
            usage_source=provider_receipt.usage_source,
            request_digest=provider_receipt.request_digest,
            response_digest=provider_receipt.response_digest,
            tool_calls=tool_calls,
            usage=TokenBreakdown(
                prompt_tokens=provider_receipt.prompt_tokens,
                cached_prompt_tokens=cached_prompt_tokens,
                reasoning_tokens=reasoning_tokens,
                completion_tokens=provider_receipt.completion_tokens,
                tool_tokens=tool_tokens,
                selector_tokens=selector_tokens,
                retrieval_tokens=retrieval_tokens,
                verification_tokens=verification_tokens,
                repair_tokens=repair_tokens,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "receipt_digest": self.receipt_digest,
            "run_spec_digest": self.run_spec_digest,
            "attempt_index": self.attempt_index,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "model_config_digest": self.model_config_digest,
            "provider_receipt_ref": self.provider_receipt_ref,
            "provider_content_digest": self.provider_content_digest,
            "usage_source": self.usage_source,
            "request_digest": self.request_digest,
            "response_digest": self.response_digest,
            "tool_calls": self.tool_calls,
            "usage": self.usage.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: object, field: str = "model_usage_receipt") -> "ModelUsageReceipt":
        value = _mapping(raw, field)
        keys = (
            "format_version",
            "receipt_digest",
            "run_spec_digest",
            "attempt_index",
            "provider_id",
            "model_id",
            "model_config_digest",
            "provider_receipt_ref",
            "provider_content_digest",
            "usage_source",
            "request_digest",
            "response_digest",
            "tool_calls",
            "usage",
        )
        _exact_keys(value, keys, field)
        if value["format_version"] != FORMAT_VERSION:
            raise TokenSavingsError(f"{field}.format_version is unsupported")
        declared = _require_digest(value["receipt_digest"], f"{field}.receipt_digest")
        receipt = cls.create(
            run_spec_digest=_require_digest(
                value["run_spec_digest"], f"{field}.run_spec_digest"
            ),
            attempt_index=_require_int(
                value["attempt_index"], f"{field}.attempt_index", minimum=1
            ),
            provider_id=_require_text(value["provider_id"], f"{field}.provider_id"),
            model_id=_require_text(value["model_id"], f"{field}.model_id"),
            model_config_digest=_require_digest(
                value["model_config_digest"], f"{field}.model_config_digest"
            ),
            provider_receipt_ref=_require_ref(
                value["provider_receipt_ref"], f"{field}.provider_receipt_ref"
            ),
            provider_content_digest=_require_digest(
                value["provider_content_digest"],
                f"{field}.provider_content_digest",
            ),
            usage_source=_require_text(
                value["usage_source"], f"{field}.usage_source"
            ),
            request_digest=_require_digest(
                value["request_digest"], f"{field}.request_digest"
            ),
            response_digest=_require_digest(
                value["response_digest"], f"{field}.response_digest"
            ),
            tool_calls=_require_int(
                value["tool_calls"], f"{field}.tool_calls"
            ),
            usage=TokenBreakdown.from_dict(value["usage"], f"{field}.usage"),
        )
        if receipt.receipt_digest != declared:
            raise TokenSavingsError(f"{field} content digest does not match its bytes")
        return receipt


@dataclass(frozen=True, slots=True)
class VerifierReceipt:
    run_spec_digest: str
    context_digest: str
    oracle_ref: str
    output_digest: str
    model_usage_receipt_digests: tuple[str, ...]
    verifier_id: str
    source_verifier_ref: str
    verifier_config_digest: str
    observed_run_wall_ms: int
    verifier_cpu_ms: int
    accepted: bool
    tests_total: int
    tests_passed: int
    tests_failed: int
    receipt_digest: str

    @classmethod
    def create(
        cls,
        *,
        run_spec_digest: str,
        context_digest: str,
        oracle_ref: str,
        output_digest: str,
        model_usage_receipt_digests: Iterable[str],
        verifier_id: str,
        source_verifier_ref: str,
        verifier_config_digest: str,
        observed_run_wall_ms: int,
        verifier_cpu_ms: int,
        accepted: bool,
        tests_total: int,
        tests_passed: int,
        tests_failed: int,
    ) -> "VerifierReceipt":
        spec = _require_digest(run_spec_digest, "verifier.run_spec_digest")
        context = _require_digest(context_digest, "verifier.context_digest")
        oracle = _require_ref(oracle_ref, "verifier.oracle_ref")
        output = _require_digest(output_digest, "verifier.output_digest")
        usages = tuple(
            _require_digest(item, "verifier.model_usage_receipt_digests")
            for item in model_usage_receipt_digests
        )
        if not usages or len(usages) != len(set(usages)):
            raise TokenSavingsError(
                "verifier model usage receipt digests must be non-empty and unique"
            )
        verifier = _require_text(verifier_id, "verifier.verifier_id")
        source_ref = _require_ref(
            source_verifier_ref, "verifier.source_verifier_ref"
        )
        config = _require_digest(
            verifier_config_digest, "verifier.verifier_config_digest"
        )
        run_wall = _require_int(
            observed_run_wall_ms, "verifier.observed_run_wall_ms"
        )
        verifier_cpu = _require_int(
            verifier_cpu_ms, "verifier.verifier_cpu_ms"
        )
        accepted_value = _require_bool(accepted, "verifier.accepted")
        total = _require_int(tests_total, "verifier.tests_total", minimum=1)
        passed = _require_int(tests_passed, "verifier.tests_passed")
        failed = _require_int(tests_failed, "verifier.tests_failed")
        if total != passed + failed:
            raise TokenSavingsError("verifier test totals must reconcile")
        if accepted_value and (passed <= 0 or failed != 0):
            raise TokenSavingsError("accepted verifier receipts require passing tests")
        if not accepted_value and failed <= 0:
            raise TokenSavingsError("rejected verifier receipts require a failed test")
        payload = {
            "format_version": FORMAT_VERSION,
            "run_spec_digest": spec,
            "context_digest": context,
            "oracle_ref": oracle,
            "output_digest": output,
            "model_usage_receipt_digests": list(usages),
            "verifier_id": verifier,
            "source_verifier_ref": source_ref,
            "verifier_config_digest": config,
            "observed_run_wall_ms": run_wall,
            "verifier_cpu_ms": verifier_cpu,
            "accepted": accepted_value,
            "tests_total": total,
            "tests_passed": passed,
            "tests_failed": failed,
        }
        return cls(
            spec,
            context,
            oracle,
            output,
            usages,
            verifier,
            source_ref,
            config,
            run_wall,
            verifier_cpu,
            accepted_value,
            total,
            passed,
            failed,
            _content_digest(payload),
        )

    @classmethod
    def for_run(
        cls,
        *,
        context: MatchedRunContext,
        arm: ProofArm,
        model_usage_receipts: Iterable[ModelUsageReceipt],
        output_digest: str,
        verifier_id: str,
        source_verifier_ref: str,
        verifier_config_digest: str,
        observed_run_wall_ms: int,
        verifier_cpu_ms: int,
        accepted: bool,
        tests_total: int,
        tests_passed: int,
        tests_failed: int,
    ) -> "VerifierReceipt":
        """Create an independent verifier receipt without manual digest plumbing."""

        usages = tuple(model_usage_receipts)
        expected_spec = run_spec_digest(context, arm)
        if not usages:
            raise TokenSavingsError("verifier must cover at least one model attempt")
        if any(item.run_spec_digest != expected_spec for item in usages):
            raise TokenSavingsError(
                "verifier input contains an attempt from another run"
            )
        return cls.create(
            run_spec_digest=expected_spec,
            context_digest=context.context_digest,
            oracle_ref=context.oracle_ref,
            output_digest=output_digest,
            model_usage_receipt_digests=(item.receipt_digest for item in usages),
            verifier_id=verifier_id,
            source_verifier_ref=source_verifier_ref,
            verifier_config_digest=verifier_config_digest,
            observed_run_wall_ms=observed_run_wall_ms,
            verifier_cpu_ms=verifier_cpu_ms,
            accepted=accepted,
            tests_total=tests_total,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "receipt_digest": self.receipt_digest,
            "run_spec_digest": self.run_spec_digest,
            "context_digest": self.context_digest,
            "oracle_ref": self.oracle_ref,
            "output_digest": self.output_digest,
            "model_usage_receipt_digests": list(self.model_usage_receipt_digests),
            "verifier_id": self.verifier_id,
            "source_verifier_ref": self.source_verifier_ref,
            "verifier_config_digest": self.verifier_config_digest,
            "observed_run_wall_ms": self.observed_run_wall_ms,
            "verifier_cpu_ms": self.verifier_cpu_ms,
            "accepted": self.accepted,
            "tests_total": self.tests_total,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
        }

    @classmethod
    def from_dict(cls, raw: object, field: str = "verifier_receipt") -> "VerifierReceipt":
        value = _mapping(raw, field)
        keys = (
            "format_version",
            "receipt_digest",
            "run_spec_digest",
            "context_digest",
            "oracle_ref",
            "output_digest",
            "model_usage_receipt_digests",
            "verifier_id",
            "source_verifier_ref",
            "verifier_config_digest",
            "observed_run_wall_ms",
            "verifier_cpu_ms",
            "accepted",
            "tests_total",
            "tests_passed",
            "tests_failed",
        )
        _exact_keys(value, keys, field)
        if value["format_version"] != FORMAT_VERSION:
            raise TokenSavingsError(f"{field}.format_version is unsupported")
        declared = _require_digest(value["receipt_digest"], f"{field}.receipt_digest")
        receipt = cls.create(
            run_spec_digest=_require_digest(
                value["run_spec_digest"], f"{field}.run_spec_digest"
            ),
            context_digest=_require_digest(
                value["context_digest"], f"{field}.context_digest"
            ),
            oracle_ref=_require_ref(value["oracle_ref"], f"{field}.oracle_ref"),
            output_digest=_require_digest(
                value["output_digest"], f"{field}.output_digest"
            ),
            model_usage_receipt_digests=(
                _require_digest(item, f"{field}.model_usage_receipt_digests")
                for item in _sequence(
                    value["model_usage_receipt_digests"],
                    f"{field}.model_usage_receipt_digests",
                )
            ),
            verifier_id=_require_text(value["verifier_id"], f"{field}.verifier_id"),
            source_verifier_ref=_require_ref(
                value["source_verifier_ref"], f"{field}.source_verifier_ref"
            ),
            verifier_config_digest=_require_digest(
                value["verifier_config_digest"], f"{field}.verifier_config_digest"
            ),
            observed_run_wall_ms=_require_int(
                value["observed_run_wall_ms"],
                f"{field}.observed_run_wall_ms",
            ),
            verifier_cpu_ms=_require_int(
                value["verifier_cpu_ms"], f"{field}.verifier_cpu_ms"
            ),
            accepted=_require_bool(value["accepted"], f"{field}.accepted"),
            tests_total=_require_int(
                value["tests_total"], f"{field}.tests_total", minimum=1
            ),
            tests_passed=_require_int(
                value["tests_passed"], f"{field}.tests_passed"
            ),
            tests_failed=_require_int(
                value["tests_failed"], f"{field}.tests_failed"
            ),
        )
        if receipt.receipt_digest != declared:
            raise TokenSavingsError(f"{field} content digest does not match its bytes")
        return receipt


@dataclass(frozen=True, slots=True)
class RunArmEvidence:
    arm: ProofArm
    context: MatchedRunContext
    run_spec_digest: str
    runner_id: str | None
    accepted: bool | None
    output_digest: str | None
    attempt_count: int | None
    model_usage_receipt_digests: tuple[str, ...]
    verifier_receipt_digest: str | None
    reported_total_tokens: int | None
    run_digest: str

    @classmethod
    def create(
        cls,
        *,
        arm: ProofArm,
        context: MatchedRunContext,
        runner_id: str | None,
        accepted: bool | None,
        output_digest: str | None,
        attempt_count: int | None,
        model_usage_receipt_digests: Iterable[str] = (),
        verifier_receipt_digest: str | None = None,
        reported_total_tokens: int | None = None,
    ) -> "RunArmEvidence":
        if runner_id is not None:
            _require_text(runner_id, "run.runner_id")
        if accepted is not None:
            _require_bool(accepted, "run.accepted")
        if output_digest is not None:
            _require_digest(output_digest, "run.output_digest")
        if attempt_count is not None:
            _require_int(attempt_count, "run.attempt_count", minimum=1)
        usage_digests = tuple(
            _require_digest(item, "run.model_usage_receipt_digests")
            for item in model_usage_receipt_digests
        )
        if len(usage_digests) != len(set(usage_digests)):
            raise TokenSavingsError("run model usage receipt digests must be unique")
        if verifier_receipt_digest is not None:
            _require_digest(verifier_receipt_digest, "run.verifier_receipt_digest")
        if reported_total_tokens is not None:
            _require_int(reported_total_tokens, "run.reported_total_tokens")
        spec = run_spec_digest(context, arm)
        payload = {
            "format_version": FORMAT_VERSION,
            "arm": arm.value,
            "context": context.to_dict(),
            "run_spec_digest": spec,
            "runner_id": runner_id,
            "accepted": accepted,
            "output_digest": output_digest,
            "attempt_count": attempt_count,
            "model_usage_receipt_digests": list(usage_digests),
            "verifier_receipt_digest": verifier_receipt_digest,
            "reported_total_tokens": reported_total_tokens,
        }
        return cls(
            arm,
            context,
            spec,
            runner_id,
            accepted,
            output_digest,
            attempt_count,
            usage_digests,
            verifier_receipt_digest,
            reported_total_tokens,
            _content_digest(payload),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "run_digest": self.run_digest,
            "arm": self.arm.value,
            "context": self.context.to_dict(),
            "run_spec_digest": self.run_spec_digest,
            "runner_id": self.runner_id,
            "accepted": self.accepted,
            "output_digest": self.output_digest,
            "attempt_count": self.attempt_count,
            "model_usage_receipt_digests": list(self.model_usage_receipt_digests),
            "verifier_receipt_digest": self.verifier_receipt_digest,
            "reported_total_tokens": self.reported_total_tokens,
        }

    @classmethod
    def from_dict(cls, raw: object, field: str = "run") -> "RunArmEvidence":
        value = _mapping(raw, field)
        keys = (
            "format_version",
            "run_digest",
            "arm",
            "context",
            "run_spec_digest",
            "runner_id",
            "accepted",
            "output_digest",
            "attempt_count",
            "model_usage_receipt_digests",
            "verifier_receipt_digest",
            "reported_total_tokens",
        )
        _exact_keys(value, keys, field)
        if value["format_version"] != FORMAT_VERSION:
            raise TokenSavingsError(f"{field}.format_version is unsupported")
        try:
            arm = ProofArm(value["arm"])
        except (TypeError, ValueError) as exc:
            raise TokenSavingsError(f"{field}.arm is invalid") from exc
        context = MatchedRunContext.from_dict(value["context"], f"{field}.context")
        runner = value["runner_id"]
        accepted = value["accepted"]
        output = value["output_digest"]
        attempt_count = value["attempt_count"]
        verifier = value["verifier_receipt_digest"]
        reported = value["reported_total_tokens"]
        run = cls.create(
            arm=arm,
            context=context,
            runner_id=None if runner is None else _require_text(runner, f"{field}.runner_id"),
            accepted=None if accepted is None else _require_bool(accepted, f"{field}.accepted"),
            output_digest=None
            if output is None
            else _require_digest(output, f"{field}.output_digest"),
            attempt_count=None
            if attempt_count is None
            else _require_int(attempt_count, f"{field}.attempt_count", minimum=1),
            model_usage_receipt_digests=(
                _require_digest(item, f"{field}.model_usage_receipt_digests")
                for item in _sequence(
                    value["model_usage_receipt_digests"],
                    f"{field}.model_usage_receipt_digests",
                )
            ),
            verifier_receipt_digest=None
            if verifier is None
            else _require_digest(verifier, f"{field}.verifier_receipt_digest"),
            reported_total_tokens=None
            if reported is None
            else _require_int(reported, f"{field}.reported_total_tokens"),
        )
        if value["run_spec_digest"] != run.run_spec_digest:
            raise TokenSavingsError(f"{field}.run_spec_digest does not match its context")
        declared = _require_digest(value["run_digest"], f"{field}.run_digest")
        if declared != run.run_digest:
            raise TokenSavingsError(f"{field} content digest does not match its bytes")
        return run


@dataclass(frozen=True, slots=True)
class TokenSavingsInput:
    label: str
    evidence_note: str
    evidence_class: TokenEvidenceClass
    subject_ref: str
    terminal_receipt_refs: tuple[str, ...]
    baseline: RunArmEvidence
    reuse: RunArmEvidence
    model_usage_receipts: tuple[ModelUsageReceipt, ...]
    verifier_receipts: tuple[VerifierReceipt, ...]
    source_digest: str

    def _payload(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "label": self.label,
            "evidence_note": self.evidence_note,
            "evidence_class": self.evidence_class.value,
            "subject_ref": self.subject_ref,
            "terminal_receipt_refs": list(self.terminal_receipt_refs),
            "baseline": self.baseline.to_dict(),
            "reuse": self.reuse.to_dict(),
            "model_usage_receipts": [item.to_dict() for item in self.model_usage_receipts],
            "verifier_receipts": [item.to_dict() for item in self.verifier_receipts],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "source_digest": self.source_digest}

    @classmethod
    def create(
        cls,
        *,
        label: str,
        evidence_note: str,
        evidence_class: TokenEvidenceClass,
        subject_ref: str,
        terminal_receipt_refs: Iterable[str],
        baseline: RunArmEvidence,
        reuse: RunArmEvidence,
        model_usage_receipts: Iterable[ModelUsageReceipt],
        verifier_receipts: Iterable[VerifierReceipt],
    ) -> "TokenSavingsInput":
        label_value = _require_text(label, "token_savings_input.label")
        note_value = _require_text(
            evidence_note, "token_savings_input.evidence_note"
        )
        if not isinstance(evidence_class, TokenEvidenceClass):
            raise TokenSavingsError("token_savings_input.evidence_class is invalid")
        subject = _require_ref(subject_ref, "token_savings_input.subject_ref")
        terminals = _exact_ref_tuple(
            terminal_receipt_refs,
            "token_savings_input.terminal_receipt_refs",
        )
        usages = tuple(model_usage_receipts)
        verifiers = tuple(verifier_receipts)
        fields = dict(
            label=label_value,
            evidence_note=note_value,
            evidence_class=evidence_class,
            subject_ref=subject,
            terminal_receipt_refs=terminals,
            baseline=baseline,
            reuse=reuse,
            model_usage_receipts=usages,
            verifier_receipts=verifiers,
        )
        provisional = cls(**fields, source_digest="sha256:" + "0" * 64)
        return cls(**fields, source_digest=_content_digest(provisional._payload()))

    @classmethod
    def create_matched_pair(
        cls,
        *,
        label: str,
        evidence_note: str,
        subject_ref: str,
        terminal_receipt_refs: Iterable[str],
        context: MatchedRunContext,
        baseline_runner_id: str,
        baseline_attempt_count: int,
        baseline_model_usage_receipts: Iterable[ModelUsageReceipt],
        baseline_verifier_receipt: VerifierReceipt,
        reuse_runner_id: str,
        reuse_attempt_count: int,
        reuse_model_usage_receipts: Iterable[ModelUsageReceipt],
        reuse_verifier_receipt: VerifierReceipt,
        evidence_class: TokenEvidenceClass = TokenEvidenceClass.CONFORMANCE_FIXTURE,
    ) -> "TokenSavingsInput":
        """Build and immediately validate a resolved matched-pair input.

        Attempt counts come from the run harness rather than being inferred from
        receipt arrays. This independent count lets evaluation detect selective
        omission.
        """

        if evidence_class not in {
            TokenEvidenceClass.CONFORMANCE_FIXTURE,
            TokenEvidenceClass.VERIFIED_REAL_MODEL,
        }:
            raise TokenSavingsError(
                "matched-pair builder requires resolved conformance or real-model evidence"
            )
        baseline_usages = tuple(baseline_model_usage_receipts)
        reuse_usages = tuple(reuse_model_usage_receipts)
        baseline = RunArmEvidence.create(
            arm=ProofArm.BASELINE,
            context=context,
            runner_id=baseline_runner_id,
            accepted=baseline_verifier_receipt.accepted,
            output_digest=baseline_verifier_receipt.output_digest,
            attempt_count=baseline_attempt_count,
            model_usage_receipt_digests=(
                item.receipt_digest for item in baseline_usages
            ),
            verifier_receipt_digest=baseline_verifier_receipt.receipt_digest,
        )
        reuse = RunArmEvidence.create(
            arm=ProofArm.REUSE,
            context=context,
            runner_id=reuse_runner_id,
            accepted=reuse_verifier_receipt.accepted,
            output_digest=reuse_verifier_receipt.output_digest,
            attempt_count=reuse_attempt_count,
            model_usage_receipt_digests=(item.receipt_digest for item in reuse_usages),
            verifier_receipt_digest=reuse_verifier_receipt.receipt_digest,
        )
        source = cls.create(
            label=label,
            evidence_note=evidence_note,
            evidence_class=evidence_class,
            subject_ref=subject_ref,
            terminal_receipt_refs=terminal_receipt_refs,
            baseline=baseline,
            reuse=reuse,
            model_usage_receipts=(*baseline_usages, *reuse_usages),
            verifier_receipts=(
                baseline_verifier_receipt,
                reuse_verifier_receipt,
            ),
        )
        # The builder is fail-closed too: callers never receive a superficially
        # complete object whose receipt graph has not actually resolved.
        evaluate_token_savings(source)
        return source

    @classmethod
    def from_dict(cls, raw: object, field: str = "token_savings_input") -> "TokenSavingsInput":
        value = _mapping(raw, field)
        keys = (
            "format_version",
            "source_digest",
            "label",
            "evidence_note",
            "evidence_class",
            "subject_ref",
            "terminal_receipt_refs",
            "baseline",
            "reuse",
            "model_usage_receipts",
            "verifier_receipts",
        )
        _exact_keys(value, keys, field)
        if value["format_version"] != FORMAT_VERSION:
            raise TokenSavingsError(f"{field}.format_version is unsupported")
        try:
            evidence_class = TokenEvidenceClass(value["evidence_class"])
        except (TypeError, ValueError) as exc:
            raise TokenSavingsError(f"{field}.evidence_class is invalid") from exc
        source = cls.create(
            label=_require_text(value["label"], f"{field}.label"),
            evidence_note=_require_text(
                value["evidence_note"], f"{field}.evidence_note"
            ),
            evidence_class=evidence_class,
            subject_ref=_require_ref(
                value["subject_ref"], f"{field}.subject_ref"
            ),
            terminal_receipt_refs=_exact_ref_tuple(
                (
                    _require_ref(item, f"{field}.terminal_receipt_refs")
                    for item in _sequence(
                        value["terminal_receipt_refs"],
                        f"{field}.terminal_receipt_refs",
                    )
                ),
                f"{field}.terminal_receipt_refs",
            ),
            baseline=RunArmEvidence.from_dict(
                value["baseline"], f"{field}.baseline"
            ),
            reuse=RunArmEvidence.from_dict(value["reuse"], f"{field}.reuse"),
            model_usage_receipts=tuple(
                ModelUsageReceipt.from_dict(item, f"{field}.model_usage_receipts[{index}]")
                for index, item in enumerate(
                    _sequence(value["model_usage_receipts"], f"{field}.model_usage_receipts")
                )
            ),
            verifier_receipts=tuple(
                VerifierReceipt.from_dict(item, f"{field}.verifier_receipts[{index}]")
                for index, item in enumerate(
                    _sequence(value["verifier_receipts"], f"{field}.verifier_receipts")
                )
            ),
        )
        declared = _require_digest(value["source_digest"], f"{field}.source_digest")
        if source.source_digest != declared:
            raise TokenSavingsError(f"{field} content digest does not match its bytes")
        return source

    def evaluate(
        self,
        *,
        trusted_resolver: TrustedEvidenceResolver | None = None,
        trusted_root: TrustedEvidenceTrustRoot | None = None,
    ) -> "TokenSavingsProof":
        return evaluate_token_savings(
            self,
            trusted_resolver=trusted_resolver,
            trusted_root=trusted_root,
        )


@dataclass(frozen=True, slots=True)
class EvidenceIntegrityResult:
    subject_ref: str
    source_digest: str
    evidence_class: TokenEvidenceClass
    proof_digest: str
    covered_receipt_refs: tuple[str, ...]
    provider_receipt_refs: tuple[str, ...]
    source_verifier_refs: tuple[str, ...]
    trust_domain: str | None
    trust_key_id: str | None
    attestation_ref: str | None
    attestation_digest: str | None
    verified: bool

    def __post_init__(self) -> None:
        _require_ref(self.subject_ref, "integrity.subject_ref")
        _require_digest(self.source_digest, "integrity.source_digest")
        if not isinstance(self.evidence_class, TokenEvidenceClass):
            raise TokenSavingsError("integrity.evidence_class is invalid")
        _require_digest(self.proof_digest, "integrity.proof_digest")
        _exact_ref_tuple(self.covered_receipt_refs, "integrity.covered_receipt_refs")
        _exact_ref_tuple(
            self.provider_receipt_refs,
            "integrity.provider_receipt_refs",
            allow_empty=not self.verified,
        )
        _exact_ref_tuple(
            self.source_verifier_refs,
            "integrity.source_verifier_refs",
            allow_empty=not self.verified,
        )
        _require_bool(self.verified, "integrity.verified")
        attestation_fields = (
            self.trust_domain,
            self.trust_key_id,
            self.attestation_ref,
            self.attestation_digest,
        )
        if self.verified:
            if self.evidence_class is not TokenEvidenceClass.VERIFIED_REAL_MODEL:
                raise TokenSavingsError(
                    "only verified_real_model evidence can verify integrity"
                )
            _require_text(self.trust_domain, "integrity.trust_domain")
            _require_ref(self.trust_key_id, "integrity.trust_key_id")
            _require_ref(self.attestation_ref, "integrity.attestation_ref")
            _require_digest(self.attestation_digest, "integrity.attestation_digest")
        elif any(item is not None for item in attestation_fields):
            raise TokenSavingsError(
                "unverified integrity results cannot carry attestation authority"
            )


@dataclass(frozen=True, slots=True)
class TokenSavingsProof:
    label: str
    evidence_note: str
    evidence_class: TokenEvidenceClass
    subject_ref: str
    source_digest: str
    terminal_receipt_refs: tuple[str, ...]
    context_digest: str
    baseline_run_digest: str
    reuse_run_digest: str
    provider_receipt_refs: tuple[str, ...]
    source_verifier_refs: tuple[str, ...]
    baseline_tokens: TokenBreakdown | None
    reuse_tokens: TokenBreakdown | None
    baseline_total_tokens: int
    reuse_total_tokens: int
    token_savings: int
    token_savings_ppm: int
    receipt_integrity_resolved: bool
    attempts_complete: bool
    paired_acceptance: bool | None
    correctness_preserving: bool
    evidence_integrity_verified: bool
    trust_domain: str | None
    trust_key_id: str | None
    attestation_ref: str | None
    attestation_digest: str | None
    savings_claimable: bool
    claim_reason: str | None
    proof_digest: str

    def _payload(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "label": self.label,
            "evidence_note": self.evidence_note,
            "evidence_class": self.evidence_class.value,
            "subject_ref": self.subject_ref,
            "source_digest": self.source_digest,
            "terminal_receipt_refs": list(self.terminal_receipt_refs),
            "context_digest": self.context_digest,
            "baseline_run_digest": self.baseline_run_digest,
            "reuse_run_digest": self.reuse_run_digest,
            "provider_receipt_refs": list(self.provider_receipt_refs),
            "source_verifier_refs": list(self.source_verifier_refs),
            "baseline_tokens": None
            if self.baseline_tokens is None
            else self.baseline_tokens.to_dict(include_totals=True),
            "reuse_tokens": None
            if self.reuse_tokens is None
            else self.reuse_tokens.to_dict(include_totals=True),
            "baseline_total_tokens": self.baseline_total_tokens,
            "reuse_total_tokens": self.reuse_total_tokens,
            "token_savings": self.token_savings,
            "token_savings_ppm": self.token_savings_ppm,
            "receipt_integrity_resolved": self.receipt_integrity_resolved,
            "attempts_complete": self.attempts_complete,
            "paired_acceptance": self.paired_acceptance,
            "correctness_preserving": self.correctness_preserving,
            "evidence_integrity_verified": self.evidence_integrity_verified,
            "trust_domain": self.trust_domain,
            "trust_key_id": self.trust_key_id,
            "attestation_ref": self.attestation_ref,
            "attestation_digest": self.attestation_digest,
            "savings_claimable": self.savings_claimable,
            "claim_reason": self.claim_reason,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "proof_digest": self.proof_digest}

    def integrity_result(self) -> EvidenceIntegrityResult:
        if self.proof_digest != _content_digest(self._payload()):
            raise TokenSavingsError("token-savings proof content digest does not match")
        return EvidenceIntegrityResult(
            subject_ref=self.subject_ref,
            source_digest=self.source_digest,
            evidence_class=self.evidence_class,
            proof_digest=self.proof_digest,
            covered_receipt_refs=self.terminal_receipt_refs,
            provider_receipt_refs=self.provider_receipt_refs,
            source_verifier_refs=self.source_verifier_refs,
            trust_domain=self.trust_domain,
            trust_key_id=self.trust_key_id,
            attestation_ref=self.attestation_ref,
            attestation_digest=self.attestation_digest,
            verified=self.evidence_integrity_verified and self.correctness_preserving,
        )


def _duplicate_digest(values: Iterable[object], attribute: str, field: str) -> None:
    digests = [getattr(item, attribute) for item in values]
    if len(digests) != len(set(digests)):
        raise TokenSavingsError(f"{field} contains duplicate content digests")


def _duplicate_source_ref(
    values: Iterable[object], attribute: str, field: str
) -> None:
    refs = [getattr(item, attribute) for item in values]
    if len(refs) != len(set(refs)):
        raise TokenSavingsError(f"{field} contains a cloned source receipt")


def _context_mismatches(
    baseline: MatchedRunContext, reuse: MatchedRunContext
) -> tuple[str, ...]:
    names = (
        "task_ref",
        "seed",
        "provider_id",
        "model_id",
        "model_config_digest",
        "harness_digest",
        "runtime_digest",
        "policy_digest",
        "oracle_ref",
        "snapshot_ref",
        "budget",
    )
    return tuple(name for name in names if getattr(baseline, name) != getattr(reuse, name))


def _validate_resolved_arm(
    run: RunArmEvidence,
    usage_by_digest: Mapping[str, ModelUsageReceipt],
    verifier_by_digest: Mapping[str, VerifierReceipt],
) -> tuple[TokenBreakdown, set[str], str]:
    if (
        run.runner_id is None
        or run.accepted is None
        or run.output_digest is None
        or run.attempt_count is None
        or run.verifier_receipt_digest is None
        or run.reported_total_tokens is not None
    ):
        raise TokenSavingsError(f"{run.arm.value} arm is missing resolved run evidence")
    if run.attempt_count != len(run.model_usage_receipt_digests):
        raise TokenSavingsError(
            f"{run.arm.value} arm selectively omitted one or more model attempts"
        )
    if run.attempt_count > run.context.budget.max_attempts:
        raise TokenSavingsError(f"{run.arm.value} arm exceeded its attempt budget")
    usages: list[ModelUsageReceipt] = []
    for digest in run.model_usage_receipt_digests:
        try:
            usage = usage_by_digest[digest]
        except KeyError as exc:
            raise TokenSavingsError(
                f"{run.arm.value} arm has an unresolved model usage receipt"
            ) from exc
        if usage.run_spec_digest != run.run_spec_digest:
            raise TokenSavingsError(f"{run.arm.value} model usage belongs to another run")
        if (
            usage.provider_id != run.context.provider_id
            or usage.model_id != run.context.model_id
            or usage.model_config_digest != run.context.model_config_digest
        ):
            raise TokenSavingsError(
                f"{run.arm.value} model usage does not match the frozen provider/model/config"
            )
        if usage.usage.prompt_tokens > run.context.budget.max_prompt_tokens_per_attempt:
            raise TokenSavingsError(f"{run.arm.value} arm exceeded its prompt budget")
        if (
            usage.usage.reasoning_tokens + usage.usage.completion_tokens
            > run.context.budget.max_output_tokens_per_attempt
        ):
            raise TokenSavingsError(f"{run.arm.value} arm exceeded its output budget")
        usages.append(usage)
    if tuple(item.attempt_index for item in usages) != tuple(range(1, run.attempt_count + 1)):
        raise TokenSavingsError(
            f"{run.arm.value} model attempts must be complete, ordered, and contiguous"
        )
    totals = TokenBreakdown.aggregate(item.usage for item in usages)
    observed_tool_calls = sum(item.tool_calls for item in usages)
    if observed_tool_calls > run.context.budget.max_tool_calls:
        raise TokenSavingsError(f"{run.arm.value} arm exceeded its tool-call budget")
    if totals.accounted_total_tokens > run.context.budget.max_total_tokens:
        raise TokenSavingsError(f"{run.arm.value} arm exceeded its total token budget")
    try:
        verifier = verifier_by_digest[run.verifier_receipt_digest]
    except KeyError as exc:
        raise TokenSavingsError(
            f"{run.arm.value} arm has an unresolved verifier receipt"
        ) from exc
    if verifier.run_spec_digest != run.run_spec_digest:
        raise TokenSavingsError(f"{run.arm.value} verifier belongs to another run")
    if verifier.context_digest != run.context.context_digest:
        raise TokenSavingsError(f"{run.arm.value} verifier context does not match")
    if verifier.oracle_ref != run.context.oracle_ref:
        raise TokenSavingsError(f"{run.arm.value} verifier used another oracle")
    if verifier.output_digest != run.output_digest:
        raise TokenSavingsError(f"{run.arm.value} verifier checked another output")
    if verifier.model_usage_receipt_digests != run.model_usage_receipt_digests:
        raise TokenSavingsError(
            f"{run.arm.value} verifier does not cover the exact model attempt set"
        )
    if verifier.accepted != run.accepted:
        raise TokenSavingsError(f"{run.arm.value} acceptance disagrees with its verifier")
    if verifier.verifier_id == run.runner_id:
        raise TokenSavingsError(f"{run.arm.value} verifier is not independent")
    if verifier.observed_run_wall_ms > run.context.budget.max_wall_ms:
        raise TokenSavingsError(f"{run.arm.value} arm exceeded its wall-time budget")
    if verifier.verifier_cpu_ms > run.context.budget.max_verifier_cpu_ms:
        raise TokenSavingsError(
            f"{run.arm.value} arm exceeded its verifier-CPU budget"
        )
    return totals, set(run.model_usage_receipt_digests), verifier.receipt_digest


def _build_proof(
    source: TokenSavingsInput,
    *,
    baseline_tokens: TokenBreakdown | None,
    reuse_tokens: TokenBreakdown | None,
    baseline_total: int,
    reuse_total: int,
    receipt_integrity_resolved: bool,
    attempts_complete: bool,
    paired_acceptance: bool | None,
    correctness_preserving: bool,
    evidence_integrity_verified: bool,
    attestation: TrustedEvidenceAttestation | None,
    savings_claimable: bool,
    claim_reason: str | None,
) -> TokenSavingsProof:
    savings = baseline_total - reuse_total
    fields = dict(
        label=source.label,
        evidence_note=source.evidence_note,
        evidence_class=source.evidence_class,
        subject_ref=source.subject_ref,
        source_digest=source.source_digest,
        terminal_receipt_refs=source.terminal_receipt_refs,
        context_digest=source.baseline.context.context_digest,
        baseline_run_digest=source.baseline.run_digest,
        reuse_run_digest=source.reuse.run_digest,
        provider_receipt_refs=tuple(
            sorted(item.provider_receipt_ref for item in source.model_usage_receipts)
        ),
        source_verifier_refs=tuple(
            sorted(item.source_verifier_ref for item in source.verifier_receipts)
        ),
        baseline_tokens=baseline_tokens,
        reuse_tokens=reuse_tokens,
        baseline_total_tokens=baseline_total,
        reuse_total_tokens=reuse_total,
        token_savings=savings,
        token_savings_ppm=_ppm(savings, baseline_total),
        receipt_integrity_resolved=receipt_integrity_resolved,
        attempts_complete=attempts_complete,
        paired_acceptance=paired_acceptance,
        correctness_preserving=correctness_preserving,
        evidence_integrity_verified=evidence_integrity_verified,
        trust_domain=None if attestation is None else attestation.trust_domain,
        trust_key_id=None if attestation is None else attestation.key_id,
        attestation_ref=None if attestation is None else attestation.attestation_ref,
        attestation_digest=None
        if attestation is None
        else attestation.attestation_digest,
        savings_claimable=savings_claimable,
        claim_reason=claim_reason,
    )
    provisional = TokenSavingsProof(**fields, proof_digest="sha256:" + "0" * 64)
    return TokenSavingsProof(**fields, proof_digest=_content_digest(provisional._payload()))


def _trusted_request(source: TokenSavingsInput) -> TrustedEvidenceRequest:
    return TrustedEvidenceRequest(
        subject_ref=source.subject_ref,
        source_digest=source.source_digest,
        context_digest=source.baseline.context.context_digest,
        baseline_run_digest=source.baseline.run_digest,
        reuse_run_digest=source.reuse.run_digest,
        provider_receipt_refs=tuple(
            sorted(item.provider_receipt_ref for item in source.model_usage_receipts)
        ),
        model_usage_receipt_digests=tuple(
            sorted(item.receipt_digest for item in source.model_usage_receipts)
        ),
        source_verifier_refs=tuple(
            sorted(item.source_verifier_ref for item in source.verifier_receipts)
        ),
        verifier_receipt_digests=tuple(
            sorted(item.receipt_digest for item in source.verifier_receipts)
        ),
        terminal_receipt_refs=source.terminal_receipt_refs,
    )


def _resolve_trusted_attestation(
    request: TrustedEvidenceRequest,
    resolver: TrustedEvidenceResolver | None,
    root: TrustedEvidenceTrustRoot | None,
) -> TrustedEvidenceAttestation | None:
    # A lookup resolver has no authority by itself.  Both halves must be injected
    # by the runtime, and the trust root is never accepted from the resolver or
    # serialized evidence.
    if resolver is None or root is None:
        return None
    if not isinstance(root, TrustedEvidenceTrustRoot):
        raise TokenSavingsError("trusted evidence root has an invalid runtime type")
    if not isinstance(resolver, TrustedEvidenceResolver):
        raise TokenSavingsError("trusted evidence resolver has an invalid runtime type")
    try:
        trust_domain = _require_text(
            resolver.trust_domain, "trusted_resolver.trust_domain"
        )
        key_id = _require_ref(resolver.key_id, "trusted_resolver.key_id")
        attestation = resolver.resolve(request)
    except TokenSavingsError:
        raise
    except Exception as exc:
        raise TokenSavingsError("trusted evidence resolver failed") from exc
    if attestation is None:
        return None
    if not isinstance(attestation, TrustedEvidenceAttestation):
        raise TokenSavingsError("trusted resolver returned an invalid attestation")
    attestation.validate_structure()
    if trust_domain != root.trust_domain or key_id != root.key_id:
        raise TokenSavingsError(
            "trusted resolver is not bound to the configured trust root"
        )
    if (
        attestation.trust_domain != trust_domain
        or attestation.key_id != key_id
    ):
        raise TokenSavingsError("trusted attestation used another trust root")
    if attestation.request != request:
        raise TokenSavingsError(
            "trusted attestation does not bind the exact proof source and receipts"
        )
    if not root.verify(attestation):
        raise TokenSavingsError(
            "trusted attestation signature is not authenticated by the configured root"
        )
    return attestation


def evaluate_token_savings(
    source: TokenSavingsInput,
    *,
    trusted_resolver: TrustedEvidenceResolver | None = None,
    trusted_root: TrustedEvidenceTrustRoot | None = None,
) -> TokenSavingsProof:
    if not isinstance(source, TokenSavingsInput):
        raise TokenSavingsError("token-savings source has an invalid type")
    try:
        # Re-resolve all content digests even for in-memory callers. Constructors
        # are public Python objects, so relying only on JSON loading would permit a
        # dataclass replacement to bypass the content-addressed contract.
        source = TokenSavingsInput.from_dict(source.to_dict())
    except TokenSavingsError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise TokenSavingsError("token-savings source is malformed") from exc
    if source.baseline.arm is not ProofArm.BASELINE:
        raise TokenSavingsError("baseline input is not the baseline arm")
    if source.reuse.arm is not ProofArm.REUSE:
        raise TokenSavingsError("reuse input is not the reuse arm")
    mismatches = _context_mismatches(source.baseline.context, source.reuse.context)
    if mismatches:
        raise TokenSavingsError("matched arms differ in: " + ", ".join(mismatches))

    _duplicate_digest(source.model_usage_receipts, "receipt_digest", "model_usage_receipts")
    _duplicate_digest(source.verifier_receipts, "receipt_digest", "verifier_receipts")
    _duplicate_source_ref(
        source.model_usage_receipts,
        "provider_receipt_ref",
        "model_usage_receipts",
    )
    _duplicate_source_ref(
        source.verifier_receipts,
        "source_verifier_ref",
        "verifier_receipts",
    )

    if source.evidence_class is TokenEvidenceClass.REPORTED_HISTORICAL:
        if source.model_usage_receipts or source.verifier_receipts:
            raise TokenSavingsError(
                "reported historical evidence cannot smuggle unresolved receipts"
            )
        for run in (source.baseline, source.reuse):
            if (
                run.reported_total_tokens is None
                or run.runner_id is not None
                or run.accepted is not None
                or run.output_digest is not None
                or run.attempt_count is not None
                or run.model_usage_receipt_digests
                or run.verifier_receipt_digest is not None
            ):
                raise TokenSavingsError(
                    "reported historical arms must contain totals only when raw evidence is absent"
                )
        assert source.baseline.reported_total_tokens is not None
        assert source.reuse.reported_total_tokens is not None
        return _build_proof(
            source,
            baseline_tokens=None,
            reuse_tokens=None,
            baseline_total=source.baseline.reported_total_tokens,
            reuse_total=source.reuse.reported_total_tokens,
            receipt_integrity_resolved=False,
            attempts_complete=False,
            paired_acceptance=None,
            correctness_preserving=False,
            evidence_integrity_verified=False,
            attestation=None,
            savings_claimable=False,
            claim_reason="reported historical totals lack raw model-usage and verifier receipts",
        )

    usage_by_digest = {item.receipt_digest: item for item in source.model_usage_receipts}
    verifier_by_digest = {item.receipt_digest: item for item in source.verifier_receipts}
    baseline_tokens, baseline_usage_refs, baseline_verifier_ref = _validate_resolved_arm(
        source.baseline, usage_by_digest, verifier_by_digest
    )
    reuse_tokens, reuse_usage_refs, reuse_verifier_ref = _validate_resolved_arm(
        source.reuse, usage_by_digest, verifier_by_digest
    )
    referenced_usage = baseline_usage_refs | reuse_usage_refs
    if referenced_usage != set(usage_by_digest):
        raise TokenSavingsError(
            "resolved model usage receipts contain unassigned attempts; "
            "selective omission is possible"
        )
    referenced_verifiers = {baseline_verifier_ref, reuse_verifier_ref}
    if referenced_verifiers != set(verifier_by_digest):
        raise TokenSavingsError(
            "resolved verifier receipts do not match the two arms exactly"
        )
    baseline_verifier = verifier_by_digest[baseline_verifier_ref]
    reuse_verifier = verifier_by_digest[reuse_verifier_ref]
    verifier_mismatches = tuple(
        name
        for name in (
            "verifier_id",
            "oracle_ref",
            "verifier_config_digest",
            "tests_total",
        )
        if getattr(baseline_verifier, name) != getattr(reuse_verifier, name)
    )
    if verifier_mismatches:
        raise TokenSavingsError(
            "matched arms differ in verifier conditions: "
            + ", ".join(verifier_mismatches)
        )
    if source.baseline.accepted != source.reuse.accepted:
        raise TokenSavingsError("matched arms have unequal independent acceptance")
    outcome_mismatches = tuple(
        name
        for name in ("tests_passed", "tests_failed")
        if getattr(baseline_verifier, name) != getattr(reuse_verifier, name)
    )
    if outcome_mismatches:
        raise TokenSavingsError(
            "matched arms differ in verifier conditions: "
            + ", ".join(outcome_mismatches)
        )
    paired_acceptance = bool(source.baseline.accepted and source.reuse.accepted)
    if not paired_acceptance:
        raise TokenSavingsError("both matched arms must be independently accepted")
    declared_real = source.evidence_class is TokenEvidenceClass.VERIFIED_REAL_MODEL
    attestation = (
        _resolve_trusted_attestation(
            _trusted_request(source), trusted_resolver, trusted_root
        )
        if declared_real
        else None
    )
    verified_real = declared_real and attestation is not None
    correctness_preserving = verified_real and paired_acceptance
    baseline_total = baseline_tokens.accounted_total_tokens
    reuse_total = reuse_tokens.accounted_total_tokens
    saves_tokens = baseline_total > reuse_total
    claimable = correctness_preserving and saves_tokens
    if not declared_real:
        reason = "synthetic conformance evidence cannot support model efficacy"
    elif attestation is None:
        reason = (
            "verified real-model claims require a resolver attestation authenticated "
            "by a separately configured runtime trust root"
        )
    elif not saves_tokens:
        reason = "the verified matched pair does not save tokens"
    else:
        reason = None
    return _build_proof(
        source,
        baseline_tokens=baseline_tokens,
        reuse_tokens=reuse_tokens,
        baseline_total=baseline_total,
        reuse_total=reuse_total,
        receipt_integrity_resolved=True,
        attempts_complete=True,
        paired_acceptance=paired_acceptance,
        correctness_preserving=correctness_preserving,
        evidence_integrity_verified=verified_real,
        attestation=attestation,
        savings_claimable=claimable,
        claim_reason=reason,
    )


@dataclass(frozen=True, slots=True)
class ProviderNativeCampaignMeasurement:
    """Non-promotable measurement extracted from a serialized live campaign."""

    campaign_ref: str
    source_digest: str
    campaign_format_version: str
    legacy_campaign: bool
    identity_chain_valid: bool
    manifest_complete: bool
    arm_matrix_complete: bool
    pair_matrix_complete: bool
    verification_occurrences_bound: bool
    provider_receipts_unique: bool
    concrete_deployment_bound: bool
    campaign_claimable_independent_execution: bool
    validation_limitations: tuple[str, ...]
    task_count: int
    provider_id: str
    model_requested: str
    model_reported: tuple[str, ...]
    matched_pair_refs: tuple[str, ...]
    terminal_receipt_refs: tuple[str, ...]
    provider_receipt_refs: tuple[str, ...]
    source_verifier_refs: tuple[str, ...]
    pair_count: int
    accepted_pair_count: int
    verified_arm_count: int
    baseline_prompt_tokens: int
    baseline_completion_tokens: int
    reuse_prompt_tokens: int
    reuse_completion_tokens: int
    baseline_total_tokens: int
    reuse_total_tokens: int
    token_savings: int
    token_savings_ppm: int
    measurement_digest: str

    @property
    def paired_acceptance(self) -> bool:
        return self.accepted_pair_count == self.pair_count

    @property
    def receipt_integrity_resolved(self) -> bool:
        return all(
            (
                self.identity_chain_valid,
                self.manifest_complete,
                self.arm_matrix_complete,
                self.pair_matrix_complete,
                self.verification_occurrences_bound,
                self.provider_receipts_unique,
                self.concrete_deployment_bound,
            )
        )

    def _payload(self) -> dict[str, object]:
        expected_arm_count = self.pair_count * 2
        claim_disqualifiers: list[str] = []
        if self.legacy_campaign:
            claim_disqualifiers.append(
                "legacy serialized campaign has unresolved task completeness "
                "and independent verifier occurrences"
            )
        elif self.receipt_integrity_resolved:
            claim_disqualifiers.append(
                "strict serialized campaign completeness is resolved"
            )
        else:
            claim_disqualifiers.append(
                "strict serialized campaign receipt integrity is unresolved"
            )
        if not self.paired_acceptance:
            claim_disqualifiers.append(
                f"only {self.accepted_pair_count}/{self.pair_count} matched pairs "
                "have both conditions accepted"
            )
        if self.verified_arm_count != expected_arm_count:
            claim_disqualifiers.append(
                f"only {self.verified_arm_count}/{expected_arm_count} expected arms "
                "have verifier receipts"
            )
        claim_disqualifiers.append(
            "operator-captured provider-response prompt/completion counters still "
            "lack a trusted runtime attestation and complete overhead receipts "
            "required for a token-savings efficacy claim"
        )
        return {
            "format_version": FORMAT_VERSION,
            "measurement_kind": "prompt_interception_provider_native_v1",
            "evidence_class": "reported_provider_native_campaign",
            "campaign_ref": self.campaign_ref,
            "source_digest": self.source_digest,
            "campaign_validation": {
                "format_version": self.campaign_format_version,
                "legacy": self.legacy_campaign,
                "identity_chain_valid": self.identity_chain_valid,
                "manifest_complete": self.manifest_complete,
                "arm_matrix_complete": self.arm_matrix_complete,
                "pair_matrix_complete": self.pair_matrix_complete,
                "verification_occurrences_bound": (
                    self.verification_occurrences_bound
                ),
                "provider_receipts_unique": self.provider_receipts_unique,
                "concrete_deployment_bound": self.concrete_deployment_bound,
                "claimable_independent_execution": (
                    self.campaign_claimable_independent_execution
                ),
                "task_count": self.task_count,
                "limitations": list(self.validation_limitations),
            },
            "provider_id": self.provider_id,
            "model_requested": self.model_requested,
            "model_reported": list(self.model_reported),
            "matched_pair_refs": list(self.matched_pair_refs),
            "terminal_receipt_refs": list(self.terminal_receipt_refs),
            "provider_receipt_refs": list(self.provider_receipt_refs),
            "source_verifier_refs": list(self.source_verifier_refs),
            "pair_count": self.pair_count,
            "accepted_pair_count": self.accepted_pair_count,
            "paired_acceptance": self.paired_acceptance,
            "verified_arm_count": self.verified_arm_count,
            "expected_arm_count": expected_arm_count,
            "verification_receipts_complete": (
                self.verified_arm_count == expected_arm_count
            ),
            "baseline_prompt_tokens": self.baseline_prompt_tokens,
            "baseline_completion_tokens": self.baseline_completion_tokens,
            "reuse_prompt_tokens": self.reuse_prompt_tokens,
            "reuse_completion_tokens": self.reuse_completion_tokens,
            "baseline_total_tokens": self.baseline_total_tokens,
            "reuse_total_tokens": self.reuse_total_tokens,
            "token_savings": self.token_savings,
            "token_savings_ppm": self.token_savings_ppm,
            "accounting_scope": "provider_native_prompt_plus_completion_only",
            "unresolved_token_categories": [
                "cached_prompt_tokens",
                "reasoning_tokens",
                "tool_tokens",
                "selector_tokens",
                "retrieval_tokens",
                "verification_tokens",
                "repair_tokens",
            ],
            "receipt_integrity_resolved": self.receipt_integrity_resolved,
            "evidence_integrity_verified": False,
            "trusted_runtime_attestation_present": False,
            "trust_domain": None,
            "trust_key_id": None,
            "attestation_ref": None,
            "correctness_preserving": False,
            "savings_claimable": False,
            "claim_reason": "; ".join(claim_disqualifiers),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._payload(), "measurement_digest": self.measurement_digest}


def _embedded_identity(
    record: Mapping[str, Any],
    *,
    expected_kind: str,
    field: str,
    expected_key: Mapping[str, Any] | None = None,
) -> str:
    identity = _mapping(record.get("identity"), f"{field}.identity")
    _exact_keys(identity, ("id", "kind", "canonical_key"), f"{field}.identity")
    reference = _require_ref(identity["id"], f"{field}.identity.id")
    kind = _require_text(identity["kind"], f"{field}.identity.kind")
    if kind != expected_kind:
        raise TokenSavingsError(f"{field} has the wrong identity kind")
    canonical_key = _mapping(
        identity["canonical_key"], f"{field}.identity.canonical_key"
    )
    try:
        IdentityRecord(reference, kind, canonical_key).validate()
    except ValueError as exc:
        raise TokenSavingsError(f"{field} has an invalid content identity") from exc
    bound_key = (
        {key: value for key, value in record.items() if key != "identity"}
        if expected_key is None
        else dict(expected_key)
    )
    if canonical_key != bound_key:
        raise TokenSavingsError(
            f"{field} fields do not match its content-addressed identity"
        )
    return reference


def _campaign_usage(
    raw: object,
    *,
    field: str,
    provider_id: str,
    model_requested: str,
) -> tuple[str, str, int, int]:
    usage = _mapping(raw, field)
    reference = _embedded_identity(
        usage,
        expected_kind="model_usage_receipt",
        field=field,
    )
    if usage.get("format_version") != FORMAT_VERSION:
        raise TokenSavingsError(f"{field}.format_version is unsupported")
    if usage.get("provider_id") != provider_id:
        raise TokenSavingsError(f"{field} used another provider")
    if usage.get("model_requested") != model_requested:
        raise TokenSavingsError(f"{field} requested another model")
    reported = _require_text(usage.get("model_reported"), f"{field}.model_reported")
    for name in ("request_digest", "response_digest", "content_digest"):
        _require_digest(usage.get(name), f"{field}.{name}")
    _require_text(usage.get("usage_source"), f"{field}.usage_source")
    prompt = _require_int(usage.get("prompt_tokens"), f"{field}.prompt_tokens")
    completion = _require_int(
        usage.get("completion_tokens"), f"{field}.completion_tokens"
    )
    return reference, reported, prompt, completion


def measure_prompt_interception_campaign(
    raw: object,
    field: str = "prompt_interception_campaign",
) -> ProviderNativeCampaignMeasurement:
    """Validate and measure a serialized campaign without granting trust authority."""

    campaign = _mapping(raw, field)
    # The campaign module owns the format-versioned identity, manifest, task x seed
    # matrix, occurrence, and deployment contracts.  Counter extraction below is
    # intentionally downstream of that reusable strict validator.
    from .prompt_interception import (
        PromptInterceptionError,
        validate_prompt_interception_campaign_document,
    )

    try:
        validation = validate_prompt_interception_campaign_document(
            campaign, allow_legacy=True
        )
    except PromptInterceptionError as exc:
        raise TokenSavingsError(
            f"{field} content-addressed identity/campaign validation failed: {exc}"
        ) from exc
    provider = _require_text(campaign["provider_id"], f"{field}.provider_id")
    model = _require_text(campaign["model_requested"], f"{field}.model_requested")
    _require_text(campaign["claim_scope"], f"{field}.claim_scope")
    _require_digest(campaign["catalog_digest"], f"{field}.catalog_digest")
    _require_digest(campaign["task_set_digest"], f"{field}.task_set_digest")
    _require_int(
        campaign["max_completion_tokens"],
        f"{field}.max_completion_tokens",
        minimum=1,
    )
    _require_int(campaign["shortlist_limit"], f"{field}.shortlist_limit", minimum=1)
    seeds = _sequence(campaign["seeds"], f"{field}.seeds")
    if not seeds:
        raise TokenSavingsError(f"{field}.seeds cannot be empty")
    for index, seed in enumerate(seeds):
        _require_int(seed, f"{field}.seeds[{index}]")

    arms_raw = _sequence(campaign["arms"], f"{field}.arms")
    pairs_raw = _sequence(campaign["matched_pairs"], f"{field}.matched_pairs")
    if not arms_raw or not pairs_raw:
        raise TokenSavingsError(f"{field} has no completed matched pairs")
    arm_by_ref: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(arms_raw):
        arm = _mapping(item, f"{field}.arms[{index}]")
        reference = _embedded_identity(
            arm,
            expected_kind="prompt_interception_campaign_arm_receipt",
            field=f"{field}.arms[{index}]",
        )
        if reference in arm_by_ref:
            raise TokenSavingsError(f"{field}.arms contains duplicate terminals")
        arm_by_ref[reference] = arm

    pair_refs: list[str] = []
    terminal_refs: set[str] = set()
    provider_refs: list[str] = []
    verifier_refs: set[str] = set()
    reported_models: set[str] = set()
    baseline_prompt = baseline_completion = 0
    reuse_prompt = reuse_completion = 0
    accepted_pairs = 0
    verified_arms = 0
    context_fields = (
        "trajectory_id",
        "task_id",
        "step_index",
        "attempt_index",
        "request_digest",
        "provider_id",
        "model_requested",
        "seed",
        "max_completion_tokens",
    )
    for index, item in enumerate(pairs_raw):
        pair_field = f"{field}.matched_pairs[{index}]"
        pair = _mapping(item, pair_field)
        pair_ref = _embedded_identity(
            pair,
            expected_kind="matched_prompt_interception_pair",
            field=pair_field,
        )
        pair_refs.append(pair_ref)
        if pair.get("provider_id") != provider or pair.get("model_requested") != model:
            raise TokenSavingsError(f"{pair_field} differs from its campaign context")
        full_ref = _require_ref(
            pair.get("full_catalog_arm_id"), f"{pair_field}.full_catalog_arm_id"
        )
        reuse_ref = _require_ref(
            pair.get("shortlist_arm_id"), f"{pair_field}.shortlist_arm_id"
        )
        if full_ref == reuse_ref:
            raise TokenSavingsError(f"{pair_field} cloned one terminal across both arms")
        try:
            full_arm = arm_by_ref[full_ref]
            reuse_arm = arm_by_ref[reuse_ref]
        except KeyError as exc:
            raise TokenSavingsError(f"{pair_field} has an unresolved terminal arm") from exc
        terminal_refs.update((full_ref, reuse_ref))
        if full_arm.get("retrieval_arm") != "full_catalog":
            raise TokenSavingsError(f"{pair_field} full-catalog arm is reversed")
        if reuse_arm.get("retrieval_arm") != "deterministic_shortlist":
            raise TokenSavingsError(f"{pair_field} shortlist arm is reversed")
        for name in context_fields:
            if full_arm.get(name) != pair.get(name) or reuse_arm.get(name) != pair.get(name):
                raise TokenSavingsError(f"{pair_field} differs in matched field {name}")

        full_usage_raw = pair.get("full_catalog_usage")
        reuse_usage_raw = pair.get("shortlist_usage")
        if full_usage_raw is None or reuse_usage_raw is None:
            raise TokenSavingsError(
                f"{pair_field} is missing operator-captured provider-response usage"
            )
        full_usage_ref, full_model, full_prompt, full_completion = _campaign_usage(
            full_usage_raw,
            field=f"{pair_field}.full_catalog_usage",
            provider_id=provider,
            model_requested=model,
        )
        reuse_usage_ref, reuse_model, prompt, completion = _campaign_usage(
            reuse_usage_raw,
            field=f"{pair_field}.shortlist_usage",
            provider_id=provider,
            model_requested=model,
        )
        provider_refs.extend((full_usage_ref, reuse_usage_ref))
        reported_models.update((full_model, reuse_model))
        baseline_prompt += full_prompt
        baseline_completion += full_completion
        reuse_prompt += prompt
        reuse_completion += completion

        full_interception = _mapping(
            full_arm.get("interception"), f"{pair_field}.full_arm.interception"
        )
        reuse_interception = _mapping(
            reuse_arm.get("interception"), f"{pair_field}.reuse_arm.interception"
        )
        if full_interception.get("model_usage") != full_usage_raw:
            raise TokenSavingsError(f"{pair_field} full usage does not resolve to its arm")
        if reuse_interception.get("model_usage") != reuse_usage_raw:
            raise TokenSavingsError(f"{pair_field} reuse usage does not resolve to its arm")

        full_accepted = _require_bool(
            pair.get("full_catalog_accepted"),
            f"{pair_field}.full_catalog_accepted",
        )
        reuse_accepted = _require_bool(
            pair.get("shortlist_accepted"), f"{pair_field}.shortlist_accepted"
        )
        for arm_name, arm, declared_ref, occurrence_ref, accepted in (
            (
                "full",
                full_arm,
                pair.get("full_catalog_verifier_id"),
                pair.get("full_catalog_verification_occurrence_id"),
                full_accepted,
            ),
            (
                "reuse",
                reuse_arm,
                pair.get("shortlist_verifier_id"),
                pair.get("shortlist_verification_occurrence_id"),
                reuse_accepted,
            ),
        ):
            verification_raw = arm.get("verification")
            if verification_raw is None:
                if declared_ref is not None or occurrence_ref is not None or accepted:
                    raise TokenSavingsError(
                        f"{pair_field} {arm_name} verifier reference is unresolved"
                    )
                continue
            verification = _mapping(
                verification_raw,
                f"{pair_field}.{arm_name}_arm.verification",
            )
            verifier_ref = _embedded_identity(
                verification,
                expected_kind="independent_primitive_verification_receipt",
                field=f"{pair_field}.{arm_name}_arm.verification",
            )
            if verifier_ref != declared_ref:
                raise TokenSavingsError(
                    f"{pair_field} {arm_name} verifier reference is unresolved"
                )
            if verification.get("accepted") is not accepted:
                raise TokenSavingsError(
                    f"{pair_field} {arm_name} acceptance is unresolved"
                )
            if validation.verification_occurrences_bound:
                verifier_refs.add(
                    _require_ref(
                        occurrence_ref,
                        f"{pair_field}.{arm_name}_verification_occurrence_id",
                    )
                )
            else:
                verifier_refs.add(verifier_ref)
            verified_arms += 1
        accepted_pairs += int(full_accepted and reuse_accepted)

    if len(provider_refs) != len(set(provider_refs)):
        raise TokenSavingsError(
            f"{field} cloned a provider source receipt across attempts"
        )
    if len(pair_refs) != len(set(pair_refs)):
        raise TokenSavingsError(f"{field} contains duplicate matched pairs")
    if terminal_refs != set(arm_by_ref):
        raise TokenSavingsError(f"{field} contains unassigned terminal arms")
    campaign_ref = _require_ref(validation.campaign_id, f"{field}.identity.id")
    baseline_total = baseline_prompt + baseline_completion
    reuse_total = reuse_prompt + reuse_completion
    savings = baseline_total - reuse_total
    fields = dict(
        campaign_ref=campaign_ref,
        source_digest=_content_digest(campaign),
        campaign_format_version=validation.format_version,
        legacy_campaign=validation.legacy,
        identity_chain_valid=validation.identity_chain_valid,
        manifest_complete=validation.manifest_complete,
        arm_matrix_complete=validation.arm_matrix_complete,
        pair_matrix_complete=validation.pair_matrix_complete,
        verification_occurrences_bound=validation.verification_occurrences_bound,
        provider_receipts_unique=validation.provider_receipts_unique,
        concrete_deployment_bound=validation.concrete_deployment_bound,
        campaign_claimable_independent_execution=(
            validation.claimable_independent_execution
        ),
        validation_limitations=validation.limitations,
        task_count=validation.task_count,
        provider_id=provider,
        model_requested=model,
        model_reported=tuple(sorted(reported_models)),
        matched_pair_refs=tuple(sorted(pair_refs)),
        terminal_receipt_refs=tuple(sorted(terminal_refs)),
        provider_receipt_refs=tuple(sorted(provider_refs)),
        source_verifier_refs=tuple(sorted(verifier_refs)),
        pair_count=len(pair_refs),
        accepted_pair_count=accepted_pairs,
        verified_arm_count=verified_arms,
        baseline_prompt_tokens=baseline_prompt,
        baseline_completion_tokens=baseline_completion,
        reuse_prompt_tokens=reuse_prompt,
        reuse_completion_tokens=reuse_completion,
        baseline_total_tokens=baseline_total,
        reuse_total_tokens=reuse_total,
        token_savings=savings,
        token_savings_ppm=_ppm(savings, baseline_total),
    )
    provisional = ProviderNativeCampaignMeasurement(
        **fields, measurement_digest="sha256:" + "0" * 64
    )
    return ProviderNativeCampaignMeasurement(
        **fields,
        measurement_digest=_content_digest(provisional._payload()),
    )


def measure_prompt_interception_campaign_file(
    path: str | Path,
) -> ProviderNativeCampaignMeasurement:
    source = Path(path)
    try:
        raw = json.loads(source.read_text("utf-8"))
    except OSError as exc:
        raise TokenSavingsError(f"cannot read campaign input: {source}") from exc
    except json.JSONDecodeError as exc:
        raise TokenSavingsError(
            f"invalid campaign JSON at line {exc.lineno} column {exc.colno}"
        ) from exc
    return measure_prompt_interception_campaign(raw)


def load_token_savings_inputs(path: str | Path) -> tuple[TokenSavingsInput, ...]:
    source = Path(path)
    try:
        text = source.read_text("utf-8")
    except OSError as exc:
        raise TokenSavingsError(f"cannot read token-savings input: {source}") from exc
    try:
        if source.suffix.lower() == ".jsonl":
            values = [
                json.loads(line)
                for line_number, line in enumerate(text.splitlines(), start=1)
                if line.strip()
            ]
            if not values:
                raise TokenSavingsError("JSONL token-savings input is empty")
        else:
            decoded = json.loads(text)
            values = decoded if isinstance(decoded, list) else [decoded]
            if not values:
                raise TokenSavingsError("JSON token-savings input is empty")
    except json.JSONDecodeError as exc:
        raise TokenSavingsError(
            f"invalid token-savings JSON at line {exc.lineno} column {exc.colno}"
        ) from exc
    return tuple(
        TokenSavingsInput.from_dict(value, f"token_savings_inputs[{index}]")
        for index, value in enumerate(values)
    )


def evaluate_token_savings_file(path: str | Path) -> tuple[TokenSavingsProof, ...]:
    return tuple(item.evaluate() for item in load_token_savings_inputs(path))
