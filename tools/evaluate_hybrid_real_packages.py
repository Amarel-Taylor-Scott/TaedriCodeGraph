#!/usr/bin/env python3
"""Evaluate artifact ingestion and hybrid retrieval on real package bytes."""

from __future__ import annotations

import argparse
import csv
import gc
import json
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from benchmark_real_packages import (  # noqa: E402
    directory_size,
    graph_slice,
    safe_distribution_sources,
    write_graph_artifacts,
)
from taedri_codegraph.artifacts import analyze_wheel  # noqa: E402
from taedri_codegraph.sources import PolyglotInventoryAnalyzer  # noqa: E402
from taedri_codegraph.storage import GraphStore  # noqa: E402

RUN_DATE = "2026-07-15"
DEFAULT_OUTPUT = ROOT / "eval" / "results" / f"hybrid-architecture-{RUN_DATE}"
DEFAULT_STORE = Path(tempfile.gettempdir()) / f"taedri-hybrid-architecture-{RUN_DATE}"

QUERIES: dict[str, tuple[tuple[str, str], ...]] = {
    "usaddress": (
        ("parse a street address into labeled components", "usaddress.parse"),
        ("tag address components and determine address type", "usaddress.tag"),
        ("tokenize an address string", "usaddress.tokenize"),
    ),
    "requests": (
        ("send an HTTP GET request", "requests.api.get"),
        ("send a request with a persistent HTTP session", "requests.sessions.Session.request"),
        ("decode an HTTP response body as JSON", "requests.models.Response.json"),
    ),
    "pypdf": (
        ("read an existing PDF document", "pypdf._reader.PdfReader"),
        ("extract text from a PDF page", "pypdf._page.PageObject.extract_text"),
        ("write a PDF document to a stream", "pypdf._writer.PdfWriter.write"),
    ),
    "python-pptx": (
        ("open or create a PowerPoint presentation", "pptx.api.Presentation"),
        ("add a slide to a presentation", "pptx.slide.Slides.add_slide"),
        ("add a text box to a slide", "pptx.shapes.shapetree.SlideShapes.add_textbox"),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="*", type=Path)
    parser.add_argument("--inventory", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE)
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def evaluate_queries(index, package: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []
    hits = 0
    top1 = 0
    lane_profiles = {
        "hybrid": ("exact", "lexical", "blocking", "vector"),
        "lexical": ("exact", "lexical"),
        "blocking": ("blocking",),
        "vector": ("vector",),
    }
    queries = QUERIES.get(package, ())
    for query, expected in queries:
        for profile, lanes in lane_profiles.items():
            start = time.perf_counter()
            results = index.hybrid_search(query, lanes=lanes, limit=10, explain=True)
            elapsed_ms = (time.perf_counter() - start) * 1000
            rank = next(
                (
                    ordinal
                    for ordinal, item in enumerate(results, start=1)
                    if expected.casefold() == item["qualified_name"].casefold()
                ),
                None,
            )
            rows.append(
                {
                    "package": package,
                    "query": query,
                    "expected": expected,
                    "profile": profile,
                    "hit_rank": rank,
                    "latency_ms": round(elapsed_ms, 4),
                    "top_result": results[0]["qualified_name"] if results else None,
                    "top_result_lanes": ",".join(results[0].get("lane_ranks", {})) if results else "",
                }
            )
            if profile == "hybrid":
                latencies.append(elapsed_ms)
                reciprocal_ranks.append(1 / rank if rank else 0.0)
                hits += int(rank is not None)
                top1 += int(rank == 1)
    count = len(queries)
    metrics = {
        "query_count": count,
        "recall_at_10": round(hits / count, 4) if count else None,
        "mrr_at_10": round(statistics.mean(reciprocal_ranks), 4) if reciprocal_ranks else None,
        "top1_accuracy": round(top1 / count, 4) if count else None,
        "hybrid_latency_p50_ms": round(percentile(latencies, 0.5), 4),
        "hybrid_latency_p95_ms": round(percentile(latencies, 0.95), 4),
    }
    return rows, metrics


def run_artifact(path: Path, output: Path, store_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    analysis_start = time.perf_counter()
    bundle, inspection = analyze_wheel(path)
    analysis_seconds = time.perf_counter() - analysis_start
    package = inspection.distribution_name.lower().replace("_", "-")
    store_path = store_root / f"{package}-{inspection.version}"
    shutil.rmtree(store_path, ignore_errors=True)
    store = GraphStore(store_path)
    store_start = time.perf_counter()
    epoch_id = store.write_candidate(bundle)
    store.publish_epoch(epoch_id)
    store_seconds = time.perf_counter() - store_start
    index = store.index()
    query_rows, query_metrics = evaluate_queries(index, package)
    epoch_path = store.published / epoch_id
    fact_bytes = directory_size(epoch_path, lambda item: item.suffix in {".json", ".jsonl"})
    index_bytes = (epoch_path / "index.sqlite").stat().st_size
    graph_base = output / "graphs" / f"{package}-{inspection.version}-slice"
    write_graph_artifacts(graph_slice(bundle), graph_base)
    license_assertions = sum(
        1
        for assertion in bundle.representation_assertions.values()
        if bundle.representation_contents[assertion.content_id].family_key == "uceg.family.license"
    )
    result = {
        "run_date": RUN_DATE,
        "mode": "full-wheel-ast-hybrid",
        "package": package,
        "version": inspection.version,
        "artifact_digest": inspection.artifact_digest,
        "artifact_bytes": inspection.artifact_size_bytes,
        "archive_members": inspection.archive_members,
        "python_files": inspection.python_sources,
        "import_roots": list(inspection.import_roots),
        "record_entries": inspection.record_entries,
        "record_hashes_verified": inspection.record_hashes_verified,
        "license_assertions": license_assertions,
        "analysis_seconds": round(analysis_seconds, 4),
        "store_seconds": round(store_seconds, 4),
        "fact_bytes": fact_bytes,
        "index_bytes": index_bytes,
        "epoch_id": epoch_id,
        **{key: value for key, value in bundle.summary().items() if isinstance(value, int)},
        **query_metrics,
    }
    del bundle, index
    gc.collect()
    return result, query_rows


def run_inventory(name: str, output: Path, store_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"taedri-inventory-{name}-") as temporary:
        acquisition = safe_distribution_sources(name, Path(temporary))
        analyzer = PolyglotInventoryAnalyzer()
        start = time.perf_counter()
        bundle = analyzer.analyze(
            Path(temporary),
            package_name=acquisition["normalized_name"],
            release=acquisition["version"],
            source_uri=f"installed-distribution:{acquisition['normalized_name']}@{acquisition['version']}",
        )
        analysis_seconds = time.perf_counter() - start
        store_path = store_root / f"inventory-{name}-{acquisition['version']}"
        shutil.rmtree(store_path, ignore_errors=True)
        store = GraphStore(store_path)
        store_start = time.perf_counter()
        epoch_id = store.write_candidate(bundle)
        store.publish_epoch(epoch_id)
        store_seconds = time.perf_counter() - store_start
        epoch_path = store.published / epoch_id
        result = {
            "run_date": RUN_DATE,
            "mode": "polyglot-inventory-only",
            "package": acquisition["normalized_name"],
            "version": acquisition["version"],
            "python_files": acquisition["file_count"],
            "source_bytes": acquisition["source_bytes"],
            "analysis_seconds": round(analysis_seconds, 4),
            "store_seconds": round(store_seconds, 4),
            "fact_bytes": directory_size(epoch_path, lambda item: item.suffix in {".json", ".jsonl"}),
            "index_bytes": (epoch_path / "index.sqlite").stat().st_size,
            "epoch_id": epoch_id,
            **{key: value for key, value in bundle.summary().items() if isinstance(value, int)},
            "query_count": 0,
            "recall_at_10": None,
            "mrr_at_10": None,
            "top1_accuracy": None,
            "hybrid_latency_p50_ms": None,
            "hybrid_latency_p95_ms": None,
        }
        write_graph_artifacts(
            graph_slice(bundle),
            output / "graphs" / f"{acquisition['normalized_name']}-{acquisition['version']}-inventory-slice",
        )
    del bundle
    gc.collect()
    return result


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def write_charts(output: Path, results: list[dict[str, Any]]) -> None:
    import matplotlib.pyplot as plt

    assets = output / "charts"
    assets.mkdir(parents=True, exist_ok=True)
    full = [row for row in results if row["mode"] == "full-wheel-ast-hybrid"]
    labels = [f"{row['package']}\n{row['version']}" for row in full]
    if full:
        figure, axis = plt.subplots(figsize=(9, 5.2))
        x = list(range(len(full)))
        width = 0.25
        for offset, key, label in (
            (-width, "entities", "Entities"),
            (0, "relations", "Relations"),
            (width, "representation_assertions", "Representation assertions"),
        ):
            axis.bar([item + offset for item in x], [row[key] for row in full], width, label=label)
        axis.set_yscale("log")
        axis.set_ylabel("Records (log scale)")
        axis.set_xticks(x, labels)
        axis.set_title("Real-wheel graph and representation growth")
        axis.legend(frameon=False)
        axis.grid(axis="y", alpha=0.2)
        figure.tight_layout()
        figure.savefig(assets / "record-growth.svg", format="svg")
        figure.savefig(assets / "record-growth.png", dpi=160)
        plt.close(figure)

        figure, axis = plt.subplots(figsize=(9, 5.2))
        quality_x = list(range(len(full)))
        quality_width = 0.36
        axis.bar(
            [item - quality_width / 2 for item in quality_x],
            [row["recall_at_10"] * 100 for row in full],
            quality_width,
            label="Recall@10",
        )
        axis.bar(
            [item + quality_width / 2 for item in quality_x],
            [row["mrr_at_10"] * 100 for row in full],
            quality_width,
            label="MRR@10",
        )
        axis.set_xticks(quality_x, labels)
        axis.set_ylim(0, 105)
        axis.set_ylabel("Percent")
        axis.set_title("Natural-language retrieval quality on declared target queries")
        axis.legend(frameon=False)
        axis.grid(axis="y", alpha=0.2)
        figure.tight_layout()
        figure.savefig(assets / "retrieval-quality.svg", format="svg")
        figure.savefig(assets / "retrieval-quality.png", dpi=160)
        plt.close(figure)

    figure, axis = plt.subplots(figsize=(10, 5.4))
    all_labels = [f"{row['package']}\n{row['mode'].split('-')[0]}" for row in results]
    axis.bar(all_labels, [(row["fact_bytes"] + row["index_bytes"]) / 1024 / 1024 for row in results])
    axis.set_ylabel("MiB")
    axis.set_title("Canonical facts plus disposable SQLite projection")
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(assets / "storage-footprint.svg", format="svg")
    figure.savefig(assets / "storage-footprint.png", dpi=160)
    plt.close(figure)


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.store_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []
    for artifact in args.artifacts:
        result, rows = run_artifact(artifact, args.output_dir, args.store_root)
        results.append(result)
        queries.extend(rows)
        print(json.dumps({"completed": artifact.name, **result}, sort_keys=True), flush=True)
    for name in args.inventory:
        result = run_inventory(name, args.output_dir, args.store_root)
        results.append(result)
        print(json.dumps({"completed": name, **result}, sort_keys=True), flush=True)
    (args.output_dir / "package-results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "query-results.json").write_text(
        json.dumps(queries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_csv(args.output_dir / "package-results.csv", results)
    write_csv(args.output_dir / "query-results.csv", queries)
    write_charts(args.output_dir, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
