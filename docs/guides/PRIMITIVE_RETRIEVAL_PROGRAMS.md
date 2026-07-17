# Retrieve primitives with versioned programs

A primitive catalog can grow without turning selection into one expensive query. Taedri
represents the selection policy as a typed `RetrievalProgram`: an ordered list of
versioned paths with explicit representation keys, lifecycle temperatures, candidate
limits, fusion weights, capability requirements, and cost units.

The checked default is `taedri.retrieval.primitive_cards@1.0.0`:

| Order | Path | State | Cost | Purpose |
|---:|---|---|---:|---|
| 1 | Exact namespace/name | Hot | 1 | Resolve an exact primitive name and stop on one unique match |
| 2 | Capability labels | Hot | 1 | Match names, keywords, and stated use cases |
| 3 | Integer BM25 | Warm | 2 | Rank the complete body-free card text |
| 4 | Token/trigram blocking | Warm | 2 | Recover grounded morphology, prefix, and close-spelling candidates |
| 5 | Lexical hash | Derived | 1 | Re-rank already grounded candidates; never introduce one through a hash collision |
| 6 | True semantic retrieval | Cold | 8 | Optional supplement when capability is present and deterministic evidence is insufficient |

Lexical hashing is not called an embedding model or treated as semantic evidence. The
semantic path requires `taedri.capability.semantic_embeddings`, has its own
representation key and receipt, and is skipped when deterministic evidence already
meets the program target and margin.

## Use the checked catalog

```python
from pathlib import Path

from taedri_codegraph.prompt_interception import (
    DeterministicRetrievalProgramShortlister,
    ReleasedPrimitiveCatalog,
)

catalog = ReleasedPrimitiveCatalog.load_checked_cohort(
    Path("eval/results/data-primitive-cohort-2026-07-17")
)
shortlister = DeterministicRetrievalProgramShortlister(catalog.cards)

execution = shortlister.execute(
    "Map blank and N/A sentinel strings to a missing value.",
    limit=4,
)
selected = catalog.card(execution.candidates[0].primitive_id)
assert selected.name == "normalize-null-marker"
```

`shortlist(request, limit)` returns the compact `RankedCandidate` interface used by
prompt interception. `execute(request, limit)` additionally returns the full program
receipt. The receipt stores the query digest, catalog and program digests, integer-only
candidate contributions, path execution/skip results, cost consumed, and stop reason;
it does not retain the raw request.

Exact-name requests cost one unit and produce skip receipts for every later path. Broad
requests move down the waterfall only until the candidate target and score margin are
satisfied. Requests with too little independent lexical grounding abstain instead of
admitting candidates on one generic word.

## Register a new policy without reinterpreting an old one

`RetrievalProgramRegistry` is additive. Registering the same reference and digest is
idempotent; attempting to reuse a published `key@version` with different contents
fails. Change the version whenever path order, representations, cost, fusion, grounding,
or stop policy changes.

A path can be `hot`, `warm`, `cold`, `derived`, or `retired`. Retirement remains visible
in the program and produces an explicit skip receipt rather than deleting history. This
keeps logical representation lifecycle separate from physical indexes or columns.

## Benchmark the policy

```bash
PYTHONPATH=src python tools/benchmark_primitive_retrieval_program.py
```

The checked result in
`eval/results/primitive-retrieval-program-2026-07-17` covers 26 exact/paraphrased
positive cases and five unsupported cases. The program achieved 26/26 positive rank-1
hits and 5/5 unsupported abstentions while returning 34 candidates, versus 25/26,
3/5, and 83 candidates for the legacy BM25-only shortlister. These are deterministic
fixture results, not corpus-wide relevance, semantic quality, coding-success, or token
savings claims. That retrieval comparison remains bound to its original 13-release
fixture. The expanded 23-release route benchmark separately records 20 retrieval
executions against the larger catalog before compatibility planning.
