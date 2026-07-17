"""Truthful component-readiness inventory and acceptance validation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


READINESS_STATUSES = frozenset(
    {"working", "partial", "conformance_only", "poc_only", "scaffolded"}
)
INVENTORY_PRODUCT_CLASSIFICATIONS = frozenset(
    {"single_node_private_alpha_candidate"}
)


class ReadinessError(ValueError):
    """Raised when the architecture/readiness manifests disagree or overclaim."""


def load_component_readiness(
    repository_root: str | Path,
    *,
    readiness_path: str | Path = "architecture/component-readiness.v1.json",
    components_path: str | Path = "architecture/components.json",
) -> dict[str, Any]:
    """Load and validate the readiness inventory against the component manifest."""

    root = Path(repository_root).resolve(strict=True)
    readiness = _load_json(root / readiness_path)
    architecture = _load_json(root / components_path)
    if readiness.get("schema_version") != "1.0.0":
        raise ReadinessError("unsupported component-readiness schema version")
    definitions = readiness.get("definition_of_done")
    if not isinstance(definitions, list) or len(definitions) < 5:
        raise ReadinessError("component readiness requires a substantive definition of done")
    readiness_product = _product_readiness(
        readiness.get("product_readiness"), "component readiness"
    )
    architecture_product = _product_readiness(
        architecture.get("product_readiness"), "component architecture"
    )
    for field in ("classification", "serves_truth", "public_paid_saas_ready"):
        if readiness_product[field] != architecture_product[field]:
            raise ReadinessError(
                f"product readiness manifests disagree on {field!r}"
            )
    if readiness_product["public_paid_saas_ready"] and not readiness_product[
        "serves_truth"
    ]:
        raise ReadinessError("public paid SaaS readiness requires serves_truth")
    if readiness_product["serves_truth"] or readiness_product[
        "public_paid_saas_ready"
    ]:
        raise ReadinessError(
            "static component inventories cannot authorize product promotion; "
            "a separately trusted release authority is not implemented"
        )
    expected = {
        item["id"] for item in _mapping_list(architecture.get("components"), "components")
    }
    records = _mapping_list(readiness.get("components"), "readiness components")
    architecture_records = {
        str(item["id"]): item
        for item in _mapping_list(architecture.get("components"), "components")
    }
    actual = {item.get("id") for item in records}
    if None in actual or len(actual) != len(records):
        raise ReadinessError("component readiness IDs must be present and unique")
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ReadinessError(
            f"readiness/component manifest mismatch; missing={missing}, extra={extra}"
        )
    for record in records:
        _validate_record(root, record)
        identifier = str(record["id"])
        if architecture_records[identifier].get("status") != record.get("status"):
            raise ReadinessError(
                f"component {identifier!r} status disagrees with readiness evidence"
            )
    statuses = Counter(str(record["status"]) for record in records)
    return {
        "schema_version": readiness["schema_version"],
        "as_of": readiness.get("as_of"),
        "component_count": len(records),
        "status_counts": dict(sorted(statuses.items())),
        "working_fraction_ppm": statuses["working"] * 1_000_000 // len(records),
        "working_fraction_scope": "declared local or transitional component scope only",
        "release_authority": "inventory_only_no_product_promotion_authority",
        "definition_of_done": definitions,
        "product_readiness": readiness_product,
        "components": records,
        "external_gates": readiness.get("external_gates", []),
    }


def _validate_record(root: Path, record: Mapping[str, Any]) -> None:
    identifier = record.get("id")
    status = record.get("status")
    if status not in READINESS_STATUSES:
        raise ReadinessError(f"component {identifier!r} has unknown status {status!r}")
    implemented_by = _string_list(record.get("implemented_by"), f"{identifier}.implemented_by")
    evidence = _string_list(
        record.get("acceptance_evidence"), f"{identifier}.acceptance_evidence"
    )
    open_gates = _string_list(record.get("open_gates"), f"{identifier}.open_gates")
    if not implemented_by:
        raise ReadinessError(f"component {identifier!r} has no implementation boundary")
    if not open_gates:
        raise ReadinessError(
            f"component {identifier!r} must name its next gate; readiness is not permanent"
        )
    for relative in (*implemented_by, *evidence):
        candidate = root / relative
        if not candidate.exists():
            raise ReadinessError(f"component {identifier!r} references missing path {relative!r}")
    if status == "working" and not evidence:
        raise ReadinessError(f"working component {identifier!r} lacks acceptance evidence")
    if status == "scaffolded" and evidence:
        raise ReadinessError(f"scaffolded component {identifier!r} cannot claim acceptance evidence")


def _product_readiness(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReadinessError(f"{name} must declare product_readiness")
    classification = value.get("classification")
    serves_truth = value.get("serves_truth")
    paid_ready = value.get("public_paid_saas_ready")
    if not isinstance(classification, str) or not classification:
        raise ReadinessError(f"{name} product classification must be non-empty")
    if classification not in INVENTORY_PRODUCT_CLASSIFICATIONS:
        raise ReadinessError(
            f"{name} static inventory cannot declare product classification "
            f"{classification!r}"
        )
    if not isinstance(serves_truth, bool) or not isinstance(paid_ready, bool):
        raise ReadinessError(f"{name} product truth flags must be booleans")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except FileNotFoundError as exc:
        raise ReadinessError(f"missing architecture manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReadinessError(f"invalid JSON architecture manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"architecture manifest must be an object: {path}")
    return value


def _mapping_list(value: Any, name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ReadinessError(f"{name} must be a list of objects")
    return value


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ReadinessError(f"{name} must be a list of non-empty strings")
    return tuple(value)
