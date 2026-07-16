"""Release-grade primitive interface graphs and evidence-bound edges.

Retrieval edges may be probabilistic.  A released primitive interface is stricter:
every node resolves to a capsule path, every edge names direction/semantics/evidence,
and every contract input/output is represented by a typed port.  These records are the
deterministic hand-off between retrieval and compatibility planning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from ..canonical import canonical_digest
from ..contracts import RecordMixin


class PrimitiveGraphError(ValueError):
    """Raised when an interface graph cannot support release or deterministic wiring."""


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_PREDICATE = re.compile(r"^[a-z][a-z0-9_.-]*\.[a-z][a-z0-9_.-]+$")
_NODE_KINDS = {
    "implementation",
    "contract",
    "input_port",
    "output_port",
    "example_set",
    "test_set",
    "runtime",
    "dependency",
    "error",
    "effect",
    "resource",
    "primitive",
}
_MODALITIES = {"asserted", "observed", "inferred"}
_QUANTIFIERS = {"exactly_one", "one_or_more", "zero_or_more"}
_DIRECTIONS = {"input", "output"}
_CARDINALITIES = {"one", "optional", "many"}
_TRANSPORTS = {"python_native", "json", "bytes", "text"}
_EXECUTION_MODELS = {"in_process_call", "subprocess_json", "remote_call"}
_PURITY = {"pure", "read_only", "effectful", "unknown"}
_REQUIRED_PREDICATES = {
    "taedri.predicate.implements_contract",
    "taedri.predicate.demonstrates",
    "taedri.predicate.verifies",
}


@dataclass(frozen=True, slots=True)
class PrimitivePort(RecordMixin):
    id: str
    owner: str
    direction: str
    name: str
    schema: Mapping[str, Any]
    schema_digest: str
    schema_ref: str
    required: bool
    cardinality: str
    transports: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrimitiveCapabilityGroup(RecordMixin):
    id: str
    kind: str
    labels: tuple[str, ...]
    member_nodes: tuple[str, ...]
    evidence_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrimitiveInterface(RecordMixin):
    interface_id: str
    graph_digest: str
    implementation_node_id: str
    entrypoint_path: str
    entrypoint: str
    language: str
    runtime_version: str
    execution_model: str
    deterministic: bool
    purity: str
    network: str
    effects: tuple[str, ...]
    compatibility_dimensions: Mapping[str, str | int | bool]
    required_dimensions: tuple[str, ...]
    ports: tuple[PrimitivePort, ...]
    groups: tuple[PrimitiveCapabilityGroup, ...]
    edge_count: int
    predicates: tuple[str, ...]
    search_terms: tuple[str, ...]

    @property
    def input_ports(self) -> tuple[PrimitivePort, ...]:
        return tuple(item for item in self.ports if item.direction == "input")

    @property
    def output_ports(self) -> tuple[PrimitivePort, ...]:
        return tuple(item for item in self.ports if item.direction == "output")


def validate_primitive_graph(
    graph: Mapping[str, Any],
    *,
    capsule_paths: Mapping[str, tuple[bytes, str]],
    contract: Mapping[str, Any],
    contract_path: str,
    language: str,
    runtime_version: str,
    entrypoint_path: str,
    entrypoint: str,
) -> PrimitiveInterface:
    """Validate one complete interface graph against capsule bytes and contract ports."""

    if graph.get("schema_version") != "1.1.0":
        raise PrimitiveGraphError("primitive graph schema_version must be 1.1.0")
    interface_id = _required_identifier(graph, "interface_id")
    nodes_value = graph.get("nodes")
    if not isinstance(nodes_value, list) or not nodes_value:
        raise PrimitiveGraphError("primitive graph requires nodes")
    nodes: dict[str, Mapping[str, Any]] = {}
    implementation_nodes: list[str] = []
    for index, value in enumerate(nodes_value):
        if not isinstance(value, Mapping):
            raise PrimitiveGraphError(f"nodes[{index}] must be an object")
        node_id = _required_identifier(value, "id")
        if node_id in nodes:
            raise PrimitiveGraphError(f"duplicate graph node: {node_id}")
        kind = _required_string(value, "kind")
        if kind not in _NODE_KINDS:
            raise PrimitiveGraphError(f"unsupported graph node kind: {kind}")
        path = _required_string(value, "path")
        if path not in capsule_paths:
            raise PrimitiveGraphError(f"graph node path is not in the capsule: {path}")
        if kind == "implementation":
            if path != entrypoint_path or value.get("symbol") != entrypoint:
                raise PrimitiveGraphError(
                    "implementation node must identify the runtime entrypoint"
                )
            implementation_nodes.append(node_id)
        nodes[node_id] = value
    if len(implementation_nodes) != 1:
        raise PrimitiveGraphError("primitive graph requires exactly one implementation node")

    edges_value = graph.get("edges")
    if not isinstance(edges_value, list) or not edges_value:
        raise PrimitiveGraphError("primitive graph requires evidence-bound edges")
    edge_ids: set[str] = set()
    predicates: set[str] = set()
    for index, value in enumerate(edges_value):
        if not isinstance(value, Mapping):
            raise PrimitiveGraphError(f"edges[{index}] must be an object")
        edge_id = _required_identifier(value, "id")
        if edge_id in edge_ids:
            raise PrimitiveGraphError(f"duplicate graph edge: {edge_id}")
        edge_ids.add(edge_id)
        source = _required_identifier(value, "source")
        target = _required_identifier(value, "target")
        if source not in nodes or target not in nodes:
            raise PrimitiveGraphError("graph edge endpoints must resolve to declared nodes")
        predicate = _required_string(value, "predicate")
        if not _PREDICATE.fullmatch(predicate):
            raise PrimitiveGraphError(f"graph predicate must be namespaced: {predicate}")
        predicates.add(predicate)
        modality = _required_string(value, "modality")
        quantifier = _required_string(value, "quantifier")
        if modality not in _MODALITIES or quantifier not in _QUANTIFIERS:
            raise PrimitiveGraphError("graph edge modality or quantifier is invalid")
        confidence = value.get("confidence_ppm")
        if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 1_000_000:
            raise PrimitiveGraphError("graph edge confidence_ppm must be 0..1000000")
        if modality == "asserted" and confidence != 1_000_000:
            raise PrimitiveGraphError("asserted graph edges require exact confidence")
        _validate_evidence(value.get("evidence"), capsule_paths, f"edges[{index}]")
    missing_predicates = sorted(_REQUIRED_PREDICATES - predicates)
    if missing_predicates:
        raise PrimitiveGraphError(
            "primitive graph is missing required relations: " + ", ".join(missing_predicates)
        )

    ports_value = graph.get("ports")
    if not isinstance(ports_value, list) or not ports_value:
        raise PrimitiveGraphError("primitive graph requires typed input and output ports")
    ports: list[PrimitivePort] = []
    port_ids: set[str] = set()
    for index, value in enumerate(ports_value):
        if not isinstance(value, Mapping):
            raise PrimitiveGraphError(f"ports[{index}] must be an object")
        port_id = _required_identifier(value, "id")
        if port_id in port_ids:
            raise PrimitiveGraphError(f"duplicate primitive port: {port_id}")
        port_ids.add(port_id)
        owner = _required_identifier(value, "owner")
        if owner != implementation_nodes[0]:
            raise PrimitiveGraphError("v1 ports must be owned by the implementation node")
        direction = _required_string(value, "direction")
        cardinality = _required_string(value, "cardinality")
        if direction not in _DIRECTIONS or cardinality not in _CARDINALITIES:
            raise PrimitiveGraphError("port direction or cardinality is invalid")
        schema = value.get("schema")
        if not isinstance(schema, Mapping) or not schema:
            raise PrimitiveGraphError("primitive port requires an explicit schema")
        schema_digest = _required_string(value, "schema_digest")
        if canonical_digest(schema) != schema_digest:
            raise PrimitiveGraphError("primitive port schema digest does not validate")
        transports_raw = value.get("transports")
        if not isinstance(transports_raw, list) or not transports_raw:
            raise PrimitiveGraphError("primitive port requires at least one transport")
        transports = tuple(sorted(set(str(item) for item in transports_raw)))
        if len(transports) != len(transports_raw) or any(item not in _TRANSPORTS for item in transports):
            raise PrimitiveGraphError("primitive port transports are invalid or duplicated")
        required = value.get("required")
        if not isinstance(required, bool):
            raise PrimitiveGraphError("primitive port required must be Boolean")
        ports.append(
            PrimitivePort(
                port_id,
                owner,
                direction,
                _required_string(value, "name"),
                dict(schema),
                schema_digest,
                _required_string(value, "schema_ref"),
                required,
                cardinality,
                transports,
            )
        )
    _validate_contract_ports(contract, contract_path, tuple(ports))

    compatibility = graph.get("compatibility")
    if not isinstance(compatibility, Mapping):
        raise PrimitiveGraphError("primitive graph requires compatibility dimensions")
    if compatibility.get("language") != language or compatibility.get("runtime_version") != runtime_version:
        raise PrimitiveGraphError("graph compatibility runtime disagrees with runtime record")
    execution_model = _required_string(compatibility, "execution_model")
    purity = _required_string(compatibility, "purity")
    if execution_model not in _EXECUTION_MODELS or purity not in _PURITY:
        raise PrimitiveGraphError("execution model or purity classification is invalid")
    deterministic = compatibility.get("deterministic")
    if not isinstance(deterministic, bool):
        raise PrimitiveGraphError("compatibility deterministic must be Boolean")
    network = _required_string(compatibility, "network")
    if network != "denied":
        raise PrimitiveGraphError("v1 deterministic primitive wiring requires denied network")
    effects_raw = compatibility.get("effects")
    if not isinstance(effects_raw, list) or not all(isinstance(item, str) and item for item in effects_raw):
        raise PrimitiveGraphError("compatibility effects must be an explicit string list")
    contract_effects = contract.get("effects")
    if not isinstance(contract_effects, list) or effects_raw != contract_effects:
        raise PrimitiveGraphError("compatibility effects must exactly match the contract")
    dimensions_raw = compatibility.get("dimensions")
    required_raw = compatibility.get("required_dimensions")
    if not isinstance(dimensions_raw, Mapping) or not dimensions_raw:
        raise PrimitiveGraphError("compatibility dimensions cannot be empty")
    dimensions: dict[str, str | int | bool] = {}
    for key, value in dimensions_raw.items():
        if not isinstance(key, str) or not _PREDICATE.fullmatch(key):
            raise PrimitiveGraphError("compatibility dimension keys must be namespaced")
        if isinstance(value, (str, int, bool)) and not (isinstance(value, str) and not value):
            dimensions[key] = value
        else:
            raise PrimitiveGraphError("compatibility dimension values must be scalar")
    if not isinstance(required_raw, list) or not required_raw:
        raise PrimitiveGraphError("required compatibility dimensions cannot be empty")
    required_dimensions = tuple(str(item) for item in required_raw)
    if len(set(required_dimensions)) != len(required_dimensions) or any(item not in dimensions for item in required_dimensions):
        raise PrimitiveGraphError("required dimensions must be unique declared dimensions")

    groups_value = graph.get("groups")
    if not isinstance(groups_value, list) or not groups_value:
        raise PrimitiveGraphError("primitive graph requires at least one capability group")
    groups: list[PrimitiveCapabilityGroup] = []
    group_ids: set[str] = set()
    for index, value in enumerate(groups_value):
        if not isinstance(value, Mapping):
            raise PrimitiveGraphError(f"groups[{index}] must be an object")
        group_id = _required_identifier(value, "id")
        if group_id in group_ids:
            raise PrimitiveGraphError(f"duplicate capability group: {group_id}")
        group_ids.add(group_id)
        labels = _string_list(value.get("labels"), "group labels")
        members = _string_list(value.get("member_nodes"), "group member_nodes")
        if implementation_nodes[0] not in members or any(item not in nodes for item in members):
            raise PrimitiveGraphError("capability group members must include the implementation")
        evidence_paths = _validate_evidence(
            value.get("evidence"), capsule_paths, f"groups[{index}]"
        )
        groups.append(
            PrimitiveCapabilityGroup(
                group_id,
                _required_string(value, "kind"),
                labels,
                members,
                evidence_paths,
            )
        )

    search_terms = tuple(
        sorted(
            set(predicates)
            | {item.id for item in groups}
            | {label for item in groups for label in item.labels}
            | {item.name for item in ports}
        )
    )
    return PrimitiveInterface(
        interface_id,
        canonical_digest(graph),
        implementation_nodes[0],
        entrypoint_path,
        entrypoint,
        language,
        runtime_version,
        execution_model,
        deterministic,
        purity,
        network,
        tuple(effects_raw),
        dimensions,
        required_dimensions,
        tuple(ports),
        tuple(groups),
        len(edges_value),
        tuple(sorted(predicates)),
        search_terms,
    )


def _validate_contract_ports(
    contract: Mapping[str, Any],
    contract_path: str,
    ports: tuple[PrimitivePort, ...],
) -> None:
    inputs = contract.get("inputs")
    output = contract.get("output")
    if not isinstance(inputs, list) or not isinstance(output, Mapping):
        raise PrimitiveGraphError("contract inputs/output are invalid")
    input_ports = {item.name: item for item in ports if item.direction == "input"}
    output_ports = [item for item in ports if item.direction == "output"]
    if len(input_ports) != len(inputs) or len(output_ports) != 1:
        raise PrimitiveGraphError("every contract input and the output require one port")
    for index, item in enumerate(inputs):
        if not isinstance(item, Mapping):
            raise PrimitiveGraphError("contract input must be an object")
        name = item.get("name")
        port = input_ports.get(str(name))
        if port is None or canonical_digest(item.get("schema")) != port.schema_digest:
            raise PrimitiveGraphError("input port schema does not match its contract input")
        if port.schema_ref != f"{contract_path}#/inputs/{index}/schema":
            raise PrimitiveGraphError("input port schema_ref must resolve the contract location")
    output_schema = output.get("schema")
    if canonical_digest(output_schema) != output_ports[0].schema_digest:
        raise PrimitiveGraphError("output port schema does not match the contract output")
    if output_ports[0].schema_ref != f"{contract_path}#/output/schema":
        raise PrimitiveGraphError("output port schema_ref must resolve the contract location")


def _validate_evidence(
    value: object,
    capsule_paths: Mapping[str, tuple[bytes, str]],
    context: str,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise PrimitiveGraphError(f"{context} requires evidence")
    paths: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise PrimitiveGraphError(f"{context} evidence must be objects")
        path = _required_string(item, "path")
        digest = _required_string(item, "digest")
        if path not in capsule_paths or capsule_paths[path][1] != digest:
            raise PrimitiveGraphError(f"{context} evidence digest does not match {path}")
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise PrimitiveGraphError(f"{context} evidence paths must be unique")
    return tuple(paths)


def _required_identifier(value: Mapping[str, Any], field: str) -> str:
    result = _required_string(value, field)
    if not _IDENTIFIER.fullmatch(result):
        raise PrimitiveGraphError(f"{field} is not a normalized graph identifier")
    return result


def _required_string(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise PrimitiveGraphError(f"{field} must be a non-empty string")
    return result.strip()


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise PrimitiveGraphError(f"{field} must be a non-empty string list")
    result = tuple(value)
    if len(set(result)) != len(result):
        raise PrimitiveGraphError(f"{field} cannot contain duplicates")
    return result
