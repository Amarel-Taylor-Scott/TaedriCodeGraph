"""Matched-lane benchmark contracts for model-assisted primitive reuse.

The benchmark worker is deliberately provider- and sandbox-neutral.  It schedules
identical task/model/budget blocks, accepts receipts from an external runner, and
rejects receipts that cross the sealed-evaluation boundary.  This module does not
pretend that a conformance fixture is evidence of model efficacy.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from itertools import combinations
from math import comb
from typing import Iterable

from .contracts import RecordMixin
from .identity import IdentityRecord
from .workers import JobKind, WorkerJob, WorkerQueue


class BenchmarkError(ValueError):
    """Raised when an experiment or receipt violates benchmark invariants."""


class BenchmarkContaminationError(BenchmarkError):
    """Raised when sealed or forbidden evidence reaches a model-facing lane."""


class CorpusPartition(str, Enum):
    MINING_AND_TRAINING = "mining_and_training"
    VALIDATION_AND_TUNING = "validation_and_tuning"
    PUBLIC_BENCHMARK = "public_benchmark"
    SEALED_COLD_HOLDOUT = "sealed_cold_holdout"


class BenchmarkLane(str, Enum):
    """Increasing levels of Taedri assistance under a frozen model budget."""

    BARE_MODEL = "bare_model"
    SEARCH_CONTEXT = "search_context"
    PRIMITIVE_PLAN = "primitive_plan"
    PRIMITIVE_MATERIALIZED = "primitive_materialized"


class RunEvidenceClass(str, Enum):
    CONFORMANCE_FIXTURE = "conformance_fixture"
    REAL_MODEL = "real_model"


class RunOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ABSTAINED = "abstained"
    POLICY_BLOCKED = "policy_blocked"
    INFRA_ERROR = "infra_error"


class ContaminationState(str, Enum):
    CLEAN = "clean"
    DETECTED = "detected"
    UNKNOWN = "unknown"


class NetworkPolicy(str, Enum):
    DISABLED = "disabled"
    BENCHMARK_DECLARED = "benchmark_declared"


_LANE_ORDER = {
    BenchmarkLane.BARE_MODEL: 0,
    BenchmarkLane.SEARCH_CONTEXT: 1,
    BenchmarkLane.PRIMITIVE_PLAN: 2,
    BenchmarkLane.PRIMITIVE_MATERIALIZED: 3,
}


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BenchmarkError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise BenchmarkError("benchmark timestamps must include a UTC offset")
    return parsed


def _require_digest(value: str, field: str) -> None:
    if not value.startswith("sha256:"):
        raise BenchmarkError(f"{field} must be sha256 content addressed")


def _require_ref(value: str, field: str, *, sealed: bool = False) -> None:
    prefixes = (
        ("sealed:",)
        if sealed
        else ("sha256:", "uceg:v1:", "registry:", "sealed:")
    )
    if not value.startswith(prefixes):
        raise BenchmarkError(f"{field} must be an allowed immutable reference")


def _nonnegative(**values: int) -> None:
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BenchmarkError(f"{name} must be a non-negative integer")


def _ppm(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    magnitude = (abs(numerator) * 1_000_000) // denominator
    return -magnitude if numerator < 0 else magnitude


@dataclass(frozen=True, slots=True)
class ResourceBudget(RecordMixin):
    max_prompt_tokens: int
    max_completion_tokens: int
    max_tool_calls: int
    max_wall_ms: int
    max_verifier_cpu_ms: int

    def __post_init__(self) -> None:
        _nonnegative(
            max_prompt_tokens=self.max_prompt_tokens,
            max_completion_tokens=self.max_completion_tokens,
            max_tool_calls=self.max_tool_calls,
            max_wall_ms=self.max_wall_ms,
            max_verifier_cpu_ms=self.max_verifier_cpu_ms,
        )
        if min(
            self.max_prompt_tokens,
            self.max_completion_tokens,
            self.max_wall_ms,
            self.max_verifier_cpu_ms,
        ) == 0:
            raise BenchmarkError("token, wall-time, and verifier budgets must be positive")


@dataclass(frozen=True, slots=True)
class BenchmarkTask(RecordMixin):
    identity: IdentityRecord
    format_version: str
    source_task_id: str
    source_family: str
    corpus_partition: CorpusPartition
    request_ref: str
    repository_snapshot_ref: str
    sealed_oracle_ref: str
    runtime_digest: str
    policy_digest: str
    forbidden_retrieval_refs: tuple[str, ...]
    strata: tuple[str, ...]
    declared_value_microunits: int | None
    value_provenance_ref: str | None

    @classmethod
    def create(
        cls,
        *,
        source_task_id: str,
        source_family: str,
        corpus_partition: CorpusPartition,
        request_ref: str,
        repository_snapshot_ref: str,
        sealed_oracle_ref: str,
        runtime_digest: str,
        policy_digest: str,
        forbidden_retrieval_refs: Iterable[str],
        strata: Iterable[str] = (),
        declared_value_microunits: int | None = None,
        value_provenance_ref: str | None = None,
    ) -> "BenchmarkTask":
        if not source_task_id or not source_family:
            raise BenchmarkError("task source identity is required")
        _require_ref(request_ref, "request_ref")
        _require_ref(repository_snapshot_ref, "repository_snapshot_ref")
        _require_ref(sealed_oracle_ref, "sealed_oracle_ref", sealed=True)
        _require_digest(runtime_digest, "runtime_digest")
        _require_digest(policy_digest, "policy_digest")
        forbidden = tuple(sorted(set(forbidden_retrieval_refs) | {sealed_oracle_ref}))
        for ref in forbidden:
            if not ref.startswith(("sealed:", "sha256:", "uceg:v1:", "registry:")):
                raise BenchmarkError("forbidden retrieval entries must be immutable references")
        task_strata = tuple(sorted(set(strata)))
        if declared_value_microunits is not None:
            _nonnegative(declared_value_microunits=declared_value_microunits)
            if value_provenance_ref is None:
                raise BenchmarkError("declared economic value requires provenance")
        if value_provenance_ref is not None:
            _require_ref(value_provenance_ref, "value_provenance_ref")
            if declared_value_microunits is None:
                raise BenchmarkError("value provenance requires a declared value")
        key = {
            "format_version": "1.0.0",
            "source_task_id": source_task_id,
            "source_family": source_family,
            "corpus_partition": corpus_partition.value,
            "request_ref": request_ref,
            "repository_snapshot_ref": repository_snapshot_ref,
            "sealed_oracle_ref": sealed_oracle_ref,
            "runtime_digest": runtime_digest,
            "policy_digest": policy_digest,
            "forbidden_retrieval_refs": forbidden,
            "strata": task_strata,
            "declared_value_microunits": declared_value_microunits,
            "value_provenance_ref": value_provenance_ref,
        }
        return cls(
            IdentityRecord.create("benchmark_task", key),
            "1.0.0",
            source_task_id,
            source_family,
            corpus_partition,
            request_ref,
            repository_snapshot_ref,
            sealed_oracle_ref,
            runtime_digest,
            policy_digest,
            forbidden,
            task_strata,
            declared_value_microunits,
            value_provenance_ref,
        )


@dataclass(frozen=True, slots=True)
class BenchmarkExperiment(RecordMixin):
    identity: IdentityRecord
    format_version: str
    name: str
    task_ids: tuple[str, ...]
    lanes: tuple[BenchmarkLane, ...]
    seeds: tuple[int, ...]
    evidence_class: RunEvidenceClass
    provider_id: str
    model_id: str
    model_config_digest: str
    harness_digest: str
    retrieval_snapshot_ref: str
    primitive_registry_snapshot_ref: str
    sandbox_image_digest: str
    policy_digest: str
    network_policy: NetworkPolicy
    budget: ResourceBudget
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        name: str,
        task_ids: Iterable[str],
        lanes: Iterable[BenchmarkLane],
        seeds: Iterable[int],
        evidence_class: RunEvidenceClass,
        provider_id: str,
        model_id: str,
        model_config_digest: str,
        harness_digest: str,
        retrieval_snapshot_ref: str,
        primitive_registry_snapshot_ref: str,
        sandbox_image_digest: str,
        policy_digest: str,
        network_policy: NetworkPolicy,
        budget: ResourceBudget,
        created_at: str,
    ) -> "BenchmarkExperiment":
        if not name or not provider_id or not model_id:
            raise BenchmarkError("experiment, provider, and model identity are required")
        tasks = tuple(sorted(set(task_ids)))
        if not tasks:
            raise BenchmarkError("an experiment requires at least one task")
        lane_values = tuple(dict.fromkeys(lanes))
        if BenchmarkLane.BARE_MODEL not in lane_values or len(lane_values) < 2:
            raise BenchmarkError("a matched experiment requires bare_model and a treatment lane")
        lane_values = tuple(sorted(lane_values, key=_LANE_ORDER.__getitem__))
        seed_values = tuple(seeds)
        if not seed_values or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seed_values):
            raise BenchmarkError("one or more integer seeds are required")
        if len(set(seed_values)) != len(seed_values):
            raise BenchmarkError("repetition seeds must be unique")
        for field, value in (
            ("model_config_digest", model_config_digest),
            ("harness_digest", harness_digest),
            ("sandbox_image_digest", sandbox_image_digest),
            ("policy_digest", policy_digest),
        ):
            _require_digest(value, field)
        _require_ref(retrieval_snapshot_ref, "retrieval_snapshot_ref")
        _require_ref(primitive_registry_snapshot_ref, "primitive_registry_snapshot_ref")
        _timestamp(created_at)
        key = {
            "format_version": "1.0.0",
            "name": name,
            "task_ids": tasks,
            "lanes": tuple(lane.value for lane in lane_values),
            "seeds": seed_values,
            "evidence_class": evidence_class.value,
            "provider_id": provider_id,
            "model_id": model_id,
            "model_config_digest": model_config_digest,
            "harness_digest": harness_digest,
            "retrieval_snapshot_ref": retrieval_snapshot_ref,
            "primitive_registry_snapshot_ref": primitive_registry_snapshot_ref,
            "sandbox_image_digest": sandbox_image_digest,
            "policy_digest": policy_digest,
            "network_policy": network_policy.value,
            "budget": budget.to_dict(),
            "created_at": created_at,
        }
        return cls(
            IdentityRecord.create("benchmark_experiment", key),
            "1.0.0",
            name,
            tasks,
            lane_values,
            seed_values,
            evidence_class,
            provider_id,
            model_id,
            model_config_digest,
            harness_digest,
            retrieval_snapshot_ref,
            primitive_registry_snapshot_ref,
            sandbox_image_digest,
            policy_digest,
            network_policy,
            budget,
            created_at,
        )


@dataclass(frozen=True, slots=True)
class BenchmarkRunSpec(RecordMixin):
    identity: IdentityRecord
    format_version: str
    experiment_id: str
    task_id: str
    lane: BenchmarkLane
    repetition: int
    seed: int
    budget: ResourceBudget

    @classmethod
    def create(
        cls,
        *,
        experiment: BenchmarkExperiment,
        task_id: str,
        lane: BenchmarkLane,
        repetition: int,
        seed: int,
    ) -> "BenchmarkRunSpec":
        if task_id not in experiment.task_ids or lane not in experiment.lanes:
            raise BenchmarkError("run spec is outside the frozen experiment")
        if repetition <= 0 or repetition > len(experiment.seeds):
            raise BenchmarkError("run repetition is outside the seed schedule")
        if experiment.seeds[repetition - 1] != seed:
            raise BenchmarkError("run seed does not match its repetition")
        key = {
            "format_version": "1.0.0",
            "experiment_id": experiment.identity.id,
            "task_id": task_id,
            "lane": lane.value,
            "repetition": repetition,
            "seed": seed,
            "budget": experiment.budget.to_dict(),
        }
        return cls(
            IdentityRecord.create("benchmark_run_spec", key),
            "1.0.0",
            experiment.identity.id,
            task_id,
            lane,
            repetition,
            seed,
            experiment.budget,
        )


@dataclass(frozen=True, slots=True)
class BenchmarkRunReceipt(RecordMixin):
    identity: IdentityRecord
    format_version: str
    run_spec_id: str
    experiment_id: str
    task_id: str
    lane: BenchmarkLane
    repetition: int
    seed: int
    evidence_class: RunEvidenceClass
    outcome: RunOutcome
    contamination_state: ContaminationState
    completed_at: str
    output_artifact_ref: str | None
    model_usage_receipt_ref: str | None
    verification_receipt_refs: tuple[str, ...]
    retrieved_refs: tuple[str, ...]
    materialized_refs: tuple[str, ...]
    tool_receipt_refs: tuple[str, ...]
    prompt_tokens: int
    completion_tokens: int
    cached_prompt_tokens: int
    tool_tokens: int
    disclosed_context_bytes: int
    materialized_source_bytes: int
    reused_source_bytes: int
    newly_authored_source_bytes: int
    wall_ms: int
    model_ms: int
    retrieval_ms: int
    verification_ms: int
    provider_cost_microunits: int
    infrastructure_cost_microunits: int
    model_attempts: int
    repair_turns: int
    tool_calls: int
    human_interventions: int
    tests_total: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    build_passed: bool
    policy_passed: bool
    verification_passed: bool
    output_digest: str | None
    behavior_digest: str | None
    failure_class: str | None

    @property
    def accepted(self) -> bool:
        return self.outcome is RunOutcome.PASSED

    @property
    def total_model_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens + self.tool_tokens

    @property
    def total_cost_microunits(self) -> int:
        return self.provider_cost_microunits + self.infrastructure_cost_microunits

    @classmethod
    def create(
        cls,
        *,
        spec: BenchmarkRunSpec,
        task: BenchmarkTask,
        evidence_class: RunEvidenceClass,
        outcome: RunOutcome,
        contamination_state: ContaminationState,
        completed_at: str,
        output_artifact_ref: str | None = None,
        model_usage_receipt_ref: str | None = None,
        verification_receipt_refs: Iterable[str] = (),
        retrieved_refs: Iterable[str] = (),
        materialized_refs: Iterable[str] = (),
        tool_receipt_refs: Iterable[str] = (),
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_prompt_tokens: int = 0,
        tool_tokens: int = 0,
        disclosed_context_bytes: int = 0,
        materialized_source_bytes: int = 0,
        reused_source_bytes: int = 0,
        newly_authored_source_bytes: int = 0,
        wall_ms: int = 0,
        model_ms: int = 0,
        retrieval_ms: int = 0,
        verification_ms: int = 0,
        provider_cost_microunits: int = 0,
        infrastructure_cost_microunits: int = 0,
        model_attempts: int = 1,
        repair_turns: int = 0,
        tool_calls: int = 0,
        human_interventions: int = 0,
        tests_total: int = 0,
        tests_passed: int = 0,
        tests_failed: int = 0,
        tests_skipped: int = 0,
        build_passed: bool = False,
        policy_passed: bool = False,
        verification_passed: bool = False,
        output_digest: str | None = None,
        behavior_digest: str | None = None,
        failure_class: str | None = None,
    ) -> "BenchmarkRunReceipt":
        if spec.task_id != task.identity.id:
            raise BenchmarkError("receipt task does not match its run spec")
        _timestamp(completed_at)
        refs = {
            "verification_receipt_refs": tuple(sorted(set(verification_receipt_refs))),
            "retrieved_refs": tuple(sorted(set(retrieved_refs))),
            "materialized_refs": tuple(sorted(set(materialized_refs))),
            "tool_receipt_refs": tuple(sorted(set(tool_receipt_refs))),
        }
        for field, values in refs.items():
            for value in values:
                _require_ref(value, field)
        for field, value in (
            ("output_artifact_ref", output_artifact_ref),
            ("model_usage_receipt_ref", model_usage_receipt_ref),
        ):
            if value is not None:
                _require_ref(value, field)
        for field, value in (("output_digest", output_digest), ("behavior_digest", behavior_digest)):
            if value is not None:
                _require_digest(value, field)
        _nonnegative(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_prompt_tokens=cached_prompt_tokens,
            tool_tokens=tool_tokens,
            disclosed_context_bytes=disclosed_context_bytes,
            materialized_source_bytes=materialized_source_bytes,
            reused_source_bytes=reused_source_bytes,
            newly_authored_source_bytes=newly_authored_source_bytes,
            wall_ms=wall_ms,
            model_ms=model_ms,
            retrieval_ms=retrieval_ms,
            verification_ms=verification_ms,
            provider_cost_microunits=provider_cost_microunits,
            infrastructure_cost_microunits=infrastructure_cost_microunits,
            model_attempts=model_attempts,
            repair_turns=repair_turns,
            tool_calls=tool_calls,
            human_interventions=human_interventions,
            tests_total=tests_total,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            tests_skipped=tests_skipped,
        )
        if cached_prompt_tokens > prompt_tokens:
            raise BenchmarkError("cached prompt tokens cannot exceed prompt tokens")
        if tests_total != tests_passed + tests_failed + tests_skipped:
            raise BenchmarkError("test totals must reconcile")
        if tool_calls != len(refs["tool_receipt_refs"]):
            raise BenchmarkError("every tool call requires one distinct invocation receipt")
        if model_ms + retrieval_ms + verification_ms > wall_ms:
            raise BenchmarkError("phase durations cannot exceed wall time")
        if prompt_tokens > spec.budget.max_prompt_tokens:
            raise BenchmarkError("prompt token budget exceeded")
        if completion_tokens > spec.budget.max_completion_tokens:
            raise BenchmarkError("completion token budget exceeded")
        if tool_calls > spec.budget.max_tool_calls or wall_ms > spec.budget.max_wall_ms:
            raise BenchmarkError("tool-call or wall-time budget exceeded")
        if evidence_class is RunEvidenceClass.REAL_MODEL and model_usage_receipt_ref is None:
            raise BenchmarkError("real-model runs require a provider/runtime usage receipt")
        exposed = set(refs["retrieved_refs"]) | set(refs["materialized_refs"])
        leaked = exposed & set(task.forbidden_retrieval_refs)
        if leaked:
            raise BenchmarkContaminationError(
                "sealed evaluation references reached the model-facing context: "
                + ", ".join(sorted(leaked))
            )
        if spec.lane is BenchmarkLane.BARE_MODEL:
            if refs["retrieved_refs"] or refs["materialized_refs"]:
                raise BenchmarkError("bare_model cannot retrieve or materialize Taedri records")
            if disclosed_context_bytes or materialized_source_bytes or reused_source_bytes:
                raise BenchmarkError("bare_model cannot disclose Taedri context or reused source")
        elif spec.lane in {BenchmarkLane.SEARCH_CONTEXT, BenchmarkLane.PRIMITIVE_PLAN}:
            if refs["materialized_refs"] or materialized_source_bytes or reused_source_bytes:
                raise BenchmarkError(f"{spec.lane.value} cannot materialize source bodies")
        if materialized_source_bytes < reused_source_bytes:
            raise BenchmarkError("reused source bytes cannot exceed materialized source bytes")
        if contamination_state is ContaminationState.DETECTED and outcome is RunOutcome.PASSED:
            raise BenchmarkError("a contaminated run cannot be accepted")
        if outcome is RunOutcome.PASSED:
            if not refs["verification_receipt_refs"]:
                raise BenchmarkError("accepted runs require an independent verification receipt")
            if not (build_passed and policy_passed and verification_passed):
                raise BenchmarkError("accepted runs must pass build, policy, and verification")
            if tests_total <= 0 or tests_passed <= 0 or tests_failed:
                raise BenchmarkError("accepted runs require reconciled passing execution tests")
            if output_artifact_ref is None or output_digest is None or behavior_digest is None:
                raise BenchmarkError("accepted runs require output and behavior identities")
        key = {
            "format_version": "1.0.0",
            "run_spec_id": spec.identity.id,
            "experiment_id": spec.experiment_id,
            "task_id": spec.task_id,
            "lane": spec.lane.value,
            "repetition": spec.repetition,
            "seed": spec.seed,
            "evidence_class": evidence_class.value,
            "outcome": outcome.value,
            "contamination_state": contamination_state.value,
            "completed_at": completed_at,
            "output_artifact_ref": output_artifact_ref,
            "model_usage_receipt_ref": model_usage_receipt_ref,
            **refs,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cached_prompt_tokens": cached_prompt_tokens,
                "tool_tokens": tool_tokens,
                "disclosed_context_bytes": disclosed_context_bytes,
                "materialized_source_bytes": materialized_source_bytes,
                "reused_source_bytes": reused_source_bytes,
                "newly_authored_source_bytes": newly_authored_source_bytes,
                "wall_ms": wall_ms,
                "model_ms": model_ms,
                "retrieval_ms": retrieval_ms,
                "verification_ms": verification_ms,
                "provider_cost_microunits": provider_cost_microunits,
                "infrastructure_cost_microunits": infrastructure_cost_microunits,
                "model_attempts": model_attempts,
                "repair_turns": repair_turns,
                "tool_calls": tool_calls,
                "human_interventions": human_interventions,
            },
            "verification": {
                "tests_total": tests_total,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "tests_skipped": tests_skipped,
                "build_passed": build_passed,
                "policy_passed": policy_passed,
                "verification_passed": verification_passed,
            },
            "output_digest": output_digest,
            "behavior_digest": behavior_digest,
            "failure_class": failure_class,
        }
        return cls(
            IdentityRecord.create("benchmark_run_receipt", key),
            "1.0.0",
            spec.identity.id,
            spec.experiment_id,
            spec.task_id,
            spec.lane,
            spec.repetition,
            spec.seed,
            evidence_class,
            outcome,
            contamination_state,
            completed_at,
            output_artifact_ref,
            model_usage_receipt_ref,
            refs["verification_receipt_refs"],
            refs["retrieved_refs"],
            refs["materialized_refs"],
            refs["tool_receipt_refs"],
            prompt_tokens,
            completion_tokens,
            cached_prompt_tokens,
            tool_tokens,
            disclosed_context_bytes,
            materialized_source_bytes,
            reused_source_bytes,
            newly_authored_source_bytes,
            wall_ms,
            model_ms,
            retrieval_ms,
            verification_ms,
            provider_cost_microunits,
            infrastructure_cost_microunits,
            model_attempts,
            repair_turns,
            tool_calls,
            human_interventions,
            tests_total,
            tests_passed,
            tests_failed,
            tests_skipped,
            build_passed,
            policy_passed,
            verification_passed,
            output_digest,
            behavior_digest,
            failure_class,
        )


def _agreement_ppm(receipts: Iterable[BenchmarkRunReceipt], attribute: str) -> int | None:
    grouped: dict[str, list[str]] = defaultdict(list)
    for receipt in receipts:
        value = getattr(receipt, attribute)
        if value is not None:
            grouped[receipt.task_id].append(value.value if isinstance(value, Enum) else value)
    matches = 0
    pair_count = 0
    for values in grouped.values():
        for left, right in combinations(values, 2):
            pair_count += 1
            matches += int(left == right)
    return _ppm(matches, pair_count)


def _paired_sign_test_p_ppm(baseline_only: int, treatment_only: int) -> int:
    """Return the exact two-sided sign-test p-value as integer parts per million."""

    discordant = baseline_only + treatment_only
    if discordant == 0:
        return 1_000_000
    smaller = min(baseline_only, treatment_only)
    tail_numerator = sum(comb(discordant, index) for index in range(smaller + 1))
    denominator = 2**discordant
    two_sided_numerator = min(denominator, 2 * tail_numerator)
    return (two_sided_numerator * 1_000_000) // denominator


class BenchmarkWorker:
    """In-memory conformance worker for schedule, receipt, and report invariants."""

    def __init__(self) -> None:
        self.tasks: dict[str, BenchmarkTask] = {}
        self.experiments: dict[str, BenchmarkExperiment] = {}
        self.specs: dict[str, BenchmarkRunSpec] = {}
        self.receipts: dict[str, BenchmarkRunReceipt] = {}

    def register_task(self, task: BenchmarkTask) -> BenchmarkTask:
        existing = self.tasks.get(task.identity.id)
        if existing is not None and existing != task:  # pragma: no cover - digest collision
            raise BenchmarkError("benchmark task identity collision")
        self.tasks[task.identity.id] = task
        return task

    def schedule(self, experiment: BenchmarkExperiment) -> tuple[BenchmarkRunSpec, ...]:
        missing = set(experiment.task_ids) - set(self.tasks)
        if missing:
            raise BenchmarkError("experiment references unregistered tasks")
        existing = self.experiments.get(experiment.identity.id)
        if existing is not None and existing != experiment:  # pragma: no cover
            raise BenchmarkError("benchmark experiment identity collision")
        self.experiments[experiment.identity.id] = experiment
        scheduled: list[BenchmarkRunSpec] = []
        for task_id in experiment.task_ids:
            for repetition, seed in enumerate(experiment.seeds, start=1):
                for lane in experiment.lanes:
                    spec = BenchmarkRunSpec.create(
                        experiment=experiment,
                        task_id=task_id,
                        lane=lane,
                        repetition=repetition,
                        seed=seed,
                    )
                    prior = self.specs.get(spec.identity.id)
                    if prior is not None and prior != spec:  # pragma: no cover
                        raise BenchmarkError("benchmark run-spec identity collision")
                    self.specs[spec.identity.id] = spec
                    scheduled.append(spec)
        return tuple(scheduled)

    def enqueue(
        self,
        experiment_id: str,
        queue: WorkerQueue,
        *,
        created_at: str,
    ) -> tuple[WorkerJob, ...]:
        _timestamp(created_at)
        experiment = self._experiment(experiment_id)
        jobs: list[WorkerJob] = []
        for spec in self._specs_for(experiment_id):
            job = WorkerJob.create(
                queue="evaluation",
                kind=JobKind.BENCHMARK,
                subject_id=spec.task_id,
                payload_ref=spec.identity.id,
                idempotency_key=f"benchmark:{spec.identity.id}",
                created_at=created_at,
                priority=70,
                max_attempts=2,
                required_capabilities=(
                    "benchmark-receipt-v1",
                    "sealed-oracle-verifier",
                    f"lane:{spec.lane.value}",
                    f"network:{experiment.network_policy.value}",
                ),
            )
            jobs.append(queue.enqueue(job))
        return tuple(jobs)

    def record(self, receipt: BenchmarkRunReceipt) -> BenchmarkRunReceipt:
        spec = self.specs.get(receipt.run_spec_id)
        if spec is None:
            raise BenchmarkError("receipt references an unscheduled run")
        experiment = self._experiment(spec.experiment_id)
        if receipt.evidence_class is not experiment.evidence_class:
            raise BenchmarkError("receipt evidence class differs from its experiment")
        if (
            receipt.experiment_id != spec.experiment_id
            or receipt.task_id != spec.task_id
            or receipt.lane is not spec.lane
            or receipt.repetition != spec.repetition
            or receipt.seed != spec.seed
        ):
            raise BenchmarkError("receipt does not match its frozen run spec")
        existing = self.receipts.get(spec.identity.id)
        if existing is not None:
            if existing != receipt:
                raise BenchmarkError("a run spec cannot have competing terminal receipts")
            return existing
        self.receipts[spec.identity.id] = receipt
        return receipt

    def report(self, experiment_id: str) -> dict[str, object]:
        experiment = self._experiment(experiment_id)
        specs = self._specs_for(experiment_id)
        receipts = [self.receipts[spec.identity.id] for spec in specs if spec.identity.id in self.receipts]
        missing = [spec.identity.id for spec in specs if spec.identity.id not in self.receipts]
        by_lane = {
            lane: [receipt for receipt in receipts if receipt.lane is lane]
            for lane in experiment.lanes
        }
        summaries = [self._lane_summary(lane, by_lane[lane]) for lane in experiment.lanes]
        baseline = by_lane[BenchmarkLane.BARE_MODEL]
        comparisons = [
            self._comparison(baseline, by_lane[lane], lane)
            for lane in experiment.lanes
            if lane is not BenchmarkLane.BARE_MODEL
        ]
        contamination_counts = Counter(receipt.contamination_state.value for receipt in receipts)
        is_complete = not missing
        all_real = bool(receipts) and all(
            receipt.evidence_class is RunEvidenceClass.REAL_MODEL for receipt in receipts
        )
        all_clean = bool(receipts) and all(
            receipt.contamination_state is ContaminationState.CLEAN for receipt in receipts
        )
        return {
            "schema_version": "1.0.0",
            "experiment_id": experiment.identity.id,
            "experiment_name": experiment.name,
            "evidence_class": experiment.evidence_class.value,
            "scheduled_run_count": len(specs),
            "completed_run_count": len(receipts),
            "missing_run_spec_ids": missing,
            "is_complete": is_complete,
            "efficacy_claimable": is_complete and all_real and all_clean,
            "claim_warning": (
                None
                if is_complete and all_real and all_clean
                else "Incomplete, fixture, contaminated, or unknown-contamination data cannot support a SaaS efficacy or ROI claim."
            ),
            "frozen_inputs": {
                "provider_id": experiment.provider_id,
                "model_id": experiment.model_id,
                "model_config_digest": experiment.model_config_digest,
                "harness_digest": experiment.harness_digest,
                "retrieval_snapshot_ref": experiment.retrieval_snapshot_ref,
                "primitive_registry_snapshot_ref": experiment.primitive_registry_snapshot_ref,
                "sandbox_image_digest": experiment.sandbox_image_digest,
                "policy_digest": experiment.policy_digest,
                "network_policy": experiment.network_policy.value,
                "budget": experiment.budget.to_dict(),
            },
            "contamination_counts": dict(sorted(contamination_counts.items())),
            "lane_summaries": summaries,
            "matched_comparisons": comparisons,
        }

    def _experiment(self, experiment_id: str) -> BenchmarkExperiment:
        try:
            return self.experiments[experiment_id]
        except KeyError as exc:
            raise BenchmarkError(f"unknown experiment: {experiment_id}") from exc

    def _specs_for(self, experiment_id: str) -> list[BenchmarkRunSpec]:
        return sorted(
            (spec for spec in self.specs.values() if spec.experiment_id == experiment_id),
            key=lambda spec: (spec.task_id, spec.repetition, _LANE_ORDER[spec.lane]),
        )

    @staticmethod
    def _lane_summary(
        lane: BenchmarkLane, receipts: list[BenchmarkRunReceipt]
    ) -> dict[str, object]:
        count = len(receipts)
        accepted = sum(receipt.accepted for receipt in receipts)
        outcomes = Counter(receipt.outcome.value for receipt in receipts)
        total_tokens = sum(receipt.total_model_tokens for receipt in receipts)
        total_wall_ms = sum(receipt.wall_ms for receipt in receipts)
        total_cost = sum(receipt.total_cost_microunits for receipt in receipts)
        reused = sum(receipt.reused_source_bytes for receipt in receipts)
        authored = sum(receipt.newly_authored_source_bytes for receipt in receipts)
        clean = [r for r in receipts if r.contamination_state is ContaminationState.CLEAN]
        clean_accepted = sum(receipt.accepted for receipt in clean)
        return {
            "lane": lane.value,
            "run_count": count,
            "outcomes": dict(sorted(outcomes.items())),
            "accepted_count": accepted,
            "success_rate_ppm": _ppm(accepted, count),
            "clean_run_count": len(clean),
            "clean_success_rate_ppm": _ppm(clean_accepted, len(clean)),
            "total_model_tokens": total_tokens,
            "mean_model_tokens": total_tokens // count if count else None,
            "total_wall_ms": total_wall_ms,
            "mean_wall_ms": total_wall_ms // count if count else None,
            "total_cost_microunits": total_cost,
            "cost_per_accepted_microunits": total_cost // accepted if accepted else None,
            "accepted_per_million_model_tokens": _ppm(accepted, total_tokens),
            "verified_reuse_fraction_ppm": _ppm(reused, reused + authored),
            "outcome_consistency_ppm": _agreement_ppm(receipts, "outcome"),
            "exact_output_consistency_ppm": _agreement_ppm(receipts, "output_digest"),
            "behavior_consistency_ppm": _agreement_ppm(receipts, "behavior_digest"),
            "repair_turns": sum(receipt.repair_turns for receipt in receipts),
            "human_interventions": sum(receipt.human_interventions for receipt in receipts),
        }

    @staticmethod
    def _comparison(
        baseline: list[BenchmarkRunReceipt],
        treatment: list[BenchmarkRunReceipt],
        treatment_lane: BenchmarkLane,
    ) -> dict[str, object]:
        base_by_key = {(r.task_id, r.repetition): r for r in baseline}
        treatment_by_key = {(r.task_id, r.repetition): r for r in treatment}
        keys = sorted(set(base_by_key) & set(treatment_by_key))
        pairs = [(base_by_key[key], treatment_by_key[key]) for key in keys]
        base_tokens = sum(left.total_model_tokens for left, _ in pairs)
        treatment_tokens = sum(right.total_model_tokens for _, right in pairs)
        base_wall = sum(left.wall_ms for left, _ in pairs)
        treatment_wall = sum(right.wall_ms for _, right in pairs)
        base_cost = sum(left.total_cost_microunits for left, _ in pairs)
        treatment_cost = sum(right.total_cost_microunits for _, right in pairs)
        claimable = [
            (left, right)
            for left, right in pairs
            if left.evidence_class is RunEvidenceClass.REAL_MODEL
            and right.evidence_class is RunEvidenceClass.REAL_MODEL
            and left.contamination_state is ContaminationState.CLEAN
            and right.contamination_state is ContaminationState.CLEAN
        ]
        both_accepted = sum(left.accepted and right.accepted for left, right in pairs)
        baseline_only = sum(left.accepted and not right.accepted for left, right in pairs)
        treatment_only = sum(not left.accepted and right.accepted for left, right in pairs)
        neither_accepted = len(pairs) - both_accepted - baseline_only - treatment_only
        return {
            "baseline_lane": BenchmarkLane.BARE_MODEL.value,
            "treatment_lane": treatment_lane.value,
            "matched_pair_count": len(pairs),
            "claimable_clean_pair_count": len(claimable),
            "both_accepted_count": both_accepted,
            "baseline_only_accepted_count": baseline_only,
            "treatment_only_accepted_count": treatment_only,
            "neither_accepted_count": neither_accepted,
            "discordant_pair_count": baseline_only + treatment_only,
            "exact_paired_sign_test_p_ppm": _paired_sign_test_p_ppm(
                baseline_only, treatment_only
            ),
            "paired_success_gain_ppm": _ppm(
                sum(int(right.accepted) - int(left.accepted) for left, right in pairs),
                len(pairs),
            ),
            "model_token_savings_ppm": _ppm(base_tokens - treatment_tokens, base_tokens),
            "wall_time_savings_ppm": _ppm(base_wall - treatment_wall, base_wall),
            "cost_savings_ppm": _ppm(base_cost - treatment_cost, base_cost),
            "baseline_accepted_count": sum(left.accepted for left, _ in pairs),
            "treatment_accepted_count": sum(right.accepted for _, right in pairs),
            "treatment_reused_source_bytes": sum(right.reused_source_bytes for _, right in pairs),
        }
