# First executable vertical slice

## Goal

Prove that one fixed Python source tree can become a deterministic Universal Code
Entity Graph (UCEG) whose exact facts remain separate from replaceable retrieval
indexes.

## Included

- Local, immutable source snapshot identity.
- Safe discovery and parsing of regular `.py` files without imports or execution.
- File, module, class, callable, parameter, variable, import-binding, instance-field,
  and unresolved-external-symbol entities.
- Byte-ranged definition/read/write/call/import occurrences.
- Evidence-bearing `contains`, `defines`, `reads`, `writes`, `references`, `imports`,
  and `calls_may` relation assertions.
- Coverage ledgers that distinguish complete supported syntax from parse gaps.
- Additive extension descriptors and feature assertions.
- Exact AST digests, normalized-token SimHash, and MinHash projections.
- Immutable fact shards, manifest validation, atomic `CURRENT` publication, and
  disposable SQLite exact/FTS/adjacency indexes.

## Excluded by design

- Installing, importing, building, or executing a target package.
- Claiming complete semantic call resolution from syntax alone.
- Treating an unresolved target, similar fingerprint, or missing type as compatible.
- All-pairs compatibility materialization.
- Network acquisition and live PyPI resolution; these require hash-pinned artifact
  receipts and hostile-archive gates first.

## Next gates

1. Add canonical cross-language identity vectors and independent TypeScript decoder.
2. Add hash-pinned wheel/sdist acquisition with safe extraction fixtures.
3. Reconcile AST facts with `symtable`, SCIP, and one type-checker adapter.
4. Add sparse compatibility signatures, poison fixtures, and on-demand pair checks.
5. Benchmark exact/FTS/fingerprint lanes on one pinned large PyPI release.
