"""Bounded primitive route discovery and exact verified-recipe reuse.

Retrieval nominates a small set of released primitives for each requested operation.
This module intersects those nominations with exact capability groups and input-schema
blocks, applies the authoritative wire checker, and returns only executable plans.
It never interprets lexical or vector similarity as compatibility and never scans an
unbounded all-pairs primitive graph.

The current executor supports linear unary Python routes.  Route steps are therefore
explicit and ordered; adapters are ordinary requested primitives.  This is a narrow,
working base for later hypergraph planning where operations can consume or produce
multiple values.
"""

from __future__ import annotations

import heapq
import re
from dataclasses import dataclass
from datetime import datetime
from itertools import count
from typing import Any, Mapping, Sequence

from ..canonical import canonical_digest
from ..contracts import RecordMixin
from ..identity import IdentityRecord
from .edges import PrimitiveInterface
from .wiring import (
    DeterministicPipelinePlan,
    DeterministicPipelineReceipt,
    ExactPrimitiveWirePlanner,
    WireVerdict,
)


class PrimitiveRouteError(ValueError):
    """Raised when a route request, catalog, or recipe proof is invalid."""


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_UCEG_ID = re.compile(r"^uceg:v1:[a-z][a-z0-9_.-]*:[a-z2-7]+$")
_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_FORMAT_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class PrimitiveRouteEntry(RecordMixin):
    """One released primitive and the exact interface used for route planning."""

    primitive_id: str
    release_id: str
    namespace: str
    name: str
    pack_digest: str
    interface: PrimitiveInterface

    def __post_init__(self) -> None:
        for field, value in (
            ("primitive_id", self.primitive_id),
            ("release_id", self.release_id),
        ):
            if not isinstance(value, str) or not _UCEG_ID.fullmatch(value):
                raise PrimitiveRouteError(f"route entry {field} is malformed")
        for field, value in (("namespace", self.namespace), ("name", self.name)):
            if not isinstance(value, str) or not _NAME.fullmatch(value):
                raise PrimitiveRouteError(f"route entry {field} is malformed")
        if not isinstance(self.pack_digest, str) or not _DIGEST.fullmatch(
            self.pack_digest
        ):
            raise PrimitiveRouteError("route entry pack digest must be SHA-256")
        if not isinstance(self.interface, PrimitiveInterface):
            raise PrimitiveRouteError("route entry requires a primitive interface")
        if len(self.interface.input_ports) != 1 or len(self.interface.output_ports) != 1:
            raise PrimitiveRouteError("v1 route entries require one input and one output")

    @property
    def capability_group_ids(self) -> tuple[str, ...]:
        return tuple(group.id for group in self.interface.groups)


class PrimitiveRouteCatalog:
    """Immutable planning view with schema and capability blocking indexes."""

    def __init__(self, entries: Sequence[PrimitiveRouteEntry]) -> None:
        ordered = tuple(
            sorted(entries, key=lambda item: (item.namespace, item.name, item.primitive_id))
        )
        if not ordered:
            raise PrimitiveRouteError("route catalog cannot be empty")
        primitive_ids = [item.primitive_id for item in ordered]
        release_ids = [item.release_id for item in ordered]
        interface_ids = [item.interface.interface_id for item in ordered]
        handles = [(item.namespace, item.name) for item in ordered]
        for field, values in (
            ("primitive ID", primitive_ids),
            ("release ID", release_ids),
            ("interface ID", interface_ids),
            ("namespace/name handle", handles),
        ):
            if len(values) != len(set(values)):
                raise PrimitiveRouteError(f"route catalog contains a duplicate {field}")
        self.entries = ordered
        self.by_primitive_id = {item.primitive_id: item for item in ordered}
        group_index: dict[str, list[PrimitiveRouteEntry]] = {}
        input_schema_index: dict[str, list[PrimitiveRouteEntry]] = {}
        for item in ordered:
            for group_id in item.capability_group_ids:
                group_index.setdefault(group_id, []).append(item)
            schema_digest = item.interface.input_ports[0].schema_digest
            input_schema_index.setdefault(schema_digest, []).append(item)
        self.by_group = {
            key: tuple(sorted(value, key=lambda item: item.primitive_id))
            for key, value in group_index.items()
        }
        self.by_input_schema = {
            key: tuple(sorted(value, key=lambda item: item.primitive_id))
            for key, value in input_schema_index.items()
        }
        self.digest = canonical_digest(
            {
                "format_version": _FORMAT_VERSION,
                "entries": [
                    {
                        "primitive_id": item.primitive_id,
                        "release_id": item.release_id,
                        "pack_digest": item.pack_digest,
                        "interface_id": item.interface.interface_id,
                        "graph_digest": item.interface.graph_digest,
                        "input_schema_digest": item.interface.input_ports[0].schema_digest,
                        "output_schema_digest": item.interface.output_ports[0].schema_digest,
                        "capability_group_ids": item.capability_group_ids,
                    }
                    for item in ordered
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class PrimitiveRouteStep(RecordMixin):
    """One ordered capability requirement plus a bounded retrieval shortlist."""

    capability_group_id: str
    nominated_primitive_ids: tuple[str, ...] = ()
    retrieval_query_digest: str | None = None
    allow_group_fallback: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability_group_id, str)
            or not _NAME.fullmatch(self.capability_group_id)
        ):
            raise PrimitiveRouteError("route step capability group is malformed")
        if not isinstance(self.nominated_primitive_ids, tuple) or any(
            not isinstance(item, str) or not _UCEG_ID.fullmatch(item)
            for item in self.nominated_primitive_ids
        ):
            raise PrimitiveRouteError("route nominations must be primitive IDs")
        if len(self.nominated_primitive_ids) != len(set(self.nominated_primitive_ids)):
            raise PrimitiveRouteError("route nominations cannot contain duplicates")
        if self.retrieval_query_digest is not None and not _DIGEST.fullmatch(
            self.retrieval_query_digest
        ):
            raise PrimitiveRouteError("route retrieval query digest must be SHA-256")
        if not isinstance(self.allow_group_fallback, bool):
            raise PrimitiveRouteError("route group fallback must be Boolean")


@dataclass(frozen=True, slots=True)
class PrimitiveRoutePolicy(RecordMixin):
    """Hard execution constraints; no field is a soft ranking preference."""

    language: str
    runtime_version: str
    execution_model: str = "in_process_call"
    deterministic_required: bool = True
    allowed_purity: tuple[str, ...] = ("pure", "read_only")
    network: str = "denied"
    effects_allowed: bool = False

    def __post_init__(self) -> None:
        for field, value in (
            ("language", self.language),
            ("runtime_version", self.runtime_version),
            ("execution_model", self.execution_model),
            ("network", self.network),
        ):
            if not isinstance(value, str) or not value:
                raise PrimitiveRouteError(f"route policy {field} is required")
        if not isinstance(self.deterministic_required, bool) or not isinstance(
            self.effects_allowed, bool
        ):
            raise PrimitiveRouteError("route policy flags must be Boolean")
        if not self.allowed_purity or len(self.allowed_purity) != len(
            set(self.allowed_purity)
        ):
            raise PrimitiveRouteError("route policy purity values must be unique")

    def permits(self, interface: PrimitiveInterface) -> bool:
        return (
            interface.language == self.language
            and interface.runtime_version == self.runtime_version
            and interface.execution_model == self.execution_model
            and (interface.deterministic or not self.deterministic_required)
            and interface.purity in self.allowed_purity
            and interface.network == self.network
            and (self.effects_allowed or not interface.effects)
        )


@dataclass(frozen=True, slots=True)
class PrimitiveRouteRequest(RecordMixin):
    """Structured, body-free composition request produced before route search."""

    identity: IdentityRecord
    format_version: str
    contract_digest: str
    input_schema: Mapping[str, Any]
    input_schema_digest: str
    output_schema: Mapping[str, Any]
    output_schema_digest: str
    steps: tuple[PrimitiveRouteStep, ...]
    policy: PrimitiveRoutePolicy
    per_step_candidate_limit: int
    max_candidate_expansions: int
    max_routes: int

    @classmethod
    def create(
        cls,
        *,
        input_schema: Mapping[str, Any],
        output_schema: Mapping[str, Any],
        steps: Sequence[PrimitiveRouteStep],
        policy: PrimitiveRoutePolicy,
        per_step_candidate_limit: int = 16,
        max_candidate_expansions: int = 256,
        max_routes: int = 4,
    ) -> "PrimitiveRouteRequest":
        input_value = dict(input_schema)
        output_value = dict(output_schema)
        if not input_value or not output_value:
            raise PrimitiveRouteError("route input and output schemas are required")
        ordered_steps = tuple(steps)
        if not ordered_steps:
            raise PrimitiveRouteError("route requires at least one ordered step")
        for field, value, minimum, maximum in (
            ("per_step_candidate_limit", per_step_candidate_limit, 1, 1_000),
            ("max_candidate_expansions", max_candidate_expansions, 1, 100_000),
            ("max_routes", max_routes, 1, 32),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise PrimitiveRouteError(f"route {field} must be an integer")
            if not minimum <= value <= maximum:
                raise PrimitiveRouteError(
                    f"route {field} must be {minimum}..{maximum}"
                )
        input_digest = canonical_digest(input_value)
        output_digest = canonical_digest(output_value)
        contract_key = {
            "format_version": _FORMAT_VERSION,
            "input_schema": input_value,
            "output_schema": output_value,
            "ordered_capability_groups": [
                item.capability_group_id for item in ordered_steps
            ],
            "policy": policy.to_dict(),
        }
        contract_digest = canonical_digest(contract_key)
        request_key = {
            **contract_key,
            "steps": [item.to_dict() for item in ordered_steps],
            "per_step_candidate_limit": per_step_candidate_limit,
            "max_candidate_expansions": max_candidate_expansions,
            "max_routes": max_routes,
        }
        return cls(
            IdentityRecord.create("primitive_route_request", request_key),
            _FORMAT_VERSION,
            contract_digest,
            input_value,
            input_digest,
            output_value,
            output_digest,
            ordered_steps,
            policy,
            per_step_candidate_limit,
            max_candidate_expansions,
            max_routes,
        )


@dataclass(frozen=True, slots=True)
class PrimitiveRoute(RecordMixin):
    """One valid route whose plan and exact artifact handles are content-bound."""

    identity: IdentityRecord
    format_version: str
    contract_digest: str
    catalog_digest: str
    plan: DeterministicPipelinePlan
    primitive_ids: tuple[str, ...]
    release_ids: tuple[str, ...]
    pack_digests: tuple[str, ...]
    capability_group_ids: tuple[str, ...]
    retrieval_preference_penalty: int

    @classmethod
    def create(
        cls,
        *,
        request: PrimitiveRouteRequest,
        catalog: PrimitiveRouteCatalog,
        entries: Sequence[PrimitiveRouteEntry],
        retrieval_preference_penalty: int,
        wire_planner: ExactPrimitiveWirePlanner,
    ) -> "PrimitiveRoute":
        ordered = tuple(entries)
        if len(ordered) != len(request.steps):
            raise PrimitiveRouteError("route does not cover every requested step")
        for step, entry in zip(request.steps, ordered, strict=True):
            if catalog.by_primitive_id.get(entry.primitive_id) != entry:
                raise PrimitiveRouteError("route entry is outside the exact catalog")
            if step.capability_group_id not in entry.capability_group_ids:
                raise PrimitiveRouteError("route entry does not satisfy its capability step")
            if not request.policy.permits(entry.interface):
                raise PrimitiveRouteError("route entry violates the hard execution policy")
        first_input = ordered[0].interface.input_ports[0]
        last_output = ordered[-1].interface.output_ports[0]
        if (
            first_input.schema_digest != request.input_schema_digest
            or dict(first_input.schema) != dict(request.input_schema)
        ):
            raise PrimitiveRouteError("route input does not satisfy the request schema")
        if (
            last_output.schema_digest != request.output_schema_digest
            or dict(last_output.schema) != dict(request.output_schema)
        ):
            raise PrimitiveRouteError("route output does not satisfy the request schema")
        plan = wire_planner.pipeline(tuple(item.interface for item in ordered))
        key = {
            "format_version": _FORMAT_VERSION,
            "contract_digest": request.contract_digest,
            "catalog_digest": catalog.digest,
            "plan_id": plan.identity.id,
            "primitive_ids": [item.primitive_id for item in ordered],
            "release_ids": [item.release_id for item in ordered],
            "pack_digests": [item.pack_digest for item in ordered],
            "capability_group_ids": [
                item.capability_group_id for item in request.steps
            ],
        }
        return cls(
            IdentityRecord.create("primitive_route", key),
            _FORMAT_VERSION,
            request.contract_digest,
            catalog.digest,
            plan,
            tuple(item.primitive_id for item in ordered),
            tuple(item.release_id for item in ordered),
            tuple(item.pack_digest for item in ordered),
            tuple(item.capability_group_id for item in request.steps),
            retrieval_preference_penalty,
        )


@dataclass(frozen=True, slots=True)
class PrimitiveRouteSearchReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    request_id: str
    contract_digest: str
    catalog_digest: str
    source: str
    considered_candidate_count: int
    schema_blocked_candidate_count: int
    policy_rejected_candidate_count: int
    repeated_primitive_rejection_count: int
    wire_assessment_count: int
    wire_rejection_count: int
    terminal_output_rejection_count: int
    expanded_state_count: int
    route_count: int
    frontier_remaining_count: int
    stop_reason: str
    verified_recipe_id: str | None
    route_ids: tuple[str, ...]
    model_calls: int

    @classmethod
    def create(
        cls,
        *,
        request: PrimitiveRouteRequest,
        catalog_digest: str,
        source: str,
        considered_candidate_count: int,
        schema_blocked_candidate_count: int,
        policy_rejected_candidate_count: int,
        repeated_primitive_rejection_count: int,
        wire_assessment_count: int,
        wire_rejection_count: int,
        terminal_output_rejection_count: int,
        expanded_state_count: int,
        route_count: int,
        frontier_remaining_count: int,
        stop_reason: str,
        verified_recipe_id: str | None,
        route_ids: Sequence[str],
    ) -> "PrimitiveRouteSearchReceipt":
        fields = {
            "format_version": _FORMAT_VERSION,
            "request_id": request.identity.id,
            "contract_digest": request.contract_digest,
            "catalog_digest": catalog_digest,
            "source": source,
            "considered_candidate_count": considered_candidate_count,
            "schema_blocked_candidate_count": schema_blocked_candidate_count,
            "policy_rejected_candidate_count": policy_rejected_candidate_count,
            "repeated_primitive_rejection_count": repeated_primitive_rejection_count,
            "wire_assessment_count": wire_assessment_count,
            "wire_rejection_count": wire_rejection_count,
            "terminal_output_rejection_count": terminal_output_rejection_count,
            "expanded_state_count": expanded_state_count,
            "route_count": route_count,
            "frontier_remaining_count": frontier_remaining_count,
            "stop_reason": stop_reason,
            "verified_recipe_id": verified_recipe_id,
            "route_ids": tuple(route_ids),
            "model_calls": 0,
        }
        return cls(
            IdentityRecord.create("primitive_route_search_receipt", fields),
            **fields,
        )


@dataclass(frozen=True, slots=True)
class PrimitiveRouteSearchResult(RecordMixin):
    routes: tuple[PrimitiveRoute, ...]
    receipt: PrimitiveRouteSearchReceipt


@dataclass(frozen=True, slots=True)
class VerifiedPrimitiveRecipe(RecordMixin):
    """An exact route backed by one successful isolated execution receipt."""

    identity: IdentityRecord
    format_version: str
    contract_digest: str
    catalog_digest: str
    environment_digest: str
    route_id: str
    plan_id: str
    primitive_ids: tuple[str, ...]
    pack_digests: tuple[str, ...]
    execution_receipt_id: str
    observed_output_digest: str
    verifier_id: str
    verified_at: str


class VerifiedPrimitiveRecipeRegistry:
    """Append-only exact recipe registry; a changed catalog is always a cache miss."""

    def __init__(self) -> None:
        self._records: dict[
            tuple[str, str, str], tuple[VerifiedPrimitiveRecipe, PrimitiveRoute]
        ] = {}

    def record(
        self,
        *,
        route: PrimitiveRoute,
        execution_receipt: DeterministicPipelineReceipt,
        environment_digest: str,
        verifier_id: str,
        verified_at: str,
    ) -> VerifiedPrimitiveRecipe:
        if not _DIGEST.fullmatch(environment_digest):
            raise PrimitiveRouteError("recipe environment digest must be SHA-256")
        if not isinstance(verifier_id, str) or not _NAME.fullmatch(verifier_id):
            raise PrimitiveRouteError("recipe verifier ID is malformed")
        try:
            datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise PrimitiveRouteError("recipe verified_at must be ISO-8601") from exc
        _validate_route_identity(route)
        _validate_pipeline_receipt(execution_receipt)
        if execution_receipt.plan_id != route.plan.identity.id:
            raise PrimitiveRouteError("recipe execution receipt belongs to another plan")
        if execution_receipt.pack_digests != route.pack_digests:
            raise PrimitiveRouteError("recipe execution packs differ from the route")
        if execution_receipt.executed_stage_count != len(route.primitive_ids):
            raise PrimitiveRouteError("recipe execution did not observe every route stage")
        key = {
            "format_version": _FORMAT_VERSION,
            "contract_digest": route.contract_digest,
            "catalog_digest": route.catalog_digest,
            "environment_digest": environment_digest,
            "route_id": route.identity.id,
            "plan_id": route.plan.identity.id,
            "primitive_ids": route.primitive_ids,
            "pack_digests": route.pack_digests,
            "execution_receipt_id": execution_receipt.identity.id,
            "observed_output_digest": execution_receipt.output_digest,
            "verifier_id": verifier_id,
            "verified_at": verified_at,
        }
        record = VerifiedPrimitiveRecipe(
            IdentityRecord.create("verified_primitive_recipe", key),
            _FORMAT_VERSION,
            route.contract_digest,
            route.catalog_digest,
            environment_digest,
            route.identity.id,
            route.plan.identity.id,
            route.primitive_ids,
            route.pack_digests,
            execution_receipt.identity.id,
            execution_receipt.output_digest,
            verifier_id,
            verified_at,
        )
        lookup_key = (
            route.contract_digest,
            route.catalog_digest,
            environment_digest,
        )
        previous = self._records.get(lookup_key)
        if previous is not None:
            if previous[0].identity.id != record.identity.id:
                raise PrimitiveRouteError(
                    "verified recipe key is immutable and already has a different proof"
                )
            return previous[0]
        self._records[lookup_key] = (record, route)
        return record

    def lookup(
        self,
        *,
        contract_digest: str,
        catalog_digest: str,
        environment_digest: str,
    ) -> tuple[VerifiedPrimitiveRecipe, PrimitiveRoute] | None:
        return self._records.get(
            (contract_digest, catalog_digest, environment_digest)
        )


@dataclass(frozen=True, slots=True)
class _RouteState:
    entries: tuple[PrimitiveRouteEntry, ...]
    retrieval_preference_penalty: int


class BoundedPrimitiveRoutePlanner:
    """Search ordered retrieval layers under schema, policy, and expansion bounds."""

    def __init__(
        self,
        catalog: PrimitiveRouteCatalog,
        *,
        wire_planner: ExactPrimitiveWirePlanner | None = None,
    ) -> None:
        self.catalog = catalog
        self.wire_planner = wire_planner or ExactPrimitiveWirePlanner()

    def resolve(
        self,
        request: PrimitiveRouteRequest,
        *,
        recipe_registry: VerifiedPrimitiveRecipeRegistry | None = None,
        environment_digest: str | None = None,
    ) -> PrimitiveRouteSearchResult:
        if recipe_registry is not None:
            if environment_digest is None or not _DIGEST.fullmatch(environment_digest):
                raise PrimitiveRouteError(
                    "recipe lookup requires an exact environment digest"
                )
            cached = recipe_registry.lookup(
                contract_digest=request.contract_digest,
                catalog_digest=self.catalog.digest,
                environment_digest=environment_digest,
            )
            if cached is not None:
                recipe, route = cached
                receipt = PrimitiveRouteSearchReceipt.create(
                    request=request,
                    catalog_digest=self.catalog.digest,
                    source="verified_recipe",
                    considered_candidate_count=0,
                    schema_blocked_candidate_count=0,
                    policy_rejected_candidate_count=0,
                    repeated_primitive_rejection_count=0,
                    wire_assessment_count=0,
                    wire_rejection_count=0,
                    terminal_output_rejection_count=0,
                    expanded_state_count=0,
                    route_count=1,
                    frontier_remaining_count=0,
                    stop_reason="verified_recipe_hit",
                    verified_recipe_id=recipe.identity.id,
                    route_ids=(route.identity.id,),
                )
                return PrimitiveRouteSearchResult((route,), receipt)
        return self.search(request)

    def search(self, request: PrimitiveRouteRequest) -> PrimitiveRouteSearchResult:
        if not isinstance(request, PrimitiveRouteRequest):
            raise PrimitiveRouteError("planner requires a primitive route request")
        serial = count()
        frontier: list[
            tuple[int, tuple[str, ...], int, _RouteState]
        ] = [(0, (), next(serial), _RouteState((), 0))]
        routes: list[PrimitiveRoute] = []
        considered = 0
        schema_blocked = 0
        policy_rejected = 0
        repeated_rejected = 0
        wire_assessments = 0
        wire_rejected = 0
        output_rejected = 0
        expanded_states = 0
        budget_exhausted = False

        while frontier and len(routes) < request.max_routes and not budget_exhausted:
            _, _, _, state = heapq.heappop(frontier)
            expanded_states += 1
            step_index = len(state.entries)
            if step_index == len(request.steps):
                output = state.entries[-1].interface.output_ports[0]
                if (
                    output.schema_digest != request.output_schema_digest
                    or dict(output.schema) != dict(request.output_schema)
                ):
                    output_rejected += 1
                    continue
                route = PrimitiveRoute.create(
                    request=request,
                    catalog=self.catalog,
                    entries=state.entries,
                    retrieval_preference_penalty=state.retrieval_preference_penalty,
                    wire_planner=self.wire_planner,
                )
                if route.identity.id not in {item.identity.id for item in routes}:
                    routes.append(route)
                continue

            step = request.steps[step_index]
            current_schema = (
                request.input_schema
                if not state.entries
                else state.entries[-1].interface.output_ports[0].schema
            )
            current_schema_digest = (
                request.input_schema_digest
                if not state.entries
                else state.entries[-1].interface.output_ports[0].schema_digest
            )
            candidates, cheaply_schema_blocked = self._step_candidates(
                step,
                request.per_step_candidate_limit,
                input_schema_digest=current_schema_digest,
            )
            schema_blocked += cheaply_schema_blocked
            for preference_rank, entry in candidates:
                if considered >= request.max_candidate_expansions:
                    budget_exhausted = True
                    break
                considered += 1
                if entry.primitive_id in {
                    item.primitive_id for item in state.entries
                }:
                    repeated_rejected += 1
                    continue
                input_port = entry.interface.input_ports[0]
                if (
                    input_port.schema_digest != current_schema_digest
                    or dict(input_port.schema) != dict(current_schema)
                ):
                    schema_blocked += 1
                    continue
                if not request.policy.permits(entry.interface):
                    policy_rejected += 1
                    continue
                if state.entries:
                    wire_assessments += 1
                    assessment = self.wire_planner.assess(
                        state.entries[-1].interface, entry.interface
                    )
                    if assessment.verdict is not WireVerdict.COMPATIBLE:
                        wire_rejected += 1
                        continue
                entries = (*state.entries, entry)
                penalty = state.retrieval_preference_penalty + preference_rank
                primitive_ids = tuple(item.primitive_id for item in entries)
                heapq.heappush(
                    frontier,
                    (
                        penalty,
                        primitive_ids,
                        next(serial),
                        _RouteState(entries, penalty),
                    ),
                )

        routes.sort(
            key=lambda item: (
                item.retrieval_preference_penalty,
                item.primitive_ids,
                item.identity.id,
            )
        )
        if len(routes) >= request.max_routes:
            stop_reason = "route_limit_reached"
        elif budget_exhausted:
            stop_reason = "candidate_expansion_budget_exhausted"
        elif routes:
            stop_reason = "search_exhausted_after_valid_routes"
        else:
            stop_reason = "no_compatible_route"
        receipt = PrimitiveRouteSearchReceipt.create(
            request=request,
            catalog_digest=self.catalog.digest,
            source="bounded_graph_search",
            considered_candidate_count=considered,
            schema_blocked_candidate_count=schema_blocked,
            policy_rejected_candidate_count=policy_rejected,
            repeated_primitive_rejection_count=repeated_rejected,
            wire_assessment_count=wire_assessments,
            wire_rejection_count=wire_rejected,
            terminal_output_rejection_count=output_rejected,
            expanded_state_count=expanded_states,
            route_count=len(routes),
            frontier_remaining_count=len(frontier),
            stop_reason=stop_reason,
            verified_recipe_id=None,
            route_ids=tuple(item.identity.id for item in routes),
        )
        return PrimitiveRouteSearchResult(tuple(routes), receipt)

    def _step_candidates(
        self,
        step: PrimitiveRouteStep,
        limit: int,
        *,
        input_schema_digest: str,
    ) -> tuple[tuple[tuple[int, PrimitiveRouteEntry], ...], int]:
        group_entries = self.catalog.by_group.get(step.capability_group_id, ())
        group_ids = {item.primitive_id for item in group_entries}
        selected: list[PrimitiveRouteEntry] = []
        if step.nominated_primitive_ids:
            for primitive_id in step.nominated_primitive_ids:
                entry = self.catalog.by_primitive_id.get(primitive_id)
                if entry is not None and primitive_id in group_ids:
                    selected.append(entry)
            if step.allow_group_fallback:
                selected.extend(
                    item for item in group_entries if item.primitive_id not in set(
                        entry.primitive_id for entry in selected
                    )
                )
        else:
            selected.extend(group_entries)
        limited = tuple(selected[:limit])
        schema_ids = {
            item.primitive_id
            for item in self.catalog.by_input_schema.get(input_schema_digest, ())
        }
        blocked = len(limited) - sum(
            1 for item in limited if item.primitive_id in schema_ids
        )
        return (
            tuple(
                (rank, item)
                for rank, item in enumerate(limited)
                if item.primitive_id in schema_ids
            ),
            blocked,
        )


def local_python_route_environment_digest(runtime_version: str) -> str:
    """Return the exact execution-environment key used by recipe lookup."""

    if not isinstance(runtime_version, str) or not runtime_version:
        raise PrimitiveRouteError("route runtime version is required")
    return canonical_digest(
        {
            "executor": "taedri.local_deterministic_python_pipeline",
            "executor_version": _FORMAT_VERSION,
            "language": "python",
            "runtime_version": runtime_version,
            "execution_model": "in_process_call",
            "network": "denied",
            "effects": "denied",
        }
    )


def _validate_route_identity(route: PrimitiveRoute) -> None:
    rebuilt_plan = DeterministicPipelinePlan.create(
        route.plan.interfaces,
        route.plan.wires,
    )
    if rebuilt_plan != route.plan:
        raise PrimitiveRouteError("recipe route plan identity does not validate")
    key = {
        "format_version": route.format_version,
        "contract_digest": route.contract_digest,
        "catalog_digest": route.catalog_digest,
        "plan_id": route.plan.identity.id,
        "primitive_ids": route.primitive_ids,
        "release_ids": route.release_ids,
        "pack_digests": route.pack_digests,
        "capability_group_ids": route.capability_group_ids,
    }
    if route.identity != IdentityRecord.create("primitive_route", key):
        raise PrimitiveRouteError("recipe route identity does not validate")


def _validate_pipeline_receipt(receipt: DeterministicPipelineReceipt) -> None:
    key = {
        "format_version": receipt.format_version,
        "plan_id": receipt.plan_id,
        "pack_digests": receipt.pack_digests,
        "input_digest": receipt.input_digest,
        "output_digest": receipt.output_digest,
        "stage_observation_digests": receipt.stage_observation_digests,
        "executed_stage_count": receipt.executed_stage_count,
    }
    if receipt.identity != IdentityRecord.create(
        "deterministic_pipeline_receipt", key
    ):
        raise PrimitiveRouteError("recipe execution receipt identity does not validate")
