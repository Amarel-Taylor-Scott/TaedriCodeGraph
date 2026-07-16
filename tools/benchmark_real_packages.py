#!/usr/bin/env python3
"""Run Taedri end to end on real installed PyPI distributions.

The parent process starts one isolated worker per distribution so peak RSS and failures
are package-specific. Workers copy only distribution-owned Python source bytes into a
temporary immutable input tree; they never import or execute the target package.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from taedri_codegraph import __version__  # noqa: E402
from taedri_codegraph.analyzers import PythonSyntaxAnalyzer  # noqa: E402
from taedri_codegraph.canonical import sha256_digest  # noqa: E402
from taedri_codegraph.contracts import GraphBundle  # noqa: E402
from taedri_codegraph.storage import GraphStore  # noqa: E402

RUN_DATE = "2026-07-15"
DEFAULT_PACKAGES = ("wheel", "packaging", "pydantic")
MEANINGFUL_PREDICATES = {
    "uceg.predicate.calls_may",
    "uceg.predicate.reads",
    "uceg.predicate.writes",
    "uceg.predicate.imports",
    "uceg.predicate.extends",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="*", default=list(DEFAULT_PACKAGES))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "eval" / "results" / f"real-pypi-{RUN_DATE}",
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=Path(tempfile.gettempdir()) / f"taedri-real-pypi-{RUN_DATE}",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "reports" / f"REAL_PYPI_BENCHMARK_{RUN_DATE}.md",
    )
    parser.add_argument("--no-charts", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-package", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def safe_distribution_sources(name: str, destination: Path) -> dict[str, Any]:
    """Materialize distribution-owned `.py` bytes without importing the package."""

    try:
        installed = distribution(name)
    except PackageNotFoundError as exc:
        raise RuntimeError(f"distribution is not installed: {name}") from exc
    copied: list[dict[str, Any]] = []
    for entry in sorted(installed.files or (), key=str):
        relative = Path(str(entry))
        if relative.suffix != ".py" or relative.is_absolute() or ".." in relative.parts:
            continue
        source = Path(installed.locate_file(entry))
        if not source.is_file() or source.is_symlink():
            continue
        content = source.read_bytes()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        copied.append(
            {
                "relative_path": relative.as_posix(),
                "size_bytes": len(content),
                "sha256": sha256_digest(content),
            }
        )
    if not copied:
        raise RuntimeError(f"distribution has no materializable Python source: {name}")
    return {
        "distribution": installed.metadata.get("Name") or name,
        "normalized_name": name.lower().replace("_", "-"),
        "version": installed.version,
        "files": copied,
        "file_count": len(copied),
        "source_bytes": sum(item["size_bytes"] for item in copied),
    }


def directory_size(path: Path, predicate=lambda _: True) -> int:
    if not path.exists():
        return 0
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file() and predicate(item)
    )


def graph_slice(bundle: GraphBundle, limit: int = 24) -> dict[str, Any]:
    degree: Counter[str] = Counter()
    candidates: list[tuple[Any, list[str]]] = []
    for relation in bundle.relations.values():
        if relation.predicate_key not in MEANINGFUL_PREDICATES:
            continue
        entity_ids = [
            item.subject.id
            for item in relation.participants
            if item.subject.subject_kind == "entity"
        ]
        if len(entity_ids) < 2:
            continue
        candidates.append((relation, entity_ids))
        degree.update(entity_ids)
    eligible = [
        (count, entity_id)
        for entity_id, count in degree.items()
        if entity_id in bundle.entities
        and not bundle.entities[entity_id].entity_kind_key.endswith(
            (".module", ".file", ".external_symbol", ".variable", ".parameter")
        )
    ]
    if not eligible:
        eligible = [(count, entity_id) for entity_id, count in degree.items()]
    root_id = max(eligible, default=(0, next(iter(bundle.entities))))[1]
    selected_relations = [
        (relation, entity_ids)
        for relation, entity_ids in candidates
        if root_id in entity_ids
    ][:limit]
    node_ids = {root_id}
    for _, entity_ids in selected_relations:
        node_ids.update(entity_ids[:2])
    nodes = [
        {
            "id": entity_id,
            "qualified_name": bundle.entities[entity_id].qualified_name,
            "entity_kind": bundle.entities[entity_id].entity_kind_key,
            "lifecycle": bundle.entities[entity_id].lifecycle.value,
            "root": entity_id == root_id,
        }
        for entity_id in sorted(node_ids)
        if entity_id in bundle.entities
    ]
    edges = []
    for relation, entity_ids in selected_relations:
        edges.append(
            {
                "assertion_id": relation.edge_assertion_id,
                "predicate": relation.predicate_key,
                "source": entity_ids[0],
                "target": entity_ids[1],
                "modality": relation.modality.value,
                "quantifier": relation.quantifier.value,
                "evidence_ids": list(relation.evidence_ids),
            }
        )
    return {
        "snapshot_id": bundle.snapshot.identity.id,
        "analysis_manifest_id": bundle.analysis.identity.id,
        "root_entity_id": root_id,
        "nodes": nodes,
        "edges": edges,
        "truncated": len(selected_relations) == limit,
    }


def write_graph_artifacts(slice_data: dict[str, Any], base: Path) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    artifact = lambda suffix: base.parent / f"{base.name}{suffix}"
    artifact(".json").write_text(
        json.dumps(slice_data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    node_labels = {node["id"]: node for node in slice_data["nodes"]}
    aliases = {entity_id: f"n{index}" for index, entity_id in enumerate(node_labels)}
    mermaid = ["flowchart TD"]
    for entity_id, node in node_labels.items():
        label = node["qualified_name"].replace('"', "'")
        mermaid.append(f'    {aliases[entity_id]}["{label}"]')
    for edge in slice_data["edges"]:
        if edge["source"] not in aliases or edge["target"] not in aliases:
            continue
        predicate = edge["predicate"].removeprefix("uceg.predicate.")
        mermaid.append(
            f"    {aliases[edge['source']]} -->|{predicate}| {aliases[edge['target']]}"
        )
    artifact(".mmd").write_text("\n".join(mermaid) + "\n", encoding="utf-8")

    graphml = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    for key_id, target, name in (
        ("qualified_name", "node", "qualified_name"),
        ("entity_kind", "node", "entity_kind"),
        ("predicate", "edge", "predicate"),
        ("assertion_id", "edge", "assertion_id"),
    ):
        ET.SubElement(
            graphml,
            "key",
            id=key_id,
            **{"for": target, "attr.name": name, "attr.type": "string"},
        )
    graph = ET.SubElement(graphml, "graph", edgedefault="directed")
    for entity_id, node in node_labels.items():
        element = ET.SubElement(graph, "node", id=entity_id)
        ET.SubElement(element, "data", key="qualified_name").text = node["qualified_name"]
        ET.SubElement(element, "data", key="entity_kind").text = node["entity_kind"]
    for index, edge in enumerate(slice_data["edges"]):
        element = ET.SubElement(
            graph,
            "edge",
            id=f"e{index}",
            source=edge["source"],
            target=edge["target"],
        )
        ET.SubElement(element, "data", key="predicate").text = edge["predicate"]
        ET.SubElement(element, "data", key="assertion_id").text = edge["assertion_id"]
    ET.ElementTree(graphml).write(artifact(".graphml"), encoding="utf-8", xml_declaration=True)


def run_worker(package: str, output_dir: Path, store_root: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"tcg-{package}-source-") as temporary:
        source_root = Path(temporary)
        acquisition = safe_distribution_sources(package, source_root)
        store_path = store_root / f"{acquisition['normalized_name']}-{acquisition['version']}"
        shutil.rmtree(store_path, ignore_errors=True)
        analyzer = PythonSyntaxAnalyzer()

        analysis_start = time.perf_counter()
        bundle = analyzer.analyze(
            source_root,
            package_name=acquisition["normalized_name"],
            release=acquisition["version"],
        )
        analysis_seconds = time.perf_counter() - analysis_start

        store = GraphStore(store_path)
        candidate_start = time.perf_counter()
        epoch_id = store.write_candidate(bundle, analyzer.registry)
        candidate_seconds = time.perf_counter() - candidate_start
        publish_start = time.perf_counter()
        store.publish_epoch(epoch_id)
        publish_seconds = time.perf_counter() - publish_start

        epoch_path = store.published / epoch_id
        coverage = next(iter(bundle.coverage.values()))
        predicates = Counter(edge.predicate_key for edge in bundle.relations.values())
        summary = bundle.summary()
        slice_data = graph_slice(bundle)
        slug = f"{acquisition['normalized_name']}-{acquisition['version']}"
        write_graph_artifacts(slice_data, output_dir / "graphs" / f"{slug}-slice")

        fact_bytes = directory_size(
            epoch_path,
            lambda item: item.suffix in {".jsonl", ".json"},
        )
        index_bytes = (epoch_path / "index.sqlite").stat().st_size
        cas_bytes = directory_size(store.cas)
        result = {
            "run_date": RUN_DATE,
            "distribution": acquisition["distribution"],
            "normalized_name": acquisition["normalized_name"],
            "version": acquisition["version"],
            "distribution_python_files": acquisition["file_count"],
            "source_bytes": acquisition["source_bytes"],
            "snapshot_id": bundle.snapshot.identity.id,
            "analysis_manifest_id": bundle.analysis.identity.id,
            "epoch_id": epoch_id,
            **{key: value for key, value in summary.items() if isinstance(value, int)},
            "coverage_state": coverage.completeness_state.value,
            "coverage_attempted_files": coverage.attempted_inputs,
            "coverage_successful_files": coverage.successful_inputs,
            "coverage_unresolved_files": coverage.unresolved_inputs,
            "analysis_seconds": round(analysis_seconds, 6),
            "candidate_and_index_seconds": round(candidate_seconds, 6),
            "publish_seconds": round(publish_seconds, 6),
            "total_seconds": round(
                analysis_seconds + candidate_seconds + publish_seconds, 6
            ),
            "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "fact_bytes": fact_bytes,
            "index_bytes": index_bytes,
            "cas_bytes": cas_bytes,
            "total_store_bytes": fact_bytes + index_bytes + cas_bytes,
            "entities_per_source_kib": round(
                len(bundle.entities) / max(acquisition["source_bytes"] / 1024, 1), 6
            ),
            "relations_per_second": round(
                len(bundle.relations) / max(analysis_seconds, 1e-9), 6
            ),
            "index_bytes_per_relation": round(
                index_bytes / max(len(bundle.relations), 1), 6
            ),
            "predicate_counts": dict(sorted(predicates.items())),
            "graph_slice": f"graphs/{slug}-slice.json",
        }
        result_path = output_dir / "packages" / f"{slug}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"completed": slug, "epoch_id": epoch_id, "counts": summary}))
        return result


def normalize_generated_text(path: Path) -> None:
    """Keep generated text artifacts stable and diff-check clean."""

    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def render_charts(results: list[dict[str, Any]], assets: Path) -> list[Path]:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib-tcg"))
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("charts require `pip install -e '.[research]'`") from exc
    assets.mkdir(parents=True, exist_ok=True)
    labels = [f"{row['normalized_name']}\n{row['version']}" for row in results]
    style = {
        "figure.facecolor": "#0b1220",
        "axes.facecolor": "#0b1220",
        "axes.edgecolor": "#64748b",
        "axes.labelcolor": "#e2e8f0",
        "xtick.color": "#cbd5e1",
        "ytick.color": "#cbd5e1",
        "text.color": "#f8fafc",
        "grid.color": "#334155",
        "font.size": 10,
    }
    paths: list[Path] = []
    with plt.rc_context(style):
        x = np.arange(len(results))
        width = 0.25
        fig, ax = plt.subplots(figsize=(10, 5.4), constrained_layout=True)
        for offset, field, label, color in (
            (-width, "entities", "Entities", "#38bdf8"),
            (0, "occurrences", "Occurrences", "#a78bfa"),
            (width, "relations", "Relations", "#fb7185"),
        ):
            ax.bar(x + offset, [row[field] for row in results], width, label=label, color=color)
        ax.set_yscale("log")
        ax.set_xticks(x, labels)
        ax.set_ylabel("Records (log scale)")
        ax.set_title("UCEG fact expansion on real PyPI distributions", loc="left", weight="bold")
        ax.grid(axis="y", alpha=0.35)
        ax.legend(frameon=False, ncols=3)
        path = assets / "real_pypi_record_counts.svg"
        fig.savefig(path, format="svg")
        plt.close(fig)
        normalize_generated_text(path)
        paths.append(path)

        fig, ax = plt.subplots(figsize=(10, 5.4), constrained_layout=True)
        bottoms = np.zeros(len(results))
        for field, label, color in (
            ("analysis_seconds", "Analyze + validate", "#38bdf8"),
            ("candidate_and_index_seconds", "Write facts + build index", "#fbbf24"),
            ("publish_seconds", "Validate + publish", "#34d399"),
        ):
            values = np.array([row[field] for row in results])
            ax.bar(x, values, bottom=bottoms, label=label, color=color)
            bottoms += values
        ax.set_xticks(x, labels)
        ax.set_ylabel("Wall-clock seconds")
        ax.set_title("End-to-end phase time", loc="left", weight="bold")
        ax.grid(axis="y", alpha=0.35)
        ax.legend(frameon=False)
        path = assets / "real_pypi_phase_times.svg"
        fig.savefig(path, format="svg")
        plt.close(fig)
        normalize_generated_text(path)
        paths.append(path)

        fig, ax = plt.subplots(figsize=(10, 5.4), constrained_layout=True)
        bottoms = np.zeros(len(results))
        for field, label, color in (
            ("fact_bytes", "Immutable JSONL facts", "#a78bfa"),
            ("index_bytes", "SQLite FTS + adjacency", "#fb7185"),
            ("cas_bytes", "Source CAS", "#34d399"),
        ):
            values = np.array([row[field] / (1024 * 1024) for row in results])
            ax.bar(x, values, bottom=bottoms, label=label, color=color)
            bottoms += values
        ax.set_xticks(x, labels)
        ax.set_ylabel("MiB")
        ax.set_title("Published epoch storage footprint", loc="left", weight="bold")
        ax.grid(axis="y", alpha=0.35)
        ax.legend(frameon=False)
        path = assets / "real_pypi_storage_footprint.svg"
        fig.savefig(path, format="svg")
        plt.close(fig)
        normalize_generated_text(path)
        paths.append(path)
    return paths


def csv_text(results: list[dict[str, Any]], fields: list[str]) -> str:
    from io import StringIO

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(results)
    return output.getvalue()


def mermaid_block(path: Path, max_lines: int = 45) -> str:
    lines = path.read_text("utf-8").splitlines()[:max_lines]
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def write_report(
    results: list[dict[str, Any]],
    output_dir: Path,
    report_path: Path,
    chart_paths: list[Path],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    relative_results = os.path.relpath(output_dir, report_path.parent).replace(os.sep, "/")
    table_rows = []
    for row in results:
        table_rows.append(
            "| {name} | {version} | {files:,} | {source:.2f} | {entities:,} | "
            "{occurrences:,} | {relations:,} | {seconds:.1f} | {rss:.1f} | "
            "{store:.1f} | {coverage} |".format(
                name=row["distribution"],
                version=row["version"],
                files=row["distribution_python_files"],
                source=row["source_bytes"] / (1024 * 1024),
                entities=row["entities"],
                occurrences=row["occurrences"],
                relations=row["relations"],
                seconds=row["total_seconds"],
                rss=row["max_rss_kb"] / 1024,
                store=row["total_store_bytes"] / (1024 * 1024),
                coverage=row["coverage_state"],
            )
        )
    largest = max(results, key=lambda item: item["relations"])
    index_share = largest["index_bytes"] / largest["total_store_bytes"] * 100
    chart_markdown = "\n\n".join(
        f"![{path.stem}]({os.path.relpath(path, report_path.parent).replace(os.sep, '/')})"
        for path in chart_paths
    )
    graph_slug = f"{largest['normalized_name']}-{largest['version']}-slice"
    graph_path = output_dir / "graphs" / f"{graph_slug}.mmd"
    package_word = "distribution" if len(results) == 1 else "distributions"
    report = f"""# Taedri CodeGraph real-PyPI benchmark

- **Run date:** {RUN_DATE}
- **Taedri version:** {__version__}
- **Python:** {platform.python_version()}
- **Profile:** non-executing CPython AST syntax analysis, immutable JSONL facts, SQLite FTS5 + adjacency, atomic publication

## Outcome

Taedri completed end-to-end publication for {len(results)} real installed PyPI {package_word}. Package code was never imported or executed. Distribution-owned `.py` bytes were selected through installed Core Metadata, copied into a temporary immutable input tree, hashed, parsed, validated, indexed, queried, and published.

| Distribution | Version | `.py` files | Source MiB | Entities | Occurrences | Relations | Total sec | Peak RSS MiB | Store MiB | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(table_rows)}

{chart_markdown}

## What the first real run proves

- The truth/search boundary works on non-synthetic packages: facts are validated before the disposable FTS/adjacency projection is published.
- Every published relation has exact participants, modality, quantifier, producer, analysis scope, and source-range evidence.
- Parse coverage is explicit; an unresolved file would yield `attempted_partial` instead of a false claim that no entities or callers exist.
- Exact package, analysis, and epoch identities make the result replayable and allow prior epochs to remain addressable.
- Search and neighbor operations run against the published epoch without importing the analyzed distribution.

## Real-data defect found and fixed

The first Pydantic run reported 105 distribution-owned Python paths but only 104 analyzed files. Two paths had identical bytes, and the prototype had incorrectly used `FileContentID` as the path-occurrence key. Real package data caught the identity-lattice error immediately.

The final implementation now keeps:

- `SourceFileID = hash(relative path + FileContentID)` for each file occurrence;
- `FileContentID = hash(exact bytes + size)` for byte-level deduplication;
- occurrences and evidence linked to both identities.

A regression fixture proves that two paths with the same bytes remain two source files while sharing one content object. The final Pydantic run accounts for all **105/105** Python files.

## Scale finding and immediate engineering consequence

The largest run, **{largest['distribution']} {largest['version']}**, expanded {largest['source_bytes'] / (1024 * 1024):.2f} MiB of Python source into {largest['entities']:,} entities, {largest['occurrences']:,} occurrences, and {largest['relations']:,} relation assertions. Its current prototype store is {largest['total_store_bytes'] / (1024 * 1024):.1f} MiB; the SQLite projection accounts for {index_share:.1f}%.

That is useful bad news: correctness held, but repeating canonical keys and full relation JSON inside both JSONL and SQLite is too expensive. The next storage milestone should introduce stable per-shard ordinals, dictionary encoding, compressed Arrow/Parquet fact shards, compact participant tables, and cards rather than full records in FTS rows. Canonical identities and evidence stay unchanged; only the disposable physical projection changes.

## Selected evidence graph

The graph below is a bounded, deterministic slice around the highest-degree non-file/non-module entity in the largest run. Approximate compatibility edges are not mixed into it.

{mermaid_block(graph_path)}

Machine-readable copies: [JSON]({relative_results}/graphs/{graph_slug}.json), [GraphML]({relative_results}/graphs/{graph_slug}.graphml), and [Mermaid]({relative_results}/graphs/{graph_slug}.mmd).

## Raw data

- [Aggregate JSON]({relative_results}/summary.json)
- [Package metrics CSV]({relative_results}/package_metrics.csv)
- [Predicate counts CSV]({relative_results}/predicate_counts.csv)
- Per-package manifests and graph slices are under [`packages/`]({relative_results}/packages/) and [`graphs/`]({relative_results}/graphs/).

## Reproduce

```bash
python tools/benchmark_real_packages.py wheel packaging pydantic
```

The large local epoch stores are intentionally excluded from Git. They are rebuildable from the recorded exact package versions and the benchmark tool; committing multi-gigabyte disposable indexes would contradict the architecture.

## Limits of this result

- Inputs are installed wheel contents, not yet independently downloaded wheel + sdist pairs with PyPI hash receipts.
- This is syntax-only evidence. Type assignability, SCIP reconciliation, runtime behavior, effects, and compatibility remain `unknown` unless separately analyzed.
- Timings and peak RSS describe this machine and are not cross-machine performance claims.
- The finite golden and poison corpora prove tested behavior, not a production error bound.
"""
    report_path.write_text(report, encoding="utf-8")


def aggregate(output_dir: Path, report_path: Path, no_charts: bool) -> list[dict[str, Any]]:
    results = [
        json.loads(path.read_text("utf-8"))
        for path in sorted((output_dir / "packages").glob("*.json"))
    ]
    results.sort(key=lambda item: item["source_bytes"])
    summary = {
        "run_date": RUN_DATE,
        "taedri_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "packages": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    metric_fields = [
        "distribution",
        "normalized_name",
        "version",
        "distribution_python_files",
        "source_bytes",
        "files",
        "entities",
        "occurrences",
        "relations",
        "evidence",
        "features",
        "projections",
        "coverage_state",
        "coverage_attempted_files",
        "coverage_successful_files",
        "coverage_unresolved_files",
        "analysis_seconds",
        "candidate_and_index_seconds",
        "publish_seconds",
        "total_seconds",
        "max_rss_kb",
        "fact_bytes",
        "index_bytes",
        "cas_bytes",
        "total_store_bytes",
        "entities_per_source_kib",
        "relations_per_second",
        "index_bytes_per_relation",
        "snapshot_id",
        "analysis_manifest_id",
        "epoch_id",
    ]
    (output_dir / "package_metrics.csv").write_text(
        csv_text(results, metric_fields), encoding="utf-8"
    )
    predicate_rows = [
        {
            "distribution": row["distribution"],
            "version": row["version"],
            "predicate": predicate,
            "count": count,
        }
        for row in results
        for predicate, count in row["predicate_counts"].items()
    ]
    (output_dir / "predicate_counts.csv").write_text(
        csv_text(predicate_rows, ["distribution", "version", "predicate", "count"]),
        encoding="utf-8",
    )
    chart_paths = [] if no_charts else render_charts(
        results, report_path.parent / "assets" / "real-pypi"
    )
    write_report(results, output_dir, report_path, chart_paths)
    return results


def parent_main(args: argparse.Namespace) -> int:
    args.output_dir = args.output_dir.resolve()
    args.store_root = args.store_root.resolve()
    args.report = args.report.resolve()
    shutil.rmtree(args.output_dir, ignore_errors=True)
    args.output_dir.mkdir(parents=True)
    args.store_root.mkdir(parents=True, exist_ok=True)
    for package in args.packages:
        print(f"[taedri] benchmarking {package}", flush=True)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--worker-package",
            package,
            "--output-dir",
            str(args.output_dir),
            "--store-root",
            str(args.store_root),
            "--report",
            str(args.report),
        ]
        subprocess.run(command, check=True)
    results = aggregate(args.output_dir, args.report, args.no_charts)
    print(
        json.dumps(
            {
                "completed_packages": [item["normalized_name"] for item in results],
                "output_dir": str(args.output_dir),
                "report": str(args.report),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.worker:
        if not args.worker_package:
            raise SystemExit("--worker-package is required with --worker")
        run_worker(args.worker_package, args.output_dir.resolve(), args.store_root.resolve())
        return 0
    return parent_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
