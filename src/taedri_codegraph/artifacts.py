"""Non-executing Python wheel inspection and source ingestion."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any

from .analyzers import PythonSyntaxAnalyzer
from .canonical import canonical_digest, sha256_digest
from .contracts import EvidenceRecord, GraphBundle, ProducerRef, SubjectRef, TypedValue, ValueKind
from .representations import (
    RepresentationSeed,
    core_representation_registry,
    materialize_seeds,
)

MAX_ARCHIVE_MEMBERS = 200_000
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


class UnsafeArtifactError(ValueError):
    """An artifact violates the non-executing ingestion safety profile."""


@dataclass(frozen=True, slots=True)
class WheelInspection:
    filename: str
    artifact_digest: str
    artifact_size_bytes: int
    distribution_name: str
    version: str
    metadata_version: str
    archive_members: int
    python_sources: int
    import_roots: tuple[str, ...]
    record_entries: int
    record_hashes_verified: int
    record_sizes_verified: int
    license_files: tuple[dict[str, Any], ...]
    metadata_headers: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "artifact_digest": self.artifact_digest,
            "artifact_size_bytes": self.artifact_size_bytes,
            "distribution_name": self.distribution_name,
            "version": self.version,
            "metadata_version": self.metadata_version,
            "archive_members": self.archive_members,
            "python_sources": self.python_sources,
            "import_roots": list(self.import_roots),
            "record_entries": self.record_entries,
            "record_hashes_verified": self.record_hashes_verified,
            "record_sizes_verified": self.record_sizes_verified,
            "license_files": list(self.license_files),
            "metadata_headers": {key: list(values) for key, values in self.metadata_headers.items()},
        }


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise UnsafeArtifactError(f"unsafe wheel member path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeArtifactError(f"unsafe wheel member path: {name!r}")
    return path.as_posix()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_IFMT(mode) == stat.S_IFLNK


def _installed_source_path(name: str) -> PurePosixPath:
    parts = list(PurePosixPath(name).parts)
    if len(parts) >= 3 and parts[0].endswith(".data") and parts[1] in {"purelib", "platlib"}:
        parts = parts[2:]
    return PurePosixPath(*parts)


def _verify_record(
    archive: zipfile.ZipFile,
    record_name: str,
    members: dict[str, zipfile.ZipInfo],
) -> tuple[int, int, int]:
    rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    hashes_verified = 0
    sizes_verified = 0
    recorded_paths: set[str] = set()
    for row in rows:
        if len(row) != 3:
            raise UnsafeArtifactError("wheel RECORD row must have exactly three fields")
        path, encoded_hash, encoded_size = row
        path = _safe_member_name(path)
        if path in recorded_paths:
            raise UnsafeArtifactError(f"duplicate wheel RECORD path: {path}")
        recorded_paths.add(path)
        info = members.get(path)
        if info is None:
            raise UnsafeArtifactError(f"wheel RECORD references a missing member: {path}")
        content = archive.read(info)
        if encoded_hash:
            try:
                algorithm, expected = encoded_hash.split("=", 1)
                if algorithm.casefold() in {"md5", "sha1"}:
                    raise ValueError("weak wheel RECORD digest")
                digest = hashlib.new(algorithm, content).digest()
            except (ValueError, TypeError) as exc:
                raise UnsafeArtifactError(f"unsupported RECORD digest: {encoded_hash}") from exc
            actual = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
            if actual != expected:
                raise UnsafeArtifactError(f"wheel RECORD hash mismatch: {path}")
            hashes_verified += 1
        if encoded_size:
            try:
                expected_size = int(encoded_size)
            except ValueError as exc:
                raise UnsafeArtifactError(f"wheel RECORD has an invalid size: {path}") from exc
            if expected_size != len(content):
                raise UnsafeArtifactError(f"wheel RECORD size mismatch: {path}")
            sizes_verified += 1
    allowed_unrecorded = {record_name, f"{record_name}.jws", f"{record_name}.p7s"}
    missing = set(members) - recorded_paths - allowed_unrecorded
    if missing:
        raise UnsafeArtifactError(
            "wheel members absent from RECORD: " + ", ".join(sorted(missing)[:5])
        )
    return len(rows), hashes_verified, sizes_verified


def inspect_wheel(path: str | os.PathLike[str]) -> WheelInspection:
    wheel = Path(path).resolve(strict=True)
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError(f"not a wheel artifact: {wheel}")
    artifact_bytes = wheel.read_bytes()
    with zipfile.ZipFile(wheel) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise UnsafeArtifactError("wheel has too many archive members")
        members: dict[str, zipfile.ZipInfo] = {}
        total_bytes = 0
        for info in infos:
            name = _safe_member_name(info.filename)
            if name in members:
                raise UnsafeArtifactError(f"duplicate wheel member path: {name}")
            if _is_symlink(info):
                raise UnsafeArtifactError(f"wheel symlinks are refused: {name}")
            if info.file_size > MAX_MEMBER_BYTES:
                raise UnsafeArtifactError(f"wheel member exceeds size limit: {name}")
            total_bytes += info.file_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise UnsafeArtifactError("wheel uncompressed size exceeds limit")
            members[name] = info

        metadata_names = [
            name for name in members if name.endswith(".dist-info/METADATA")
        ]
        record_names = [name for name in members if name.endswith(".dist-info/RECORD")]
        if len(metadata_names) != 1 or len(record_names) != 1:
            raise UnsafeArtifactError("wheel must contain exactly one METADATA and RECORD")
        message = BytesParser(policy=policy.default).parsebytes(archive.read(metadata_names[0]))
        headers: dict[str, list[str]] = {}
        for key, value in message.raw_items():
            headers.setdefault(key, []).append(str(value))
        name = str(message.get("Name") or "").strip()
        version = str(message.get("Version") or "").strip()
        metadata_version = str(message.get("Metadata-Version") or "").strip()
        if not name or not version or not metadata_version:
            raise UnsafeArtifactError("wheel core metadata lacks Name, Version, or Metadata-Version")
        entries, hashes, sizes = _verify_record(
            archive, record_names[0], members
        )
        license_records: list[dict[str, Any]] = []
        declared_license_files = [str(item) for item in message.get_all("License-File", [])]
        dist_info = metadata_names[0].rsplit("/", 1)[0]
        for declared in declared_license_files:
            candidates = (declared, f"{dist_info}/licenses/{declared}", f"{dist_info}/{declared}")
            resolved = next((candidate for candidate in candidates if candidate in members), None)
            if resolved:
                content = archive.read(resolved)
                license_records.append(
                    {
                        "declared_path": declared,
                        "archive_path": resolved,
                        "content_digest": sha256_digest(content),
                        "size_bytes": len(content),
                    }
                )
            else:
                license_records.append({"declared_path": declared, "archive_path": None})
        python_sources = sum(
            1 for name, info in members.items() if name.endswith(".py") and not info.is_dir()
        )
        import_roots: set[str] = set()
        for member_name, info in members.items():
            if info.is_dir() or not member_name.endswith(".py"):
                continue
            parts = list(_installed_source_path(member_name).parts)
            if not parts:
                continue
            root = parts[0][:-3] if len(parts) == 1 else parts[0]
            if root and not root.endswith((".dist-info", ".data")):
                import_roots.add(root.replace("-", "_"))
    return WheelInspection(
        wheel.name,
        sha256_digest(artifact_bytes),
        len(artifact_bytes),
        name,
        version,
        metadata_version,
        len(infos),
        python_sources,
        tuple(sorted(import_roots)),
        entries,
        hashes,
        sizes,
        tuple(license_records),
        {key: tuple(values) for key, values in sorted(headers.items())},
    )


def _extract_python_sources(wheel: Path, destination: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            name = _safe_member_name(info.filename)
            if info.is_dir() or not name.endswith(".py"):
                continue
            if _is_symlink(info):
                raise UnsafeArtifactError(f"wheel symlinks are refused: {name}")
            output = destination.joinpath(*_installed_source_path(name).parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(info))


def _metadata_seeds(
    bundle: GraphBundle,
    inspection: WheelInspection,
    evidence_id: str,
) -> list[RepresentationSeed]:
    subject = SubjectRef("snapshot", bundle.snapshot.identity.id)
    evidence = (evidence_id,)
    source = SubjectRef("evidence", evidence_id)

    def seed(family: str, key: str, value: TypedValue) -> RepresentationSeed:
        return RepresentationSeed(subject, family, key, value, evidence, source)

    seeds = [
        seed("uceg.family.artifact", "uceg.artifact.digest", TypedValue(ValueKind.DIGEST, inspection.artifact_digest)),
        seed("uceg.family.artifact", "uceg.artifact.filename", TypedValue(ValueKind.TEXT, inspection.filename)),
        seed("uceg.family.artifact", "uceg.artifact.pypi.name", TypedValue(ValueKind.KEYWORD, inspection.distribution_name)),
        seed("uceg.family.artifact", "uceg.artifact.pypi.version", TypedValue(ValueKind.KEYWORD, inspection.version)),
        seed(
            "uceg.family.artifact",
            "uceg.artifact.record_verification",
            TypedValue(
                ValueKind.JSON,
                {
                    "entries": inspection.record_entries,
                    "hashes_verified": inspection.record_hashes_verified,
                    "sizes_verified": inspection.record_sizes_verified,
                },
            ),
        ),
        seed(
            "uceg.family.artifact",
            "uceg.artifact.core_metadata",
            TypedValue(
                ValueKind.JSON,
                {key: list(values) for key, values in inspection.metadata_headers.items()},
            ),
        ),
    ]
    headers = inspection.metadata_headers
    for value in headers.get("Requires-Python", ()):
        seeds.append(seed("uceg.family.artifact", "uceg.artifact.python.requires", TypedValue(ValueKind.TEXT, value)))
    for value in headers.get("Requires-Dist", ()):
        seeds.append(seed("uceg.family.artifact", "uceg.artifact.dependency", TypedValue(ValueKind.TEXT, value)))
    for value in headers.get("Project-URL", ()):
        label, separator, url = value.partition(",")
        seeds.append(
            seed(
                "uceg.family.artifact",
                "uceg.artifact.project_url",
                TypedValue(ValueKind.JSON, {"label": label.strip(), "url": url.strip() if separator else ""}),
            )
        )
    for value in headers.get("License-Expression", ()):
        seeds.append(seed("uceg.family.license", "uceg.license.declared.spdx", TypedValue(ValueKind.TEXT, value)))
    for value in headers.get("License", ()):
        if value.strip():
            seeds.append(seed("uceg.family.license", "uceg.license.declared.raw", TypedValue(ValueKind.TEXT, value)))
    for value in headers.get("Classifier", ()):
        if value.startswith("License ::"):
            seeds.append(seed("uceg.family.license", "uceg.license.classifier", TypedValue(ValueKind.TEXT, value)))
    for value in inspection.license_files:
        seeds.append(seed("uceg.family.license", "uceg.license.file", TypedValue(ValueKind.JSON, value)))
    return seeds


def analyze_wheel(
    path: str | os.PathLike[str],
    analyzer: PythonSyntaxAnalyzer | None = None,
) -> tuple[GraphBundle, WheelInspection]:
    """Inspect and analyze a wheel without importing, building, or executing it."""

    wheel = Path(path).resolve(strict=True)
    inspection = inspect_wheel(wheel)
    analyzer = analyzer or PythonSyntaxAnalyzer()
    with tempfile.TemporaryDirectory(prefix="taedri-wheel-") as temporary:
        root = Path(temporary)
        _extract_python_sources(wheel, root)
        bundle = analyzer.analyze(
            root,
            package_name=inspection.distribution_name,
            release=inspection.version,
            source_kind="pypi_wheel",
            source_uri=f"wheel:{inspection.filename}@{inspection.artifact_digest}",
            module_roots=inspection.import_roots,
        )
    producer = ProducerRef(
        "taedri.wheel-inspector",
        "0.1.0",
        canonical_digest(
            {
                "record_verification": True,
                "execute": False,
                "build": False,
                "limits": [MAX_ARCHIVE_MEMBERS, MAX_MEMBER_BYTES, MAX_TOTAL_BYTES],
            }
        ),
    )
    evidence = EvidenceRecord.create(
        snapshot_id=bundle.snapshot.identity.id,
        evidence_type_key="uceg.evidence.python.wheel_artifact",
        uri=f"artifact:{inspection.filename}",
        content_digest=inspection.artifact_digest,
        producer=producer,
    )
    bundle.evidence[evidence.identity.id] = evidence
    artifact_bytes = wheel.read_bytes()
    if sha256_digest(artifact_bytes) != inspection.artifact_digest:
        raise UnsafeArtifactError("wheel changed during analysis")
    bundle.source_blobs[inspection.artifact_digest] = artifact_bytes
    materialize_seeds(
        bundle,
        _metadata_seeds(bundle, inspection, evidence.identity.id),
        producer=producer,
        attempt_key=f"wheel-inspection:{inspection.artifact_digest}",
        environment={"network_allowed": False, "execution_allowed": False},
    )
    bundle.validate(analyzer.registry.resolve, core_representation_registry().resolve)
    return bundle, inspection
