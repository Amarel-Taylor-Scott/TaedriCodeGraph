"""Proof-carrying release contract for reusable Taedri primitives.

Candidate descriptions and source fragments never satisfy this contract.  A release
requires a complete capsule plus an acceptance receipt created by an executable
verifier and a separate authorization decision.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..canonical import canonical_json_bytes, sha256_digest
from ..contracts import RecordMixin
from ..identity import IdentityRecord
from ..primitive_capsules import CapsuleRole, PrimitiveRevision, PrimitiveTree, RefKind
from .edges import PrimitiveGraphError, PrimitiveInterface, validate_primitive_graph

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_LANGUAGE = re.compile(r"^[a-z][a-z0-9.+-]{0,63}$")
_IMMUTABLE_REVISION = re.compile(r"^(?:sha256:[0-9a-f]{64}|[0-9a-f]{40}|[0-9a-f]{64})$")


class PrimitiveReleaseError(ValueError):
    """Raised when a capsule lacks release-grade code or evidence."""


class AssuranceLevel(str, Enum):
    """Curation strictness; functional completeness is identical at every level."""

    BOOTSTRAP = "bootstrap"
    STANDARD = "standard"
    HIGH_ASSURANCE = "high_assurance"


class ReleaseProofKind(str, Enum):
    ARTIFACT_STRUCTURE = "artifact_structure"
    RUNTIME_PINNED = "runtime_pinned"
    CONTRACT_VALIDATED = "contract_validated"
    INTERFACE_GRAPH_VALIDATED = "interface_graph_validated"
    EXAMPLES_EXECUTED = "examples_executed"
    TESTS_PASSED = "tests_passed"
    ORACLE_PASSED = "oracle_passed"
    LICENSE_VERIFIED = "license_verified"
    PROVENANCE_VERIFIED = "provenance_verified"
    DEDUPLICATION_CHECKED = "deduplication_checked"
    INGESTION_PASSED = "ingestion_passed"
    PACK_DOWNLOADED = "pack_downloaded"
    MATERIALIZATION_PASSED = "materialization_passed"
    QUERY_PASSED = "query_passed"


REQUIRED_RELEASE_PROOFS = frozenset(ReleaseProofKind)
REQUIRED_ACCEPTANCE_PROOFS = REQUIRED_RELEASE_PROOFS - {
    ReleaseProofKind.DEDUPLICATION_CHECKED,
    ReleaseProofKind.QUERY_PASSED,
}
REQUIRED_RELEASE_ROLES = frozenset(
    {
        CapsuleRole.SOURCE,
        CapsuleRole.CONTRACT,
        CapsuleRole.DESCRIPTOR,
        CapsuleRole.TEST,
        CapsuleRole.VERIFIER,
        CapsuleRole.DEPENDENCY_LOCK,
        CapsuleRole.GRAPH_DELTA,
        CapsuleRole.DOCUMENTATION,
        CapsuleRole.RUNTIME,
        CapsuleRole.EXAMPLE,
        CapsuleRole.LICENSE,
        CapsuleRole.PROVENANCE,
    }
)


@dataclass(frozen=True, slots=True)
class PrimitiveArtifactAssessment(RecordMixin):
    source_digest: str
    contract_digest: str
    descriptor_digest: str
    search_text: str
    runtime_path: str
    language: str
    entrypoint_path: str
    entrypoint: str
    dependency_lock_path: str
    runtime_version: str
    implementation_producer_id: str
    oracle_producer_id: str
    example_count: int
    test_case_count: int
    interface_id: str
    interface_graph_digest: str
    interface_edge_count: int
    interface_port_count: int
    capability_group_count: int
    interface: PrimitiveInterface


@dataclass(frozen=True, slots=True)
class PrimitiveAcceptanceReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    revision_id: str
    tree_id: str
    source_digest: str
    verifier_id: str
    implementation_producer_id: str
    oracle_producer_id: str
    verified_at: str
    proofs: tuple[ReleaseProofKind, ...]
    executed_case_count: int
    language: str
    runtime_version: str
    output_digest: str

    @classmethod
    def create(
        cls,
        *,
        revision_id: str,
        tree_id: str,
        source_digest: str,
        verifier_id: str,
        implementation_producer_id: str,
        oracle_producer_id: str,
        verified_at: str,
        proofs: tuple[ReleaseProofKind, ...],
        executed_case_count: int,
        language: str,
        runtime_version: str,
        output_digest: str,
    ) -> "PrimitiveAcceptanceReceipt":
        ordered = tuple(sorted(set(proofs), key=lambda item: item.value))
        if set(ordered) != REQUIRED_ACCEPTANCE_PROOFS:
            missing = sorted(item.value for item in REQUIRED_ACCEPTANCE_PROOFS - set(ordered))
            unexpected = sorted(item.value for item in set(ordered) - REQUIRED_ACCEPTANCE_PROOFS)
            detail = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if unexpected:
                detail.append("unexpected=" + ",".join(unexpected))
            raise PrimitiveReleaseError(
                "acceptance receipt executable proof set is invalid: " + "; ".join(detail)
            )
        if not all(
            (
                revision_id,
                tree_id,
                verifier_id,
                implementation_producer_id,
                oracle_producer_id,
                verified_at,
                language,
                runtime_version,
            )
        ):
            raise PrimitiveReleaseError("acceptance identity and provenance are required")
        if executed_case_count < 3:
            raise PrimitiveReleaseError("positive, boundary, and negative cases must execute")
        _require_digest(source_digest, "source digest")
        _require_digest(output_digest, "acceptance output digest")
        key = {
            "format_version": "1.0.0",
            "revision_id": revision_id,
            "tree_id": tree_id,
            "source_digest": source_digest,
            "verifier_id": verifier_id,
            "implementation_producer_id": implementation_producer_id,
            "oracle_producer_id": oracle_producer_id,
            "verified_at": verified_at,
            "proofs": [item.value for item in ordered],
            "executed_case_count": executed_case_count,
            "language": language,
            "runtime_version": runtime_version,
            "output_digest": output_digest,
        }
        return cls(
            IdentityRecord.create("primitive_acceptance_receipt", key),
            "1.0.0",
            revision_id,
            tree_id,
            source_digest,
            verifier_id,
            implementation_producer_id,
            oracle_producer_id,
            verified_at,
            ordered,
            executed_case_count,
            language,
            runtime_version,
            output_digest,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PrimitiveAcceptanceReceipt":
        identity = value.get("identity")
        if not isinstance(identity, Mapping):
            raise PrimitiveReleaseError("acceptance receipt identity is missing")
        try:
            created = cls.create(
                revision_id=str(value.get("revision_id", "")),
                tree_id=str(value.get("tree_id", "")),
                source_digest=str(value.get("source_digest", "")),
                verifier_id=str(value.get("verifier_id", "")),
                implementation_producer_id=str(
                    value.get("implementation_producer_id", "")
                ),
                oracle_producer_id=str(value.get("oracle_producer_id", "")),
                verified_at=str(value.get("verified_at", "")),
                proofs=tuple(
                    ReleaseProofKind(str(item)) for item in value.get("proofs", [])
                ),
                executed_case_count=int(value.get("executed_case_count", 0)),
                language=str(value.get("language", "")),
                runtime_version=str(value.get("runtime_version", "")),
                output_digest=str(value.get("output_digest", "")),
            )
        except (TypeError, ValueError) as exc:
            raise PrimitiveReleaseError("acceptance receipt is invalid") from exc
        if created.identity.to_dict() != dict(identity):
            raise PrimitiveReleaseError("acceptance receipt identity does not validate")
        return created


@dataclass(frozen=True, slots=True)
class PrimitiveReleaseAuthorization(RecordMixin):
    authorizer_id: str
    policy_decision_id: str
    authorized_at: str
    assurance_level: AssuranceLevel = AssuranceLevel.BOOTSTRAP

    def __post_init__(self) -> None:
        if not self.authorizer_id or not self.policy_decision_id or not self.authorized_at:
            raise PrimitiveReleaseError("release authorization fields are required")


@dataclass(frozen=True, slots=True)
class PrimitiveReleaseRecord(RecordMixin):
    identity: IdentityRecord
    format_version: str
    primitive_id: str
    revision_id: str
    tree_id: str
    source_digest: str
    contract_digest: str
    descriptor_digest: str
    language: str
    runtime_version: str
    search_text: str
    ref_kind: RefKind
    ref_name: str
    acceptance_receipt_ref: str
    verifier_id: str
    implementation_producer_id: str
    oracle_producer_id: str
    authorizer_id: str
    policy_decision_id: str
    released_at: str
    assurance_level: AssuranceLevel
    proofs: tuple[ReleaseProofKind, ...]

    @classmethod
    def create(
        cls,
        *,
        revision: PrimitiveRevision,
        artifacts: PrimitiveArtifactAssessment,
        acceptance: PrimitiveAcceptanceReceipt,
        acceptance_receipt_ref: str,
        authorization: PrimitiveReleaseAuthorization,
        ref_kind: RefKind,
        ref_name: str,
    ) -> "PrimitiveReleaseRecord":
        _require_digest(acceptance_receipt_ref, "acceptance receipt reference")
        if acceptance.revision_id != revision.identity.id:
            raise PrimitiveReleaseError("acceptance receipt names another revision")
        if acceptance.tree_id != revision.tree_id:
            raise PrimitiveReleaseError("acceptance receipt names another tree")
        if acceptance.source_digest != artifacts.source_digest:
            raise PrimitiveReleaseError("accepted source digest does not match capsule source")
        if acceptance.language != artifacts.language:
            raise PrimitiveReleaseError("accepted runtime language does not match capsule runtime")
        if acceptance.runtime_version != artifacts.runtime_version:
            raise PrimitiveReleaseError("accepted runtime version does not match capsule runtime")
        if acceptance.implementation_producer_id != artifacts.implementation_producer_id:
            raise PrimitiveReleaseError("implementation producer evidence disagrees")
        if acceptance.oracle_producer_id != artifacts.oracle_producer_id:
            raise PrimitiveReleaseError("oracle producer evidence disagrees")
        _validate_separation(acceptance, authorization)
        if not ref_name:
            raise PrimitiveReleaseError("release ref name is required")
        search_text = " ".join(
            (
                revision.primitive.namespace,
                revision.primitive.name,
                artifacts.search_text,
            )
        )
        key = {
            "format_version": "1.0.0",
            "primitive_id": revision.primitive.identity.id,
            "revision_id": revision.identity.id,
            "tree_id": revision.tree_id,
            "source_digest": artifacts.source_digest,
            "contract_digest": artifacts.contract_digest,
            "descriptor_digest": artifacts.descriptor_digest,
            "language": artifacts.language,
            "runtime_version": artifacts.runtime_version,
            "search_text": search_text,
            "ref_kind": ref_kind.value,
            "ref_name": ref_name,
            "acceptance_receipt_ref": acceptance_receipt_ref,
            "verifier_id": acceptance.verifier_id,
            "implementation_producer_id": acceptance.implementation_producer_id,
            "oracle_producer_id": acceptance.oracle_producer_id,
            "authorizer_id": authorization.authorizer_id,
            "policy_decision_id": authorization.policy_decision_id,
            "released_at": authorization.authorized_at,
            "assurance_level": authorization.assurance_level.value,
            "proofs": [item.value for item in sorted(REQUIRED_RELEASE_PROOFS, key=lambda value: value.value)],
        }
        return cls(
            IdentityRecord.create("primitive_release", key),
            "1.0.0",
            revision.primitive.identity.id,
            revision.identity.id,
            revision.tree_id,
            artifacts.source_digest,
            artifacts.contract_digest,
            artifacts.descriptor_digest,
            artifacts.language,
            artifacts.runtime_version,
            search_text,
            ref_kind,
            ref_name,
            acceptance_receipt_ref,
            acceptance.verifier_id,
            acceptance.implementation_producer_id,
            acceptance.oracle_producer_id,
            authorization.authorizer_id,
            authorization.policy_decision_id,
            authorization.authorized_at,
            authorization.assurance_level,
            tuple(sorted(REQUIRED_RELEASE_PROOFS, key=lambda value: value.value)),
        )


@dataclass(frozen=True, slots=True)
class PrimitiveReleaseRevocation(RecordMixin):
    """Append-only removal of one release from all serving projections."""

    identity: IdentityRecord
    format_version: str
    release_id: str
    primitive_id: str
    revision_id: str
    actor: str
    policy_decision_id: str
    reason: str
    revoked_at: str

    @classmethod
    def create(
        cls,
        *,
        release_id: str,
        primitive_id: str,
        revision_id: str,
        actor: str,
        policy_decision_id: str,
        reason: str,
        revoked_at: str,
    ) -> "PrimitiveReleaseRevocation":
        if not all(
            (
                release_id,
                primitive_id,
                revision_id,
                actor,
                policy_decision_id,
                reason,
                revoked_at,
            )
        ):
            raise PrimitiveReleaseError("release revocation fields are required")
        key = {
            "format_version": "1.0.0",
            "release_id": release_id,
            "primitive_id": primitive_id,
            "revision_id": revision_id,
            "actor": actor,
            "policy_decision_id": policy_decision_id,
            "reason": reason,
            "revoked_at": revoked_at,
        }
        return cls(
            IdentityRecord.create("primitive_release_revocation", key),
            "1.0.0",
            release_id,
            primitive_id,
            revision_id,
            actor,
            policy_decision_id,
            reason,
            revoked_at,
        )


def inspect_release_artifacts(
    tree: PrimitiveTree, blobs: Mapping[str, bytes]
) -> PrimitiveArtifactAssessment:
    """Validate the complete release capsule and return normalized search/runtime data."""

    roles = {entry.role for entry in tree.entries}
    missing_roles = sorted(item.value for item in REQUIRED_RELEASE_ROLES - roles)
    if missing_roles:
        raise PrimitiveReleaseError(
            "release capsule is missing required roles: " + ", ".join(missing_roles)
        )
    by_role: dict[CapsuleRole, list[tuple[str, bytes, str]]] = {}
    by_path: dict[str, tuple[bytes, str]] = {}
    for entry in tree.entries:
        try:
            content = blobs[entry.blob.digest]
        except KeyError as exc:
            raise PrimitiveReleaseError("release tree references a missing blob") from exc
        entry.blob.validate(content)
        by_role.setdefault(entry.role, []).append(
            (entry.path, content, entry.blob.digest)
        )
        by_path[entry.path] = (content, entry.blob.digest)
    contract_path, contract, contract_digest = _one_json(by_role, CapsuleRole.CONTRACT)
    _, descriptor, descriptor_digest = _one_json(by_role, CapsuleRole.DESCRIPTOR)
    runtime_path, runtime, _ = _one_json(by_role, CapsuleRole.RUNTIME)
    _, examples, _ = _one_json(by_role, CapsuleRole.EXAMPLE)
    _, tests, _ = _one_json(by_role, CapsuleRole.TEST)
    _, verifier, _ = _one_json(by_role, CapsuleRole.VERIFIER)
    _, license_record, _ = _one_json(by_role, CapsuleRole.LICENSE)
    _, provenance, _ = _one_json(by_role, CapsuleRole.PROVENANCE)
    _, graph, _ = _one_json(by_role, CapsuleRole.GRAPH_DELTA)

    if contract.get("schema_version") != "1.0.0":
        raise PrimitiveReleaseError("contract schema_version must be 1.0.0")
    inputs = contract.get("inputs")
    output = contract.get("output")
    if not isinstance(inputs, list) or not all(
        isinstance(item, Mapping)
        and isinstance(item.get("name"), str)
        and item.get("name")
        and isinstance(item.get("schema"), Mapping)
        for item in inputs
    ):
        raise PrimitiveReleaseError("contract inputs require names and explicit schemas")
    if not isinstance(output, Mapping) or not isinstance(output.get("schema"), Mapping):
        raise PrimitiveReleaseError("contract output requires an explicit schema")
    for field in ("errors", "effects"):
        if not isinstance(contract.get(field), list):
            raise PrimitiveReleaseError(f"contract {field} must be an explicit list")

    summary = descriptor.get("summary")
    keywords = descriptor.get("keywords")
    use_cases = descriptor.get("use_cases")
    limitations = descriptor.get("limitations")
    if not isinstance(summary, str) or len(summary.strip()) < 10:
        raise PrimitiveReleaseError("descriptor requires a substantive summary")
    if not _string_list(keywords) or not _string_list(use_cases):
        raise PrimitiveReleaseError("descriptor requires keywords and use cases")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) and item for item in limitations
    ):
        raise PrimitiveReleaseError("descriptor limitations must be explicit")

    if runtime.get("schema_version") != "1.0.0":
        raise PrimitiveReleaseError("release runtime schema_version must be 1.0.0")
    language = runtime.get("language")
    runtime_version = runtime.get("runtime_version")
    entrypoint = runtime.get("entrypoint")
    entrypoint_path = runtime.get("entrypoint_path")
    lock_path = runtime.get("dependency_lock_path")
    lock_digest = runtime.get("dependency_lock_digest")
    if not all(
        isinstance(item, str) and item
        for item in (language, runtime_version, entrypoint_path, entrypoint, lock_path)
    ):
        raise PrimitiveReleaseError(
            "runtime language, version, entrypoint path/name, and dependency lock are required"
        )
    if not _LANGUAGE.fullmatch(str(language)):
        raise PrimitiveReleaseError("runtime language must be a normalized registry key")
    source_paths = {path for path, _, _ in by_role[CapsuleRole.SOURCE]}
    if entrypoint_path not in source_paths:
        raise PrimitiveReleaseError("runtime entrypoint path is not a source-role file")
    lock_entries = {path: (content, digest) for path, content, digest in by_role[CapsuleRole.DEPENDENCY_LOCK]}
    if lock_path not in lock_entries or lock_entries[str(lock_path)][1] != lock_digest:
        raise PrimitiveReleaseError("runtime dependency lock path or digest does not match")
    if runtime.get("network") != "denied":
        raise PrimitiveReleaseError("v1 primitive runtime must explicitly deny network access")

    example_rows = examples.get("examples")
    test_rows = tests.get("cases")
    if not isinstance(example_rows, list) or not isinstance(test_rows, list) or not test_rows:
        raise PrimitiveReleaseError("examples and executable test cases are required")
    kinds = {item.get("kind") for item in example_rows if isinstance(item, Mapping)}
    if kinds != {"positive", "boundary", "negative"}:
        raise PrimitiveReleaseError("examples must include positive, boundary, and negative cases")
    for item in (*example_rows, *test_rows):
        _validate_case(item)

    implementation_producer_id = provenance.get("implementation_producer_id")
    oracle_producer_id = verifier.get("oracle_producer_id")
    if not isinstance(implementation_producer_id, str) or not implementation_producer_id:
        raise PrimitiveReleaseError("implementation provenance producer is required")
    if not isinstance(oracle_producer_id, str) or not oracle_producer_id:
        raise PrimitiveReleaseError("independent oracle producer is required")
    if not all(
        isinstance(provenance.get(field), str) and provenance.get(field)
        for field in ("source_uri", "source_revision")
    ):
        raise PrimitiveReleaseError("source URI and immutable revision provenance are required")
    if not _IMMUTABLE_REVISION.fullmatch(str(provenance.get("source_revision"))):
        raise PrimitiveReleaseError(
            "source_revision must be a Git object ID or SHA-256 content identity"
        )

    source_digest = sha256_digest(
        canonical_json_bytes(
            [
                {"path": path, "digest": digest}
                for path, _, digest in sorted(by_role[CapsuleRole.SOURCE])
            ]
        )
    )
    if provenance.get("source_digest") != source_digest:
        raise PrimitiveReleaseError("provenance source digest does not match source files")
    if license_record.get("state") != "verified":
        raise PrimitiveReleaseError("license evidence must be verified before release")
    if not isinstance(license_record.get("spdx_expression"), str) or not license_record.get("spdx_expression"):
        raise PrimitiveReleaseError("verified license requires an SPDX expression")
    license_evidence_digest = str(license_record.get("evidence_digest", ""))
    license_evidence_path = license_record.get("evidence_path")
    _require_digest(license_evidence_digest, "license evidence digest")
    if (
        not isinstance(license_evidence_path, str)
        or license_evidence_path not in by_path
        or by_path[license_evidence_path][1] != license_evidence_digest
    ):
        raise PrimitiveReleaseError(
            "license evidence path and digest must identify a capsule file"
        )
    try:
        interface = validate_primitive_graph(
            graph,
            capsule_paths=by_path,
            contract=contract,
            contract_path=contract_path,
            language=str(language),
            runtime_version=str(runtime_version),
            entrypoint_path=str(entrypoint_path),
            entrypoint=str(entrypoint),
        )
    except PrimitiveGraphError as exc:
        raise PrimitiveReleaseError(f"primitive interface graph is invalid: {exc}") from exc
    if not any(content.strip() for _, content, _ in by_role[CapsuleRole.DOCUMENTATION]):
        raise PrimitiveReleaseError("release documentation cannot be empty")

    search_text = " ".join(
        [
            summary.strip(),
            *sorted(set(str(item) for item in keywords)),
            *sorted(set(str(item) for item in use_cases)),
            str(entrypoint),
            contract_path,
            *interface.search_terms,
        ]
    )
    return PrimitiveArtifactAssessment(
        source_digest,
        contract_digest,
        descriptor_digest,
        search_text,
        runtime_path,
        str(language),
        str(entrypoint_path),
        str(entrypoint),
        str(lock_path),
        str(runtime_version),
        str(implementation_producer_id),
        str(oracle_producer_id),
        len(example_rows),
        len(test_rows),
        interface.interface_id,
        interface.graph_digest,
        interface.edge_count,
        len(interface.ports),
        len(interface.groups),
        interface,
    )


def _one_json(
    by_role: Mapping[CapsuleRole, list[tuple[str, bytes, str]]], role: CapsuleRole
) -> tuple[str, Mapping[str, Any], str]:
    values = by_role.get(role, [])
    if len(values) != 1:
        raise PrimitiveReleaseError(f"release capsule requires exactly one {role.value} record")
    path, content, digest = values[0]
    try:
        decoded = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrimitiveReleaseError(f"{role.value} record must be valid JSON") from exc
    if not isinstance(decoded, Mapping):
        raise PrimitiveReleaseError(f"{role.value} record must be a JSON object")
    return path, decoded, digest


def _validate_case(value: object) -> None:
    if not isinstance(value, Mapping):
        raise PrimitiveReleaseError("example/test cases must be objects")
    if not isinstance(value.get("kind"), str) or value.get("kind") not in {
        "positive",
        "boundary",
        "negative",
    }:
        raise PrimitiveReleaseError("case kind must be positive, boundary, or negative")
    if not isinstance(value.get("args", []), list) or not isinstance(value.get("kwargs", {}), Mapping):
        raise PrimitiveReleaseError("case args and kwargs must be JSON arrays/objects")
    has_expected = "expected" in value
    has_error = isinstance(value.get("expected_error"), str) and bool(value.get("expected_error"))
    if has_expected == has_error:
        raise PrimitiveReleaseError("each case requires exactly one expected result or error")


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        return ()
    return tuple(value)


def _require_digest(value: str, field: str) -> None:
    if not _DIGEST.fullmatch(value):
        raise PrimitiveReleaseError(f"{field} must be a lowercase SHA-256 digest")


def _validate_separation(
    acceptance: PrimitiveAcceptanceReceipt,
    authorization: PrimitiveReleaseAuthorization,
) -> None:
    identities = {
        "implementation": acceptance.implementation_producer_id,
        "oracle": acceptance.oracle_producer_id,
        "verifier": acceptance.verifier_id,
        "authorizer": authorization.authorizer_id,
    }
    if authorization.assurance_level is AssuranceLevel.BOOTSTRAP:
        return
    if acceptance.verifier_id == acceptance.implementation_producer_id:
        raise PrimitiveReleaseError(
            "standard assurance requires a verifier independent of the implementation producer"
        )
    if acceptance.oracle_producer_id == acceptance.implementation_producer_id:
        raise PrimitiveReleaseError(
            "standard assurance requires an oracle independent of the implementation producer"
        )
    if authorization.authorizer_id == acceptance.implementation_producer_id:
        raise PrimitiveReleaseError(
            "standard assurance requires release authorization independent of implementation"
        )
    if (
        authorization.assurance_level is AssuranceLevel.HIGH_ASSURANCE
        and len(set(identities.values())) != len(identities)
    ):
        raise PrimitiveReleaseError(
            "high assurance requires separate implementation, oracle, verifier, and authorizer identities"
        )
