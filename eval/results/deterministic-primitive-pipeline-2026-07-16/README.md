# Deterministic primitive pipeline evidence

Status: **passed**

An explicit user-tier trigger fired for `trim surrounding whitespace and apply Unicode case folding`. Two released primitives were
found by separate registry queries, their evidence-bound interface graphs were loaded,
and the normalize-text output port was connected to the casefold-text input port only
after exact schema, transport, runtime, determinism, purity, network, and call-style
checks passed.

The trusted-source local executor downloaded and digest-checked both complete packs,
materialized them, and transformed `"  Straße  "` into `"strasse"`. It made zero model
calls and generated or rewrote zero primitive code bytes.

- Plan: `uceg:v1:deterministic_pipeline_plan:3bhsy7afa2fsgdd5gpefbsazy7rxwbak5dvsestj4k4e7aulardq`
- Interfaces: 2
- Evidence-bound edges: 12
- Typed ports: 4
- Exact wires: 1
- Pipeline receipt: `uceg:v1:deterministic_pipeline_receipt:cfqyiuadk2njhofokx57prri2wweidbpql7qdmltszhtpl7telha`

This proves a narrow deterministic reuse path, not general natural-language planning,
adapter synthesis, hostile-code isolation, or population-level token/cost savings.
