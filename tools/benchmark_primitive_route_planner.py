#!/usr/bin/env python3
"""Benchmark retrieval-nominated route search, execution, and recipe reuse."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from taedri_codegraph.canonical import canonical_json_bytes, sha256_digest
from taedri_codegraph.prompt_interception import (
    DeterministicRetrievalProgramShortlister,
    ReleasedPrimitiveCatalog,
)
from taedri_codegraph.primitives.routes import (
    BoundedPrimitiveRoutePlanner,
    PrimitiveRouteCatalog,
    PrimitiveRouteEntry,
    PrimitiveRoutePolicy,
    PrimitiveRouteRequest,
    PrimitiveRouteStep,
    VerifiedPrimitiveRecipeRegistry,
    local_python_route_environment_digest,
)
from taedri_codegraph.primitives.wiring import (
    LocalDeterministicPythonPipelineExecutor,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-17"
DEFAULT_OUTPUT = ROOT / "eval/results/primitive-route-planner-2026-07-17"
VERIFIED_AT = "2026-07-17T08:00:00Z"


@dataclass(frozen=True, slots=True)
class RouteTask:
    task_id: str
    names: tuple[str, ...]
    queries: tuple[str, ...]
    input_value: Any
    expected_output: Any


TASKS = (
    RouteTask(
        "text_identifier",
        (
            "normalize-text",
            "collapse-whitespace",
            "casefold-text",
            "normalize-column-name",
        ),
        (
            "remove surrounding whitespace without changing internal spacing",
            "collapse internal whitespace",
            "caseless unicode matching",
            "normalize dataframe column header",
        ),
        "  Customer\t Straße  ",
        "customer_strasse",
    ),
    RouteTask(
        "numeric_mean",
        ("minmax-scale", "numeric-mean"),
        ("scale numeric vector zero one", "arithmetic mean numeric vector"),
        [10, 20, 30],
        0.5,
    ),
    RouteTask(
        "datetime_utc",
        ("normalize-text", "normalize-iso-datetime"),
        (
            "remove surrounding whitespace without changing internal spacing",
            "normalize ISO datetime to UTC",
        ),
        " 2026-07-17T08:30:00-04:00 ",
        "2026-07-17T12:30:00Z",
    ),
    RouteTask(
        "null_marker",
        ("collapse-whitespace", "normalize-null-marker"),
        ("collapse internal whitespace", "normalize null markers"),
        "  N/A  ",
        None,
    ),
    RouteTask(
        "json_flatten",
        (
            "parse-json-object",
            "drop-null-fields",
            "wrap-flatten-request",
            "flatten-record",
            "canonical-json-object",
        ),
        (
            "strict JSON object parser",
            "drop top level null object fields",
            "wrap object for flatten record",
            "flatten nested record",
            "canonical compact JSON object serializer",
        ),
        '{"user":{"name":"Ada","age":37},"unused":null}',
        '{"user.age":37,"user.name":"Ada"}',
    ),
    RouteTask(
        "number_adapter",
        ("normalize-text", "coerce-finite-number", "format-compact-number"),
        (
            "remove surrounding whitespace without changing internal spacing",
            "finite numeric string coercion",
            "compact finite number formatting",
        ),
        " 1.25 ",
        "1.25",
    ),
    RouteTask(
        "vector_normalized_sum",
        ("l2-normalize", "numeric-sum"),
        ("unit L2 vector normalization", "accurate finite numeric sum"),
        [3, 4],
        1.4,
    ),
)


def run(*, cohort: Path, output: Path) -> Mapping[str, Any]:
    cohort = cohort.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    released = ReleasedPrimitiveCatalog.load_checked_cohort(cohort)
    shortlister = DeterministicRetrievalProgramShortlister(released.cards)
    route_entries: list[PrimitiveRouteEntry] = []
    packs: dict[str, bytes] = {}
    by_name: dict[str, PrimitiveRouteEntry] = {}
    for card in released.cards:
        encoded, interface = released.resolve(card.artifact_handle)
        entry = PrimitiveRouteEntry(
            card.primitive_id,
            card.release_id,
            card.namespace,
            card.name,
            card.pack_digest,
            interface,
        )
        route_entries.append(entry)
        packs[entry.primitive_id] = encoded
        by_name[entry.name] = entry
    catalog = PrimitiveRouteCatalog(route_entries)
    runtimes = {entry.interface.runtime_version for entry in route_entries}
    if len(runtimes) != 1:
        raise SystemExit("route benchmark cohort must pin exactly one runtime")
    runtime = runtimes.pop()
    local_runtime = f"{sys.version_info.major}.{sys.version_info.minor}"
    if runtime != local_runtime:
        raise SystemExit(
            f"route benchmark cohort pins Python {runtime}; "
            f"executor runs {local_runtime}"
        )
    policy = PrimitiveRoutePolicy("python", runtime)
    planner = BoundedPrimitiveRoutePlanner(catalog)
    executor = LocalDeterministicPythonPipelineExecutor()
    recipes = VerifiedPrimitiveRecipeRegistry()
    environment_digest = local_python_route_environment_digest(runtime)

    task_records: list[dict[str, Any]] = []
    retrieval_records: list[dict[str, Any]] = []
    route_records: list[dict[str, Any]] = []
    recipe_records: list[dict[str, Any]] = []
    total_retrieval_cost = 0
    total_retrieved_candidates = 0
    total_wire_assessments = 0
    total_considered_candidates = 0
    successful_tasks = 0
    cache_hits = 0

    for task_index, task in enumerate(TASKS):
        steps: list[PrimitiveRouteStep] = []
        for step_index, (name, query) in enumerate(
            zip(task.names, task.queries, strict=True)
        ):
            retrieval = shortlister.execute(query, 4)
            nominations = tuple(item.primitive_id for item in retrieval.candidates)
            target = by_name[name]
            if target.primitive_id not in nominations:
                raise SystemExit(
                    f"retrieval did not nominate {name!r} for task {task.task_id!r}"
                )
            steps.append(
                PrimitiveRouteStep(
                    target.capability_group_ids[0],
                    nominations,
                    retrieval.query_digest,
                )
            )
            total_retrieval_cost += retrieval.consumed_cost_units
            total_retrieved_candidates += len(retrieval.candidates)
            retrieval_records.append(
                {
                    "task_id": task.task_id,
                    "step_index": step_index,
                    "target_name": name,
                    "target_rank": nominations.index(target.primitive_id) + 1,
                    "execution": retrieval.to_dict(),
                }
            )
        first = by_name[task.names[0]].interface.input_ports[0]
        last = by_name[task.names[-1]].interface.output_ports[0]
        request = PrimitiveRouteRequest.create(
            input_schema=first.schema,
            output_schema=last.schema,
            steps=steps,
            policy=policy,
            max_routes=4,
        )
        searched = planner.search(request)
        total_wire_assessments += searched.receipt.wire_assessment_count
        total_considered_candidates += searched.receipt.considered_candidate_count
        if not searched.routes:
            raise SystemExit(f"route search failed for {task.task_id!r}")
        selected = searched.routes[0]
        selected_names = tuple(
            catalog.by_primitive_id[item].name for item in selected.primitive_ids
        )
        if selected_names != task.names:
            raise SystemExit(
                f"route search selected {selected_names!r}, expected {task.names!r}"
            )
        execution = executor.execute(
            selected.plan,
            tuple(packs[item] for item in selected.primitive_ids),
            task.input_value,
        )
        if execution.output != task.expected_output:
            raise SystemExit(
                f"route output for {task.task_id!r} was {execution.output!r}"
            )
        recipe = recipes.record(
            route=selected,
            execution_receipt=execution.receipt,
            environment_digest=environment_digest,
            verifier_id="taedri.route-benchmark.v1",
            verified_at=VERIFIED_AT,
        )
        recipe_records.append(recipe.to_dict())

        reuse_steps = tuple(
            PrimitiveRouteStep(
                by_name[name].capability_group_ids[0],
                (),
                sha256_digest(f"reuse:{task.task_id}:{index}".encode()),
                True,
            )
            for index, name in enumerate(task.names)
        )
        reuse_request = PrimitiveRouteRequest.create(
            input_schema=first.schema,
            output_schema=last.schema,
            steps=reuse_steps,
            policy=policy,
            max_routes=1,
        )
        if request.identity.id == reuse_request.identity.id:
            raise SystemExit("recipe reuse request did not vary retrieval evidence")
        reused = planner.resolve(
            reuse_request,
            recipe_registry=recipes,
            environment_digest=environment_digest,
        )
        if (
            reused.routes != (selected,)
            or reused.receipt.source != "verified_recipe"
            or reused.receipt.considered_candidate_count
            or reused.receipt.wire_assessment_count
        ):
            raise SystemExit("verified recipe did not bypass route graph search")
        cache_hits += 1
        successful_tasks += 1
        task_records.append(
            {
                "task_id": task.task_id,
                "expected_names": list(task.names),
                "selected_names": list(selected_names),
                "stage_count": len(selected_names),
                "input_digest": execution.receipt.input_digest,
                "output_digest": execution.receipt.output_digest,
                "alternative_route_count": len(searched.routes) - 1,
                "search_source": searched.receipt.source,
                "search_considered_candidates": searched.receipt.considered_candidate_count,
                "search_wire_assessments": searched.receipt.wire_assessment_count,
                "route_id": selected.identity.id,
                "plan_id": selected.plan.identity.id,
                "execution_receipt_id": execution.receipt.identity.id,
                "recipe_id": recipe.identity.id,
                "reuse_request_id": reuse_request.identity.id,
                "reuse_receipt_id": reused.receipt.identity.id,
                "reuse_source": reused.receipt.source,
            }
        )
        route_records.append(
            {
                "task_id": task.task_id,
                "request": request.to_dict(),
                "search_receipt": searched.receipt.to_dict(),
                "routes": [_route_summary(item, catalog) for item in searched.routes],
                "reuse_receipt": reused.receipt.to_dict(),
            }
        )

    negative_records = _negative_cases(
        planner=planner,
        by_name=by_name,
        policy=policy,
    )
    if any(item["route_count"] != 0 for item in negative_records):
        raise SystemExit("a negative route case did not abstain")

    run_record = {
        "schema_version": "1.0.0",
        "status": "passed",
        "claim_scope": (
            "body-free deterministic retrieval nominations; ordered unary route "
            "contracts; exact schema/policy/wire checks; isolated execution; exact "
            "verified-recipe reuse on a 23-release checked fixture"
        ),
        "cohort_digest": sha256_digest((cohort / "run.json").read_bytes()),
        "released_catalog_digest": released.digest,
        "route_catalog_digest": catalog.digest,
        "retrieval_program_ref": shortlister.program.ref,
        "retrieval_program_digest": shortlister.program.digest,
        "environment_digest": environment_digest,
        "catalog_primitive_count": len(catalog.entries),
        "positive_task_count": len(TASKS),
        "successful_task_count": successful_tasks,
        "negative_task_count": len(negative_records),
        "negative_abstention_count": sum(
            int(item["route_count"] == 0) for item in negative_records
        ),
        "requested_stage_count": sum(len(item.names) for item in TASKS),
        "retrieval_execution_count": len(retrieval_records),
        "retrieved_candidate_count": total_retrieved_candidates,
        "retrieval_cost_units": total_retrieval_cost,
        "route_search_considered_candidate_count": total_considered_candidates,
        "route_search_wire_assessment_count": total_wire_assessments,
        "verified_recipe_count": len(recipe_records),
        "verified_recipe_cache_hit_count": cache_hits,
        "cache_hit_considered_candidate_count": 0,
        "cache_hit_wire_assessment_count": 0,
        "model_calls": 0,
        "semantic_calls": 0,
        "generated_route_code_bytes": 0,
        "tasks": task_records,
        "negative_cases": negative_records,
    }
    _write_artifacts(
        output,
        run_record,
        retrieval_records,
        route_records,
        recipe_records,
    )
    return run_record


def _negative_cases(
    *,
    planner: BoundedPrimitiveRoutePlanner,
    by_name: Mapping[str, PrimitiveRouteEntry],
    policy: PrimitiveRoutePolicy,
) -> list[dict[str, Any]]:
    normalize = by_name["normalize-text"]
    parse = by_name["parse-json-object"]
    coerce = by_name["coerce-finite-number"]
    requests = (
        (
            "unsupported_capability",
            PrimitiveRouteRequest.create(
                input_schema=normalize.interface.input_ports[0].schema,
                output_schema=normalize.interface.output_ports[0].schema,
                steps=(PrimitiveRouteStep("taedri.group.unsupported_capability"),),
                policy=policy,
            ),
        ),
        (
            "incompatible_output_schema",
            PrimitiveRouteRequest.create(
                input_schema=coerce.interface.input_ports[0].schema,
                output_schema={"type": "object"},
                steps=(
                    PrimitiveRouteStep(
                        coerce.capability_group_ids[0],
                        (coerce.primitive_id,),
                    ),
                ),
                policy=policy,
            ),
        ),
        (
            "wrong_retrieval_nomination",
            PrimitiveRouteRequest.create(
                input_schema=parse.interface.input_ports[0].schema,
                output_schema=parse.interface.output_ports[0].schema,
                steps=(
                    PrimitiveRouteStep(
                        parse.capability_group_ids[0],
                        (normalize.primitive_id,),
                    ),
                ),
                policy=policy,
            ),
        ),
    )
    records: list[dict[str, Any]] = []
    for case_id, request in requests:
        result = planner.search(request)
        records.append(
            {
                "case_id": case_id,
                "request_id": request.identity.id,
                "route_count": len(result.routes),
                "stop_reason": result.receipt.stop_reason,
                "receipt_id": result.receipt.identity.id,
                "considered_candidate_count": result.receipt.considered_candidate_count,
                "wire_assessment_count": result.receipt.wire_assessment_count,
            }
        )
    return records


def _route_summary(
    route: Any, catalog: PrimitiveRouteCatalog
) -> dict[str, Any]:
    return {
        "route_id": route.identity.id,
        "plan_id": route.plan.identity.id,
        "primitive_ids": list(route.primitive_ids),
        "primitive_names": [
            catalog.by_primitive_id[item].name for item in route.primitive_ids
        ],
        "pack_digests": list(route.pack_digests),
        "capability_group_ids": list(route.capability_group_ids),
        "retrieval_preference_penalty": route.retrieval_preference_penalty,
    }


def _write_artifacts(
    output: Path,
    run_record: Mapping[str, Any],
    retrieval_records: Sequence[Mapping[str, Any]],
    route_records: Sequence[Mapping[str, Any]],
    recipe_records: Sequence[Mapping[str, Any]],
) -> None:
    (output / "run.json").write_bytes(canonical_json_bytes(run_record) + b"\n")
    for name, records in (
        ("retrieval-executions.jsonl", retrieval_records),
        ("route-searches.jsonl", route_records),
        ("verified-recipes.jsonl", recipe_records),
    ):
        (output / name).write_bytes(
            b"".join(canonical_json_bytes(item) + b"\n" for item in records)
        )
    with (output / "tasks.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = (
            "task_id",
            "stage_count",
            "selected_names",
            "alternative_route_count",
            "search_considered_candidates",
            "search_wire_assessments",
            "route_id",
            "plan_id",
            "recipe_id",
            "reuse_source",
        )
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in run_record["tasks"]:
            row = {field: item[field] for field in fields}
            row["selected_names"] = " -> ".join(item["selected_names"])
            writer.writerow(row)
    (output / "README.md").write_text(_report(run_record), "utf-8")


def _report(run: Mapping[str, Any]) -> str:
    rows = "\n".join(
        f"| `{item['task_id']}` | {item['stage_count']} | "
        f"`{' → '.join(item['selected_names'])}` | {item['alternative_route_count']} |"
        for item in run["tasks"]
    )
    return f"""# Primitive route planner evidence

Status: **passed**

The checked benchmark translated {run['requested_stage_count']} operation intents into
body-free retrieval shortlists, found and executed {run['successful_task_count']} of
{run['positive_task_count']} expected compatible routes, and correctly abstained on all
{run['negative_abstention_count']} of {run['negative_task_count']} negative cases.

| Task | Stages | Selected route | Other valid routes |
|---|---:|---|---:|
{rows}

The first pass considered {run['route_search_considered_candidate_count']} candidates
and performed {run['route_search_wire_assessment_count']} authoritative adjacent-wire
assessments across a {run['catalog_primitive_count']}-release catalog. Every successful
route was executed from exact digest-bound packs with zero model calls and zero bytes of
generated glue code.

The resulting {run['verified_recipe_count']} exact recipes were then resolved again
under the same catalog and runtime environment. All
{run['verified_recipe_cache_hit_count']} lookups were cache hits and required zero
candidate expansions and zero wire assessments. A changed catalog or environment digest
is a cache miss.

This fixture proves bounded ordered unary route discovery and reuse. It does not yet
prove multi-input hypergraph planning, corpus-scale relevance, hostile-code isolation,
or correctness beyond each capsule's tests and the recorded route executions.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    result = run(cohort=arguments.cohort, output=arguments.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
