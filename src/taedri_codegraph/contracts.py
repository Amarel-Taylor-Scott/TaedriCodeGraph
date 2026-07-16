"""Stable UCEG kernel records for the first executable slice.

The kernel is intentionally small. Analyzer-specific meaning belongs in extension
descriptors, feature assertions, and derived projections rather than new nullable
fields on these records.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from .canonical import canonical_digest, sha256_digest, to_primitive
from .identity import IdentityError, IdentityRecord

_KEY = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")


class Modality(str, Enum):
    ASSERTED = "asserted"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    OBSERVED = "observed"
    VERIFIED = "verified"


class Polarity(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class Quantifier(str, Enum):
    MAY = "may"
    MUST = "must"
    OBSERVED = "observed"
    NOT_APPLICABLE = "not_applicable"


class CompletenessState(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    UNSUPPORTED = "unsupported"
    ATTEMPTED_PARTIAL = "attempted_partial"
    COMPLETE_FOR_DECLARED_SYNTAX = "complete_for_declared_syntax"
    RESOLVED_UNDER_ENVIRONMENT = "resolved_under_environment"
    OBSERVED_FOR_WORKLOAD = "observed_for_workload"
    VERIFIED_FOR_CONTRACT = "verified_for_contract"
    UNKNOWN = "unknown"


class EvidenceLevel(str, Enum):
    RAW = "L0_raw"
    CANDIDATE = "L1_candidate"
    STRUCTURED = "L2_structured"
    SOURCE_BACKED = "L3_source_backed"
    TESTED = "L4_tested"
    PROMOTED = "L5_promoted"
    PREFERRED = "L6_preferred"


class ValueKind(str, Enum):
    """Stable wire families for independently governed representations.

    Physical stores may promote these values into native columns or external
    indexes.  The canonical ledger keeps the declared wire kind and value
    together so an experimental representation never changes a kernel table.
    """

    TEXT = "text"
    KEYWORD = "keyword"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    TIMESTAMP = "timestamp"
    URI = "uri"
    DIGEST = "digest"
    JSON = "json"
    DENSE_VECTOR = "dense_vector"
    SPARSE_VECTOR = "sparse_vector"
    DISTRIBUTION = "distribution"
    BYTES_REF = "bytes_ref"


class GraphValidationError(ValueError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("graph validation failed:\n- " + "\n- ".join(self.errors))


class RecordMixin:
    def to_dict(self) -> dict[str, Any]:
        value = to_primitive(self)
        if not isinstance(value, dict):  # pragma: no cover - defensive
            raise TypeError("record did not serialize to a mapping")
        return value


@dataclass(frozen=True, slots=True)
class ProducerRef(RecordMixin):
    id: str
    version: str
    config_digest: str

    def __post_init__(self) -> None:
        if not self.id or not self.version:
            raise ValueError("producer id and version are required")
        if not self.config_digest.startswith("sha256:"):
            raise ValueError("producer config_digest must be sha256-prefixed")


@dataclass(frozen=True, slots=True)
class SubjectRef(RecordMixin):
    subject_kind: str
    id: str

    def __post_init__(self) -> None:
        if not self.subject_kind or not self.id:
            raise ValueError("subject kind and id are required")


@dataclass(frozen=True, slots=True)
class TypedValue(RecordMixin):
    """A canonical value with an explicit logical wire family.

    Decimal and floating-point-like values use decimal strings. Dense vector
    payloads may either contain deterministic integer/decimal-string values or
    a content-addressed external data reference. This avoids platform float
    encodings leaking into exact identities.
    """

    kind: ValueKind
    value: Any

    def __post_init__(self) -> None:
        value = to_primitive(self.value)
        object.__setattr__(self, "value", value)
        valid = False
        if self.kind in {ValueKind.TEXT, ValueKind.KEYWORD, ValueKind.TIMESTAMP, ValueKind.URI}:
            valid = isinstance(value, str)
        elif self.kind is ValueKind.BOOLEAN:
            valid = isinstance(value, bool)
        elif self.kind is ValueKind.INTEGER:
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif self.kind is ValueKind.DECIMAL:
            valid = isinstance(value, str) and bool(
                re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value)
            )
        elif self.kind is ValueKind.DIGEST:
            valid = isinstance(value, str) and value.startswith("sha256:")
        elif self.kind in {ValueKind.JSON, ValueKind.DISTRIBUTION}:
            valid = isinstance(value, dict | list)
        elif self.kind is ValueKind.BYTES_REF:
            valid = (
                isinstance(value, dict)
                and isinstance(value.get("digest"), str)
                and value["digest"].startswith("sha256:")
                and isinstance(value.get("size_bytes"), int)
                and value["size_bytes"] >= 0
            )
        elif self.kind is ValueKind.DENSE_VECTOR:
            valid = _valid_dense_vector(value)
        elif self.kind is ValueKind.SPARSE_VECTOR:
            valid = _valid_sparse_vector(value)
        if not valid:
            raise ValueError(f"value does not conform to {self.kind.value}")


def _valid_dense_vector(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("dimensions"), int):
        return False
    dimensions = value["dimensions"]
    if dimensions <= 0:
        return False
    if "data_ref" in value:
        ref = value["data_ref"]
        return (
            isinstance(ref, dict)
            and isinstance(ref.get("digest"), str)
            and ref["digest"].startswith("sha256:")
        )
    values = value.get("values")
    return (
        isinstance(values, list)
        and len(values) == dimensions
        and all(
            (isinstance(item, int) and not isinstance(item, bool))
            or (isinstance(item, str) and bool(re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", item)))
            for item in values
        )
    )


def _valid_sparse_vector(value: Any) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("dimensions"), int):
        return False
    entries = value.get("entries")
    if value["dimensions"] <= 0 or not isinstance(entries, list):
        return False
    return all(
        isinstance(entry, dict)
        and isinstance(entry.get("index"), int)
        and 0 <= entry["index"] < value["dimensions"]
        and (
            (isinstance(entry.get("value"), int) and not isinstance(entry["value"], bool))
            or isinstance(entry.get("value"), str)
        )
        for entry in entries
    )


@dataclass(frozen=True, slots=True)
class ParticipantRef(RecordMixin):
    role_key: str
    subject: SubjectRef
    ordinal: int | None = None

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.role_key):
            raise ValueError(f"participant role must be namespaced: {self.role_key!r}")
        if self.ordinal is not None and self.ordinal < 0:
            raise ValueError("participant ordinal cannot be negative")


@dataclass(frozen=True, slots=True)
class SourceFileRecord(RecordMixin):
    identity: IdentityRecord
    content_identity: IdentityRecord
    relative_path: str
    content_digest: str
    size_bytes: int
    media_type: str = "text/x-python"

    @classmethod
    def create(
        cls,
        relative_path: str,
        content: bytes,
        media_type: str = "text/x-python",
    ) -> "SourceFileRecord":
        if relative_path.startswith("/") or ".." in relative_path.split("/"):
            raise ValueError(f"source path must be normalized and relative: {relative_path}")
        digest = sha256_digest(content)
        content_identity = IdentityRecord.create(
            "file_content",
            {"content_digest": digest, "size_bytes": len(content)},
        )
        identity = IdentityRecord.create(
            "source_file",
            {
                "relative_path": relative_path,
                "file_content_id": content_identity.id,
            },
        )
        return cls(identity, content_identity, relative_path, digest, len(content), media_type)


@dataclass(frozen=True, slots=True)
class PackageSnapshot(RecordMixin):
    identity: IdentityRecord
    source_kind: str
    source_uri: str
    package_name: str
    release: str | None
    language_key: str
    root_digest: str
    file_ids: tuple[str, ...]
    interpreter: str

    @classmethod
    def create(
        cls,
        *,
        source_kind: str,
        source_uri: str,
        package_name: str,
        release: str | None,
        language_key: str,
        root_digest: str,
        file_ids: Iterable[str],
        interpreter: str,
    ) -> "PackageSnapshot":
        ordered_files = tuple(sorted(file_ids))
        key = {
            "source_kind": source_kind,
            "package_name": package_name,
            "release": release,
            "language_key": language_key,
            "root_digest": root_digest,
            "file_ids": ordered_files,
            "interpreter": interpreter,
        }
        return cls(
            IdentityRecord.create("package_snapshot", key),
            source_kind,
            source_uri,
            package_name,
            release,
            language_key,
            root_digest,
            ordered_files,
            interpreter,
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord(RecordMixin):
    identity: IdentityRecord
    snapshot_id: str
    evidence_type_key: str
    uri: str
    content_digest: str
    producer: ProducerRef
    source_file_id: str | None = None
    file_content_id: str | None = None
    byte_range: tuple[int, int] | None = None

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        evidence_type_key: str,
        uri: str,
        content_digest: str,
        producer: ProducerRef,
        source_file_id: str | None = None,
        file_content_id: str | None = None,
        byte_range: tuple[int, int] | None = None,
    ) -> "EvidenceRecord":
        if not _KEY.fullmatch(evidence_type_key):
            raise ValueError("evidence type must be namespaced")
        if byte_range is not None and not (0 <= byte_range[0] <= byte_range[1]):
            raise ValueError("invalid evidence byte range")
        key = {
            "snapshot_id": snapshot_id,
            "evidence_type_key": evidence_type_key,
            "uri": uri,
            "content_digest": content_digest,
            "producer": producer.to_dict(),
            "source_file_id": source_file_id,
            "file_content_id": file_content_id,
            "byte_range": byte_range,
        }
        return cls(
            IdentityRecord.create("evidence", key),
            snapshot_id,
            evidence_type_key,
            uri,
            content_digest,
            producer,
            source_file_id,
            file_content_id,
            byte_range,
        )


@dataclass(frozen=True, slots=True)
class EntityRecord(RecordMixin):
    identity: IdentityRecord
    snapshot_id: str
    entity_kind_key: str
    language_key: str
    native_name: str
    qualified_name: str
    module_name: str
    defining_occurrence_id: str | None
    enclosing_entity_id: str | None
    lifecycle: EvidenceLevel = EvidenceLevel.SOURCE_BACKED

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        entity_kind_key: str,
        language_key: str,
        native_name: str,
        qualified_name: str,
        module_name: str,
        locator: Mapping[str, Any],
        defining_occurrence_id: str | None = None,
        enclosing_entity_id: str | None = None,
        lifecycle: EvidenceLevel = EvidenceLevel.SOURCE_BACKED,
    ) -> "EntityRecord":
        key = {
            "snapshot_id": snapshot_id,
            "entity_kind_key": entity_kind_key,
            "language_key": language_key,
            "module_name": module_name,
            "qualified_name": qualified_name,
            "locator": dict(locator),
        }
        return cls(
            IdentityRecord.create("entity", key),
            snapshot_id,
            entity_kind_key,
            language_key,
            native_name,
            qualified_name,
            module_name,
            defining_occurrence_id,
            enclosing_entity_id,
            lifecycle,
        )


@dataclass(frozen=True, slots=True)
class OccurrenceRecord(RecordMixin):
    identity: IdentityRecord
    snapshot_id: str
    source_file_id: str
    file_content_id: str
    entity_id: str | None
    enclosing_entity_id: str | None
    byte_range: tuple[int, int]
    line_column_range: tuple[int, int, int, int]
    roles: tuple[str, ...]
    syntax_path: tuple[str, ...]
    producer: ProducerRef

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        source_file_id: str,
        file_content_id: str,
        entity_id: str | None,
        enclosing_entity_id: str | None,
        byte_range: tuple[int, int],
        line_column_range: tuple[int, int, int, int],
        roles: Iterable[str],
        syntax_path: Iterable[str],
        producer: ProducerRef,
    ) -> "OccurrenceRecord":
        if not (0 <= byte_range[0] <= byte_range[1]):
            raise ValueError("invalid occurrence byte range")
        ordered_roles = tuple(sorted(set(roles)))
        path = tuple(syntax_path)
        key = {
            "snapshot_id": snapshot_id,
            "source_file_id": source_file_id,
            "file_content_id": file_content_id,
            "entity_id": entity_id,
            "enclosing_entity_id": enclosing_entity_id,
            "byte_range": byte_range,
            "roles": ordered_roles,
            "syntax_path": path,
        }
        return cls(
            IdentityRecord.create("occurrence", key),
            snapshot_id,
            source_file_id,
            file_content_id,
            entity_id,
            enclosing_entity_id,
            byte_range,
            line_column_range,
            ordered_roles,
            path,
            producer,
        )


@dataclass(frozen=True, slots=True)
class RelationAssertion(RecordMixin):
    relation_key: IdentityRecord
    assertion_identity: IdentityRecord
    snapshot_id: str
    predicate_key: str
    participants: tuple[ParticipantRef, ...]
    modality: Modality
    polarity: Polarity
    quantifier: Quantifier
    producer: ProducerRef
    analysis_manifest_id: str
    evidence_ids: tuple[str, ...]
    confidence: float | None = None

    @property
    def relation_key_id(self) -> str:
        return self.relation_key.id

    @property
    def edge_assertion_id(self) -> str:
        return self.assertion_identity.id

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        predicate_key: str,
        participants: Iterable[ParticipantRef],
        modality: Modality,
        polarity: Polarity,
        quantifier: Quantifier,
        producer: ProducerRef,
        analysis_manifest_id: str,
        evidence_ids: Iterable[str],
        confidence: float | None = None,
    ) -> "RelationAssertion":
        if not _KEY.fullmatch(predicate_key):
            raise ValueError(f"predicate must be namespaced: {predicate_key!r}")
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        participant_tuple = tuple(participants)
        if len(participant_tuple) < 2:
            raise ValueError("relations require at least two participants")
        evidence_tuple = tuple(sorted(set(evidence_ids)))
        proposition = {
            "snapshot_id": snapshot_id,
            "predicate_key": predicate_key,
            "quantifier": quantifier.value,
            "participants": [item.to_dict() for item in participant_tuple],
        }
        relation_key = IdentityRecord.create("relation_key", proposition)
        assertion_key = {
            "relation_key_id": relation_key.id,
            "modality": modality.value,
            "polarity": polarity.value,
            "producer": producer.to_dict(),
            "analysis_manifest_id": analysis_manifest_id,
            "evidence_ids": evidence_tuple,
            "confidence": confidence,
        }
        # Confidence is recorded but excluded from exact identity because floats are
        # intentionally forbidden in identity keys. Its deterministic text form is
        # included only when present.
        if confidence is not None:
            assertion_key["confidence_decimal"] = format(confidence, ".17g")
            assertion_key.pop("confidence")
        return cls(
            relation_key,
            IdentityRecord.create("edge_assertion", assertion_key),
            snapshot_id,
            predicate_key,
            participant_tuple,
            modality,
            polarity,
            quantifier,
            producer,
            analysis_manifest_id,
            evidence_tuple,
            confidence,
        )


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor(RecordMixin):
    extension_key: str
    descriptor_version: str
    authority: str
    applies_to: tuple[str, ...]
    wire_type: str
    missing_value_semantics: str
    merge_semantics: str = "retain_parallel_assertions"
    exact_index: bool = False
    lexical_index: bool = False
    graph_projection: bool = False
    status: str = "experimental"

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.extension_key):
            raise ValueError(f"extension key must be namespaced: {self.extension_key!r}")
        if not _VERSION.fullmatch(self.descriptor_version):
            raise ValueError(f"invalid descriptor version: {self.descriptor_version!r}")
        if not self.authority or not self.applies_to:
            raise ValueError("extension authority and applies_to are required")
        if self.missing_value_semantics not in {
            "unknown",
            "not_applicable",
            "empty_is_meaningful",
        }:
            raise ValueError("missing-value semantics must be explicit")

    @property
    def descriptor_digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class FeatureAssertion(RecordMixin):
    identity: IdentityRecord
    subject: SubjectRef
    extension_key: str
    descriptor_version: str
    typed_value: Any
    modality: Modality
    polarity: Polarity
    producer: ProducerRef
    evidence_ids: tuple[str, ...]
    snapshot_id: str

    @classmethod
    def create(
        cls,
        *,
        subject: SubjectRef,
        extension_key: str,
        descriptor_version: str,
        typed_value: Any,
        modality: Modality,
        polarity: Polarity,
        producer: ProducerRef,
        evidence_ids: Iterable[str],
        snapshot_id: str,
    ) -> "FeatureAssertion":
        primitive_value = to_primitive(typed_value)
        evidence_tuple = tuple(sorted(set(evidence_ids)))
        key = {
            "subject": subject.to_dict(),
            "extension_key": extension_key,
            "descriptor_version": descriptor_version,
            "typed_value": primitive_value,
            "modality": modality.value,
            "polarity": polarity.value,
            "producer": producer.to_dict(),
            "evidence_ids": evidence_tuple,
            "snapshot_id": snapshot_id,
        }
        return cls(
            IdentityRecord.create("feature_assertion", key),
            subject,
            extension_key,
            descriptor_version,
            primitive_value,
            modality,
            polarity,
            producer,
            evidence_tuple,
            snapshot_id,
        )


@dataclass(frozen=True, slots=True)
class ProjectionRecord(RecordMixin):
    identity: IdentityRecord
    subject: SubjectRef
    projection_key: str
    projection_schema_version: str
    input_refs: tuple[str, ...]
    generator: ProducerRef
    payload: Any
    snapshot_id: str

    @classmethod
    def create(
        cls,
        *,
        subject: SubjectRef,
        projection_key: str,
        projection_schema_version: str,
        input_refs: Iterable[str],
        generator: ProducerRef,
        payload: Any,
        snapshot_id: str,
    ) -> "ProjectionRecord":
        primitive = to_primitive(payload)
        refs = tuple(sorted(set(input_refs)))
        key = {
            "subject": subject.to_dict(),
            "projection_key": projection_key,
            "projection_schema_version": projection_schema_version,
            "input_refs": refs,
            "generator": generator.to_dict(),
            "payload_digest": canonical_digest(primitive),
            "snapshot_id": snapshot_id,
        }
        return cls(
            IdentityRecord.create("projection", key),
            subject,
            projection_key,
            projection_schema_version,
            refs,
            generator,
            primitive,
            snapshot_id,
        )


@dataclass(frozen=True, slots=True)
class RepresentationContent(RecordMixin):
    """Subject-independent, content-addressed representation output."""

    identity: IdentityRecord
    family_key: str
    representation_key: str
    schema_version: str
    typed_value: TypedValue
    payload_digest: str

    @classmethod
    def create(
        cls,
        *,
        family_key: str,
        representation_key: str,
        schema_version: str,
        typed_value: TypedValue,
    ) -> "RepresentationContent":
        if not _KEY.fullmatch(family_key) or not _KEY.fullmatch(representation_key):
            raise ValueError("representation family and key must be namespaced")
        if not _VERSION.fullmatch(schema_version):
            raise ValueError("invalid representation schema version")
        payload_digest = canonical_digest(typed_value.to_dict())
        key = {
            "family_key": family_key,
            "representation_key": representation_key,
            "schema_version": schema_version,
            "value_kind": typed_value.kind.value,
            "payload_digest": payload_digest,
        }
        return cls(
            IdentityRecord.create("representation_content", key),
            family_key,
            representation_key,
            schema_version,
            typed_value,
            payload_digest,
        )


@dataclass(frozen=True, slots=True)
class GenerationRun(RecordMixin):
    """A receipt for one production attempt, including failures and retries."""

    identity: IdentityRecord
    snapshot_id: str
    attempt_key: str
    producer: ProducerRef
    input_refs: tuple[str, ...]
    output_content_ids: tuple[str, ...]
    output_digest: str
    status: str
    started_at: str | None
    completed_at: str | None
    environment: Any

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        attempt_key: str,
        producer: ProducerRef,
        input_refs: Iterable[str],
        output_content_ids: Iterable[str],
        status: str = "succeeded",
        started_at: str | None = None,
        completed_at: str | None = None,
        environment: Any = None,
    ) -> "GenerationRun":
        if status not in {"planned", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError("unsupported generation-run status")
        inputs = tuple(sorted(set(input_refs)))
        outputs = tuple(sorted(set(output_content_ids)))
        output_digest = canonical_digest(outputs)
        primitive_environment = to_primitive(environment if environment is not None else {})
        key = {
            "snapshot_id": snapshot_id,
            "attempt_key": attempt_key,
            "producer": producer.to_dict(),
            "input_refs": inputs,
            "output_digest": output_digest,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "environment": primitive_environment,
        }
        return cls(
            IdentityRecord.create("generation_run", key),
            snapshot_id,
            attempt_key,
            producer,
            inputs,
            outputs,
            output_digest,
            status,
            started_at,
            completed_at,
            primitive_environment,
        )


@dataclass(frozen=True, slots=True)
class RepresentationAssertion(RecordMixin):
    """A provenance-bearing claim that representation content describes a subject."""

    identity: IdentityRecord
    snapshot_id: str
    subject: SubjectRef
    content_id: str
    modality: Modality
    polarity: Polarity
    producer: ProducerRef
    generation_run_id: str
    evidence_ids: tuple[str, ...]
    confidence_ppm: int | None
    scope: Any
    valid_from: str | None
    valid_to: str | None
    lifecycle: EvidenceLevel

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        subject: SubjectRef,
        content_id: str,
        modality: Modality,
        polarity: Polarity,
        producer: ProducerRef,
        generation_run_id: str,
        evidence_ids: Iterable[str] = (),
        confidence_ppm: int | None = None,
        scope: Any = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        lifecycle: EvidenceLevel = EvidenceLevel.STRUCTURED,
    ) -> "RepresentationAssertion":
        if confidence_ppm is not None and not 0 <= confidence_ppm <= 1_000_000:
            raise ValueError("confidence_ppm must be within [0, 1000000]")
        evidence = tuple(sorted(set(evidence_ids)))
        primitive_scope = to_primitive(scope if scope is not None else {})
        key = {
            "snapshot_id": snapshot_id,
            "subject": subject.to_dict(),
            "content_id": content_id,
            "modality": modality.value,
            "polarity": polarity.value,
            "producer": producer.to_dict(),
            "generation_run_id": generation_run_id,
            "evidence_ids": evidence,
            "confidence_ppm": confidence_ppm,
            "scope": primitive_scope,
            "valid_from": valid_from,
            "valid_to": valid_to,
            "lifecycle": lifecycle.value,
        }
        return cls(
            IdentityRecord.create("representation_assertion", key),
            snapshot_id,
            subject,
            content_id,
            modality,
            polarity,
            producer,
            generation_run_id,
            evidence,
            confidence_ppm,
            primitive_scope,
            valid_from,
            valid_to,
            lifecycle,
        )


@dataclass(frozen=True, slots=True)
class LineageAssertion(RecordMixin):
    """Versioned, evidence-bearing lineage between arbitrary graph subjects."""

    identity: IdentityRecord
    snapshot_id: str
    predicate_key: str
    source: SubjectRef
    target: SubjectRef
    role_key: str | None
    ordinal: int | None
    producer: ProducerRef
    generation_run_id: str | None
    evidence_ids: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        predicate_key: str,
        source: SubjectRef,
        target: SubjectRef,
        producer: ProducerRef,
        generation_run_id: str | None = None,
        evidence_ids: Iterable[str] = (),
        role_key: str | None = None,
        ordinal: int | None = None,
    ) -> "LineageAssertion":
        if not _KEY.fullmatch(predicate_key):
            raise ValueError("lineage predicate must be namespaced")
        if ordinal is not None and ordinal < 0:
            raise ValueError("lineage ordinal cannot be negative")
        if role_key is not None and not _KEY.fullmatch(role_key):
            raise ValueError("lineage role must be namespaced")
        evidence = tuple(sorted(set(evidence_ids)))
        key = {
            "snapshot_id": snapshot_id,
            "predicate_key": predicate_key,
            "source": source.to_dict(),
            "target": target.to_dict(),
            "role_key": role_key,
            "ordinal": ordinal,
            "producer": producer.to_dict(),
            "generation_run_id": generation_run_id,
            "evidence_ids": evidence,
        }
        return cls(
            IdentityRecord.create("lineage_assertion", key),
            snapshot_id,
            predicate_key,
            source,
            target,
            role_key,
            ordinal,
            producer,
            generation_run_id,
            evidence,
        )


@dataclass(frozen=True, slots=True)
class CoverageLedger(RecordMixin):
    identity: IdentityRecord
    snapshot_id: str
    family_key: str
    attempted_inputs: int
    successful_inputs: int
    unresolved_inputs: int
    unsupported_constructs: tuple[str, ...]
    completeness_state: CompletenessState
    extractor_versions: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        family_key: str,
        attempted_inputs: int,
        successful_inputs: int,
        unresolved_inputs: int,
        unsupported_constructs: Iterable[str],
        completeness_state: CompletenessState,
        extractor_versions: Iterable[str],
    ) -> "CoverageLedger":
        if min(attempted_inputs, successful_inputs, unresolved_inputs) < 0:
            raise ValueError("coverage counts cannot be negative")
        unsupported = tuple(sorted(set(unsupported_constructs)))
        extractors = tuple(sorted(set(extractor_versions)))
        key = {
            "snapshot_id": snapshot_id,
            "family_key": family_key,
            "extractor_versions": extractors,
        }
        return cls(
            IdentityRecord.create("coverage_ledger", key),
            snapshot_id,
            family_key,
            attempted_inputs,
            successful_inputs,
            unresolved_inputs,
            unsupported,
            completeness_state,
            extractors,
        )


@dataclass(frozen=True, slots=True)
class AnalysisManifest(RecordMixin):
    identity: IdentityRecord
    snapshot_id: str
    analyzer_id: str
    analyzer_version: str
    config_digest: str
    profile: str
    network_allowed: bool
    execution_allowed: bool

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        analyzer_id: str,
        analyzer_version: str,
        config_digest: str,
        profile: str,
        network_allowed: bool = False,
        execution_allowed: bool = False,
    ) -> "AnalysisManifest":
        key = {
            "snapshot_id": snapshot_id,
            "analyzer_id": analyzer_id,
            "analyzer_version": analyzer_version,
            "config_digest": config_digest,
            "profile": profile,
            "network_allowed": network_allowed,
            "execution_allowed": execution_allowed,
        }
        return cls(
            IdentityRecord.create("analysis_manifest", key),
            snapshot_id,
            analyzer_id,
            analyzer_version,
            config_digest,
            profile,
            network_allowed,
            execution_allowed,
        )


@dataclass(slots=True)
class GraphBundle(RecordMixin):
    snapshot: PackageSnapshot
    analysis: AnalysisManifest
    files: dict[str, SourceFileRecord] = field(default_factory=dict)
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    occurrences: dict[str, OccurrenceRecord] = field(default_factory=dict)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    relations: dict[str, RelationAssertion] = field(default_factory=dict)
    features: dict[str, FeatureAssertion] = field(default_factory=dict)
    projections: dict[str, ProjectionRecord] = field(default_factory=dict)
    representation_contents: dict[str, RepresentationContent] = field(default_factory=dict)
    representation_assertions: dict[str, RepresentationAssertion] = field(default_factory=dict)
    generation_runs: dict[str, GenerationRun] = field(default_factory=dict)
    lineage: dict[str, LineageAssertion] = field(default_factory=dict)
    coverage: dict[str, CoverageLedger] = field(default_factory=dict)
    source_blobs: dict[str, bytes] = field(default_factory=dict, repr=False)

    def summary(self) -> dict[str, int | str]:
        return {
            "snapshot_id": self.snapshot.identity.id,
            "analysis_manifest_id": self.analysis.identity.id,
            "files": len(self.files),
            "entities": len(self.entities),
            "occurrences": len(self.occurrences),
            "relations": len(self.relations),
            "evidence": len(self.evidence),
            "features": len(self.features),
            "projections": len(self.projections),
            "representation_contents": len(self.representation_contents),
            "representation_assertions": len(self.representation_assertions),
            "generation_runs": len(self.generation_runs),
            "lineage_assertions": len(self.lineage),
            "coverage_ledgers": len(self.coverage),
        }

    def record_sets(self) -> dict[str, Mapping[str, Any]]:
        return {
            "files": self.files,
            "entities": self.entities,
            "occurrences": self.occurrences,
            "evidence": self.evidence,
            "relations": self.relations,
            "features": self.features,
            "projections": self.projections,
            "representation_contents": self.representation_contents,
            "representation_assertions": self.representation_assertions,
            "generation_runs": self.generation_runs,
            "lineage": self.lineage,
            "coverage": self.coverage,
        }

    def validate(
        self,
        descriptor_lookup: Callable[[str, str], ExtensionDescriptor] | None = None,
        representation_descriptor_lookup: Callable[[str, str], Any] | None = None,
    ) -> None:
        errors: list[str] = []
        try:
            self.snapshot.identity.validate()
            self.analysis.identity.validate()
        except IdentityError as exc:
            errors.append(str(exc))
        snapshot_id = self.snapshot.identity.id
        if self.analysis.snapshot_id != snapshot_id:
            errors.append("analysis manifest is scoped to a different snapshot")

        for collection_name, records in self.record_sets().items():
            for record_id, record in records.items():
                identity = getattr(record, "identity", None)
                if identity is None and isinstance(record, RelationAssertion):
                    identity = record.assertion_identity
                if identity is None:
                    errors.append(f"{collection_name}:{record_id} has no identity")
                    continue
                if record_id != identity.id:
                    errors.append(f"{collection_name} key does not match record identity: {record_id}")
                try:
                    identity.validate()
                    if isinstance(record, RelationAssertion):
                        record.relation_key.validate()
                except IdentityError as exc:
                    errors.append(str(exc))
                record_snapshot = getattr(record, "snapshot_id", snapshot_id)
                if record_snapshot != snapshot_id:
                    errors.append(f"{collection_name}:{record_id} crosses snapshot boundary")

        file_ids = set(self.files)
        file_content_ids = {
            record.content_identity.id for record in self.files.values()
        }
        entity_ids = set(self.entities)
        occurrence_ids = set(self.occurrences)
        evidence_ids = set(self.evidence)
        relation_ids = set(self.relations)
        content_ids = set(self.representation_contents)
        assertion_ids = set(self.representation_assertions)
        run_ids = set(self.generation_runs)

        if set(self.snapshot.file_ids) != file_ids:
            errors.append("snapshot file ID inventory does not equal graph file records")
        for digest, blob in self.source_blobs.items():
            if sha256_digest(blob) != digest:
                errors.append(f"source/CAS blob digest mismatch for {digest}")
        for file_id, record in self.files.items():
            try:
                record.content_identity.validate()
            except IdentityError as exc:
                errors.append(str(exc))
            blob = self.source_blobs.get(record.content_digest)
            if blob is not None and sha256_digest(blob) != record.content_digest:
                errors.append(f"source blob digest mismatch for {file_id}")
        for occurrence in self.occurrences.values():
            if occurrence.source_file_id not in file_ids:
                errors.append(f"occurrence {occurrence.identity.id} references unknown source file")
            if occurrence.file_content_id not in file_content_ids:
                errors.append(f"occurrence {occurrence.identity.id} references unknown file content")
            if occurrence.entity_id and occurrence.entity_id not in entity_ids:
                errors.append(f"occurrence {occurrence.identity.id} references unknown entity")
            if occurrence.enclosing_entity_id and occurrence.enclosing_entity_id not in entity_ids:
                errors.append(f"occurrence {occurrence.identity.id} has unknown enclosing entity")
            file_record = self.files.get(occurrence.source_file_id)
            if file_record and occurrence.file_content_id != file_record.content_identity.id:
                errors.append(f"occurrence {occurrence.identity.id} has mismatched file content")
            if file_record and occurrence.byte_range[1] > file_record.size_bytes:
                errors.append(f"occurrence {occurrence.identity.id} exceeds file bounds")
        for entity in self.entities.values():
            if entity.defining_occurrence_id and entity.defining_occurrence_id not in occurrence_ids:
                errors.append(f"entity {entity.identity.id} has unknown defining occurrence")
            if entity.enclosing_entity_id and entity.enclosing_entity_id not in entity_ids:
                errors.append(f"entity {entity.identity.id} has unknown enclosing entity")
        for evidence in self.evidence.values():
            if evidence.source_file_id and evidence.source_file_id not in file_ids:
                errors.append(f"evidence {evidence.identity.id} references unknown source file")
            if evidence.file_content_id and evidence.file_content_id not in file_content_ids:
                errors.append(f"evidence {evidence.identity.id} references unknown file content")
            if evidence.source_file_id and evidence.file_content_id:
                record = self.files.get(evidence.source_file_id)
                if record and record.content_identity.id != evidence.file_content_id:
                    errors.append(f"evidence {evidence.identity.id} has mismatched file content")
        known_by_kind = {
            "entity": entity_ids,
            "occurrence": occurrence_ids,
            "relation": relation_ids,
            "snapshot": {snapshot_id},
            "file": file_ids,
            "file_content": file_content_ids,
            "feature": set(self.features),
            "projection": set(self.projections),
            "representation_content": content_ids,
            "representation_assertion": assertion_ids,
            "generation_run": run_ids,
            "analysis": {self.analysis.identity.id},
            "evidence": evidence_ids,
        }
        for relation in self.relations.values():
            if not relation.evidence_ids:
                errors.append(f"relation {relation.edge_assertion_id} has no evidence")
            for evidence_id in relation.evidence_ids:
                if evidence_id not in evidence_ids:
                    errors.append(f"relation {relation.edge_assertion_id} has unknown evidence")
            for participant in relation.participants:
                allowed = known_by_kind.get(participant.subject.subject_kind)
                if allowed is None or participant.subject.id not in allowed:
                    errors.append(
                        f"relation {relation.edge_assertion_id} has unknown "
                        f"{participant.subject.subject_kind} participant"
                    )
        for feature in self.features.values():
            if feature.subject.subject_kind == "entity" and feature.subject.id not in entity_ids:
                errors.append(f"feature {feature.identity.id} references unknown entity")
            for evidence_id in feature.evidence_ids:
                if evidence_id not in evidence_ids:
                    errors.append(f"feature {feature.identity.id} has unknown evidence")
            if descriptor_lookup:
                try:
                    descriptor = descriptor_lookup(
                        feature.extension_key, feature.descriptor_version
                    )
                except KeyError:
                    errors.append(
                        f"feature {feature.identity.id} uses unregistered descriptor "
                        f"{feature.extension_key}@{feature.descriptor_version}"
                    )
                else:
                    if feature.subject.subject_kind not in descriptor.applies_to:
                        errors.append(
                            f"descriptor {descriptor.extension_key} does not apply to "
                            f"{feature.subject.subject_kind}"
                        )
        for projection in self.projections.values():
            if projection.subject.subject_kind == "entity" and projection.subject.id not in entity_ids:
                errors.append(f"projection {projection.identity.id} references unknown entity")
            if projection.subject.subject_kind == "relation" and projection.subject.id not in relation_ids:
                errors.append(f"projection {projection.identity.id} references unknown relation")

        for content in self.representation_contents.values():
            if canonical_digest(content.typed_value.to_dict()) != content.payload_digest:
                errors.append(f"representation content {content.identity.id} has a payload mismatch")
            if representation_descriptor_lookup:
                try:
                    descriptor = representation_descriptor_lookup(
                        content.representation_key, content.schema_version
                    )
                except KeyError:
                    errors.append(
                        f"representation content {content.identity.id} uses unregistered descriptor "
                        f"{content.representation_key}@{content.schema_version}"
                    )
                else:
                    if descriptor.family_key != content.family_key:
                        errors.append(
                            f"representation content {content.identity.id} has the wrong family"
                        )
                    if content.typed_value.kind not in descriptor.allowed_value_kinds:
                        errors.append(
                            f"representation content {content.identity.id} has a disallowed value kind"
                        )
        for run in self.generation_runs.values():
            if canonical_digest(run.output_content_ids) != run.output_digest:
                errors.append(f"generation run {run.identity.id} has an output-set mismatch")
            for content_id in run.output_content_ids:
                if content_id not in content_ids:
                    errors.append(f"generation run {run.identity.id} has unknown output content")
        for assertion in self.representation_assertions.values():
            allowed = known_by_kind.get(assertion.subject.subject_kind)
            if allowed is None or assertion.subject.id not in allowed:
                errors.append(f"representation assertion {assertion.identity.id} has unknown subject")
            if assertion.content_id not in content_ids:
                errors.append(f"representation assertion {assertion.identity.id} has unknown content")
            if assertion.generation_run_id not in run_ids:
                errors.append(f"representation assertion {assertion.identity.id} has unknown run")
            if representation_descriptor_lookup and assertion.content_id in self.representation_contents:
                content = self.representation_contents[assertion.content_id]
                try:
                    descriptor = representation_descriptor_lookup(
                        content.representation_key, content.schema_version
                    )
                except KeyError:
                    pass
                else:
                    if assertion.subject.subject_kind not in descriptor.applies_to:
                        errors.append(
                            f"representation {content.representation_key} does not apply to "
                            f"{assertion.subject.subject_kind}"
                        )
            for evidence_id in assertion.evidence_ids:
                if evidence_id not in evidence_ids:
                    errors.append(f"representation assertion {assertion.identity.id} has unknown evidence")
        for item in self.lineage.values():
            for label, reference in (("source", item.source), ("target", item.target)):
                allowed = known_by_kind.get(reference.subject_kind)
                if allowed is None or reference.id not in allowed:
                    errors.append(f"lineage {item.identity.id} has unknown {label}")
            if item.generation_run_id and item.generation_run_id not in run_ids:
                errors.append(f"lineage {item.identity.id} has unknown run")
            for evidence_id in item.evidence_ids:
                if evidence_id not in evidence_ids:
                    errors.append(f"lineage {item.identity.id} has unknown evidence")

        if errors:
            raise GraphValidationError(errors)
