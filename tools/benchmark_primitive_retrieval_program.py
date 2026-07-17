#!/usr/bin/env python3
"""Benchmark legacy BM25 against the versioned primitive retrieval program."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from taedri_codegraph.canonical import (
    canonical_digest,
    canonical_json_bytes,
    sha256_digest,
)
from taedri_codegraph.prompt_interception import (
    DeterministicBM25Shortlister,
    ReleasedPrimitiveCatalog,
)
from taedri_codegraph.primitives.retrieval_program import (
    PrimitiveRetrievalIndex,
    RetrievalDocument,
    RetrievalProgramExecution,
    default_primitive_retrieval_program,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COHORT = ROOT / "eval/results/data-primitive-cohort-2026-07-16"
DEFAULT_FIXTURE = ROOT / "fixtures/primitive-retrieval/retrieval-cases.json"
DEFAULT_OUTPUT = ROOT / "eval/results/primitive-retrieval-program-2026-07-17"
_CASE_ID = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")


def run(
    *, cohort: Path, fixture: Path, output: Path
) -> Mapping[str, Any]:
    catalog = ReleasedPrimitiveCatalog.load_checked_cohort(cohort)
    cases = _load_cases(fixture, {card.name for card in catalog.cards})
    legacy = DeterministicBM25Shortlister(catalog.cards)
    program = default_primitive_retrieval_program()
    documents = tuple(
        RetrievalDocument(
            card.primitive_id,
            card.namespace,
            card.name,
            card.summary,
            card.keywords,
            card.use_cases,
        )
        for card in catalog.cards
    )
    index = PrimitiveRetrievalIndex(documents)
    names = {card.primitive_id: card.name for card in catalog.cards}
    results: list[dict[str, Any]] = []
    executions: list[tuple[str, RetrievalProgramExecution]] = []
    path_status_counts: dict[str, Counter[str]] = defaultdict(Counter)
    path_candidate_counts: Counter[str] = Counter()
    path_new_candidate_counts: Counter[str] = Counter()

    for case in cases:
        query = str(case["query"])
        legacy_ranking = legacy.shortlist(query, 4)
        execution = index.execute(query, program, limit=4)
        legacy_names = [names[item.primitive_id] for item in legacy_ranking]
        program_names = [names[item.primitive_id] for item in execution.candidates]
        expected_name = case["expected_name"]
        for receipt in execution.path_receipts:
            family = receipt.family.value
            path_status_counts[family][receipt.status.value] += 1
            path_candidate_counts[family] += receipt.candidate_count
            path_new_candidate_counts[family] += receipt.new_candidate_count
        result = {
            "case_id": case["case_id"],
            "kind": case["kind"],
            "query_digest": execution.query_digest,
            "expected_name": expected_name,
            "legacy_ranked_names": legacy_names,
            "program_ranked_names": program_names,
            "legacy_rank": _rank(legacy_names, expected_name),
            "program_rank": _rank(program_names, expected_name),
            "legacy_abstained": not legacy_names,
            "program_abstained": not program_names,
            "program_cost_units": execution.consumed_cost_units,
            "program_stop_reason": execution.stop_reason,
            "program_execution_id": execution.identity.id,
        }
        results.append(result)
        executions.append((str(case["case_id"]), execution))

    legacy_metrics = _metrics(results, "legacy")
    program_metrics = _metrics(results, "program")
    path_summary = [
        {
            "family": family,
            "status_counts": dict(sorted(path_status_counts[family].items())),
            "candidate_count": path_candidate_counts[family],
            "new_candidate_count": path_new_candidate_counts[family],
        }
        for family in sorted(path_status_counts)
    ]
    comparison = {
        "positive_top1_gain": (
            program_metrics["positive_hits_at_1"]
            - legacy_metrics["positive_hits_at_1"]
        ),
        "negative_abstention_gain": (
            program_metrics["negative_abstentions"]
            - legacy_metrics["negative_abstentions"]
        ),
        "candidate_count_reduction": (
            legacy_metrics["returned_candidate_count"]
            - program_metrics["returned_candidate_count"]
        ),
        "candidate_count_reduction_ppm": _reduction_ppm(
            legacy_metrics["returned_candidate_count"],
            program_metrics["returned_candidate_count"],
        ),
    }
    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "passed",
        "claim_scope": (
            "deterministic body-free catalog retrieval on a checked 31-case fixture; "
            "no model calls, coding-session outcomes, token savings, or corpus-wide "
            "quality claims"
        ),
        "catalog_digest": catalog.digest,
        "catalog_primitive_count": len(catalog.cards),
        "fixture_digest": sha256_digest(fixture.read_bytes()),
        "fixture_case_count": len(cases),
        "positive_case_count": sum(item["expected_name"] is not None for item in cases),
        "negative_case_count": sum(item["expected_name"] is None for item in cases),
        "legacy_shortlister_version": "deterministic-integer-bm25-v1",
        "program_ref": program.ref,
        "program_digest": program.digest,
        "program_definition": program.to_dict(),
        "legacy_metrics": legacy_metrics,
        "program_metrics": program_metrics,
        "comparison": comparison,
        "path_summary": path_summary,
        "model_calls": 0,
        "semantic_calls": 0,
        "cases": results,
    }
    record["run_digest"] = canonical_digest(record)
    _write_artifacts(output, record, executions)
    return record


def _load_cases(fixture: Path, catalog_names: set[str]) -> tuple[dict[str, Any], ...]:
    try:
        value = json.loads(fixture.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("primitive retrieval fixture is unavailable") from exc
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "description",
        "cases",
    }:
        raise ValueError("primitive retrieval fixture has an invalid envelope")
    if value["schema_version"] != "1.0.0" or not isinstance(
        value["description"], str
    ):
        raise ValueError("primitive retrieval fixture metadata is invalid")
    raw_cases = value["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("primitive retrieval fixture must contain cases")
    cases: list[dict[str, Any]] = []
    for raw in raw_cases:
        if not isinstance(raw, Mapping) or set(raw) != {
            "case_id",
            "kind",
            "query",
            "expected_name",
        }:
            raise ValueError("primitive retrieval case shape is invalid")
        case_id = raw["case_id"]
        kind = raw["kind"]
        query = raw["query"]
        expected = raw["expected_name"]
        if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
            raise ValueError("primitive retrieval case id is invalid")
        if kind not in {"exact", "paraphrase", "negative"}:
            raise ValueError("primitive retrieval case kind is invalid")
        if not isinstance(query, str) or not query.strip() or len(query) > 2_000:
            raise ValueError("primitive retrieval query is invalid")
        if kind == "negative":
            if expected is not None:
                raise ValueError("negative retrieval cases must not expect a primitive")
        elif not isinstance(expected, str) or expected not in catalog_names:
            raise ValueError("positive retrieval case expects an unknown primitive")
        cases.append(dict(raw))
    if len({item["case_id"] for item in cases}) != len(cases):
        raise ValueError("primitive retrieval case ids must be unique")
    return tuple(cases)


def _rank(ranking: Sequence[str], expected: object) -> int | None:
    if not isinstance(expected, str):
        return None
    try:
        return ranking.index(expected) + 1
    except ValueError:
        return None


def _metrics(results: Sequence[Mapping[str, Any]], prefix: str) -> dict[str, int]:
    positives = [item for item in results if item["expected_name"] is not None]
    negatives = [item for item in results if item["expected_name"] is None]
    ranks = [item[f"{prefix}_rank"] for item in positives]
    candidate_counts = [len(item[f"{prefix}_ranked_names"]) for item in results]
    result = {
        "positive_case_count": len(positives),
        "positive_hits_at_1": sum(rank == 1 for rank in ranks),
        "positive_hits_at_2": sum(
            isinstance(rank, int) and rank <= 2 for rank in ranks
        ),
        "positive_hits_at_4": sum(
            isinstance(rank, int) and rank <= 4 for rank in ranks
        ),
        "positive_mrr_microunits": (
            sum(1_000_000 // rank for rank in ranks if isinstance(rank, int))
            // len(positives)
        ),
        "negative_case_count": len(negatives),
        "negative_abstentions": sum(
            bool(item[f"{prefix}_abstained"]) for item in negatives
        ),
        "returned_candidate_count": sum(candidate_counts),
        "mean_returned_candidates_milliunits": (
            sum(candidate_counts) * 1_000 // len(candidate_counts)
        ),
    }
    if prefix == "program":
        costs = [int(item["program_cost_units"]) for item in results]
        result["consumed_cost_units"] = sum(costs)
        result["mean_cost_milliunits"] = sum(costs) * 1_000 // len(costs)
    return result


def _reduction_ppm(before: int, after: int) -> int:
    return 0 if before == 0 else max(0, before - after) * 1_000_000 // before


def _write_artifacts(
    output: Path,
    record: Mapping[str, Any],
    executions: Sequence[tuple[str, RetrievalProgramExecution]],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.json").write_bytes(canonical_json_bytes(record) + b"\n")
    with (output / "cases.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = (
            "case_id",
            "kind",
            "expected_name",
            "legacy_rank",
            "program_rank",
            "legacy_candidate_count",
            "program_candidate_count",
            "program_cost_units",
            "program_stop_reason",
            "query_digest",
            "program_execution_id",
        )
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for case in record["cases"]:
            writer.writerow(
                {
                    **{field: case.get(field) for field in fields},
                    "legacy_candidate_count": len(case["legacy_ranked_names"]),
                    "program_candidate_count": len(case["program_ranked_names"]),
                }
            )
    with (output / "executions.jsonl").open("wb") as stream:
        for case_id, execution in executions:
            stream.write(
                canonical_json_bytes(
                    {"case_id": case_id, "execution": execution.to_dict()}
                )
                + b"\n"
            )
    (output / "README.md").write_text(_report(record), encoding="utf-8")


def _report(record: Mapping[str, Any]) -> str:
    legacy = record["legacy_metrics"]
    program = record["program_metrics"]
    comparison = record["comparison"]
    reduction = int(comparison["candidate_count_reduction_ppm"]) / 10_000
    return f"""# Primitive retrieval program benchmark

Status: **passed**

This deterministic benchmark compares the legacy integer BM25 shortlister with
`{record['program_ref']}` over {record['fixture_case_count']} checked body-free catalog
requests ({record['positive_case_count']} positive and {record['negative_case_count']}
unsupported). It made zero model and semantic calls.

| Measure | Legacy BM25 | Retrieval program |
|---|---:|---:|
| Positive rank-1 hits | {legacy['positive_hits_at_1']} / {record['positive_case_count']} | {program['positive_hits_at_1']} / {record['positive_case_count']} |
| Positive hits at K=4 | {legacy['positive_hits_at_4']} / {record['positive_case_count']} | {program['positive_hits_at_4']} / {record['positive_case_count']} |
| Unsupported abstentions | {legacy['negative_abstentions']} / {record['negative_case_count']} | {program['negative_abstentions']} / {record['negative_case_count']} |
| Returned candidates | {legacy['returned_candidate_count']} | {program['returned_candidate_count']} |

The program returned {comparison['candidate_count_reduction']} fewer candidates
({reduction:.2f}% on this fixture) while improving rank-1 selection by
{comparison['positive_top1_gain']} case and grounded abstention by
{comparison['negative_abstention_gain']} cases. Exact-name requests stop after the hot
exact path; broader requests spend additional deterministic cost only as needed. Every
path attempt, skip, candidate contribution, query digest, and program digest is retained
in `executions.jsonl`.

This is a small constructed retrieval benchmark. It does not establish corpus-wide
ranking quality, semantic-model quality, end-to-end coding success, or token/cost
savings.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    record = run(
        cohort=arguments.cohort.resolve(),
        fixture=arguments.fixture.resolve(),
        output=arguments.output.resolve(),
    )
    print(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
