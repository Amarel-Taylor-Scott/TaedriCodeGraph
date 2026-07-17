# Find, compose, execute, and reuse primitive routes

Primitive retrieval and primitive compatibility are separate operations. Retrieval
nominates a bounded set of likely components for each requested operation. The route
planner then accepts only paths whose released contracts, ports, runtime policy, and
authoritative compatibility dimensions connect exactly.

The implemented flow is:

```text
natural-language request
→ ordered operation intents and input/output schemas
→ versioned body-free retrieval per operation
→ capability-group and input-schema blocking
→ exact policy and adjacent-wire checks
→ content-addressed route plan
→ exact pack resolution and isolated execution
→ execution receipt
→ exact verified-recipe lookup on later requests
```

Similarity never proves a connection. A retrieved candidate outside the requested
capability group is discarded. A matching capability with the wrong input schema is
blocked before a wire assessment. Missing runtime, policy, schema, transport, or
compatibility evidence remains unknown or incompatible and cannot be treated as a
wildcard.

## Structured route request

The current planner operates on ordered unary steps. Each step contains a capability
group and, normally, the primitive IDs nominated by a retrieval execution. Adapters are
ordinary explicit steps rather than generated glue.

```python
import sys

from taedri_codegraph.primitives.routes import (
    BoundedPrimitiveRoutePlanner,
    PrimitiveRoutePolicy,
    PrimitiveRouteRequest,
    PrimitiveRouteStep,
)

policy = PrimitiveRoutePolicy(
    language="python",
    runtime_version=f"{sys.version_info.major}.{sys.version_info.minor}",
)

request = PrimitiveRouteRequest.create(
    input_schema={"type": "string"},
    output_schema={"type": "string"},
    steps=(
        PrimitiveRouteStep(
            "taedri.group.data_engineering_numeric_coercion",
            nominated_primitive_ids=(coerce_primitive_id,),
        ),
        PrimitiveRouteStep(
            "taedri.group.data_engineering_numeric_formatting",
            nominated_primitive_ids=(format_primitive_id,),
        ),
    ),
    policy=policy,
    per_step_candidate_limit=16,
    max_candidate_expansions=256,
    max_routes=4,
)

result = BoundedPrimitiveRoutePlanner(route_catalog).search(request)
if not result.routes:
    raise RuntimeError(result.receipt.stop_reason)
plan = result.routes[0].plan
```

The receipt retains the request, catalog, and returned-route identities plus exact
counts for cheap schema blocks, policy rejections, wire assessments, wire rejections,
candidate expansions, remaining frontier states, and the stop reason. It records zero
model calls and does not retain raw step queries; retrieval query digests bind the
nominations.

## Exact recipe reuse

After a route executes successfully, `VerifiedPrimitiveRecipeRegistry.record` binds:

- the reusable structured route-contract digest;
- the exact catalog digest;
- the execution-environment digest;
- route, plan, primitive, release, and pack identities;
- the successful pipeline execution receipt and observed output digest; and
- verifier identity and verification time.

A paraphrased request can reuse the route when it compiles to the same structured
contract and the catalog and environment are unchanged. A changed primitive release,
pack, catalog membership, runtime, executor policy, or environment digest is a miss.
The returned route is still executed for the new input; the cache avoids rediscovering
the path, not validating arbitrary future outputs by assumption.

## Checked benchmark

Run:

```bash
PYTHONPATH=src python tools/benchmark_primitive_route_planner.py
```

The checked evidence in `eval/results/primitive-route-planner-2026-07-17` uses the
23-release cohort. Twenty body-free retrieval executions nominated components for seven
tasks containing 20 ordered steps. Route search considered 24 candidates, performed 16
authoritative wire assessments, selected and executed every intended route, and
abstained on three unsupported or incompatible requests. It generated no glue code and
made no model or semantic calls.

The seven successful routes were registered and resolved again under the same catalog
and Python environment. All seven second lookups used the verified recipe and performed
zero candidate expansions and zero wire assessments.

This is not yet a general program synthesizer. Multi-input operations, branching,
parallel values, stateful lifecycles, dependency solving, and process/proof graphs need
a set-valued or hypergraph search state. The current ordered unary planner is kept small
so its correctness boundary and receipts are explicit while that next representation is
developed.
