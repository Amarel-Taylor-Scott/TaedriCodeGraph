"""Immutable local fact storage and atomic graph-epoch publication."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from .canonical import canonical_digest, canonical_json_bytes, sha256_digest
from .contracts import GraphBundle, RecordMixin
from .identity import IdentityRecord
from .query import GraphIndex, build_index
from .registry import ExtensionRegistry, core_registry


class EpochValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GraphEpochManifest(RecordMixin):
    identity: IdentityRecord
    format_version: str
    snapshot_id: str
    analysis_manifest_id: str
    registry_digest: str
    shard_digests: Mapping[str, str]
    record_counts: Mapping[str, int]
    index_manifest: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        analysis_manifest_id: str,
        registry_digest: str,
        shard_digests: Mapping[str, str],
        record_counts: Mapping[str, int],
        index_manifest: Mapping[str, Any],
    ) -> "GraphEpochManifest":
        key = {
            "format_version": "1.0.0",
            "snapshot_id": snapshot_id,
            "analysis_manifest_id": analysis_manifest_id,
            "registry_digest": registry_digest,
            "shard_digests": dict(sorted(shard_digests.items())),
            "record_counts": dict(sorted(record_counts.items())),
            "index_manifest": dict(index_manifest),
        }
        return cls(
            IdentityRecord.create("graph_epoch", key),
            "1.0.0",
            snapshot_id,
            analysis_manifest_id,
            registry_digest,
            dict(sorted(shard_digests.items())),
            dict(sorted(record_counts.items())),
            dict(index_manifest),
        )


class GraphStore:
    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.cas = self.root / "cas" / "sha256"
        self.candidates = self.root / "epochs" / "candidates"
        self.published = self.root / "epochs" / "published"
        self.current_pointer = self.root / "CURRENT"

    def _ensure_layout(self) -> None:
        self.cas.mkdir(parents=True, exist_ok=True)
        self.candidates.mkdir(parents=True, exist_ok=True)
        self.published.mkdir(parents=True, exist_ok=True)

    def _write_atomic(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _write_cas(self, digest: str, content: bytes) -> Path:
        if sha256_digest(content) != digest:
            raise EpochValidationError(f"CAS content does not match digest {digest}")
        hexadecimal = digest.removeprefix("sha256:")
        destination = self.cas / hexadecimal[:2] / hexadecimal[2:]
        if destination.exists():
            if sha256_digest(destination.read_bytes()) != digest:
                raise EpochValidationError(f"existing CAS object is corrupt: {digest}")
            return destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def write_candidate(
        self,
        bundle: GraphBundle,
        registry: ExtensionRegistry | None = None,
    ) -> str:
        registry = registry or core_registry()
        bundle.validate(registry.resolve)
        self._ensure_layout()
        for digest, content in bundle.source_blobs.items():
            self._write_cas(digest, content)

        stage = self.candidates / f".building-{uuid.uuid4().hex}"
        stage.mkdir()
        try:
            shard_digests: dict[str, str] = {}
            record_counts: dict[str, int] = {}
            fixed_records = {
                "snapshot": [bundle.snapshot],
                "analysis": [bundle.analysis],
            }
            for name, records in fixed_records.items():
                data = b"".join(canonical_json_bytes(record) + b"\n" for record in records)
                path = stage / f"{name}.jsonl"
                path.write_bytes(data)
                shard_digests[path.name] = sha256_digest(data)
                record_counts[name] = len(records)
            for name, mapping in bundle.record_sets().items():
                records = [mapping[key] for key in sorted(mapping)]
                data = b"".join(canonical_json_bytes(record) + b"\n" for record in records)
                path = stage / f"{name}.jsonl"
                path.write_bytes(data)
                shard_digests[path.name] = sha256_digest(data)
                record_counts[name] = len(records)
            registry_bytes = canonical_json_bytes(registry.manifest()) + b"\n"
            (stage / "registry.json").write_bytes(registry_bytes)
            registry_digest = sha256_digest(registry_bytes)
            shard_digests["registry.json"] = registry_digest
            record_counts["registry_descriptors"] = len(registry.descriptors())

            index_manifest = build_index(bundle, stage / "index.sqlite")
            index_manifest["logical_config_digest"] = canonical_digest(index_manifest)
            manifest = GraphEpochManifest.create(
                snapshot_id=bundle.snapshot.identity.id,
                analysis_manifest_id=bundle.analysis.identity.id,
                registry_digest=registry_digest,
                shard_digests=shard_digests,
                record_counts=record_counts,
                index_manifest=index_manifest,
            )
            manifest_bytes = canonical_json_bytes(manifest) + b"\n"
            (stage / "manifest.json").write_bytes(manifest_bytes)
            epoch_id = manifest.identity.id
            destination = self.candidates / epoch_id
            if destination.exists() or (self.published / epoch_id).exists():
                shutil.rmtree(stage)
                existing = destination if destination.exists() else self.published / epoch_id
                self.validate_epoch(epoch_id, published=existing.parent == self.published)
                return epoch_id
            os.replace(stage, destination)
            self.validate_epoch(epoch_id, published=False)
            return epoch_id
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def _epoch_path(self, epoch_id: str, *, published: bool | None = None) -> Path:
        if published is True:
            return self.published / epoch_id
        if published is False:
            return self.candidates / epoch_id
        published_path = self.published / epoch_id
        return published_path if published_path.exists() else self.candidates / epoch_id

    def read_manifest(
        self, epoch_id: str, *, published: bool | None = None
    ) -> dict[str, Any]:
        path = self._epoch_path(epoch_id, published=published) / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"unknown graph epoch: {epoch_id}")
        return json.loads(path.read_text("utf-8"))

    def validate_epoch(self, epoch_id: str, *, published: bool | None = None) -> dict[str, Any]:
        path = self._epoch_path(epoch_id, published=published)
        manifest = self.read_manifest(epoch_id, published=published)
        identity_data = manifest.get("identity", {})
        identity = IdentityRecord(
            identity_data.get("id", ""),
            identity_data.get("kind", ""),
            identity_data.get("canonical_key"),
        )
        try:
            identity.validate()
        except Exception as exc:
            raise EpochValidationError(str(exc)) from exc
        if identity.id != epoch_id:
            raise EpochValidationError("epoch directory does not match manifest identity")
        for filename, expected_digest in manifest["shard_digests"].items():
            shard = path / filename
            if not shard.is_file():
                raise EpochValidationError(f"missing epoch shard: {filename}")
            actual = sha256_digest(shard.read_bytes())
            if actual != expected_digest:
                raise EpochValidationError(
                    f"epoch shard digest mismatch for {filename}: {actual} != {expected_digest}"
                )
        index = path / "index.sqlite"
        if not index.is_file() or GraphIndex(index).integrity_check() != "ok":
            raise EpochValidationError("epoch serving index failed integrity check")
        return manifest

    @contextmanager
    def _publish_lock(self) -> Iterator[None]:
        self._ensure_layout()
        handle = (self.root / "PUBLISH.lock").open("a+b")
        try:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - Windows adapter comes later
                pass
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover
                pass
            handle.close()

    def publish_epoch(self, epoch_id: str) -> str:
        with self._publish_lock():
            candidate = self.candidates / epoch_id
            destination = self.published / epoch_id
            if candidate.exists():
                self.validate_epoch(epoch_id, published=False)
                if destination.exists():
                    shutil.rmtree(candidate)
                else:
                    os.replace(candidate, destination)
            elif not destination.exists():
                raise FileNotFoundError(f"unknown candidate graph epoch: {epoch_id}")
            self.validate_epoch(epoch_id, published=True)
            self._write_atomic(self.current_pointer, (epoch_id + "\n").encode("utf-8"))
        return epoch_id

    def current_epoch_id(self) -> str:
        try:
            epoch_id = self.current_pointer.read_text("utf-8").strip()
        except FileNotFoundError as exc:
            raise FileNotFoundError("no graph epoch has been published") from exc
        if not epoch_id:
            raise EpochValidationError("CURRENT epoch pointer is empty")
        return epoch_id

    def index(self, epoch_id: str | None = None) -> GraphIndex:
        resolved = epoch_id or self.current_epoch_id()
        path = self.published / resolved / "index.sqlite"
        if not path.is_file():
            raise FileNotFoundError(f"published graph epoch has no index: {resolved}")
        return GraphIndex(path)

    def list_epochs(self) -> dict[str, list[str]]:
        self._ensure_layout()
        return {
            "candidates": sorted(
                path.name for path in self.candidates.iterdir() if not path.name.startswith(".")
            ),
            "published": sorted(
                path.name for path in self.published.iterdir() if not path.name.startswith(".")
            ),
            "current": [self.current_epoch_id()] if self.current_pointer.exists() else [],
        }
