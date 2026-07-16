"""Fail-closed client inspection, caching, and selective primitive materialization."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol

from ..canonical import canonical_json_bytes, sha256_digest
from ..contracts import RecordMixin
from ..primitive_capsules import (
    BlobDescriptor,
    CapsuleRole,
    PrimitiveRegistryError,
    decode_primitive_pack,
)


DEFAULT_DIGESTION_ROLES = tuple(
    role for role in CapsuleRole if role is not CapsuleRole.VERIFIER
)


class BlobCache(Protocol):
    def get(self, digest: str) -> bytes | None: ...

    def put(self, descriptor: BlobDescriptor, content: bytes) -> None: ...


@dataclass(frozen=True, slots=True)
class DigestionPolicy(RecordMixin):
    allowed_roles: tuple[CapsuleRole, ...] = DEFAULT_DIGESTION_ROLES
    maximum_encoded_bytes: int = 32 * 1024 * 1024
    maximum_uncompressed_bytes: int = 128 * 1024 * 1024
    maximum_files: int = 512
    maximum_materialized_bytes: int = 64 * 1024 * 1024
    allow_executable_mode: bool = False
    require_contract: bool = True

    def __post_init__(self) -> None:
        if len(set(self.allowed_roles)) != len(self.allowed_roles):
            raise ValueError("digestion roles must be unique")
        if min(
            self.maximum_encoded_bytes,
            self.maximum_uncompressed_bytes,
            self.maximum_files,
            self.maximum_materialized_bytes,
        ) <= 0:
            raise ValueError("digestion limits must be positive")


@dataclass(frozen=True, slots=True)
class DigestedFile(RecordMixin):
    path: str
    role: CapsuleRole
    digest: str
    size_bytes: int
    mode: str
    from_cache: bool


@dataclass(frozen=True, slots=True)
class DigestionReceipt(RecordMixin):
    pack_id: str
    pack_digest: str
    target: str
    files: tuple[DigestedFile, ...]
    omitted_roles: tuple[str, ...]
    materialized_bytes: int
    cache_hits: int
    executable_bits_removed: int


class FilesystemBlobCache:
    """Small digest-addressed client cache shared across thin primitive downloads."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        value = digest.removeprefix("sha256:")
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise PrimitiveRegistryError("cache digest must be lowercase sha256")
        return self.root / "sha256" / value[:2] / value[2:]

    def get(self, digest: str) -> bytes | None:
        path = self._path(digest)
        if not path.is_file():
            return None
        content = path.read_bytes()
        if sha256_digest(content) != digest:
            raise PrimitiveRegistryError(f"cached blob digest mismatch: {digest}")
        return content

    def put(self, descriptor: BlobDescriptor, content: bytes) -> None:
        descriptor.validate(content)
        path = self._path(descriptor.digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = path.read_bytes()
            descriptor.validate(existing)
            return
        descriptor_path = path.parent
        with tempfile.NamedTemporaryFile(dir=descriptor_path, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)


class PrimitiveDigester:
    def __init__(self, policy: DigestionPolicy | None = None) -> None:
        self.policy = policy or DigestionPolicy()

    def materialize(
        self,
        encoded: bytes,
        target: str | Path,
        *,
        cache: BlobCache | None = None,
    ) -> DigestionReceipt:
        if len(encoded) > self.policy.maximum_encoded_bytes:
            raise PrimitiveRegistryError("encoded primitive pack exceeds client policy")
        manifest, payloads = decode_primitive_pack(
            encoded, max_uncompressed_bytes=self.policy.maximum_uncompressed_bytes
        )
        pack_id = str(_mapping(manifest.get("identity"), "identity").get("id", ""))
        if not pack_id.startswith("uceg:v1:primitive_pack:"):
            raise PrimitiveRegistryError("primitive pack identity kind is invalid")
        entries = manifest.get("entries")
        if not isinstance(entries, list) or len(entries) > self.policy.maximum_files:
            raise PrimitiveRegistryError("primitive pack file count exceeds client policy")
        allowed = {item.value for item in self.policy.allowed_roles}
        selected: list[tuple[dict[str, object], BlobDescriptor, bytes, bool]] = []
        omitted_roles: set[str] = set()
        contract_seen = False
        total = 0
        cache_hits = 0
        for raw in entries:
            entry = _mapping(raw, "entry")
            role = str(entry.get("role", ""))
            if role not in allowed:
                omitted_roles.add(role)
                continue
            path = _safe_path(str(entry.get("path", "")))
            blob = _mapping(entry.get("blob"), "entry blob")
            descriptor = BlobDescriptor(
                str(blob.get("digest", "")),
                int(blob.get("size_bytes", -1)),
                str(blob.get("media_type", "")),
            )
            content = payloads.get(descriptor.digest)
            from_cache = False
            if content is None and cache is not None:
                content = cache.get(descriptor.digest)
                from_cache = content is not None
            if content is None:
                raise PrimitiveRegistryError(
                    f"thin pack requires missing cached blob {descriptor.digest}"
                )
            descriptor.validate(content)
            total += len(content)
            if total > self.policy.maximum_materialized_bytes:
                raise PrimitiveRegistryError("materialized primitive exceeds client byte policy")
            if role == CapsuleRole.CONTRACT.value:
                contract_seen = True
            if from_cache:
                cache_hits += 1
            selected.append((dict(entry, path=path.as_posix()), descriptor, content, from_cache))
        if self.policy.require_contract and not contract_seen:
            raise PrimitiveRegistryError("selected primitive content has no contract")
        if cache is not None:
            included = _descriptor_map(manifest.get("included_blobs"))
            for digest, content in payloads.items():
                descriptor = included.get(digest)
                if descriptor is None:
                    raise PrimitiveRegistryError("payload is absent from included blob manifest")
                cache.put(descriptor, content)

        root = Path(target).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        materialized: list[DigestedFile] = []
        executable_bits_removed = 0
        for entry, descriptor, content, from_cache in selected:
            relative = _safe_path(str(entry["path"]))
            destination = (root / relative.as_posix()).resolve()
            if root != destination and root not in destination.parents:
                raise PrimitiveRegistryError("primitive path escapes materialization root")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                raise PrimitiveRegistryError("primitive destination cannot be a symlink")
            with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            requested_mode = str(entry.get("mode", "100644"))
            effective_mode = requested_mode
            if requested_mode == "100755" and not self.policy.allow_executable_mode:
                effective_mode = "100644"
                executable_bits_removed += 1
            temporary.chmod(0o755 if effective_mode == "100755" else 0o644)
            temporary.replace(destination)
            materialized.append(
                DigestedFile(
                    relative.as_posix(),
                    CapsuleRole(str(entry["role"])),
                    descriptor.digest,
                    descriptor.size_bytes,
                    effective_mode,
                    from_cache,
                )
            )
        return DigestionReceipt(
            pack_id,
            sha256_digest(encoded),
            root.as_posix(),
            tuple(materialized),
            tuple(sorted(omitted_roles)),
            total,
            cache_hits,
            executable_bits_removed,
        )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise PrimitiveRegistryError(f"primitive pack {label} must be an object")
    return value


def _safe_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PrimitiveRegistryError(f"unsafe primitive path: {value!r}")
    return path


def _descriptor_map(value: object) -> dict[str, BlobDescriptor]:
    if not isinstance(value, list):
        raise PrimitiveRegistryError("included blob manifest must be a list")
    result = {}
    for raw in value:
        item = _mapping(raw, "blob descriptor")
        descriptor = BlobDescriptor(
            str(item.get("digest", "")),
            int(item.get("size_bytes", -1)),
            str(item.get("media_type", "")),
        )
        result[descriptor.digest] = descriptor
    return result
