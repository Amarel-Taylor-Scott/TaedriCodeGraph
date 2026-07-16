# Primitive registry contracts

Owns stable primitive handles, immutable content trees, revision DAGs, branch/tag
semantics, fork lineage, and thin pack formats. It defines no database or object-store
choice. The executable transitional POC is currently in
`src/taedri_codegraph/primitive_capsules.py`.

Generated primitives enter as candidate capsules. Promotion, execution authorization,
and public serving remain separate evidence-bearing decisions.
