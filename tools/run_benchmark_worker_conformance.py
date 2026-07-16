#!/usr/bin/env python3
"""Build a non-claimable benchmark-worker conformance bundle from real repo data."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from taedri_codegraph.benchmarking import (  # noqa: E402
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
from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest  # noqa: E402
from taedri_codegraph.workers import WorkerQueue  # noqa: E402


OUTPUT = ROOT / "eval" / "results" / "benchmark-worker-2026-07-16"
FACTORY_RESULTS = ROOT / "eval" / "results" / "primitive-factory-2026-07-16"
CREATED_AT = "2026-07-16T15:00:00Z"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _write_jsonl(path: Path, values: list[object]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values),
        "utf-8",
    )


def _source_snapshot() -> str:
    source_root = ROOT / "src" / "taedri_codegraph"
    inventory = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "digest": sha256_digest(path.read_bytes()),
        }
        for path in sorted(source_root.rglob("*.py"))
        if path.is_file() and "__pycache__" not in path.parts
    ]
    return sha256_digest(canonical_json_bytes(inventory))


def _candidates() -> dict[str, dict[str, object]]:
    records = [
        json.loads(line)
        for line in (FACTORY_RESULTS / "candidates.jsonl").read_text("utf-8").splitlines()
    ]
    wanted = ("canonical_json_bytes", "WorkerQueue.claim")
    selected: dict[str, dict[str, object]] = {}
    for name in wanted:
        selected[name] = next(record for record in records if record["qualified_name"] == name)
    return selected


def _campaign_plan() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "status": "ready-for-provider-and-sealed-suite-adapters-no-efficacy-data-yet",
        "primary_question": "Does Taedri assistance improve independently verified working-code outcomes per token, second, and total cost while increasing attributable reuse?",
        "value_unit": "independently-accepted-policy-compliant-outcome",
        "lanes": [
            {
                "id": "bare_model",
                "model_visible": ["task request", "repository snapshot", "fixed tool schema"],
                "taedri_access": [],
            },
            {
                "id": "search_context",
                "model_visible": ["ranked D0-D2 cards", "search explanations", "provenance summaries"],
                "taedri_access": ["search"],
            },
            {
                "id": "primitive_plan",
                "model_visible": ["typed contracts", "ports", "compatibility edges", "candidate route handles"],
                "taedri_access": ["search", "plan IR"],
            },
            {
                "id": "primitive_materialized",
                "model_visible": ["selected source bodies", "examples", "tests", "adapter witnesses"],
                "taedri_access": ["search", "plan IR", "authorized thin packs", "deterministic composer"],
            },
        ],
        "matched_controls": [
            "same provider and exact model revision",
            "same harness, system policy, task snapshot, sandbox image, and verifier",
            "same prompt/completion/tool/wall/verification budgets",
            "same repetition seeds and task order randomization block",
            "all retrieval, body resolution, tool, model, build, test, policy, and cost receipts retained",
        ],
        "evaluation_tracks": [
            {
                "id": "private-product-tasks",
                "purpose": "closest measure of design-partner value and retention",
                "source_policy": "sealed_cold_holdout",
                "pilot": "start with real accepted/rejected tasks across at least three teams; use pilot discordance to power the next paired run",
            },
            {
                "id": "swe-skills-bench-adapter",
                "purpose": "paired reusable-context and token/duration comparison",
                "source_policy": "eval_only",
                "adapter_state": "planned",
            },
            {
                "id": "swe-bench-adapter",
                "purpose": "repository issue repair with containerized tests",
                "source_policy": "eval_only",
                "adapter_state": "planned",
            },
            {
                "id": "terminal-bench-harbor-adapter",
                "purpose": "DevOps and long-horizon terminal work",
                "source_policy": "eval_only",
                "adapter_state": "planned",
            },
            {
                "id": "swe-lancer-adapter",
                "purpose": "sourced economic-value analysis for real freelance software tasks",
                "source_policy": "eval_only",
                "adapter_state": "planned",
            },
        ],
        "metric_families": {
            "correctness": [
                "accepted outcome rate",
                "build/test/policy/verification pass rates",
                "failure and abstention classes",
                "clean versus contaminated versus unknown strata",
            ],
            "consistency": [
                "outcome agreement across repetitions",
                "exact artifact agreement",
                "behavioral agreement under independent tests",
                "flake and retry rates",
            ],
            "reuse": [
                "selected and materialized primitive refs",
                "verified reused source bytes",
                "newly authored source bytes",
                "route and adapter verification receipts",
                "body-resolution rate after selection",
            ],
            "efficiency": [
                "provider-billable prompt/completion/cached/tool tokens",
                "disclosed context and materialized bytes",
                "model/retrieval/verification/wall time",
                "provider and infrastructure cost per attempted and accepted outcome",
                "repair turns, tool calls, and human interventions",
            ],
            "devops": [
                "sandbox build reproducibility",
                "dependency-lock and SBOM completeness",
                "deployment acceptance and rollback verification",
                "resource limits, queue latency, and failure-domain incidents",
            ],
            "finance": [
                "failure-inclusive cost per independently accepted outcome",
                "matched baseline cost delta",
                "sourced task value only when an external value receipt exists",
                "human-time value only when a declared study captures actual time",
            ],
        },
        "promotion_gate": {
            "required": [
                "complete paired blocks",
                "real provider/runtime usage receipts",
                "independent execution verification",
                "zero detected contamination in the promoted stratum",
                "reported uncertainty and retained failures",
                "success is non-inferior and at least one material efficiency metric improves",
            ],
            "forbidden_claims": [
                "fixture or replay data presented as model efficacy",
                "token savings without retrieval/tool/verification overhead",
                "economic value inferred from unsourced task labels",
                "pass rate that excludes retries, failures, policy blocks, or timeouts",
            ],
        },
        "external_harnesses": [
            "https://github.com/GeniusHTX/SWE-Skills-Bench",
            "https://github.com/SWE-bench/SWE-bench",
            "https://github.com/harbor-framework/terminal-bench",
            "https://github.com/openai/frontier-evals/tree/main/project/swelancer",
        ],
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    selected = _candidates()
    repository_snapshot = _source_snapshot()
    registry_snapshot = sha256_digest((FACTORY_RESULTS / "candidate-manifest.json").read_bytes())
    retrieval_snapshot = sha256_digest((FACTORY_RESULTS / "search-index.jsonl").read_bytes())
    task_inputs = [
        {
            "source_task_id": "taedri-conformance:canonical-json-composition",
            "request": "Build a deterministic JSON-byte encoding component and prove stable map ordering and non-finite rejection.",
            "candidate": selected["canonical_json_bytes"],
            "artifact": ROOT / "src" / "taedri_codegraph" / "canonical.py",
            "test": ROOT / "tests" / "unit" / "test_identity.py",
        },
        {
            "source_task_id": "taedri-conformance:leased-worker-queue",
            "request": "Build an idempotent lease-based worker queue with capability matching, retries, expiry, and terminal receipts.",
            "candidate": selected["WorkerQueue.claim"],
            "artifact": ROOT / "src" / "taedri_codegraph" / "workers.py",
            "test": ROOT / "tests" / "unit" / "test_workers.py",
        },
    ]
    worker = BenchmarkWorker()
    tasks: list[BenchmarkTask] = []
    visible_requests: list[dict[str, str]] = []
    task_data: dict[str, dict[str, object]] = {}
    for value in task_inputs:
        request_ref = sha256_digest(str(value["request"]).encode("utf-8"))
        task = worker.register_task(
            BenchmarkTask.create(
                source_task_id=str(value["source_task_id"]),
                source_family="taedri-real-source-conformance-fixture",
                corpus_partition=CorpusPartition.VALIDATION_AND_TUNING,
                request_ref=request_ref,
                repository_snapshot_ref=repository_snapshot,
                sealed_oracle_ref=f"sealed:{value['source_task_id']}:oracle",
                runtime_digest=sha256_digest(b"cpython-3.12:unittest:local-conformance"),
                policy_digest=sha256_digest(b"taedri-benchmark-policy-v1"),
                forbidden_retrieval_refs=(f"sealed:{value['source_task_id']}:gold",),
                strata=("python", "real-taedri-source", "conformance-only"),
            )
        )
        tasks.append(task)
        visible_requests.append(
            {
                "source_task_id": str(value["source_task_id"]),
                "request_ref": request_ref,
                "request": str(value["request"]),
            }
        )
        task_data[task.identity.id] = value
    experiment = BenchmarkExperiment.create(
        name="benchmark worker progressive-disclosure conformance",
        task_ids=(task.identity.id for task in tasks),
        lanes=tuple(BenchmarkLane),
        seeds=(101, 202),
        evidence_class=RunEvidenceClass.CONFORMANCE_FIXTURE,
        provider_id="deterministic-contract-fixture",
        model_id="not-a-model",
        model_config_digest=sha256_digest(b"no-provider-call"),
        harness_digest=sha256_digest(Path(__file__).read_bytes()),
        retrieval_snapshot_ref=retrieval_snapshot,
        primitive_registry_snapshot_ref=registry_snapshot,
        sandbox_image_digest=sha256_digest(b"local-python-3.12-conformance-environment"),
        policy_digest=sha256_digest(b"taedri-benchmark-policy-v1"),
        network_policy=NetworkPolicy.DISABLED,
        budget=ResourceBudget(2_000, 1_000, 8, 60_000, 30_000),
        created_at=CREATED_AT,
    )
    specs = worker.schedule(experiment)
    queue = WorkerQueue()
    jobs = worker.enqueue(experiment.identity.id, queue, created_at="2026-07-16T15:00:01Z")
    task_by_id = {task.identity.id: task for task in tasks}
    for index, spec in enumerate(specs, start=1):
        task = task_by_id[spec.task_id]
        value = task_data[spec.task_id]
        candidate = value["candidate"]
        assert isinstance(candidate, dict)
        candidate_id = str(candidate["identity"]["id"])
        revision_id = str(candidate["revision_id"])
        descriptor_ref = str(candidate["descriptor_digest"])
        artifact_path = value["artifact"]
        test_path = value["test"]
        assert isinstance(artifact_path, Path) and isinstance(test_path, Path)
        retrieved: tuple[str, ...] = ()
        materialized: tuple[str, ...] = ()
        context_bytes = 0
        source_bytes = 0
        reused_bytes = 0
        authored_bytes = 100
        if spec.lane is BenchmarkLane.SEARCH_CONTEXT:
            retrieved = (candidate_id, descriptor_ref)
            context_bytes = 512
        elif spec.lane is BenchmarkLane.PRIMITIVE_PLAN:
            retrieved = (candidate_id, descriptor_ref, str(candidate["contract_digest"]), str(candidate["graph_digest"]))
            context_bytes = 768
        elif spec.lane is BenchmarkLane.PRIMITIVE_MATERIALIZED:
            retrieved = (candidate_id, descriptor_ref, str(candidate["contract_digest"]), str(candidate["graph_digest"]))
            materialized = (revision_id, str(candidate["fragment_digest"]))
            context_bytes = 768
            source_lines = artifact_path.read_text("utf-8").splitlines(keepends=True)
            source_bytes = len(
                "".join(
                    source_lines[
                        int(candidate["start_line"]) - 1 : int(candidate["end_line"])
                    ]
                ).encode("utf-8")
            )
            reused_bytes = source_bytes
            authored_bytes = 20
        verification_ref = sha256_digest(
            canonical_json_bytes(
                {
                    "evidence_class": "conformance_fixture",
                    "test_path": test_path.relative_to(ROOT).as_posix(),
                    "test_digest": sha256_digest(test_path.read_bytes()),
                    "declared_fixture_outcome": "passed",
                    "warning": "not a real provider or isolated model-efficacy run",
                }
            )
        )
        output_digest = sha256_digest(artifact_path.read_bytes())
        receipt = BenchmarkRunReceipt.create(
            spec=spec,
            task=task,
            evidence_class=RunEvidenceClass.CONFORMANCE_FIXTURE,
            outcome=RunOutcome.PASSED,
            contamination_state=ContaminationState.CLEAN,
            completed_at=f"2026-07-16T15:{index:02d}:00Z",
            output_artifact_ref=output_digest,
            verification_receipt_refs=(verification_ref,),
            retrieved_refs=retrieved,
            materialized_refs=materialized,
            prompt_tokens=80,
            completion_tokens=20,
            disclosed_context_bytes=context_bytes,
            materialized_source_bytes=source_bytes,
            reused_source_bytes=reused_bytes,
            newly_authored_source_bytes=authored_bytes,
            wall_ms=1_000,
            model_ms=600,
            retrieval_ms=100 if retrieved else 0,
            verification_ms=200,
            provider_cost_microunits=0,
            infrastructure_cost_microunits=100,
            tests_total=2,
            tests_passed=2,
            build_passed=True,
            policy_passed=True,
            verification_passed=True,
            output_digest=output_digest,
            behavior_digest=sha256_digest(test_path.read_bytes()),
        )
        worker.record(receipt)
    report = worker.report(experiment.identity.id)
    _write_json(OUTPUT / "campaign-plan.json", _campaign_plan())
    _write_json(OUTPUT / "conformance-experiment.json", experiment.to_dict())
    _write_json(OUTPUT / "conformance-visible-requests.json", visible_requests)
    _write_jsonl(OUTPUT / "conformance-tasks.jsonl", [task.to_dict() for task in tasks])
    _write_jsonl(OUTPUT / "conformance-run-specs.jsonl", [spec.to_dict() for spec in specs])
    _write_jsonl(
        OUTPUT / "conformance-run-receipts.jsonl",
        [worker.receipts[spec.identity.id].to_dict() for spec in specs],
    )
    _write_jsonl(OUTPUT / "worker-jobs.jsonl", [job.to_dict() for job in jobs])
    _write_json(OUTPUT / "conformance-report.json", report)
    with (OUTPUT / "lane-summary.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "lane",
            "run_count",
            "accepted_count",
            "success_rate_ppm",
            "mean_model_tokens",
            "mean_wall_ms",
            "cost_per_accepted_microunits",
            "verified_reuse_fraction_ppm",
            "outcome_consistency_ppm",
            "exact_output_consistency_ppm",
            "behavior_consistency_ppm",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for summary in report["lane_summaries"]:
            writer.writerow({field: summary.get(field) for field in fields})
    with (OUTPUT / "matched-comparisons.csv").open("w", newline="", encoding="utf-8") as handle:
        comparisons = report["matched_comparisons"]
        writer = csv.DictWriter(handle, fieldnames=list(comparisons[0]))
        writer.writeheader()
        writer.writerows(comparisons)
    (OUTPUT / "benchmark-lanes.mmd").write_text(
        """flowchart LR
  T[Sealed evaluation controller] --> B[Bare model]
  T --> S[Search context]
  T --> P[Primitive plan]
  T --> M[Primitive materialized]
  R[(Production retrieval snapshot)] --> S
  R --> P
  R --> M
  G[(Primitive registry snapshot)] --> P
  G --> M
  B --> V[Independent verifier]
  S --> V
  P --> V
  M --> V
  O[(Sealed oracle / hidden tests)] --> V
  V --> E[Immutable run receipts + paired report]
  O -. prohibited .-> R
""",
        "utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
