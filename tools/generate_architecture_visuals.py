#!/usr/bin/env python3
"""Generate reproducible architecture charts and their source data."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "visuals"
ASSETS = OUT / "assets"
DATA = OUT / "data"
EVAL = ROOT / "eval" / "results" / "hybrid-architecture-2026-07-15"

INK = "#172033"
MUTED = "#667085"
GRID = "#d8dee9"
BLUE = "#3b67d9"
TEAL = "#168f8b"
GOLD = "#c58a16"
CORAL = "#d05c50"
PURPLE = "#7656b7"
PALE = "#f5f7fb"


def setup() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "text.color": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "svg.hashsalt": "taedri-codegraph-architecture-v1",
            "axes.titlesize": 16,
            "axes.titleweight": "bold",
            "axes.grid": True,
            "grid.color": GRID,
            "grid.alpha": 0.65,
            "grid.linewidth": 0.7,
        }
    )


def save(fig: plt.Figure, stem: str) -> None:
    svg_path = ASSETS / f"{stem}.svg"
    fig.savefig(
        svg_path,
        bbox_inches="tight",
        metadata={"Date": None, "Creator": "Taedri CodeGraph architecture visual generator"},
    )
    # Matplotlib's path serializer leaves spaces before many newlines. They are
    # semantically irrelevant but make generated diffs noisy, so normalize them.
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_path.read_text("utf-8").splitlines()) + "\n",
        "utf-8",
    )
    fig.savefig(
        ASSETS / f"{stem}.png",
        dpi=180,
        bbox_inches="tight",
        metadata={"Software": "Taedri CodeGraph architecture visual generator"},
    )
    plt.close(fig)


def lsh_collision_chart() -> list[dict[str, float | str]]:
    similarities = np.linspace(0.0, 1.0, 101)
    profiles = (
        ("narrow · 8 bands × 2 rows", 8, 2, BLUE),
        ("medium · 4 × 4", 4, 4, TEAL),
        ("wide · 2 × 8", 2, 8, GOLD),
    )
    rows: list[dict[str, float | str]] = []
    fig, ax = plt.subplots(figsize=(10.8, 6.1))
    for label, bands, width, color in profiles:
        probabilities = 1 - (1 - similarities**width) ** bands
        ax.plot(similarities, probabilities, linewidth=2.6, color=color, label=label)
        for similarity, probability in zip(similarities, probabilities, strict=True):
            rows.append(
                {
                    "profile": label.split(" ·", 1)[0],
                    "similarity": round(float(similarity), 2),
                    "collision_probability": round(float(probability), 8),
                    "bands": bands,
                    "rows_per_band": width,
                }
            )
    ax.set_title("MinHash16 profiles expose different recall–precision regions", loc="left", pad=14)
    ax.set_xlabel("True Jaccard similarity s")
    ax.set_ylabel("Probability of at least one matching band")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "Single-table theory: 1 − (1 − sʳ)ᵇ. Overlapping offsets are correlated candidate arms; exact similarity and verification remain authoritative.",
        color=MUTED,
        fontsize=8.5,
    )
    save(fig, "multiresolution-lsh-collision")
    return rows


def adaptive_depth_chart() -> list[dict[str, int | str]]:
    levels = np.arange(0, 1_000_001, 50_000)
    grid = np.zeros((len(levels), len(levels)), dtype=int)
    thresholds = (100_000, 225_000, 375_000, 550_000, 725_000, 875_000)
    rows: list[dict[str, int | str]] = []
    for y, confusion in enumerate(levels):
        for x, query in enumerate(levels):
            need = (
                query * 25
                + confusion * 30
                + 500_000 * 15
                + 500_000 * 10
                + 500_000 * 15
            ) // 100
            depth = sum(need >= threshold for threshold in thresholds)
            grid[y, x] = depth
            rows.append(
                {
                    "query_demand_ppm": int(query),
                    "candidate_confusion_ppm": int(confusion),
                    "need_ppm": int(need),
                    "recommended_depth": f"E{depth}",
                }
            )
    cmap = plt.matplotlib.colors.ListedColormap(
        ["#eef2fb", "#d9e3fa", "#bdd0f5", "#91b6ed", "#5f91df", "#3768bd", "#213f7d"]
    )
    fig, ax = plt.subplots(figsize=(10.8, 6.3))
    image = ax.imshow(grid, origin="lower", extent=(0, 1, 0, 1), aspect="auto", cmap=cmap, vmin=-0.5, vmax=6.5)
    colorbar = fig.colorbar(image, ax=ax, ticks=range(7), pad=0.02)
    colorbar.ax.set_yticklabels([f"E{level}" for level in range(7)])
    colorbar.set_label("Recommended enrichment depth")
    ax.set_title("Dynamic depth rises only when subject-local differentiation pressure rises", loc="left", pad=14)
    ax.set_xlabel("Observed query demand")
    ax.set_ylabel("Candidate confusion")
    ax.set_xticks(np.linspace(0, 1, 6), ["0", ".2", ".4", ".6", ".8", "1.0"])
    ax.set_yticks(np.linspace(0, 1, 6), ["0", ".2", ".4", ".6", ".8", "1.0"])
    ax.grid(False)
    fig.text(
        0.01,
        0.01,
        "Reuse potential, graph centrality, and evidence gap fixed at 0.5. Package purpose is not a negative gate.",
        color=MUTED,
        fontsize=8.5,
    )
    save(fig, "adaptive-enrichment-depth")
    return rows


def benchmark_scale_chart() -> list[dict[str, float | int | str | None]]:
    packages = json.loads((EVAL / "package-results.json").read_text("utf-8"))
    rows: list[dict[str, float | int | str | None]] = []
    fig, ax = plt.subplots(figsize=(10.8, 6.1))
    for item in packages:
        storage_mib = (item["fact_bytes"] + item["index_bytes"]) / (1024 * 1024)
        mode = item["mode"]
        color = BLUE if mode == "full-wheel-ast-hybrid" else GOLD
        marker = "o" if mode == "full-wheel-ast-hybrid" else "s"
        ax.scatter(item["entities"], storage_mib, s=110, color=color, marker=marker, edgecolor="white", linewidth=1.3, zorder=3)
        ax.annotate(
            f"{item['package']} {item['version']}",
            (item["entities"], storage_mib),
            xytext=(8, 7),
            textcoords="offset points",
            fontsize=9,
        )
        rows.append(
            {
                "package": item["package"],
                "version": item["version"],
                "mode": mode,
                "entities": item["entities"],
                "representation_assertions": item["representation_assertions"],
                "storage_mib": round(storage_mib, 4),
                "recall_at_10": item["recall_at_10"],
                "mrr_at_10": item["mrr_at_10"],
            }
        )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Entities (log scale)")
    ax.set_ylabel("Facts + SQLite index, MiB (log scale)")
    ax.set_title("Real-package POC exposes physical duplication before logical schema limits", loc="left", pad=14)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "Square: inventory-only pandas. Circles: full wheel AST + hybrid index. PyPDF reaches ~1.6 GiB, motivating Parquet/CAS + replaceable serving projections.",
        color=MUTED,
        fontsize=8.5,
    )
    save(fig, "real-package-storage-scale")
    return rows


def rounded_box(ax: plt.Axes, xy: tuple[float, float], width: float, height: float, label: str, color: str, subtitle: str = "") -> None:
    x, y = xy
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.018,rounding_size=0.025",
        facecolor=color,
        edgecolor="white",
        linewidth=1.2,
    )
    ax.add_patch(box)
    ax.text(x + width / 2, y + height * 0.62, label, ha="center", va="center", color="white", weight="bold", fontsize=9)
    if subtitle:
        ax.text(x + width / 2, y + height * 0.28, subtitle, ha="center", va="center", color="white", fontsize=7.3)


def arrow(ax: plt.Axes, start: tuple[float, float], end: tuple[float, float], color: str = MUTED, alpha: float = 0.8, rad: float = 0.0) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.0,
            color=color,
            alpha=alpha,
            connectionstyle=f"arc3,rad={rad}",
        )
    )


def data_model_chart() -> None:
    fig, ax = plt.subplots(figsize=(13.2, 7.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Typed long tables preserve unlimited variants without a wide entity schema", loc="left", pad=18)
    ax.text(0, 1.01, "Content dedupe, attempt provenance, subject claims, lineage, state, views, and indexes remain separate", color=MUTED, transform=ax.transAxes)
    nodes = {
        "subject": ((0.02, 0.39), 0.14, 0.14, "Subject", "entity · edge · group"),
        "descriptor": ((0.02, 0.73), 0.17, 0.14, "Descriptor definition", "schema · applicability"),
        "run": ((0.25, 0.73), 0.15, 0.14, "Generation run", "attempt · cost · status"),
        "assertion": ((0.27, 0.39), 0.18, 0.16, "Assertion", "scope · evidence · validity"),
        "content": ((0.54, 0.39), 0.18, 0.16, "Typed content", "CAS payload · value kind"),
        "lineage": ((0.51, 0.73), 0.18, 0.14, "Lineage DAG", "roles · ordinals · inputs"),
        "state": ((0.23, 0.10), 0.18, 0.14, "Materialization state", "failed · stale · withheld"),
        "view": ((0.49, 0.10), 0.18, 0.14, "Preferred view", "purpose-scoped selection"),
        "index": ((0.79, 0.39), 0.18, 0.16, "Projection epoch", "FTS · LSH · ANN · graph"),
    }
    colors = {
        "subject": BLUE,
        "descriptor": PURPLE,
        "run": CORAL,
        "assertion": TEAL,
        "content": BLUE,
        "lineage": CORAL,
        "state": GOLD,
        "view": PURPLE,
        "index": TEAL,
    }
    for key, (xy, width, height, label, subtitle) in nodes.items():
        rounded_box(ax, xy, width, height, label, colors[key], subtitle)
    arrow(ax, (0.16, 0.46), (0.27, 0.46))
    arrow(ax, (0.45, 0.46), (0.54, 0.46))
    arrow(ax, (0.72, 0.46), (0.79, 0.46))
    arrow(ax, (0.34, 0.73), (0.36, 0.55))
    arrow(ax, (0.60, 0.73), (0.63, 0.55))
    arrow(ax, (0.19, 0.78), (0.27, 0.52), rad=-0.12)
    arrow(ax, (0.12, 0.39), (0.29, 0.24), rad=0.12)
    arrow(ax, (0.41, 0.17), (0.49, 0.17))
    arrow(ax, (0.67, 0.17), (0.86, 0.39), rad=-0.12)
    ax.text(0.02, 0.02, "New attribute = registry row + typed payload/assertion rows + optional index recipe", fontsize=10, color=INK, weight="bold")
    save(fig, "typed-long-table-model")


def monorepo_chart() -> list[dict[str, str | list[str]]]:
    manifest = json.loads((ROOT / "architecture" / "components.json").read_text("utf-8"))
    components = manifest["components"]
    layer = {
        "shared-kernel": 0,
        "shared-schemas": 0,
        "schema-artifacts": 0,
        "primitive-capsules": 1,
        "ingestion-pypi": 1,
        "ingestion-git": 1,
        "analyzer-python": 1,
        "analyzer-polyglot": 1,
        "storage": 1,
        "retrieval": 1,
        "compatibility": 1,
        "indexer-service": 2,
        "query-api": 2,
        "registry-api": 2,
        "mcp-integration": 3,
        "agent-integrations": 3,
        "explorer-app": 3,
        "deployment": 3,
        "evaluation": 3,
    }
    columns = {
        0: ["shared-kernel", "shared-schemas", "schema-artifacts"],
        1: ["primitive-capsules", "ingestion-pypi", "ingestion-git", "analyzer-python", "analyzer-polyglot", "storage", "retrieval", "compatibility"],
        2: ["indexer-service", "query-api", "registry-api"],
        3: ["mcp-integration", "agent-integrations", "explorer-app", "deployment", "evaluation"],
    }
    positions: dict[str, tuple[float, float]] = {}
    fig, ax = plt.subplots(figsize=(14.5, 8.3))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Monorepo: one contract graph, multiple libraries, services, integrations, and apps", loc="left", pad=18)
    headings = ["Foundations", "Reusable packages", "Deployable services", "Consumers & operations"]
    xs = [0.03, 0.27, 0.56, 0.77]
    widths = [0.17, 0.21, 0.17, 0.20]
    for index, heading in enumerate(headings):
        ax.text(xs[index], 0.94, heading, weight="bold", color=INK, fontsize=11)
    component_by_id = {component["id"]: component for component in components}
    for column, ids in columns.items():
        ys = np.linspace(0.82, 0.12, len(ids))
        for component_id, y in zip(ids, ys, strict=True):
            x = xs[column]
            width = widths[column]
            positions[component_id] = (x, float(y))
            kind = component_by_id[component_id]["kind"]
            color = {0: PURPLE, 1: BLUE, 2: TEAL, 3: GOLD}[column]
            rounded_box(ax, (x, float(y)), width, 0.075, component_id, color, kind)
    for component in components:
        target = component["id"]
        if target not in positions:
            continue
        tx, ty = positions[target]
        for dependency in component["depends_on"]:
            if dependency not in positions:
                continue
            sx, sy = positions[dependency]
            start = (sx + widths[layer[dependency]], sy + 0.037)
            end = (tx, ty + 0.037)
            arrow(ax, start, end, color=MUTED, alpha=0.28, rad=0.04 if sy < ty else -0.04)
    ax.add_patch(FancyBboxPatch((0.03, 0.015), 0.94, 0.05, boxstyle="round,pad=0.01", facecolor=PALE, edgecolor=GRID))
    ax.text(0.50, 0.040, "src/taedri_codegraph stays active during test-preserving extraction; the manifest prevents dependency drift", ha="center", va="center", color=MUTED, fontsize=9)
    save(fig, "monorepo-component-topology")
    return components


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    setup()
    lsh = lsh_collision_chart()
    adaptive = adaptive_depth_chart()
    packages = benchmark_scale_chart()
    data_model_chart()
    components = monorepo_chart()
    write_csv(DATA / "lsh-collision-probabilities.csv", lsh)
    write_csv(DATA / "adaptive-depth-grid.csv", adaptive)
    write_csv(DATA / "real-package-scale.csv", packages)
    summary = {
        "schema_version": "1.0.0",
        "generated_from": {
            "package_results": str(EVAL.relative_to(ROOT) / "package-results.json"),
            "component_manifest": "architecture/components.json",
            "policy_implementation": "src/taedri_codegraph/portfolio.py",
        },
        "charts": [
            "multiresolution-lsh-collision",
            "adaptive-enrichment-depth",
            "real-package-storage-scale",
            "typed-long-table-model",
            "monorepo-component-topology",
        ],
        "package_rows": packages,
        "component_count": len(components),
        "lsh_profiles": [
            {"profile": "narrow", "minhash_bands": 8, "rows_per_band": 2, "offsets": [0, 1]},
            {"profile": "medium", "minhash_bands": 4, "rows_per_band": 4, "offsets": [0, 2]},
            {"profile": "wide", "minhash_bands": 2, "rows_per_band": 8, "offsets": [0, 4]},
        ],
    }
    (DATA / "architecture-visuals.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    main()
