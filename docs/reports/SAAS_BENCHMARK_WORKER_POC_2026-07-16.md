# SaaS benchmark worker POC — 2026-07-16

## Outcome

Taedri now has an executable, provider-neutral benchmark controller for the central
SaaS hypothesis: can a frozen coding model produce more independently verified working
code per token, second, and total cost when it can search, plan with, and materialize
already-solved components?

The controller schedules the same task through four matched lanes:

1. `bare_model`;
2. `search_context`;
3. `primitive_plan`;
4. `primitive_materialized`.

It creates capability-aware `benchmark` jobs, immutable run specifications, terminal
receipts, lane summaries, and task-matched comparisons. It rejects hidden-test/gold
references in model-facing retrieval, requires one receipt per tool call, requires
independent verification for accepted results, and keeps failed, abstained,
policy-blocked, contaminated, unknown, and infrastructure-error outcomes in the
denominator.

## Conformance run

The checked-in conformance bundle uses two real entities from the Taedri source and
primitive registry:

- deterministic canonical JSON encoding;
- capability-aware lease-based worker claiming.

It generated:

| Artifact | Count |
|---|---:|
| Real-source conformance tasks | 2 |
| Lanes | 4 |
| Repetition seeds | 2 |
| Frozen run specifications | 16 |
| Idempotent benchmark jobs | 16 |
| Terminal fixture receipts | 16 |
| Matched treatment comparisons | 3 |
| Detected sealed-reference leaks | 0 |
| Claimable efficacy runs | 0 |

The last row is intentional. The conformance experiment identifies its provider as
`deterministic-contract-fixture` and model as `not-a-model`. No provider was called and
no SaaS lift is claimed. The report mechanically emits `efficacy_claimable: false`.
This validates the evidence plumbing without turning fixture measurements into
marketing claims.

## Files to inspect

- `apps/explorer/benchmark-console.html` — self-contained GitHub-downloadable benchmark console;
- `docs/visuals/assets/benchmark-worker-evidence-boundary.svg` — GitHub-renderable architecture;
- `eval/results/benchmark-worker-2026-07-16/campaign-plan.json` — real campaign tracks, metrics, controls, and promotion gate;
- `eval/results/benchmark-worker-2026-07-16/conformance-experiment.json` — frozen experiment identity;
- `eval/results/benchmark-worker-2026-07-16/conformance-tasks.jsonl` — immutable task contracts;
- `eval/results/benchmark-worker-2026-07-16/conformance-run-specs.jsonl` — matched schedule;
- `eval/results/benchmark-worker-2026-07-16/worker-jobs.jsonl` — queue-ready jobs;
- `eval/results/benchmark-worker-2026-07-16/conformance-run-receipts.jsonl` — retained terminal evidence;
- `eval/results/benchmark-worker-2026-07-16/conformance-report.json` — claim-aware aggregate;
- `eval/results/benchmark-worker-2026-07-16/lane-summary.csv` and `matched-comparisons.csv` — analysis-friendly tables.

## First real campaign

The strongest first evidence is a mixed sealed suite:

- customer-private cold tasks for actual product value;
- SWE-Skills-Bench for a direct reusable-context control/treatment comparison;
- a small SWE-bench repository-repair stratum;
- Terminal-Bench/Harbor for DevOps work;
- SWE-Lancer only for sourced economic-value analysis.

Start with a pilot to estimate paired discordance and resource variance, then power the
main run from those observations. Hold model/provider/harness/budget constant. Count
retrieval and verification overhead. Randomize lane order within task. Preserve a
never-tuned cold holdout. Report exact-output and behavioral consistency separately.

## SaaS test and offer

The business-model manifest now includes a `benchmark-and-assurance-pilot`. Its
deliverable is a decision-quality evidence bundle for an engineering organization,
with provider and infrastructure usage disclosed separately. Prices and ROI remain
unset until real delivery costs, customer willingness to pay, and controlled workload
outcomes exist.

This is a useful commercial wedge: it can prove or disprove the managed registry and
verification control-plane value before the customer commits to a broad rollout.
