"""Content-addressed object storage and portable graph-epoch backup manifests."""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Mapping, Protocol

from .canonical import canonical_json_bytes, sha256_digest
from .contracts import RecordMixin
from .identity import IdentityRecord
from .storage import GraphStore


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ObjectStoreError(ValueError):
    """Raised when immutable object storage violates its digest contract."""


@dataclass(frozen=True, slots=True)
class StoredObject(RecordMixin):
    digest: str
    size_bytes: int
    key: str
    media_type: str

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.digest):
            raise ObjectStoreError("stored object requires a sha256 digest")
        if self.size_bytes < 0 or not self.key or not self.media_type:
            raise ObjectStoreError("stored object size, key, and media type are required")


class ObjectStore(Protocol):
    """Small immutable port implemented by local files and S3-compatible clients."""

    def put_bytes(self, content: bytes, *, media_type: str) -> StoredObject: ...

    def get_bytes(self, digest: str, *, max_bytes: int | None = None) -> bytes: ...

    def contains(self, digest: str) -> bool: ...


def object_key(digest: str, *, prefix: str = "") -> str:
    if not _DIGEST.fullmatch(digest):
        raise ObjectStoreError("object key requires a sha256 digest")
    hexadecimal = digest.removeprefix("sha256:")
    base = f"blobs/sha256/{hexadecimal[:2]}/{hexadecimal[2:]}"
    clean = prefix.strip("/")
    return f"{clean}/{base}" if clean else base


class FilesystemObjectStore:
    """Atomic local implementation of the same immutable object contract."""

    def __init__(self, root: str | os.PathLike[str], *, prefix: str = ""):
        self.root = Path(root)
        self.prefix = prefix.strip("/")

    def put_bytes(
        self, content: bytes, *, media_type: str = "application/octet-stream"
    ) -> StoredObject:
        digest = sha256_digest(content)
        key = object_key(digest, prefix=self.prefix)
        destination = self.root.joinpath(*PurePosixPath(key).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing = destination.read_bytes()
            if sha256_digest(existing) != digest:
                raise ObjectStoreError(f"existing object is corrupt: {digest}")
            return StoredObject(digest, len(existing), key, media_type)
        temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredObject(digest, len(content), key, media_type)

    def get_bytes(self, digest: str, *, max_bytes: int | None = None) -> bytes:
        path = self.root.joinpath(*PurePosixPath(object_key(digest, prefix=self.prefix)).parts)
        try:
            size = path.stat().st_size
        except FileNotFoundError as exc:
            raise ObjectStoreError(f"object not found: {digest}") from exc
        if max_bytes is not None and size > max_bytes:
            raise ObjectStoreError(f"object exceeds read limit: {digest}")
        content = path.read_bytes()
        if sha256_digest(content) != digest:
            raise ObjectStoreError(f"object digest mismatch: {digest}")
        return content

    def contains(self, digest: str) -> bool:
        return self.root.joinpath(
            *PurePosixPath(object_key(digest, prefix=self.prefix)).parts
        ).is_file()


class S3ObjectStore:
    """S3-compatible adapter using an injected boto3-style client.

    The core keeps no boto dependency. Production construction may lazily import boto3,
    while conformance tests use a protocol-compatible client and exercise identical keys,
    metadata, immutability checks, and digest validation.
    """

    def __init__(self, client: Any, bucket: str, *, prefix: str = ""):
        if not bucket:
            raise ObjectStoreError("S3 bucket is required")
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    @classmethod
    def from_boto3(
        cls,
        *,
        bucket: str,
        prefix: str = "",
        endpoint_url: str | None = None,
        region_name: str | None = None,
    ) -> "S3ObjectStore":
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - optional production dependency
            raise RuntimeError("install taedri-codegraph[cloud] for S3 object storage") from exc
        client = boto3.client(
            "s3", endpoint_url=endpoint_url, region_name=region_name
        )
        return cls(client, bucket, prefix=prefix)

    def put_bytes(
        self, content: bytes, *, media_type: str = "application/octet-stream"
    ) -> StoredObject:
        digest = sha256_digest(content)
        key = object_key(digest, prefix=self.prefix)
        if self.contains(digest):
            existing = self.get_bytes(digest, max_bytes=len(content))
            if existing != content:
                raise ObjectStoreError(f"content collision behind digest: {digest}")
            return StoredObject(digest, len(content), key, media_type)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=media_type,
            Metadata={"sha256": digest.removeprefix("sha256:")},
        )
        return StoredObject(digest, len(content), key, media_type)

    def get_bytes(self, digest: str, *, max_bytes: int | None = None) -> bytes:
        key = object_key(digest, prefix=self.prefix)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if _missing_s3_object(exc):
                raise ObjectStoreError(f"object not found: {digest}") from exc
            raise
        declared = response.get("ContentLength")
        if max_bytes is not None and isinstance(declared, int) and declared > max_bytes:
            raise ObjectStoreError(f"object exceeds read limit: {digest}")
        body = response.get("Body")
        content = body.read(max_bytes + 1 if max_bytes is not None else -1)
        if not isinstance(content, bytes):
            raise ObjectStoreError("S3 client returned a non-bytes object body")
        if max_bytes is not None and len(content) > max_bytes:
            raise ObjectStoreError(f"object exceeds read limit: {digest}")
        if sha256_digest(content) != digest:
            raise ObjectStoreError(f"object digest mismatch: {digest}")
        return content

    def contains(self, digest: str) -> bool:
        key = object_key(digest, prefix=self.prefix)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if _missing_s3_object(exc):
                return False
            raise


@dataclass(frozen=True, slots=True)
class EpochBackupManifest(RecordMixin):
    identity: IdentityRecord
    format_version: str
    epoch_id: str
    graph_manifest_digest: str
    epoch_files: Mapping[str, StoredObject]
    cas_objects: Mapping[str, StoredObject]

    @classmethod
    def create(
        cls,
        *,
        epoch_id: str,
        graph_manifest_digest: str,
        epoch_files: Mapping[str, StoredObject],
        cas_objects: Mapping[str, StoredObject],
    ) -> "EpochBackupManifest":
        if not epoch_id or not _DIGEST.fullmatch(graph_manifest_digest):
            raise ObjectStoreError("epoch and graph manifest digest are required")
        key = {
            "format_version": "1.0.0",
            "epoch_id": epoch_id,
            "graph_manifest_digest": graph_manifest_digest,
            "epoch_files": {
                path: value.to_dict() for path, value in sorted(epoch_files.items())
            },
            "cas_objects": {
                digest: value.to_dict() for digest, value in sorted(cas_objects.items())
            },
        }
        return cls(
            IdentityRecord.create("epoch_backup", key),
            "1.0.0",
            epoch_id,
            graph_manifest_digest,
            dict(sorted(epoch_files.items())),
            dict(sorted(cas_objects.items())),
        )


def backup_epoch(
    graph_store: GraphStore,
    object_store: ObjectStore,
    epoch_id: str | None = None,
) -> tuple[EpochBackupManifest, StoredObject]:
    """Upload one validated published epoch and exactly its reachable CAS objects."""

    resolved = epoch_id or graph_store.current_epoch_id()
    graph_store.validate_epoch(resolved, published=True)
    epoch_root = graph_store.published / resolved
    files: dict[str, StoredObject] = {}
    for path in sorted(epoch_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(epoch_root).as_posix()
        content = path.read_bytes()
        files[relative] = object_store.put_bytes(
            content, media_type=_epoch_media_type(relative)
        )
    manifest_path = epoch_root / "manifest.json"
    graph_manifest_digest = sha256_digest(manifest_path.read_bytes())
    cas_objects: dict[str, StoredObject] = {}
    for digest in sorted(_reachable_cas_digests(epoch_root, graph_store)):
        content = _read_graph_cas(graph_store, digest)
        cas_objects[digest] = object_store.put_bytes(
            content, media_type="application/octet-stream"
        )
    backup = EpochBackupManifest.create(
        epoch_id=resolved,
        graph_manifest_digest=graph_manifest_digest,
        epoch_files=files,
        cas_objects=cas_objects,
    )
    backup_object = object_store.put_bytes(
        canonical_json_bytes(backup) + b"\n",
        media_type="application/vnd.taedri.epoch-backup+json",
    )
    return backup, backup_object


def restore_epoch(
    graph_store: GraphStore,
    object_store: ObjectStore,
    manifest: EpochBackupManifest,
    *,
    publish: bool = False,
) -> str:
    """Restore a portable epoch backup and fail closed before publication."""

    graph_store._ensure_layout()
    destination = graph_store.candidates / manifest.epoch_id
    published_destination = graph_store.published / manifest.epoch_id
    if destination.exists() or published_destination.exists():
        graph_store.validate_epoch(
            manifest.epoch_id, published=published_destination.exists()
        )
        if publish and not published_destination.exists():
            graph_store.publish_epoch(manifest.epoch_id)
        return manifest.epoch_id
    stage = graph_store.candidates / f".restoring-{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        for relative, stored in sorted(manifest.epoch_files.items()):
            safe = _safe_relative(relative)
            content = object_store.get_bytes(stored.digest, max_bytes=stored.size_bytes)
            if len(content) != stored.size_bytes:
                raise ObjectStoreError(f"epoch object size mismatch: {relative}")
            output = stage.joinpath(*safe.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        restored_manifest = stage / "manifest.json"
        if sha256_digest(restored_manifest.read_bytes()) != manifest.graph_manifest_digest:
            raise ObjectStoreError("restored graph manifest digest mismatch")
        for digest, stored in sorted(manifest.cas_objects.items()):
            if stored.digest != digest:
                raise ObjectStoreError("CAS manifest key and object digest disagree")
            content = object_store.get_bytes(digest, max_bytes=stored.size_bytes)
            graph_store._write_cas(digest, content)
        os.replace(stage, destination)
        graph_store.validate_epoch(manifest.epoch_id, published=False)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    if publish:
        graph_store.publish_epoch(manifest.epoch_id)
    return manifest.epoch_id


def epoch_backup_from_dict(value: Mapping[str, Any]) -> EpochBackupManifest:
    """Decode and validate an epoch backup record from its portable JSON form."""

    identity_value = value.get("identity")
    if not isinstance(identity_value, Mapping):
        raise ObjectStoreError("backup identity is missing")
    identity = IdentityRecord(
        str(identity_value.get("id", "")),
        str(identity_value.get("kind", "")),
        identity_value.get("canonical_key"),
    )
    identity.validate()
    epoch_files = _stored_mapping(value.get("epoch_files"), "epoch_files")
    cas_objects = _stored_mapping(value.get("cas_objects"), "cas_objects")
    decoded = EpochBackupManifest(
        identity,
        str(value.get("format_version", "")),
        str(value.get("epoch_id", "")),
        str(value.get("graph_manifest_digest", "")),
        epoch_files,
        cas_objects,
    )
    expected = EpochBackupManifest.create(
        epoch_id=decoded.epoch_id,
        graph_manifest_digest=decoded.graph_manifest_digest,
        epoch_files=decoded.epoch_files,
        cas_objects=decoded.cas_objects,
    )
    if expected != decoded:
        raise ObjectStoreError("backup manifest identity or content is invalid")
    return decoded


def _stored_mapping(value: Any, name: str) -> dict[str, StoredObject]:
    if not isinstance(value, Mapping):
        raise ObjectStoreError(f"{name} must be an object")
    result: dict[str, StoredObject] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, Mapping):
            raise ObjectStoreError(f"{name} entries are invalid")
        result[key] = StoredObject(
            str(item.get("digest", "")),
            int(item.get("size_bytes", -1)),
            str(item.get("key", "")),
            str(item.get("media_type", "")),
        )
    return result


def _reachable_cas_digests(epoch_root: Path, graph_store: GraphStore) -> set[str]:
    values: set[str] = set()
    for path in sorted(epoch_root.glob("*.json*")):
        if path.name == "index.sqlite":
            continue
        for line in path.read_text("utf-8").splitlines():
            if not line:
                continue
            try:
                _collect_digests(json.loads(line), values)
            except json.JSONDecodeError as exc:
                raise ObjectStoreError(f"invalid epoch JSON while backing up {path.name}") from exc
    return {digest for digest in values if _graph_cas_path(graph_store, digest).is_file()}


def _collect_digests(value: Any, output: set[str]) -> None:
    if isinstance(value, str) and _DIGEST.fullmatch(value):
        output.add(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            _collect_digests(item, output)
    elif isinstance(value, list):
        for item in value:
            _collect_digests(item, output)


def _graph_cas_path(graph_store: GraphStore, digest: str) -> Path:
    hexadecimal = digest.removeprefix("sha256:")
    return graph_store.cas / hexadecimal[:2] / hexadecimal[2:]


def _read_graph_cas(graph_store: GraphStore, digest: str) -> bytes:
    path = _graph_cas_path(graph_store, digest)
    try:
        content = path.read_bytes()
    except FileNotFoundError as exc:
        raise ObjectStoreError(f"graph CAS object is missing: {digest}") from exc
    if sha256_digest(content) != digest:
        raise ObjectStoreError(f"graph CAS object is corrupt: {digest}")
    return content


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ObjectStoreError(f"unsafe epoch object path: {value!r}")
    return path


def _epoch_media_type(relative: str) -> str:
    if relative.endswith((".json", ".jsonl")):
        return "application/json"
    if relative.endswith(".sqlite"):
        return "application/vnd.sqlite3"
    return "application/octet-stream"


def _missing_s3_object(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return isinstance(exc, (KeyError, FileNotFoundError))
    error = response.get("Error")
    return isinstance(error, Mapping) and str(error.get("Code")) in {
        "404",
        "NoSuchKey",
        "NotFound",
    }
