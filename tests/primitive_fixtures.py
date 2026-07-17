"""Runtime-native primitive fixtures for cross-version verifier tests.

Checked-in reference capsules are immutable Python 3.12 artifacts. Tests running
under another Python minor must not pretend those artifacts were verified by that
runtime. These helpers create an explicitly test-only variant and update the
runtime evidence and interface graph together. The resulting fixture is never
used as benchmark or product evidence.
"""

from __future__ import annotations

import json
import shutil
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.primitive_capsules import CapsuleRole
from taedri_codegraph.primitive_repository import PrimitiveFileInput
from taedri_codegraph.primitives.bundle import (
    PrimitiveDirectoryBundle,
    load_primitive_directory,
)


requires_checked_campaign_runtime = unittest.skipUnless(
    sys.version_info[:2] == (3, 12),
    "checked campaign packs and strict execution receipts require Python 3.12",
)


def current_python_minor() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def runtime_native_bundle(
    bundle: PrimitiveDirectoryBundle,
) -> PrimitiveDirectoryBundle:
    """Return a test-only bundle whose runtime evidence names this interpreter."""

    return replace(bundle, files=runtime_native_files(bundle.files))


def runtime_native_files(
    files: Iterable[PrimitiveFileInput],
    *,
    runtime_version: str | None = None,
) -> tuple[PrimitiveFileInput, ...]:
    """Retarget runtime metadata and every graph reference as one atomic fixture."""

    items = tuple(files)
    version = runtime_version or current_python_minor()
    runtime_items = [item for item in items if item.role is CapsuleRole.RUNTIME]
    graph_items = [item for item in items if item.role is CapsuleRole.GRAPH_DELTA]
    if len(runtime_items) != 1 or len(graph_items) != 1:
        raise ValueError("runtime-native fixture requires one runtime and one graph")

    runtime = json.loads(runtime_items[0].content)
    if runtime.get("language") != "python":
        raise ValueError("runtime-native fixture only supports Python capsules")
    runtime["runtime_version"] = version
    runtime_content = _json_bytes(runtime)
    runtime_digest = sha256_digest(runtime_content)

    graph = json.loads(graph_items[0].content)
    runtime_nodes = [
        node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and node.get("kind") == "runtime"
    ]
    if len(runtime_nodes) != 1:
        raise ValueError("runtime-native fixture requires one runtime graph node")
    old_node_id = str(runtime_nodes[0]["id"])
    suffix = "".join(character for character in version if character.isalnum())
    new_node_id = f"runtime.python{suffix}"
    runtime_nodes[0]["id"] = new_node_id

    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        if edge.get("source") == old_node_id:
            edge["source"] = new_node_id
        if edge.get("target") == old_node_id:
            edge["target"] = new_node_id
        if edge.get("predicate") == "taedri.predicate.runs_on":
            edge["id"] = f"edge.runs_on_python{suffix}"
        for evidence in edge.get("evidence", []):
            if isinstance(evidence, dict) and evidence.get("path") == "runtime.json":
                evidence["digest"] = runtime_digest

    compatibility = graph.get("compatibility")
    if not isinstance(compatibility, dict):
        raise ValueError("runtime-native fixture requires graph compatibility metadata")
    compatibility["runtime_version"] = version
    dimensions = compatibility.get("dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError("runtime-native fixture requires compatibility dimensions")
    dimensions["taedri.compatibility.runtime_major_minor"] = version
    graph_content = _json_bytes(graph)

    transformed: list[PrimitiveFileInput] = []
    for item in items:
        if item.role is CapsuleRole.RUNTIME:
            transformed.append(replace(item, content=runtime_content))
        elif item.role is CapsuleRole.GRAPH_DELTA:
            transformed.append(replace(item, content=graph_content))
        else:
            transformed.append(item)
    return tuple(transformed)


def copy_runtime_native_primitive(source: Path, target: Path) -> Path:
    """Copy one primitive directory and materialize a runtime-native test variant."""

    shutil.copytree(source, target)
    bundle = load_primitive_directory(target)
    transformed = runtime_native_files(bundle.files)
    for before, after in zip(bundle.files, transformed, strict=True):
        if before.content != after.content:
            (target / after.path).write_bytes(after.content)
    return target


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
