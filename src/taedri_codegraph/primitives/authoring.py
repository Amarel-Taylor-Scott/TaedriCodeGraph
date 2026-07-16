"""Strict compiler for complete repository-native primitive directories.

The compiler reduces repetitive authoring without weakening the release boundary. A
specification must contain real source, contracts, examples, tests, documentation,
license policy, provenance identities, and capability labels. It emits all capsule
records with digest-bound evidence, then the normal bundle inspector independently
validates the result. It never stages or releases a primitive.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..canonical import canonical_digest, canonical_json_bytes, sha256_digest
from .bundle import InspectedPrimitiveDirectory, inspect_primitive_directory


class PrimitiveAuthoringError(ValueError):
    """Raised when an authoring spec would produce an incomplete capsule."""


_REGISTRY_NAME = re.compile(r"^[a-z][a-z0-9.-]{1,127}$")
_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PREDICATE_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_PLACEHOLDER_MARKERS = ("todo", "placeholder", "not implemented", "tbd")
_LICENSE_EVIDENCE = (
    "This primitive follows the repository's current licensing status: all rights "
    "reserved.\nNo public open-source license or redistribution grant is asserted "
    "by this capsule.\n"
).encode("utf-8")


@dataclass(frozen=True, slots=True)
class PrimitiveAuthoringSpec:
    namespace: str
    name: str
    category: str
    function_name: str
    source_code: str
    summary: str
    keywords: tuple[str, ...]
    use_cases: tuple[str, ...]
    limitations: tuple[str, ...]
    input_name: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    errors: tuple[Mapping[str, str], ...]
    examples: tuple[Mapping[str, Any], ...]
    tests: tuple[Mapping[str, Any], ...]
    group_id: str
    group_labels: tuple[str, ...]
    documentation: str
    references: tuple[str, ...]
    source_uri: str
    implementation_producer_id: str
    oracle_producer_id: str
    policy_decision_id: str
    allowed_imports: tuple[str, ...] = ()
    runtime_version: str = "3.12"
    dependency_lock: str = "# This primitive has no third-party dependencies.\n"
    license_expression: str = "LicenseRef-Taedri-All-Rights-Reserved"

    @property
    def module_name(self) -> str:
        return self.name.replace("-", "_")

    @property
    def source_path(self) -> str:
        return f"src/{self.module_name}.py"


def build_primitive_files(spec: PrimitiveAuthoringSpec) -> Mapping[str, bytes]:
    """Compile one strict spec into the 13 files of a complete v1 capsule."""

    _validate_spec(spec)
    source = spec.source_code.encode("utf-8")
    contract = {
        "schema_version": "1.0.0",
        "inputs": [{"name": spec.input_name, "schema": dict(spec.input_schema)}],
        "output": {"schema": dict(spec.output_schema)},
        "errors": [dict(item) for item in spec.errors],
        "effects": [],
    }
    descriptor = {
        "summary": spec.summary,
        "keywords": list(spec.keywords),
        "use_cases": list(spec.use_cases),
        "limitations": list(spec.limitations),
        "references": list(spec.references),
    }
    examples = {"examples": [dict(item) for item in spec.examples]}
    tests = {"cases": [dict(item) for item in spec.tests]}
    verifier = {
        "schema_version": "1.0.0",
        "oracle_producer_id": spec.oracle_producer_id,
        "comparison": "exact JSON value or exact exception class",
        "minimum_cases": len(spec.examples) + len(spec.tests),
    }
    dependency_lock = spec.dependency_lock.encode("utf-8")
    runtime = {
        "schema_version": "1.0.0",
        "language": "python",
        "runtime_version": spec.runtime_version,
        "entrypoint_path": spec.source_path,
        "entrypoint": spec.function_name,
        "dependency_lock_path": "dependencies.lock",
        "dependency_lock_digest": sha256_digest(dependency_lock),
        "network": "denied",
    }

    contract_bytes = _json_bytes(contract)
    descriptor_bytes = _json_bytes(descriptor)
    examples_bytes = _json_bytes(examples)
    tests_bytes = _json_bytes(tests)
    runtime_bytes = _json_bytes(runtime)
    source_blob_digest = sha256_digest(source)
    source_digest = sha256_digest(
        canonical_json_bytes(
            [{"path": spec.source_path, "digest": source_blob_digest}]
        )
    )
    provenance = {
        "schema_version": "1.0.0",
        "implementation_producer_id": spec.implementation_producer_id,
        "source_uri": spec.source_uri,
        "source_revision": source_digest,
        "source_digest": source_digest,
    }
    license_record = {
        "schema_version": "1.0.0",
        "state": "verified",
        "spdx_expression": spec.license_expression,
        "evidence_path": "LICENSE_EVIDENCE.txt",
        "evidence_digest": sha256_digest(_LICENSE_EVIDENCE),
        "note": "All rights reserved; no public project license has been granted.",
    }
    graph = _interface_graph(
        spec,
        contract=contract,
        contract_digest=sha256_digest(contract_bytes),
        descriptor_digest=sha256_digest(descriptor_bytes),
        examples_digest=sha256_digest(examples_bytes),
        tests_digest=sha256_digest(tests_bytes),
        runtime_digest=sha256_digest(runtime_bytes),
        source_digest=source_blob_digest,
    )
    readme = (
        f"# {spec.name} primitive\n\n"
        f"`{spec.function_name}({spec.input_name})` {spec.documentation.strip()}\n\n"
        "Reference semantics:\n"
        + "".join(f"- {item}\n" for item in spec.references)
        + "\n"
        "This is a complete, dependency-free, deterministic capsule: source, contract, "
        "examples, tests, runtime lock, license evidence, provenance, interface graph, "
        "and searchable capability labels are all present and independently validated.\n"
    ).encode("utf-8")

    file_rows = (
        (spec.source_path, "source", "text/x-python"),
        ("contract.json", "contract", "application/json"),
        ("descriptor.json", "descriptor", "application/json"),
        ("examples.json", "example", "application/json"),
        ("tests.json", "test", "application/json"),
        ("verifier.json", "verifier", "application/json"),
        ("dependencies.lock", "dependency_lock", "text/plain"),
        ("runtime.json", "runtime", "application/json"),
        ("graph.json", "graph_delta", "application/json"),
        ("README.md", "documentation", "text/markdown"),
        ("LICENSE_EVIDENCE.txt", "documentation", "text/plain"),
        ("license.json", "license", "application/json"),
        ("provenance.json", "provenance", "application/json"),
    )
    manifest = {
        "schema_version": "1.0.0",
        "namespace": spec.namespace,
        "name": spec.name,
        "contract_path": "contract.json",
        "ref_kind": "branch",
        "ref_name": "main",
        "message": f"Release the complete {spec.name} data primitive.",
        "policy_decision_id": spec.policy_decision_id,
        "assurance_level": "standard",
        "files": [
            {"path": path, "role": role, "media_type": media_type}
            for path, role, media_type in file_rows
        ],
    }
    return {
        "primitive.json": _json_bytes(manifest),
        spec.source_path: source,
        "contract.json": contract_bytes,
        "descriptor.json": descriptor_bytes,
        "examples.json": examples_bytes,
        "tests.json": tests_bytes,
        "verifier.json": _json_bytes(verifier),
        "dependencies.lock": dependency_lock,
        "runtime.json": runtime_bytes,
        "graph.json": _json_bytes(graph),
        "README.md": readme,
        "LICENSE_EVIDENCE.txt": _LICENSE_EVIDENCE,
        "license.json": _json_bytes(license_record),
        "provenance.json": _json_bytes(provenance),
    }


def render_primitive_directory(
    spec: PrimitiveAuthoringSpec,
    destination: str | Path,
) -> InspectedPrimitiveDirectory:
    """Write exactly one capsule and independently inspect the emitted directory."""

    root = Path(destination).resolve()
    files = build_primitive_files(spec)
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise PrimitiveAuthoringError("primitive destination must be a regular directory")
        actual = {
            item.relative_to(root).as_posix()
            for item in root.rglob("*")
            if item.is_file() or item.is_symlink()
        }
        unexpected = sorted(actual - set(files))
        if unexpected:
            raise PrimitiveAuthoringError(
                "primitive destination has undeclared content: " + ", ".join(unexpected)
            )
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise PrimitiveAuthoringError(f"refusing to replace symlink: {relative}")
        target.write_bytes(content)
    try:
        return inspect_primitive_directory(root)
    except ValueError as exc:
        raise PrimitiveAuthoringError(
            f"compiled primitive failed independent inspection: {exc}"
        ) from exc


def _interface_graph(
    spec: PrimitiveAuthoringSpec,
    *,
    contract: Mapping[str, Any],
    contract_digest: str,
    descriptor_digest: str,
    examples_digest: str,
    tests_digest: str,
    runtime_digest: str,
    source_digest: str,
) -> Mapping[str, Any]:
    implementation = f"implementation.{spec.function_name}"
    contract_node = f"contract.{spec.function_name}"
    input_port = f"port.input.{spec.input_name}"
    output_port = "port.output.result"
    examples_node = f"examples.{spec.function_name}"
    tests_node = f"tests.{spec.function_name}"
    runtime_node = "runtime.python" + spec.runtime_version.replace(".", "")
    input_transports = _transports(spec.input_schema)
    output_transports = _transports(spec.output_schema)
    return {
        "schema_version": "1.1.0",
        "interface_id": f"{spec.namespace}.{spec.name}.v1",
        "nodes": [
            {
                "id": implementation,
                "kind": "implementation",
                "path": spec.source_path,
                "symbol": spec.function_name,
            },
            {"id": contract_node, "kind": "contract", "path": "contract.json"},
            {
                "id": input_port,
                "kind": "input_port",
                "path": "contract.json",
                "json_pointer": "#/inputs/0",
            },
            {
                "id": output_port,
                "kind": "output_port",
                "path": "contract.json",
                "json_pointer": "#/output",
            },
            {
                "id": examples_node,
                "kind": "example_set",
                "path": "examples.json",
            },
            {"id": tests_node, "kind": "test_set", "path": "tests.json"},
            {"id": runtime_node, "kind": "runtime", "path": "runtime.json"},
        ],
        "edges": [
            _edge(
                "edge.implements_contract",
                implementation,
                "taedri.predicate.implements_contract",
                contract_node,
                "asserted",
                "exactly_one",
                ((spec.source_path, source_digest), ("contract.json", contract_digest)),
            ),
            _edge(
                f"edge.accepts_{spec.input_name}",
                implementation,
                "taedri.predicate.accepts_port",
                input_port,
                "asserted",
                "exactly_one",
                (("contract.json", contract_digest),),
            ),
            _edge(
                "edge.produces_result",
                implementation,
                "taedri.predicate.produces_port",
                output_port,
                "asserted",
                "exactly_one",
                (("contract.json", contract_digest),),
            ),
            _edge(
                "edge.demonstrated_by_examples",
                examples_node,
                "taedri.predicate.demonstrates",
                implementation,
                "observed",
                "one_or_more",
                (("examples.json", examples_digest),),
            ),
            _edge(
                "edge.verified_by_tests",
                tests_node,
                "taedri.predicate.verifies",
                implementation,
                "observed",
                "one_or_more",
                (("tests.json", tests_digest),),
            ),
            _edge(
                "edge.runs_on_python" + spec.runtime_version.replace(".", ""),
                implementation,
                "taedri.predicate.runs_on",
                runtime_node,
                "asserted",
                "exactly_one",
                (("runtime.json", runtime_digest),),
            ),
        ],
        "ports": [
            {
                "id": input_port,
                "owner": implementation,
                "direction": "input",
                "name": spec.input_name,
                "schema": dict(spec.input_schema),
                "schema_digest": canonical_digest(spec.input_schema),
                "schema_ref": "contract.json#/inputs/0/schema",
                "required": True,
                "cardinality": "one",
                "transports": input_transports,
            },
            {
                "id": output_port,
                "owner": implementation,
                "direction": "output",
                "name": "result",
                "schema": dict(spec.output_schema),
                "schema_digest": canonical_digest(spec.output_schema),
                "schema_ref": "contract.json#/output/schema",
                "required": True,
                "cardinality": "one",
                "transports": output_transports,
            },
        ],
        "compatibility": {
            "language": "python",
            "runtime_version": spec.runtime_version,
            "execution_model": "in_process_call",
            "deterministic": True,
            "purity": "pure",
            "network": "denied",
            "effects": [],
            "dimensions": {
                "taedri.compatibility.call_style": "sync",
                "taedri.compatibility.language": "python",
                "taedri.compatibility.runtime_major_minor": spec.runtime_version,
                "taedri.compatibility.value_transport": "python_native",
            },
            "required_dimensions": [
                "taedri.compatibility.call_style",
                "taedri.compatibility.language",
                "taedri.compatibility.runtime_major_minor",
                "taedri.compatibility.value_transport",
            ],
        },
        "groups": [
            {
                "id": spec.group_id,
                "kind": "capability",
                "labels": list(spec.group_labels),
                "member_nodes": [implementation],
                "evidence": [
                    {"path": "descriptor.json", "digest": descriptor_digest},
                    {"path": "contract.json", "digest": contract_digest},
                ],
            }
        ],
    }


def _edge(
    identifier: str,
    source: str,
    predicate: str,
    target: str,
    modality: str,
    quantifier: str,
    evidence: tuple[tuple[str, str], ...],
) -> Mapping[str, Any]:
    return {
        "id": identifier,
        "source": source,
        "predicate": predicate,
        "target": target,
        "modality": modality,
        "quantifier": quantifier,
        "confidence_ppm": 1_000_000,
        "evidence": [
            {"path": path, "digest": digest} for path, digest in evidence
        ],
    }


def _transports(schema: Mapping[str, Any]) -> list[str]:
    if schema.get("type") == "string":
        return ["json", "python_native", "text"]
    return ["json", "python_native"]


def _validate_spec(spec: PrimitiveAuthoringSpec) -> None:
    if not _REGISTRY_NAME.fullmatch(spec.namespace) or not _REGISTRY_NAME.fullmatch(
        spec.name
    ):
        raise PrimitiveAuthoringError("namespace and name must be normalized registry keys")
    if not _REGISTRY_NAME.fullmatch(spec.category):
        raise PrimitiveAuthoringError("category must be a normalized registry key")
    if not _SYMBOL.fullmatch(spec.function_name) or not _SYMBOL.fullmatch(
        spec.input_name
    ):
        raise PrimitiveAuthoringError("function and input names must be Python symbols")
    if not _PREDICATE_NAME.fullmatch(spec.group_id):
        raise PrimitiveAuthoringError("capability group ID must be namespaced")
    if len(spec.summary.strip()) < 20 or len(spec.documentation.strip()) < 20:
        raise PrimitiveAuthoringError("summary and documentation must be substantive")
    for label, values in (
        ("keywords", spec.keywords),
        ("use cases", spec.use_cases),
        ("limitations", spec.limitations),
        ("group labels", spec.group_labels),
        ("references", spec.references),
    ):
        if not values or any(not item.strip() for item in values):
            raise PrimitiveAuthoringError(f"{label} must contain non-empty strings")
    if not spec.input_schema or not spec.output_schema:
        raise PrimitiveAuthoringError("input and output schemas are required")
    if spec.implementation_producer_id == spec.oracle_producer_id:
        raise PrimitiveAuthoringError("implementation and oracle producers must differ")
    if not spec.source_uri.startswith("https://github.com/"):
        raise PrimitiveAuthoringError("source URI must identify the GitHub collaboration form")
    if not re.fullmatch(r"[0-9]+\.[0-9]+", spec.runtime_version):
        raise PrimitiveAuthoringError("runtime version must pin a Python major/minor")
    if not spec.source_code.endswith("\n"):
        raise PrimitiveAuthoringError("source code must end with one newline")
    lowered = spec.source_code.casefold()
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        raise PrimitiveAuthoringError("source contains a placeholder marker")
    try:
        module = ast.parse(spec.source_code, filename=spec.source_path)
    except SyntaxError as exc:
        raise PrimitiveAuthoringError("source code is not valid Python") from exc
    targets = [
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == spec.function_name
    ]
    if len(targets) != 1:
        raise PrimitiveAuthoringError("source requires exactly one declared entrypoint")
    if any(isinstance(node, (ast.Pass, ast.AsyncFunctionDef)) for node in ast.walk(module)):
        raise PrimitiveAuthoringError("source cannot contain pass or async placeholder behavior")
    if any(isinstance(node, ast.Constant) and node.value is Ellipsis for node in ast.walk(module)):
        raise PrimitiveAuthoringError("source cannot contain ellipsis placeholders")
    for node in ast.walk(module):
        if not isinstance(node, ast.Raise):
            continue
        raised = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
        if isinstance(raised, ast.Name) and raised.id == "NotImplementedError":
            raise PrimitiveAuthoringError("source cannot raise NotImplementedError")
    imports: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imports.update(item.name.split(".", 1)[0] for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
    undeclared_imports = sorted(imports - set(spec.allowed_imports))
    if undeclared_imports:
        raise PrimitiveAuthoringError(
            "source imports are not declared by the spec: " + ", ".join(undeclared_imports)
        )
    if len(spec.examples) < 3 or len(spec.tests) < 3:
        raise PrimitiveAuthoringError("at least three examples and three tests are required")
    example_kinds = {str(item.get("kind")) for item in spec.examples}
    if example_kinds != {"positive", "boundary", "negative"}:
        raise PrimitiveAuthoringError(
            "examples must contain positive, boundary, and negative cases"
        )
    for case in (*spec.examples, *spec.tests):
        try:
            json.dumps(case, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise PrimitiveAuthoringError("cases must be finite JSON values") from exc


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
