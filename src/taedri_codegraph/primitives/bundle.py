"""Load complete primitive capsules from repository-native directories.

The directory format lets Taedri-owned and third-party primitives live in Git while
the registry remains the searchable serving system.  The manifest declares every
capsule file; undeclared files and symlinks are rejected so a reviewed tree is the
same tree that is staged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..contracts import RecordMixin
from ..primitive_capsules import (
    CapsuleRole,
    PrimitiveRegistry,
    PrimitiveTreeEntry,
    RefKind,
)
from ..primitive_repository import PrimitiveFileInput
from .release import (
    AssuranceLevel,
    PrimitiveArtifactAssessment,
    inspect_release_artifacts,
)


class PrimitiveBundleError(ValueError):
    """Raised when a repository-native primitive directory is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class PrimitiveDirectoryBundle(RecordMixin):
    namespace: str
    name: str
    contract_path: str
    files: tuple[PrimitiveFileInput, ...]
    ref_kind: RefKind
    ref_name: str
    message: str
    policy_decision_id: str
    assurance_level: AssuranceLevel


@dataclass(frozen=True, slots=True)
class InspectedPrimitiveDirectory(RecordMixin):
    bundle: PrimitiveDirectoryBundle
    artifacts: PrimitiveArtifactAssessment
    tree_id: str


def inspect_primitive_directory(
    directory: str | Path,
) -> InspectedPrimitiveDirectory:
    """Fail closed unless a Git-native directory is complete and release-grade."""

    bundle = load_primitive_directory(directory)
    registry = PrimitiveRegistry()
    entries = []
    for item in bundle.files:
        blob = registry.put_blob(item.content, item.media_type)
        entries.append(
            PrimitiveTreeEntry(item.path, item.role, blob, item.mode)
        )
    tree = registry.create_tree(entries)
    return InspectedPrimitiveDirectory(
        bundle,
        inspect_release_artifacts(tree, registry.blobs),
        tree.identity.id,
    )


def load_primitive_directory(directory: str | Path) -> PrimitiveDirectoryBundle:
    """Read and validate one complete capsule directory without executing its code."""

    root = Path(directory).expanduser().resolve()
    manifest_path = root / "primitive.json"
    if not root.is_dir() or not manifest_path.is_file() or manifest_path.is_symlink():
        raise PrimitiveBundleError("primitive directory requires a regular primitive.json")
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrimitiveBundleError("primitive.json must be readable UTF-8 JSON") from exc
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != "1.0.0":
        raise PrimitiveBundleError("primitive.json schema_version must be 1.0.0")
    values = manifest.get("files")
    if not isinstance(values, list) or not values:
        raise PrimitiveBundleError("primitive.json requires a non-empty files array")
    files: list[PrimitiveFileInput] = []
    declared: set[str] = set()
    for index, raw in enumerate(values):
        if not isinstance(raw, Mapping):
            raise PrimitiveBundleError(f"files[{index}] must be an object")
        path_value = _required_string(raw, "path")
        pure = PurePosixPath(path_value)
        if (
            path_value.startswith("/")
            or "\\" in path_value
            or pure.as_posix() != path_value
            or any(part in {"", ".", ".."} for part in pure.parts)
            or path_value == "primitive.json"
        ):
            raise PrimitiveBundleError(f"unsafe primitive file path: {path_value!r}")
        if path_value in declared:
            raise PrimitiveBundleError(f"duplicate primitive file path: {path_value}")
        declared.add(path_value)
        source = root.joinpath(*pure.parts)
        if source.is_symlink() or not source.is_file() or root not in source.resolve().parents:
            raise PrimitiveBundleError(f"declared primitive file is missing or unsafe: {path_value}")
        try:
            role = CapsuleRole(_required_string(raw, "role"))
        except ValueError as exc:
            raise PrimitiveBundleError(f"files[{index}] has an invalid capsule role") from exc
        files.append(
            PrimitiveFileInput(
                path_value,
                role,
                _required_string(raw, "media_type"),
                source.read_bytes(),
                str(raw.get("mode") or "100644"),
            )
        )
    actual = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and not item.is_symlink() and item != manifest_path
    }
    undeclared = sorted(actual - declared)
    if undeclared:
        raise PrimitiveBundleError(
            "primitive directory contains undeclared files: " + ", ".join(undeclared)
        )
    try:
        ref_kind = RefKind(str(manifest.get("ref_kind") or "branch"))
        assurance = AssuranceLevel(str(manifest.get("assurance_level") or "bootstrap"))
    except ValueError as exc:
        raise PrimitiveBundleError("primitive ref kind or assurance level is invalid") from exc
    return PrimitiveDirectoryBundle(
        _required_string(manifest, "namespace"),
        _required_string(manifest, "name"),
        _required_string(manifest, "contract_path"),
        tuple(files),
        ref_kind,
        _required_string(manifest, "ref_name"),
        _required_string(manifest, "message"),
        _required_string(manifest, "policy_decision_id"),
        assurance,
    )


def _required_string(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise PrimitiveBundleError(f"{field} must be a non-empty string")
    return result.strip()
