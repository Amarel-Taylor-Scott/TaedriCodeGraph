"""Exact primitive port matching and deterministic trusted-source pipeline execution.

Search and ranking nominate a bounded set of candidates.  This module does not compare
every primitive pair and does not infer adapters: it accepts an ordered shortlist,
requires exact schemas and authoritative compatibility dimensions, then emits a
content-addressed wire plan.  The local executor proves a narrow no-LLM composition
path for unary Python primitives; it is not a hostile-code sandbox.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..canonical import canonical_digest, canonical_json_bytes, sha256_digest
from ..contracts import RecordMixin
from ..identity import IdentityRecord
from ..primitive_capsules import CapsuleRole, decode_primitive_pack
from .digestion import DigestionPolicy, PrimitiveDigester
from .edges import PrimitiveInterface, PrimitivePort


class PrimitiveWiringError(ValueError):
    """Raised when exact deterministic wiring or execution cannot be proven."""


class WireVerdict(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class WireDimensionAssessment(RecordMixin):
    dimension: str
    verdict: WireVerdict
    producer_value: str | int | bool | None
    consumer_value: str | int | bool | None
    reason: str


@dataclass(frozen=True, slots=True)
class PrimitiveWireAssessment(RecordMixin):
    producer_interface_id: str
    consumer_interface_id: str
    producer_port_id: str
    consumer_port_id: str
    verdict: WireVerdict
    common_transports: tuple[str, ...]
    dimensions: tuple[WireDimensionAssessment, ...]


@dataclass(frozen=True, slots=True)
class PrimitiveWire(RecordMixin):
    producer_interface_id: str
    producer_port_id: str
    consumer_interface_id: str
    consumer_port_id: str
    schema_digest: str
    transport: str
    assessment: PrimitiveWireAssessment


@dataclass(frozen=True, slots=True)
class DeterministicPipelinePlan(RecordMixin):
    identity: IdentityRecord
    format_version: str
    interfaces: tuple[PrimitiveInterface, ...]
    wires: tuple[PrimitiveWire, ...]

    @classmethod
    def create(
        cls,
        interfaces: Sequence[PrimitiveInterface],
        wires: Sequence[PrimitiveWire],
    ) -> "DeterministicPipelinePlan":
        ordered_interfaces = tuple(interfaces)
        ordered_wires = tuple(wires)
        if not ordered_interfaces:
            raise PrimitiveWiringError("pipeline requires at least one primitive interface")
        if len(ordered_wires) != max(0, len(ordered_interfaces) - 1):
            raise PrimitiveWiringError("pipeline requires exactly one wire between adjacent steps")
        if any(
            wire.producer_interface_id != ordered_interfaces[index].interface_id
            or wire.consumer_interface_id != ordered_interfaces[index + 1].interface_id
            for index, wire in enumerate(ordered_wires)
        ):
            raise PrimitiveWiringError("pipeline wires must connect the ordered adjacent interfaces")
        key = {
            "format_version": "1.0.0",
            "interfaces": [
                {
                    "interface_id": item.interface_id,
                    "graph_digest": item.graph_digest,
                }
                for item in ordered_interfaces
            ],
            "wires": [wire.to_dict() for wire in ordered_wires],
        }
        return cls(
            IdentityRecord.create("deterministic_pipeline_plan", key),
            "1.0.0",
            ordered_interfaces,
            ordered_wires,
        )


@dataclass(frozen=True, slots=True)
class DeterministicPipelineReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    plan_id: str
    pack_digests: tuple[str, ...]
    input_digest: str
    output_digest: str
    stage_observation_digests: tuple[str, ...]
    executed_stage_count: int


@dataclass(frozen=True, slots=True)
class DeterministicPipelineResult(RecordMixin):
    output: Any
    receipt: DeterministicPipelineReceipt


class ExactPrimitiveWirePlanner:
    """Plan only exact, authoritative, adapter-free port connections."""

    def assess(
        self,
        producer: PrimitiveInterface,
        consumer: PrimitiveInterface,
        *,
        producer_port_id: str | None = None,
        consumer_port_id: str | None = None,
    ) -> PrimitiveWireAssessment:
        output = self._port(producer, "output", producer_port_id)
        input_port = self._port(consumer, "input", consumer_port_id)
        dimensions: list[WireDimensionAssessment] = []

        schema_match = output.schema_digest == input_port.schema_digest and dict(output.schema) == dict(input_port.schema)
        dimensions.append(
            WireDimensionAssessment(
                "taedri.wire.schema",
                WireVerdict.COMPATIBLE if schema_match else WireVerdict.INCOMPATIBLE,
                output.schema_digest,
                input_port.schema_digest,
                "canonical schemas match exactly" if schema_match else "canonical schemas differ; no implicit adapter is allowed",
            )
        )
        common_transports = tuple(sorted(set(output.transports) & set(input_port.transports)))
        dimensions.append(
            WireDimensionAssessment(
                "taedri.wire.transport",
                WireVerdict.COMPATIBLE if common_transports else WireVerdict.INCOMPATIBLE,
                ",".join(output.transports),
                ",".join(input_port.transports),
                "at least one declared transport is shared" if common_transports else "ports have no shared declared transport",
            )
        )
        deterministic = producer.deterministic and consumer.deterministic
        dimensions.append(
            WireDimensionAssessment(
                "taedri.wire.deterministic",
                WireVerdict.COMPATIBLE if deterministic else WireVerdict.UNKNOWN,
                producer.deterministic,
                consumer.deterministic,
                "both interfaces declare deterministic behavior" if deterministic else "determinism is not established for both interfaces",
            )
        )
        safe_execution = (
            producer.execution_model == consumer.execution_model == "in_process_call"
            and producer.network == consumer.network == "denied"
            and producer.purity in {"pure", "read_only"}
            and consumer.purity in {"pure", "read_only"}
        )
        dimensions.append(
            WireDimensionAssessment(
                "taedri.wire.execution_policy",
                WireVerdict.COMPATIBLE if safe_execution else WireVerdict.UNKNOWN,
                f"{producer.execution_model}:{producer.purity}:{producer.network}",
                f"{consumer.execution_model}:{consumer.purity}:{consumer.network}",
                "both interfaces satisfy the local deterministic execution policy" if safe_execution else "execution model, effects, purity, or network policy needs an explicit adapter/policy decision",
            )
        )

        required = tuple(
            sorted(set(producer.required_dimensions) | set(consumer.required_dimensions))
        )
        for key in required:
            provided = producer.compatibility_dimensions.get(key)
            needed = consumer.compatibility_dimensions.get(key)
            if provided is None or needed is None:
                verdict = WireVerdict.UNKNOWN
                reason = "a required compatibility dimension is missing"
            elif provided != needed:
                verdict = WireVerdict.INCOMPATIBLE
                reason = "authoritative compatibility values differ"
            else:
                verdict = WireVerdict.COMPATIBLE
                reason = "authoritative compatibility values match"
            dimensions.append(
                WireDimensionAssessment(key, verdict, provided, needed, reason)
            )
        verdicts = {item.verdict for item in dimensions}
        if WireVerdict.INCOMPATIBLE in verdicts:
            verdict = WireVerdict.INCOMPATIBLE
        elif dimensions and verdicts == {WireVerdict.COMPATIBLE}:
            verdict = WireVerdict.COMPATIBLE
        else:
            verdict = WireVerdict.UNKNOWN
        return PrimitiveWireAssessment(
            producer.interface_id,
            consumer.interface_id,
            output.id,
            input_port.id,
            verdict,
            common_transports,
            tuple(dimensions),
        )

    def connect(
        self,
        producer: PrimitiveInterface,
        consumer: PrimitiveInterface,
        *,
        producer_port_id: str | None = None,
        consumer_port_id: str | None = None,
    ) -> PrimitiveWire:
        assessment = self.assess(
            producer,
            consumer,
            producer_port_id=producer_port_id,
            consumer_port_id=consumer_port_id,
        )
        if assessment.verdict is not WireVerdict.COMPATIBLE:
            raise PrimitiveWiringError(
                "primitive ports are not proven compatible: " + assessment.verdict.value
            )
        output = self._port(producer, "output", assessment.producer_port_id)
        return PrimitiveWire(
            producer.interface_id,
            assessment.producer_port_id,
            consumer.interface_id,
            assessment.consumer_port_id,
            output.schema_digest,
            (
                "python_native"
                if "python_native" in assessment.common_transports
                else assessment.common_transports[0]
            ),
            assessment,
        )

    def pipeline(
        self, interfaces: Sequence[PrimitiveInterface]
    ) -> DeterministicPipelinePlan:
        ordered = tuple(interfaces)
        wires = tuple(
            self.connect(ordered[index], ordered[index + 1])
            for index in range(len(ordered) - 1)
        )
        return DeterministicPipelinePlan.create(ordered, wires)

    @staticmethod
    def _port(
        interface: PrimitiveInterface, direction: str, identifier: str | None
    ) -> PrimitivePort:
        matches = [
            item
            for item in interface.ports
            if item.direction == direction and (identifier is None or item.id == identifier)
        ]
        if len(matches) != 1:
            raise PrimitiveWiringError(
                f"{interface.interface_id} requires one selected {direction} port"
            )
        return matches[0]


_PIPELINE_RUNNER = r'''
import asyncio
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import pathlib
import sys

request = json.loads(sys.stdin.read())

def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.posix_spawn"}:
        raise PermissionError("primitive pipeline policy denied " + event)

def digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()

sys.addaudithook(audit)
value = request["input"]
observations = []
captured = io.StringIO()
with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
    for index, stage in enumerate(request["stages"]):
        root = pathlib.Path(stage["root"]).resolve()
        source = (root / stage["entrypoint_path"]).resolve()
        if root not in source.parents:
            raise AssertionError("pipeline entrypoint escaped materialized root")
        spec = importlib.util.spec_from_file_location("taedri_pipeline_stage_%d" % index, source)
        if spec is None or spec.loader is None:
            raise AssertionError("pipeline stage could not be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        target = getattr(module, stage["entrypoint_symbol"])
        input_digest = digest(value)
        value = target(value)
        if inspect.isawaitable(value):
            value = asyncio.run(value)
        observations.append({
            "interface_id": stage["interface_id"],
            "input_digest": input_digest,
            "output_digest": digest(value),
        })
result = {
    "status": "passed",
    "output": value,
    "observations": observations,
    "captured_output_digest": "sha256:" + hashlib.sha256(captured.getvalue().encode()).hexdigest(),
}
print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
'''


class LocalDeterministicPythonPipelineExecutor:
    """Execute an exact unary Python pipeline using verified packs and no model call."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        if not 0.1 <= timeout_seconds <= 120:
            raise PrimitiveWiringError("pipeline timeout must be 0.1..120 seconds")
        self.timeout_seconds = timeout_seconds

    def execute(
        self,
        plan: DeterministicPipelinePlan,
        encoded_packs: Sequence[bytes],
        input_value: Any,
    ) -> DeterministicPipelineResult:
        packs = tuple(encoded_packs)
        if len(packs) != len(plan.interfaces):
            raise PrimitiveWiringError("pipeline requires one full pack per interface")
        canonical_json_bytes(input_value)
        pack_digests: list[str] = []
        with tempfile.TemporaryDirectory(prefix="taedri-deterministic-pipeline-") as temporary:
            base = Path(temporary)
            stages: list[dict[str, str]] = []
            for index, (interface, encoded) in enumerate(zip(plan.interfaces, packs, strict=True)):
                manifest, _ = decode_primitive_pack(encoded)
                roles = {str(item["role"]) for item in manifest["entries"]}
                if roles != {item.value for item in CapsuleRole}:
                    raise PrimitiveWiringError("deterministic execution requires a complete pack")
                root = base / f"stage-{index}"
                receipt = PrimitiveDigester(
                    DigestionPolicy(allowed_roles=tuple(CapsuleRole))
                ).materialize(encoded, root)
                graph_entries = [
                    item for item in manifest["entries"] if item["role"] == CapsuleRole.GRAPH_DELTA.value
                ]
                if len(graph_entries) != 1:
                    raise PrimitiveWiringError("pack must contain one interface graph")
                graph_path = root / str(graph_entries[0]["path"])
                graph = json.loads(graph_path.read_text("utf-8"))
                if not isinstance(graph, Mapping) or interface.graph_digest != canonical_digest(graph):
                    raise PrimitiveWiringError("pack interface graph does not match the wire plan")
                _verify_interface_graph_binding(graph, interface)
                pack_digests.append(receipt.pack_digest)
                stages.append(
                    {
                        "interface_id": interface.interface_id,
                        "root": root.as_posix(),
                        "entrypoint_path": interface.entrypoint_path,
                        "entrypoint_symbol": interface.entrypoint,
                    }
                )
            request = {"input": input_value, "stages": stages}
            completed = subprocess.run(
                (sys.executable, "-I", "-c", _PIPELINE_RUNNER),
                input=canonical_json_bytes(request),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=base,
                env={"PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"},
                timeout=self.timeout_seconds,
                check=False,
            )
        if completed.returncode != 0:
            raise PrimitiveWiringError(
                "deterministic pipeline execution failed: "
                + completed.stderr.decode("utf-8", "replace")[-2000:]
            )
        try:
            execution = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PrimitiveWiringError("pipeline executor returned invalid JSON") from exc
        if not isinstance(execution, Mapping) or execution.get("status") != "passed":
            raise PrimitiveWiringError("pipeline executor did not return passed status")
        observations = execution.get("observations")
        if not isinstance(observations, list) or len(observations) != len(plan.interfaces):
            raise PrimitiveWiringError("pipeline executor observations are incomplete")
        input_digest = sha256_digest(canonical_json_bytes(input_value))
        output = execution.get("output")
        output_digest = sha256_digest(canonical_json_bytes(output))
        observation_digests = tuple(
            sha256_digest(canonical_json_bytes(item)) for item in observations
        )
        key = {
            "format_version": "1.0.0",
            "plan_id": plan.identity.id,
            "pack_digests": pack_digests,
            "input_digest": input_digest,
            "output_digest": output_digest,
            "stage_observation_digests": observation_digests,
            "executed_stage_count": len(observations),
        }
        receipt = DeterministicPipelineReceipt(
            IdentityRecord.create("deterministic_pipeline_receipt", key),
            "1.0.0",
            plan.identity.id,
            tuple(pack_digests),
            input_digest,
            output_digest,
            observation_digests,
            len(observations),
        )
        return DeterministicPipelineResult(output, receipt)


def _verify_interface_graph_binding(
    graph: Mapping[str, Any], interface: PrimitiveInterface
) -> None:
    """Ensure execution fields are the exact fields committed by the graph digest."""

    if graph.get("interface_id") != interface.interface_id:
        raise PrimitiveWiringError("pack interface identifier does not match the wire plan")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise PrimitiveWiringError("pack interface nodes are invalid")
    implementations = [
        item
        for item in nodes
        if isinstance(item, Mapping) and item.get("kind") == "implementation"
    ]
    if len(implementations) != 1 or (
        implementations[0].get("id") != interface.implementation_node_id
        or implementations[0].get("path") != interface.entrypoint_path
        or implementations[0].get("symbol") != interface.entrypoint
    ):
        raise PrimitiveWiringError("pack entrypoint does not match the wire plan")
    ports = graph.get("ports")
    if not isinstance(ports, list) or canonical_digest(ports) != canonical_digest(
        [item.to_dict() for item in interface.ports]
    ):
        raise PrimitiveWiringError("pack ports do not match the wire plan")
    compatibility = graph.get("compatibility")
    expected = {
        "language": interface.language,
        "runtime_version": interface.runtime_version,
        "execution_model": interface.execution_model,
        "deterministic": interface.deterministic,
        "purity": interface.purity,
        "network": interface.network,
        "effects": list(interface.effects),
        "dimensions": dict(interface.compatibility_dimensions),
        "required_dimensions": list(interface.required_dimensions),
    }
    if not isinstance(compatibility, Mapping) or any(
        compatibility.get(key) != value for key, value in expected.items()
    ):
        raise PrimitiveWiringError("pack compatibility dimensions do not match the wire plan")
    edges = graph.get("edges")
    if not isinstance(edges, list) or len(edges) != interface.edge_count:
        raise PrimitiveWiringError("pack edge count does not match the wire plan")
