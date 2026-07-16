"""Universal, typed representation variants and deterministic search enrichment.

The graph kernel stores representation content separately from assertions and
generation attempts.  This lets identical output bytes deduplicate while every
model run, extractor version, scope, confidence, and evidence trail remains
independently queryable.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .canonical import canonical_digest
from .contracts import (
    EvidenceLevel,
    GenerationRun,
    GraphBundle,
    LineageAssertion,
    Modality,
    Polarity,
    ProducerRef,
    RepresentationAssertion,
    RepresentationContent,
    SubjectRef,
    TypedValue,
    ValueKind,
)

_KEY = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
INDEX_LANES = frozenset({"exact", "lexical", "facet", "scalar", "blocking", "vector", "graph"})


@dataclass(frozen=True, slots=True)
class RepresentationDescriptor:
    family_key: str
    representation_key: str
    schema_version: str
    authority: str
    applies_to: tuple[str, ...]
    allowed_value_kinds: tuple[ValueKind, ...]
    index_lanes: tuple[str, ...]
    missing_value_semantics: str = "unknown"
    merge_semantics: str = "retain_parallel_assertions"
    status: str = "experimental"

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.family_key) or not _KEY.fullmatch(self.representation_key):
            raise ValueError("representation descriptor keys must be namespaced")
        if not _VERSION.fullmatch(self.schema_version):
            raise ValueError("invalid representation descriptor version")
        if not self.authority or not self.applies_to or not self.allowed_value_kinds:
            raise ValueError("descriptor authority, subjects, and value kinds are required")
        if not set(self.index_lanes).issubset(INDEX_LANES):
            raise ValueError("descriptor declares an unknown index lane")
        if self.missing_value_semantics not in {"unknown", "not_applicable", "empty_is_meaningful"}:
            raise ValueError("missing-value semantics must be explicit")

    @property
    def descriptor_digest(self) -> str:
        return canonical_digest(
            {
                "family_key": self.family_key,
                "representation_key": self.representation_key,
                "schema_version": self.schema_version,
                "authority": self.authority,
                "applies_to": self.applies_to,
                "allowed_value_kinds": tuple(item.value for item in self.allowed_value_kinds),
                "index_lanes": self.index_lanes,
                "missing_value_semantics": self.missing_value_semantics,
                "merge_semantics": self.merge_semantics,
                "status": self.status,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_key": self.family_key,
            "representation_key": self.representation_key,
            "schema_version": self.schema_version,
            "authority": self.authority,
            "applies_to": list(self.applies_to),
            "allowed_value_kinds": [item.value for item in self.allowed_value_kinds],
            "index_lanes": list(self.index_lanes),
            "missing_value_semantics": self.missing_value_semantics,
            "merge_semantics": self.merge_semantics,
            "status": self.status,
            "descriptor_digest": self.descriptor_digest,
        }


class RepresentationRegistry:
    """Add-only registry; a published key/version can never be reinterpreted."""

    def __init__(self) -> None:
        self._descriptors: dict[tuple[str, str], RepresentationDescriptor] = {}

    def register(self, descriptor: RepresentationDescriptor) -> None:
        key = (descriptor.representation_key, descriptor.schema_version)
        existing = self._descriptors.get(key)
        if existing and existing.descriptor_digest != descriptor.descriptor_digest:
            raise ValueError(
                f"cannot reinterpret {descriptor.representation_key}@{descriptor.schema_version}"
            )
        self._descriptors[key] = descriptor

    def register_many(self, descriptors: Iterable[RepresentationDescriptor]) -> None:
        for descriptor in descriptors:
            self.register(descriptor)

    def resolve(self, representation_key: str, schema_version: str) -> RepresentationDescriptor:
        try:
            return self._descriptors[(representation_key, schema_version)]
        except KeyError as exc:
            raise KeyError(
                f"unknown representation {representation_key}@{schema_version}"
            ) from exc

    def descriptors(self) -> tuple[RepresentationDescriptor, ...]:
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))

    def manifest(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.descriptors()]


def core_representation_registry() -> RepresentationRegistry:
    registry = RepresentationRegistry()
    authority = "https://taedri.dev/representation-registry"

    def descriptor(
        family: str,
        key: str,
        kinds: tuple[ValueKind, ...],
        lanes: tuple[str, ...],
        subjects: tuple[str, ...] = ("entity",),
    ) -> RepresentationDescriptor:
        return RepresentationDescriptor(
            family,
            key,
            "1.0.0",
            authority,
            subjects,
            kinds,
            lanes,
        )

    registry.register_many(
        (
            descriptor("uceg.family.name", "uceg.name.native", (ValueKind.TEXT,), ("exact", "lexical")),
            descriptor("uceg.family.name", "uceg.name.qualified", (ValueKind.TEXT,), ("exact", "lexical")),
            descriptor("uceg.family.lexical", "uceg.lexical.identifier_tokens", (ValueKind.JSON,), ("lexical",)),
            descriptor("uceg.family.label", "uceg.label.entity_kind", (ValueKind.KEYWORD,), ("facet", "exact")),
            descriptor("uceg.family.label", "uceg.label.language", (ValueKind.KEYWORD,), ("facet", "exact")),
            descriptor("uceg.family.label", "uceg.label.module", (ValueKind.KEYWORD,), ("facet", "lexical")),
            descriptor("uceg.family.label", "uceg.label.package", (ValueKind.KEYWORD,), ("facet", "exact")),
            descriptor("uceg.family.label", "uceg.label.lifecycle", (ValueKind.KEYWORD,), ("facet", "exact")),
            descriptor("uceg.family.metric", "uceg.metric.name_length", (ValueKind.INTEGER,), ("scalar",)),
            descriptor("uceg.family.metric", "uceg.metric.qualified_depth", (ValueKind.INTEGER,), ("scalar",)),
            descriptor("uceg.family.blocking", "uceg.block.identifier", (ValueKind.JSON,), ("blocking",)),
            descriptor("uceg.family.blocking", "uceg.block.fingerprint_lsh", (ValueKind.JSON,), ("blocking",)),
            descriptor("uceg.family.embedding", "uceg.embedding.lexical_hash64", (ValueKind.DENSE_VECTOR,), ("vector",)),
            descriptor("uceg.family.description", "uceg.description.source.docstring", (ValueKind.TEXT,), ("lexical",)),
            descriptor("uceg.family.description", "uceg.description.deterministic.synopsis", (ValueKind.TEXT,), ("lexical",)),
            descriptor("uceg.family.fingerprint", "uceg.fingerprint.python.ast_sha256", (ValueKind.DIGEST, ValueKind.JSON), ("exact",)),
            descriptor("uceg.family.fingerprint", "uceg.fingerprint.python.token_simhash64", (ValueKind.KEYWORD, ValueKind.JSON), ("exact", "blocking")),
            descriptor("uceg.family.fingerprint", "uceg.fingerprint.python.token_minhash16", (ValueKind.JSON,), ("blocking",)),
            descriptor("uceg.family.aspect", "uceg.aspect.python.signature", (ValueKind.JSON,), ("lexical",)),
            descriptor("uceg.family.aspect", "uceg.aspect.python.decorators", (ValueKind.JSON,), ("lexical", "facet")),
            descriptor("uceg.family.aspect", "uceg.aspect.python.binding_role", (ValueKind.TEXT, ValueKind.KEYWORD), ("facet", "lexical")),
            descriptor("uceg.family.aspect", "uceg.aspect.python.annotation", (ValueKind.TEXT,), ("lexical",)),
            descriptor("uceg.family.artifact", "uceg.artifact.digest", (ValueKind.DIGEST,), ("exact",), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.filename", (ValueKind.TEXT,), ("exact", "lexical"), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.pypi.name", (ValueKind.KEYWORD,), ("exact", "facet"), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.pypi.version", (ValueKind.KEYWORD,), ("exact", "facet"), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.python.requires", (ValueKind.TEXT,), ("lexical", "facet"), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.dependency", (ValueKind.TEXT,), ("lexical", "facet"), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.project_url", (ValueKind.JSON,), ("lexical",), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.record_verification", (ValueKind.JSON,), (), ("snapshot",)),
            descriptor("uceg.family.artifact", "uceg.artifact.core_metadata", (ValueKind.JSON,), ("lexical",), ("snapshot",)),
            descriptor("uceg.family.license", "uceg.license.declared.spdx", (ValueKind.TEXT,), ("exact", "facet", "lexical"), ("snapshot", "file")),
            descriptor("uceg.family.license", "uceg.license.declared.raw", (ValueKind.TEXT,), ("lexical",), ("snapshot", "file")),
            descriptor("uceg.family.license", "uceg.license.classifier", (ValueKind.TEXT,), ("facet", "lexical"), ("snapshot",)),
            descriptor("uceg.family.license", "uceg.license.file", (ValueKind.JSON,), ("lexical",), ("snapshot", "file")),
            descriptor("uceg.family.router", "uceg.router.decision", (ValueKind.JSON,), ("lexical",), ("snapshot", "analysis")),
        )
    )
    return registry


@dataclass(frozen=True, slots=True)
class RepresentationSeed:
    subject: SubjectRef
    family_key: str
    representation_key: str
    typed_value: TypedValue
    evidence_ids: tuple[str, ...] = ()
    input_ref: SubjectRef | None = None
    modality: Modality = Modality.EXTRACTED
    polarity: Polarity = Polarity.POSITIVE
    confidence_ppm: int | None = None
    scope: Any = None
    lifecycle: EvidenceLevel = EvidenceLevel.STRUCTURED


def materialize_seeds(
    bundle: GraphBundle,
    seeds: Iterable[RepresentationSeed],
    *,
    producer: ProducerRef,
    attempt_key: str,
    environment: Any = None,
) -> GenerationRun:
    """Materialize one receipt-producing batch without overwriting prior variants."""

    prepared: list[tuple[RepresentationSeed, RepresentationContent]] = []
    for seed in seeds:
        content = RepresentationContent.create(
            family_key=seed.family_key,
            representation_key=seed.representation_key,
            schema_version="1.0.0",
            typed_value=seed.typed_value,
        )
        bundle.representation_contents.setdefault(content.identity.id, content)
        prepared.append((seed, content))
    run = GenerationRun.create(
        snapshot_id=bundle.snapshot.identity.id,
        attempt_key=attempt_key,
        producer=producer,
        input_refs=(bundle.snapshot.identity.id, bundle.analysis.identity.id),
        output_content_ids=(content.identity.id for _, content in prepared),
        environment=environment,
    )
    bundle.generation_runs[run.identity.id] = run
    for seed, content in prepared:
        assertion = RepresentationAssertion.create(
            snapshot_id=bundle.snapshot.identity.id,
            subject=seed.subject,
            content_id=content.identity.id,
            modality=seed.modality,
            polarity=seed.polarity,
            producer=producer,
            generation_run_id=run.identity.id,
            evidence_ids=seed.evidence_ids,
            confidence_ppm=seed.confidence_ppm,
            scope=seed.scope,
            lifecycle=seed.lifecycle,
        )
        bundle.representation_assertions[assertion.identity.id] = assertion
        if seed.input_ref is not None:
            lineage = LineageAssertion.create(
                snapshot_id=bundle.snapshot.identity.id,
                predicate_key="uceg.lineage.derived_from",
                source=SubjectRef("representation_content", content.identity.id),
                target=seed.input_ref,
                producer=producer,
                generation_run_id=run.identity.id,
                evidence_ids=seed.evidence_ids,
            )
            bundle.lineage[lineage.identity.id] = lineage
    return run


def identifier_tokens(value: str) -> tuple[str, ...]:
    expanded = _CAMEL.sub(" ", value.replace("_", " ").replace("-", " "))
    tokens = {item.lower() for item in _WORD.findall(expanded)}
    tokens.update(item.lower() for item in _WORD.findall(value))
    return tuple(sorted(tokens))


def identifier_blocking_keys(native_name: str, qualified_name: str) -> tuple[str, ...]:
    normalized = re.sub(r"[^a-z0-9]+", "", native_name.lower())
    keys = {f"exact:{native_name.casefold()}", f"qualified:{qualified_name.casefold()}"}
    if normalized:
        keys.add(f"prefix:{normalized[: min(6, len(normalized))]}")
        keys.add(f"suffix:{normalized[-min(6, len(normalized)): ]}")
        for index in range(max(0, len(normalized) - 2)):
            keys.add(f"tri:{normalized[index:index + 3]}")
    return tuple(sorted(keys))


def lexical_hash_vector(text: str, dimensions: int = 64) -> tuple[int, ...]:
    """Deterministic signed feature hashing; explicitly not a semantic embedding."""

    import hashlib

    values = [0] * dimensions
    for token in identifier_tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        values[index] += 1 if digest[4] & 1 else -1
    maximum = max((abs(item) for item in values), default=0)
    if maximum > 8:
        values = [round(item * 8 / maximum) for item in values]
    return tuple(values)


def _typed_from_legacy(value: Any, key: str) -> TypedValue:
    if isinstance(value, dict) and set(value) == {"text"} and isinstance(value["text"], str):
        return TypedValue(ValueKind.TEXT, value["text"])
    if isinstance(value, dict) and set(value) == {"digest"} and isinstance(value["digest"], str):
        return TypedValue(ValueKind.DIGEST, value["digest"])
    if isinstance(value, str):
        kind = ValueKind.KEYWORD if key.endswith(("binding_role", "simhash64")) else ValueKind.TEXT
        return TypedValue(kind, value)
    if isinstance(value, bool):
        return TypedValue(ValueKind.BOOLEAN, value)
    if isinstance(value, int):
        return TypedValue(ValueKind.INTEGER, value)
    return TypedValue(ValueKind.JSON, value)


def core_entity_seeds(bundle: GraphBundle) -> list[RepresentationSeed]:
    seeds: list[RepresentationSeed] = []
    lexical_by_entity: dict[str, list[str]] = defaultdict(list)
    for projection in bundle.projections.values():
        if projection.subject.subject_kind != "entity":
            continue
        if projection.projection_key.startswith("uceg.description."):
            lexical_by_entity[projection.subject.id].append(_typed_from_legacy(
                projection.payload, projection.projection_key
            ).value)
    lsh_by_entity: dict[str, list[str]] = defaultdict(list)
    for projection in bundle.projections.values():
        if projection.subject.subject_kind != "entity" or not isinstance(projection.payload, dict):
            continue
        if projection.projection_key.endswith("token_simhash64"):
            value = projection.payload.get("value")
            if isinstance(value, str) and len(value) == 16:
                for band in range(4):
                    lsh_by_entity[projection.subject.id].append(
                        f"simhash16:b{band}:{value[band * 4:(band + 1) * 4]}"
                    )
        elif projection.projection_key.endswith("token_minhash16"):
            values = projection.payload.get("values")
            if isinstance(values, list) and len(values) == 16:
                for band in range(4):
                    band_values = values[band * 4:(band + 1) * 4]
                    lsh_by_entity[projection.subject.id].append(
                        f"minhash4:b{band}:{canonical_digest(band_values).removeprefix('sha256:')[:16]}"
                    )
    evidence_by_entity: dict[str, tuple[str, ...]] = defaultdict(tuple)
    for entity in bundle.entities.values():
        if entity.defining_occurrence_id:
            occurrence = bundle.occurrences.get(entity.defining_occurrence_id)
            if occurrence:
                evidence_by_entity[entity.identity.id] = tuple(
                    evidence.identity.id
                    for evidence in bundle.evidence.values()
                    if evidence.source_file_id == occurrence.source_file_id
                    and evidence.byte_range == occurrence.byte_range
                )[:1]
    for entity in sorted(bundle.entities.values(), key=lambda item: item.identity.id):
        subject = SubjectRef("entity", entity.identity.id)
        evidence = evidence_by_entity[entity.identity.id]
        tokens = identifier_tokens(f"{entity.native_name} {entity.qualified_name}")
        vector_text = " ".join(
            [entity.qualified_name, *tokens, *lexical_by_entity.get(entity.identity.id, ())]
        )
        direct = (
            ("uceg.family.name", "uceg.name.native", TypedValue(ValueKind.TEXT, entity.native_name)),
            ("uceg.family.name", "uceg.name.qualified", TypedValue(ValueKind.TEXT, entity.qualified_name)),
            ("uceg.family.lexical", "uceg.lexical.identifier_tokens", TypedValue(ValueKind.JSON, list(tokens))),
            ("uceg.family.label", "uceg.label.entity_kind", TypedValue(ValueKind.KEYWORD, entity.entity_kind_key)),
            ("uceg.family.label", "uceg.label.language", TypedValue(ValueKind.KEYWORD, entity.language_key)),
            ("uceg.family.label", "uceg.label.module", TypedValue(ValueKind.KEYWORD, entity.module_name)),
            ("uceg.family.label", "uceg.label.package", TypedValue(ValueKind.KEYWORD, bundle.snapshot.package_name)),
            ("uceg.family.label", "uceg.label.lifecycle", TypedValue(ValueKind.KEYWORD, entity.lifecycle.value)),
            ("uceg.family.metric", "uceg.metric.name_length", TypedValue(ValueKind.INTEGER, len(entity.native_name))),
            ("uceg.family.metric", "uceg.metric.qualified_depth", TypedValue(ValueKind.INTEGER, entity.qualified_name.count(".") + 1)),
            ("uceg.family.blocking", "uceg.block.identifier", TypedValue(ValueKind.JSON, list(identifier_blocking_keys(entity.native_name, entity.qualified_name)))),
            (
                "uceg.family.embedding",
                "uceg.embedding.lexical_hash64",
                TypedValue(
                    ValueKind.DENSE_VECTOR,
                    {
                        "dimensions": 64,
                        "element_type": "int8",
                        "values": list(lexical_hash_vector(vector_text)),
                    },
                ),
            ),
        )
        seeds.extend(
            RepresentationSeed(subject, family, key, value, evidence_ids=evidence)
            for family, key, value in direct
        )
        if lsh_by_entity.get(entity.identity.id):
            seeds.append(
                RepresentationSeed(
                    subject,
                    "uceg.family.blocking",
                    "uceg.block.fingerprint_lsh",
                    TypedValue(ValueKind.JSON, sorted(lsh_by_entity[entity.identity.id])),
                    evidence_ids=evidence,
                )
            )

    for feature in bundle.features.values():
        seeds.append(
            RepresentationSeed(
                feature.subject,
                "uceg.family.aspect",
                feature.extension_key,
                _typed_from_legacy(feature.typed_value, feature.extension_key),
                feature.evidence_ids,
                SubjectRef("feature", feature.identity.id),
                feature.modality,
                feature.polarity,
            )
        )
    for projection in bundle.projections.values():
        if projection.subject.subject_kind != "entity":
            continue
        if projection.projection_key.startswith("uceg.description."):
            family = "uceg.family.description"
        elif projection.projection_key.startswith("uceg.fingerprint."):
            family = "uceg.family.fingerprint"
        else:
            family = "uceg.family.projection"
        evidence = tuple(ref for ref in projection.input_refs if ref in bundle.evidence)
        seeds.append(
            RepresentationSeed(
                projection.subject,
                family,
                projection.projection_key,
                _typed_from_legacy(projection.payload, projection.projection_key),
                evidence,
                SubjectRef("projection", projection.identity.id),
            )
        )
    return seeds


def enrich_bundle_representations(bundle: GraphBundle) -> GenerationRun:
    producer = ProducerRef(
        "taedri.core-representation-materializer",
        "0.1.0",
        canonical_digest(
            {
                "identifier_tokens": "unicode-word+camel-v1",
                "blocking": "identifier-v1",
                "vector": "signed-feature-hash64-v1",
            }
        ),
    )
    return materialize_seeds(
        bundle,
        core_entity_seeds(bundle),
        producer=producer,
        attempt_key=f"core-search:{bundle.analysis.identity.id}",
        environment={"execution_allowed": False, "network_allowed": False},
    )
