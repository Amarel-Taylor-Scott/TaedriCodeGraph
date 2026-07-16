"""Provider, model-router, and monitor contracts for open-ended enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol

from .canonical import canonical_digest
from .contracts import (
    EvidenceLevel,
    GraphBundle,
    Modality,
    Polarity,
    ProducerRef,
    SubjectRef,
    TypedValue,
    ValueKind,
)
from .representations import (
    RepresentationDescriptor,
    RepresentationRegistry,
    RepresentationSeed,
    core_representation_registry,
    materialize_seeds,
)


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider_key: str
    provider_version: str
    authority: str
    deterministic: bool
    capabilities: tuple[str, ...]
    output_descriptors: tuple[RepresentationDescriptor, ...]
    network_required: bool = False
    target_execution_required: bool = False

    @property
    def descriptor_digest(self) -> str:
        return canonical_digest(
            {
                "provider_key": self.provider_key,
                "provider_version": self.provider_version,
                "authority": self.authority,
                "deterministic": self.deterministic,
                "capabilities": self.capabilities,
                "output_descriptor_digests": tuple(
                    item.descriptor_digest for item in self.output_descriptors
                ),
                "network_required": self.network_required,
                "target_execution_required": self.target_execution_required,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "provider_version": self.provider_version,
            "authority": self.authority,
            "deterministic": self.deterministic,
            "capabilities": list(self.capabilities),
            "output_descriptor_digests": [
                item.descriptor_digest for item in self.output_descriptors
            ],
            "network_required": self.network_required,
            "target_execution_required": self.target_execution_required,
            "descriptor_digest": self.descriptor_digest,
        }


@dataclass(frozen=True, slots=True)
class ProviderInput:
    subject: SubjectRef
    fields: Any
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderOutput:
    family_key: str
    representation_key: str
    typed_value: TypedValue
    confidence_ppm: int | None = None
    polarity: Polarity = Polarity.POSITIVE
    scope: Any = None
    lifecycle: EvidenceLevel = EvidenceLevel.CANDIDATE


class RepresentationProvider(Protocol):
    descriptor: ProviderDescriptor

    def produce(self, request: ProviderInput) -> Iterable[ProviderOutput]: ...


class ProviderRegistry:
    """Registers deterministic labelers, NLP pipelines, LLMs, and embedding models alike."""

    def __init__(self) -> None:
        self._providers: dict[tuple[str, str], RepresentationProvider] = {}

    def register(self, provider: RepresentationProvider) -> None:
        descriptor = provider.descriptor
        key = (descriptor.provider_key, descriptor.provider_version)
        existing = self._providers.get(key)
        if existing and existing.descriptor.descriptor_digest != descriptor.descriptor_digest:
            raise ValueError(
                f"cannot reinterpret provider {descriptor.provider_key}@{descriptor.provider_version}"
            )
        self._providers[key] = provider

    def resolve(self, provider_key: str, provider_version: str) -> RepresentationProvider:
        return self._providers[(provider_key, provider_version)]

    def descriptors(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(
            self._providers[key].descriptor for key in sorted(self._providers)
        )

    def representation_registry(self) -> RepresentationRegistry:
        registry = core_representation_registry()
        for descriptor in self.descriptors():
            registry.register_many(descriptor.output_descriptors)
        return registry


class CallbackProvider:
    """Adapter for an in-process NLP model, remote LLM, or embedding client.

    The callback is deliberately outside the kernel. Callers choose its sandbox,
    credentials, retries, and rate limits, then supply a unique attempt key.
    """

    def __init__(
        self,
        descriptor: ProviderDescriptor,
        callback: Callable[[ProviderInput], Iterable[ProviderOutput]],
    ) -> None:
        self.descriptor = descriptor
        self._callback = callback

    def produce(self, request: ProviderInput) -> Iterable[ProviderOutput]:
        return self._callback(request)


def run_provider(
    bundle: GraphBundle,
    provider: RepresentationProvider,
    requests: Iterable[ProviderInput],
    *,
    attempt_key: str,
    model_config: Any,
) -> str:
    """Run one explicitly authorized provider attempt and retain every output."""

    descriptor = provider.descriptor
    producer = ProducerRef(
        descriptor.provider_key,
        descriptor.provider_version,
        canonical_digest(model_config),
    )
    outputs_by_key = {
        item.representation_key: item for item in descriptor.output_descriptors
    }
    seeds: list[RepresentationSeed] = []
    for request in requests:
        for output in provider.produce(request):
            try:
                declared = outputs_by_key[output.representation_key]
            except KeyError as exc:
                raise ValueError(
                    f"provider emitted undeclared representation {output.representation_key}"
                ) from exc
            if output.family_key != declared.family_key:
                raise ValueError("provider output family does not match its descriptor")
            if output.typed_value.kind not in declared.allowed_value_kinds:
                raise ValueError("provider output has an undeclared value kind")
            seeds.append(
                RepresentationSeed(
                    request.subject,
                    output.family_key,
                    output.representation_key,
                    output.typed_value,
                    request.evidence_ids,
                    input_ref=request.subject,
                    modality=(Modality.EXTRACTED if descriptor.deterministic else Modality.INFERRED),
                    polarity=output.polarity,
                    confidence_ppm=output.confidence_ppm,
                    scope=output.scope,
                    lifecycle=output.lifecycle,
                )
            )
    run = materialize_seeds(
        bundle,
        seeds,
        producer=producer,
        attempt_key=attempt_key,
        environment={
            "provider_descriptor": descriptor.to_dict(),
            "deterministic": descriptor.deterministic,
            "network_required": descriptor.network_required,
            "target_execution_required": descriptor.target_execution_required,
        },
    )
    return run.identity.id


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    provider_key: str
    provider_version: str
    eligible: bool
    reason: str
    estimated_cost_microunits: int | None = None
    estimated_latency_ms: int | None = None


def record_route_decision(
    bundle: GraphBundle,
    *,
    task_key: str,
    policy_key: str,
    policy_version: str,
    candidates: Iterable[RouteCandidate],
    selected_provider: str | None,
    input_digest: str,
    producer: ProducerRef,
    attempt_key: str,
) -> str:
    """Persist a router/monitor decision as another versioned representation."""

    ordered = tuple(candidates)
    seed = RepresentationSeed(
        SubjectRef("snapshot", bundle.snapshot.identity.id),
        "uceg.family.router",
        "uceg.router.decision",
        TypedValue(
            kind=ValueKind.JSON,
            value={
                "task_key": task_key,
                "policy_key": policy_key,
                "policy_version": policy_version,
                "input_digest": input_digest,
                "selected_provider": selected_provider,
                "candidates": [
                    {
                        "provider_key": item.provider_key,
                        "provider_version": item.provider_version,
                        "eligible": item.eligible,
                        "reason": item.reason,
                        "estimated_cost_microunits": item.estimated_cost_microunits,
                        "estimated_latency_ms": item.estimated_latency_ms,
                    }
                    for item in ordered
                ],
            },
        ),
        modality=Modality.OBSERVED,
        lifecycle=EvidenceLevel.STRUCTURED,
    )
    run = materialize_seeds(
        bundle,
        (seed,),
        producer=producer,
        attempt_key=attempt_key,
        environment={"router_monitor": True},
    )
    return run.identity.id
