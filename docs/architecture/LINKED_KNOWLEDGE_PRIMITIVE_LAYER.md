# Linked knowledge and context layer

Taedri can extend beyond executable code, but it must not collapse every source,
statement, observation, model, proof, process, and action into one vague primitive
record. CodeGraph remains the exact executable component system. A linked knowledge
layer can share identities, provenance, retrieval programs, and result packaging while
retaining domain-specific truth and verification rules.

## Record kinds stay distinct

| Kind | Example | Required validity boundary |
|---|---|---|
| Entity or concept | Mars, democracy, triangle | Stable identity and source mappings |
| Source document | One Wikipedia revision | Exact bytes/revision, date, origin, license |
| Claim | A sourced radius for Mars | Subject, predicate, value, qualifiers, source span |
| Observation | A sensor measured 19.7 °C | Instrument, method, time, place, unit, uncertainty |
| Event | Election, eruption, release | Participants, time/location, evidence |
| Process definition | Manufacture a battery | Inputs, state, actions, branches, outputs, failures |
| Action | Heat water, compile code | Preconditions, effects, resources, permissions, executor |
| Rule or model | Ideal gas law, tax rule | Variables, assumptions, domain or jurisdiction, validity |
| Mathematical object | Matrix, group, equation | Formal type and meaning |
| Problem and solution | Integral and derivation | Assumptions, goal, steps, checker evidence |
| Template | Invoice or experiment template | Parameter schema, constraints, renderer |
| Executable component | Function, API, CLI | Exact artifact, contract, dependencies, tests |
| Hierarchy definition | Taxonomy, AST, org chart | Domain-specific meaning of parent and child |

A Wikipedia page is not its subject. A phenomenon is not an observation of it. A model
is not the evidence testing it. A mathematical explanation is not a checked proof. A
suggested code connection is not an observed call or a verified composition.

## Contextual claims

Each claim or relationship is its own versioned record. At minimum it can carry:

- canonical subject, relationship, value, direction, and inverse;
- source identity, exact source version, and supporting span or table/equation cell;
- time, place, jurisdiction, population, units, dimensions, and uncertainty;
- assumptions, boundary conditions, exceptions, and validity interval;
- extraction method and producer identity;
- separate extraction confidence and source/truth status;
- asserted, observed, inferred, verified, disputed, deprecated, or suggested state;
- access policy and license; and
- agreement, contradiction, derivation, and supersession links.

Contradictory source-backed claims can coexist. Missing information remains unknown,
not false. Search descriptions, keywords, embeddings, and structural fingerprints are
derived representations of the record and never replace its source or formal meaning.

## Composition is domain-specific

| Domain | Hard compatibility check |
|---|---|
| Code | Types, schemas, effects, dependencies, runtime, policy, tests |
| Mathematics | Theorem hypotheses, variable domains, assumptions, proof checker |
| Physical science | Units, dimensions, frames, conditions, uncertainty, model scope |
| Processes | State, resources, permissions, ordering, effects, compensation |
| Historical claims | Identity, time, place, source, perspective |
| Law and policy | Jurisdiction, authority, effective date, covered subject |
| Templates | Required parameters, formats, constraints, renderer |
| Observations | Property, instrument, method, place, time, unit, comparability |
| Causal explanations | Causal evidence and mechanism, not textual proximity |

There is no universal compatibility score. Exact, lexical, vector, LSH, graph, and
structural retrieval can nominate candidates; the relevant domain checker decides
whether a proof step, process action, scientific inference, or code connection is valid.

## Storage and retrieval boundary

Immutable source artifacts remain the recovery point. Structured entity, claim,
observation, process, proof, and executable records can live in separately governed
partitions linked by stable identifiers. Full-text, vector, LSH, graph, and route caches
are rebuildable projections. Mathematical checker environments, code executors, process
histories, and benchmark records remain separate because their evidence has different
meaning and lifecycle.

User-facing retrieval can span partitions and return the smallest source-backed set of
facts, rules, proofs, observations, and executable components needed for one task. The
result is a directed evidence graph, not always a linear recipe: transformations,
procedures, proofs, explanations, timelines, hierarchies, comparisons, and decisions
have different shapes.

## Delivery sequence

1. Keep the completed code path working: prompt or structured intent → bounded
   retrieval → compatible route → exact artifacts → isolated execution → receipt.
2. Generalize the route state from one current value to a set of available values and
   capabilities so multi-input components and explicit adapters can be planned.
3. Add one fixed, source-bounded Wikidata/Wikipedia snapshot with exact revisions,
   entities, source documents, contextual claims, citations, and extraction lineage.
4. Benchmark source coverage, identity resolution, claim/qualifier extraction,
   retrieval, contradictions, evidence-chain correctness, and refusal separately.
5. Add mathematics, processes, and observations one domain at a time, each with its
   own formal or operational verifier.

“Everything” means measurable coverage of named, dated source snapshots—not complete
knowledge of reality. Every coverage or correctness claim must name its source boundary,
record kind, verification method, and unresolved unknowns.
