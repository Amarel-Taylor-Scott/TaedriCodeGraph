from __future__ import annotations

import unittest

from taedri_codegraph.benchmarking import (
    BenchmarkContaminationError,
    BenchmarkError,
    BenchmarkExperiment,
    BenchmarkLane,
    BenchmarkRunReceipt,
    BenchmarkTask,
    BenchmarkWorker,
    ContaminationState,
    CorpusPartition,
    NetworkPolicy,
    ResourceBudget,
    RunEvidenceClass,
    RunOutcome,
)
from taedri_codegraph.canonical import sha256_digest
from taedri_codegraph.workers import JobKind, WorkerQueue


def digest(label: str) -> str:
    return sha256_digest(label.encode("utf-8"))


class BenchmarkWorkerTests(unittest.TestCase):
    def task(self, label: str = "task-1") -> BenchmarkTask:
        return BenchmarkTask.create(
            source_task_id=label,
            source_family="private-repository-acceptance-task",
            corpus_partition=CorpusPartition.SEALED_COLD_HOLDOUT,
            request_ref=digest(f"request:{label}"),
            repository_snapshot_ref=digest(f"repository:{label}"),
            sealed_oracle_ref=f"sealed:oracle:{label}",
            runtime_digest=digest("python-3.12-runtime"),
            policy_digest=digest("benchmark-policy"),
            forbidden_retrieval_refs=(f"sealed:gold:{label}",),
            strata=("python", "component-composition"),
        )

    def experiment(
        self,
        tasks: tuple[BenchmarkTask, ...],
        *,
        evidence_class: RunEvidenceClass = RunEvidenceClass.CONFORMANCE_FIXTURE,
        seeds: tuple[int, ...] = (11, 22),
        lanes: tuple[BenchmarkLane, ...] = tuple(BenchmarkLane),
    ) -> BenchmarkExperiment:
        return BenchmarkExperiment.create(
            name="matched primitive assistance",
            task_ids=(task.identity.id for task in tasks),
            lanes=lanes,
            seeds=seeds,
            evidence_class=evidence_class,
            provider_id="fixture-provider" if evidence_class is RunEvidenceClass.CONFORMANCE_FIXTURE else "real-provider",
            model_id="frozen-model-v1",
            model_config_digest=digest("model-config"),
            harness_digest=digest("harness"),
            retrieval_snapshot_ref=digest("retrieval-epoch"),
            primitive_registry_snapshot_ref=digest("primitive-registry"),
            sandbox_image_digest=digest("sandbox-image"),
            policy_digest=digest("benchmark-policy"),
            network_policy=NetworkPolicy.DISABLED,
            budget=ResourceBudget(2_000, 1_000, 8, 60_000, 30_000),
            created_at="2026-07-16T14:00:00Z",
        )

    def scheduled(
        self,
        *,
        evidence_class: RunEvidenceClass = RunEvidenceClass.CONFORMANCE_FIXTURE,
        seeds: tuple[int, ...] = (11, 22),
        lanes: tuple[BenchmarkLane, ...] = tuple(BenchmarkLane),
    ) -> tuple[BenchmarkWorker, BenchmarkTask, BenchmarkExperiment]:
        worker = BenchmarkWorker()
        task = worker.register_task(self.task())
        experiment = self.experiment((task,), evidence_class=evidence_class, seeds=seeds, lanes=lanes)
        worker.schedule(experiment)
        return worker, task, experiment

    def receipt(
        self,
        worker: BenchmarkWorker,
        task: BenchmarkTask,
        experiment: BenchmarkExperiment,
        lane: BenchmarkLane,
        repetition: int,
        *,
        outcome: RunOutcome = RunOutcome.PASSED,
        contamination: ContaminationState = ContaminationState.CLEAN,
        prompt_tokens: int = 100,
        completion_tokens: int = 40,
        reused_source_bytes: int = 0,
        newly_authored_source_bytes: int = 100,
        retrieved_refs: tuple[str, ...] = (),
        materialized_refs: tuple[str, ...] = (),
        output_label: str = "equivalent-output",
    ) -> BenchmarkRunReceipt:
        spec = next(
            spec
            for spec in worker.specs.values()
            if spec.lane is lane and spec.repetition == repetition
        )
        passed = outcome is RunOutcome.PASSED
        materialized_source_bytes = reused_source_bytes if materialized_refs else 0
        if lane is BenchmarkLane.PRIMITIVE_MATERIALIZED and reused_source_bytes:
            materialized_source_bytes = reused_source_bytes
        return BenchmarkRunReceipt.create(
            spec=spec,
            task=task,
            evidence_class=experiment.evidence_class,
            outcome=outcome,
            contamination_state=contamination,
            completed_at=f"2026-07-16T14:0{repetition}:00Z",
            output_artifact_ref=digest(f"artifact:{output_label}") if passed else None,
            model_usage_receipt_ref=(
                digest(f"usage:{lane.value}:{repetition}")
                if experiment.evidence_class is RunEvidenceClass.REAL_MODEL
                else None
            ),
            verification_receipt_refs=(digest(f"verification:{lane.value}:{repetition}"),),
            retrieved_refs=retrieved_refs,
            materialized_refs=materialized_refs,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            disclosed_context_bytes=512 if retrieved_refs else 0,
            materialized_source_bytes=materialized_source_bytes,
            reused_source_bytes=reused_source_bytes,
            newly_authored_source_bytes=newly_authored_source_bytes,
            wall_ms=1_000,
            model_ms=700,
            retrieval_ms=100 if retrieved_refs else 0,
            verification_ms=200,
            provider_cost_microunits=70,
            infrastructure_cost_microunits=30,
            tests_total=2,
            tests_passed=2 if passed else 1,
            tests_failed=0 if passed else 1,
            build_passed=True,
            policy_passed=True,
            verification_passed=passed,
            output_digest=digest(f"output:{output_label}") if passed else None,
            behavior_digest=digest("behavior:passes-contract") if passed else None,
            failure_class=None if passed else "test_failure",
        )

    def test_schedule_is_matched_and_enqueues_idempotent_benchmark_jobs(self) -> None:
        worker = BenchmarkWorker()
        tasks = tuple(worker.register_task(self.task(f"task-{index}")) for index in range(2))
        experiment = self.experiment(tasks)
        specs = worker.schedule(experiment)
        self.assertEqual(len(specs), 2 * 2 * 4)
        self.assertEqual({spec.budget for spec in specs}, {experiment.budget})
        queue = WorkerQueue()
        first = worker.enqueue(experiment.identity.id, queue, created_at="2026-07-16T14:00:01Z")
        second = worker.enqueue(experiment.identity.id, queue, created_at="2026-07-16T14:00:01Z")
        self.assertEqual(first, second)
        self.assertEqual({job.kind for job in first}, {JobKind.BENCHMARK})
        self.assertTrue(all("sealed-oracle-verifier" in job.required_capabilities for job in first))

    def test_sealed_evidence_cannot_reach_retrieval_or_materialization(self) -> None:
        worker, task, experiment = self.scheduled()
        spec = next(spec for spec in worker.specs.values() if spec.lane is BenchmarkLane.SEARCH_CONTEXT)
        with self.assertRaises(BenchmarkContaminationError):
            BenchmarkRunReceipt.create(
                spec=spec,
                task=task,
                evidence_class=experiment.evidence_class,
                outcome=RunOutcome.FAILED,
                contamination_state=ContaminationState.DETECTED,
                completed_at="2026-07-16T14:01:00Z",
                retrieved_refs=(task.sealed_oracle_ref,),
                verification_receipt_refs=(digest("verification"),),
                tests_total=1,
                tests_failed=1,
                wall_ms=100,
            )

    def test_accepted_run_requires_independent_execution_evidence(self) -> None:
        worker, task, experiment = self.scheduled()
        spec = next(spec for spec in worker.specs.values() if spec.lane is BenchmarkLane.BARE_MODEL)
        with self.assertRaisesRegex(BenchmarkError, "independent verification"):
            BenchmarkRunReceipt.create(
                spec=spec,
                task=task,
                evidence_class=experiment.evidence_class,
                outcome=RunOutcome.PASSED,
                contamination_state=ContaminationState.CLEAN,
                completed_at="2026-07-16T14:01:00Z",
                output_artifact_ref=digest("artifact"),
                tests_total=1,
                tests_passed=1,
                build_passed=True,
                policy_passed=True,
                verification_passed=True,
                output_digest=digest("output"),
                behavior_digest=digest("behavior"),
                wall_ms=100,
            )

    def test_lanes_enforce_progressive_disclosure(self) -> None:
        worker, task, experiment = self.scheduled()
        bare = next(spec for spec in worker.specs.values() if spec.lane is BenchmarkLane.BARE_MODEL)
        with self.assertRaisesRegex(BenchmarkError, "cannot retrieve"):
            BenchmarkRunReceipt.create(
                spec=bare,
                task=task,
                evidence_class=experiment.evidence_class,
                outcome=RunOutcome.FAILED,
                contamination_state=ContaminationState.CLEAN,
                completed_at="2026-07-16T14:01:00Z",
                retrieved_refs=(digest("candidate"),),
                tests_total=1,
                tests_failed=1,
                wall_ms=100,
            )
        search = next(spec for spec in worker.specs.values() if spec.lane is BenchmarkLane.SEARCH_CONTEXT)
        with self.assertRaisesRegex(BenchmarkError, "cannot materialize"):
            BenchmarkRunReceipt.create(
                spec=search,
                task=task,
                evidence_class=experiment.evidence_class,
                outcome=RunOutcome.FAILED,
                contamination_state=ContaminationState.CLEAN,
                completed_at="2026-07-16T14:01:00Z",
                materialized_refs=(digest("source"),),
                materialized_source_bytes=10,
                tests_total=1,
                tests_failed=1,
                wall_ms=100,
            )

    def test_report_retains_failures_and_computes_matched_efficiency(self) -> None:
        worker, task, experiment = self.scheduled(
            lanes=(BenchmarkLane.BARE_MODEL, BenchmarkLane.PRIMITIVE_MATERIALIZED)
        )
        worker.record(self.receipt(worker, task, experiment, BenchmarkLane.BARE_MODEL, 1, prompt_tokens=60, completion_tokens=40))
        worker.record(
            self.receipt(
                worker,
                task,
                experiment,
                BenchmarkLane.BARE_MODEL,
                2,
                outcome=RunOutcome.FAILED,
                prompt_tokens=60,
                completion_tokens=40,
            )
        )
        for repetition in (1, 2):
            worker.record(
                self.receipt(
                    worker,
                    task,
                    experiment,
                    BenchmarkLane.PRIMITIVE_MATERIALIZED,
                    repetition,
                    prompt_tokens=40,
                    completion_tokens=20,
                    reused_source_bytes=80,
                    newly_authored_source_bytes=20,
                    retrieved_refs=(digest("candidate"),),
                    materialized_refs=(digest("source"),),
                )
            )
        report = worker.report(experiment.identity.id)
        self.assertTrue(report["is_complete"])
        self.assertFalse(report["efficacy_claimable"])
        baseline, treatment = report["lane_summaries"]
        self.assertEqual(baseline["accepted_count"], 1)
        self.assertEqual(baseline["outcomes"], {"failed": 1, "passed": 1})
        self.assertEqual(treatment["behavior_consistency_ppm"], 1_000_000)
        self.assertEqual(treatment["verified_reuse_fraction_ppm"], 800_000)
        comparison = report["matched_comparisons"][0]
        self.assertEqual(comparison["paired_success_gain_ppm"], 500_000)
        self.assertEqual(comparison["model_token_savings_ppm"], 400_000)
        self.assertEqual(comparison["claimable_clean_pair_count"], 0)
        self.assertEqual(comparison["both_accepted_count"], 1)
        self.assertEqual(comparison["treatment_only_accepted_count"], 1)
        self.assertEqual(comparison["discordant_pair_count"], 1)
        self.assertEqual(comparison["exact_paired_sign_test_p_ppm"], 1_000_000)

    def test_complete_real_clean_run_can_support_a_claim(self) -> None:
        worker, task, experiment = self.scheduled(
            evidence_class=RunEvidenceClass.REAL_MODEL,
            seeds=(11,),
            lanes=(BenchmarkLane.BARE_MODEL, BenchmarkLane.SEARCH_CONTEXT),
        )
        worker.record(self.receipt(worker, task, experiment, BenchmarkLane.BARE_MODEL, 1))
        worker.record(
            self.receipt(
                worker,
                task,
                experiment,
                BenchmarkLane.SEARCH_CONTEXT,
                1,
                retrieved_refs=(digest("search-card"),),
            )
        )
        report = worker.report(experiment.identity.id)
        self.assertTrue(report["efficacy_claimable"])
        self.assertEqual(report["matched_comparisons"][0]["claimable_clean_pair_count"], 1)

    def test_real_model_receipt_requires_usage_provenance(self) -> None:
        worker, task, experiment = self.scheduled(
            evidence_class=RunEvidenceClass.REAL_MODEL,
            seeds=(11,),
            lanes=(BenchmarkLane.BARE_MODEL, BenchmarkLane.SEARCH_CONTEXT),
        )
        spec = next(spec for spec in worker.specs.values() if spec.lane is BenchmarkLane.BARE_MODEL)
        with self.assertRaisesRegex(BenchmarkError, "usage receipt"):
            BenchmarkRunReceipt.create(
                spec=spec,
                task=task,
                evidence_class=experiment.evidence_class,
                outcome=RunOutcome.FAILED,
                contamination_state=ContaminationState.CLEAN,
                completed_at="2026-07-16T14:01:00Z",
                tests_total=1,
                tests_failed=1,
                wall_ms=100,
            )

    def test_budget_and_tool_receipt_reconciliation_are_enforced(self) -> None:
        worker, task, experiment = self.scheduled()
        spec = next(spec for spec in worker.specs.values() if spec.lane is BenchmarkLane.BARE_MODEL)
        with self.assertRaisesRegex(BenchmarkError, "prompt token budget"):
            BenchmarkRunReceipt.create(
                spec=spec,
                task=task,
                evidence_class=experiment.evidence_class,
                outcome=RunOutcome.FAILED,
                contamination_state=ContaminationState.CLEAN,
                completed_at="2026-07-16T14:01:00Z",
                prompt_tokens=2_001,
                tests_total=1,
                tests_failed=1,
                wall_ms=100,
            )
        with self.assertRaisesRegex(BenchmarkError, "every tool call"):
            BenchmarkRunReceipt.create(
                spec=spec,
                task=task,
                evidence_class=experiment.evidence_class,
                outcome=RunOutcome.FAILED,
                contamination_state=ContaminationState.CLEAN,
                completed_at="2026-07-16T14:01:00Z",
                tool_calls=1,
                tests_total=1,
                tests_failed=1,
                wall_ms=100,
            )

    def test_competing_terminal_receipts_are_rejected_but_replay_is_idempotent(self) -> None:
        worker, task, experiment = self.scheduled(
            seeds=(11,), lanes=(BenchmarkLane.BARE_MODEL, BenchmarkLane.SEARCH_CONTEXT)
        )
        receipt = self.receipt(worker, task, experiment, BenchmarkLane.BARE_MODEL, 1)
        self.assertEqual(worker.record(receipt), worker.record(receipt))
        competing = self.receipt(
            worker,
            task,
            experiment,
            BenchmarkLane.BARE_MODEL,
            1,
            outcome=RunOutcome.FAILED,
        )
        with self.assertRaisesRegex(BenchmarkError, "competing terminal"):
            worker.record(competing)

    def test_declared_economic_value_requires_sourced_provenance(self) -> None:
        with self.assertRaisesRegex(BenchmarkError, "requires provenance"):
            BenchmarkTask.create(
                source_task_id="economic-task",
                source_family="benchmark",
                corpus_partition=CorpusPartition.PUBLIC_BENCHMARK,
                request_ref=digest("request"),
                repository_snapshot_ref=digest("repository"),
                sealed_oracle_ref="sealed:oracle:economic-task",
                runtime_digest=digest("runtime"),
                policy_digest=digest("policy"),
                forbidden_retrieval_refs=(),
                declared_value_microunits=10_000,
            )


if __name__ == "__main__":
    unittest.main()
