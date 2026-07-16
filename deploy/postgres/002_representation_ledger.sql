-- Taedri CodeGraph extensible representation ledger and disposable serving projections.
-- Facts are append-only long rows. New facets and providers register descriptor versions;
-- they do not add columns to canonical subject tables. Projection rows are rebuildable.

BEGIN;

CREATE SCHEMA IF NOT EXISTS taedri;

CREATE TABLE IF NOT EXISTS taedri.graph_snapshot (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    snapshot_id text NOT NULL CHECK (snapshot_id LIKE 'uceg:v1:%'),
    source_locator jsonb NOT NULL CHECK (jsonb_typeof(source_locator) = 'object'),
    source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS taedri.graph_subject (
    tenant_id text NOT NULL,
    snapshot_id text NOT NULL,
    subject_id text NOT NULL CHECK (subject_id LIKE 'uceg:v1:%'),
    subject_kind text NOT NULL,
    qualified_name text,
    lifecycle text NOT NULL CHECK (lifecycle IN ('candidate', 'structured', 'verified', 'revoked')),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, snapshot_id, subject_id),
    FOREIGN KEY (tenant_id, snapshot_id)
        REFERENCES taedri.graph_snapshot(tenant_id, snapshot_id)
);
CREATE INDEX IF NOT EXISTS graph_subject_kind_idx
    ON taedri.graph_subject(tenant_id, snapshot_id, subject_kind, subject_id);
CREATE INDEX IF NOT EXISTS graph_subject_name_idx
    ON taedri.graph_subject(tenant_id, snapshot_id, qualified_name)
    WHERE qualified_name IS NOT NULL;

CREATE TABLE IF NOT EXISTS taedri.descriptor_definition (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    descriptor_key text NOT NULL CHECK (
        descriptor_key ~ '^[a-z][a-z0-9_-]*(\.[a-z0-9_-]+)+$'
    ),
    schema_version text NOT NULL,
    family_key text NOT NULL,
    authority text NOT NULL,
    allowed_value_kinds jsonb NOT NULL CHECK (jsonb_typeof(allowed_value_kinds) = 'array'),
    index_lanes jsonb NOT NULL CHECK (jsonb_typeof(index_lanes) = 'array'),
    missing_value_semantics text NOT NULL CHECK (
        missing_value_semantics IN ('unknown', 'not_applicable', 'empty_is_meaningful')
    ),
    merge_semantics text NOT NULL,
    definition_digest text NOT NULL CHECK (definition_digest ~ '^sha256:[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('experimental', 'active', 'deprecated', 'revoked')),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, descriptor_key, schema_version),
    UNIQUE (tenant_id, definition_digest)
);
CREATE INDEX IF NOT EXISTS descriptor_family_idx
    ON taedri.descriptor_definition(tenant_id, family_key, descriptor_key, schema_version);
CREATE INDEX IF NOT EXISTS descriptor_definition_gin_idx
    ON taedri.descriptor_definition USING gin(record);

CREATE TABLE IF NOT EXISTS taedri.representation_content (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    content_id text NOT NULL CHECK (content_id LIKE 'uceg:v1:representation_content:%'),
    descriptor_key text NOT NULL,
    schema_version text NOT NULL,
    value_kind text NOT NULL CHECK (
        value_kind IN ('text', 'keyword', 'boolean', 'integer', 'decimal', 'timestamp',
                       'uri', 'digest', 'json', 'dense_vector', 'sparse_vector',
                       'distribution', 'bytes_ref')
    ),
    payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[0-9a-f]{64}$'),
    canonical_value jsonb NOT NULL,
    external_payload_ref jsonb,
    size_bytes bigint NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, content_id),
    UNIQUE (tenant_id, descriptor_key, schema_version, value_kind, payload_digest),
    FOREIGN KEY (tenant_id, descriptor_key, schema_version)
        REFERENCES taedri.descriptor_definition(tenant_id, descriptor_key, schema_version)
);
CREATE INDEX IF NOT EXISTS representation_content_descriptor_idx
    ON taedri.representation_content(tenant_id, descriptor_key, schema_version, value_kind);

CREATE TABLE IF NOT EXISTS taedri.generation_run (
    tenant_id text NOT NULL,
    run_id text NOT NULL CHECK (run_id LIKE 'uceg:v1:generation_run:%'),
    snapshot_id text NOT NULL,
    attempt_key text NOT NULL,
    producer_id text NOT NULL,
    producer_version text NOT NULL,
    producer_config_digest text NOT NULL CHECK (producer_config_digest ~ '^sha256:[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('planned', 'running', 'succeeded', 'failed', 'cancelled')),
    input_refs jsonb NOT NULL CHECK (jsonb_typeof(input_refs) = 'array'),
    output_digest text NOT NULL CHECK (output_digest ~ '^sha256:[0-9a-f]{64}$'),
    environment jsonb NOT NULL,
    prompt_ref jsonb,
    model_ref jsonb,
    seed text,
    cost_microunits bigint CHECK (cost_microunits >= 0),
    started_at timestamptz,
    completed_at timestamptz,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, run_id),
    UNIQUE (tenant_id, snapshot_id, attempt_key, producer_id, producer_version, producer_config_digest),
    FOREIGN KEY (tenant_id, snapshot_id)
        REFERENCES taedri.graph_snapshot(tenant_id, snapshot_id)
);
CREATE INDEX IF NOT EXISTS generation_run_status_idx
    ON taedri.generation_run(tenant_id, status, started_at, run_id);

CREATE TABLE IF NOT EXISTS taedri.representation_assertion (
    tenant_id text NOT NULL,
    assertion_id text NOT NULL CHECK (assertion_id LIKE 'uceg:v1:representation_assertion:%'),
    snapshot_id text NOT NULL,
    subject_id text NOT NULL,
    content_id text NOT NULL,
    run_id text NOT NULL,
    modality text NOT NULL CHECK (modality IN ('asserted', 'extracted', 'inferred', 'observed', 'computed')),
    polarity text NOT NULL CHECK (polarity IN ('positive', 'negative', 'unknown', 'conflicting')),
    confidence_ppm integer CHECK (confidence_ppm BETWEEN 0 AND 1000000),
    scope jsonb NOT NULL,
    lifecycle text NOT NULL CHECK (lifecycle IN ('candidate', 'structured', 'verified', 'revoked')),
    valid_from timestamptz,
    valid_to timestamptz,
    freshness_at timestamptz,
    cost_microunits bigint CHECK (cost_microunits >= 0),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, assertion_id),
    FOREIGN KEY (tenant_id, snapshot_id, subject_id)
        REFERENCES taedri.graph_subject(tenant_id, snapshot_id, subject_id),
    FOREIGN KEY (tenant_id, content_id)
        REFERENCES taedri.representation_content(tenant_id, content_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES taedri.generation_run(tenant_id, run_id),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from)
);
CREATE INDEX IF NOT EXISTS representation_assertion_subject_idx
    ON taedri.representation_assertion(tenant_id, snapshot_id, subject_id, lifecycle);
CREATE INDEX IF NOT EXISTS representation_assertion_content_idx
    ON taedri.representation_assertion(tenant_id, content_id, assertion_id);

CREATE TABLE IF NOT EXISTS taedri.evidence_link (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    record_kind text NOT NULL CHECK (
        record_kind IN ('representation_assertion', 'lineage_assertion', 'relation_assertion',
                        'preferred_view_revision', 'projection_epoch')
    ),
    record_id text NOT NULL,
    evidence_id text NOT NULL,
    evidence_role text NOT NULL DEFAULT 'supports',
    ordinal integer CHECK (ordinal IS NULL OR ordinal >= 0),
    PRIMARY KEY (tenant_id, record_kind, record_id, evidence_id, evidence_role)
);
CREATE INDEX IF NOT EXISTS evidence_reverse_idx
    ON taedri.evidence_link(tenant_id, evidence_id, record_kind, record_id);

CREATE TABLE IF NOT EXISTS taedri.lineage_assertion (
    tenant_id text NOT NULL,
    lineage_id text NOT NULL CHECK (lineage_id LIKE 'uceg:v1:lineage_assertion:%'),
    snapshot_id text NOT NULL,
    predicate_key text NOT NULL,
    source_subject_id text NOT NULL,
    target_subject_id text NOT NULL,
    role_key text,
    ordinal integer CHECK (ordinal IS NULL OR ordinal >= 0),
    run_id text,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, lineage_id),
    FOREIGN KEY (tenant_id, snapshot_id, source_subject_id)
        REFERENCES taedri.graph_subject(tenant_id, snapshot_id, subject_id),
    FOREIGN KEY (tenant_id, snapshot_id, target_subject_id)
        REFERENCES taedri.graph_subject(tenant_id, snapshot_id, subject_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES taedri.generation_run(tenant_id, run_id)
);
CREATE INDEX IF NOT EXISTS lineage_source_idx
    ON taedri.lineage_assertion(tenant_id, snapshot_id, source_subject_id, predicate_key);
CREATE INDEX IF NOT EXISTS lineage_target_idx
    ON taedri.lineage_assertion(tenant_id, snapshot_id, target_subject_id, predicate_key);

CREATE TABLE IF NOT EXISTS taedri.relation_assertion (
    tenant_id text NOT NULL,
    relation_id text NOT NULL CHECK (relation_id LIKE 'uceg:v1:%'),
    snapshot_id text NOT NULL,
    predicate_key text NOT NULL,
    source_subject_id text NOT NULL,
    target_subject_id text NOT NULL,
    modality text NOT NULL,
    polarity text NOT NULL,
    scope jsonb NOT NULL,
    run_id text,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, relation_id),
    FOREIGN KEY (tenant_id, snapshot_id, source_subject_id)
        REFERENCES taedri.graph_subject(tenant_id, snapshot_id, subject_id),
    FOREIGN KEY (tenant_id, snapshot_id, target_subject_id)
        REFERENCES taedri.graph_subject(tenant_id, snapshot_id, subject_id),
    FOREIGN KEY (tenant_id, run_id)
        REFERENCES taedri.generation_run(tenant_id, run_id)
);
CREATE INDEX IF NOT EXISTS relation_source_idx
    ON taedri.relation_assertion(tenant_id, snapshot_id, source_subject_id, predicate_key);
CREATE INDEX IF NOT EXISTS relation_target_idx
    ON taedri.relation_assertion(tenant_id, snapshot_id, target_subject_id, predicate_key);

CREATE TABLE IF NOT EXISTS taedri.representation_combination (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    combination_id text NOT NULL CHECK (combination_id LIKE 'uceg:v1:%'),
    purpose_key text NOT NULL,
    selector_version text NOT NULL,
    combination_digest text NOT NULL CHECK (combination_digest ~ '^sha256:[0-9a-f]{64}$'),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, combination_id),
    UNIQUE (tenant_id, purpose_key, combination_digest)
);

CREATE TABLE IF NOT EXISTS taedri.representation_combination_member (
    tenant_id text NOT NULL,
    combination_id text NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    assertion_id text NOT NULL,
    role_key text NOT NULL,
    marginal_value_ppm integer CHECK (marginal_value_ppm BETWEEN 0 AND 1000000),
    PRIMARY KEY (tenant_id, combination_id, ordinal),
    UNIQUE (tenant_id, combination_id, assertion_id, role_key),
    FOREIGN KEY (tenant_id, combination_id)
        REFERENCES taedri.representation_combination(tenant_id, combination_id),
    FOREIGN KEY (tenant_id, assertion_id)
        REFERENCES taedri.representation_assertion(tenant_id, assertion_id)
);

CREATE TABLE IF NOT EXISTS taedri.preferred_view_revision (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL,
    view_revision_id text NOT NULL CHECK (view_revision_id LIKE 'uceg:v1:%'),
    snapshot_id text NOT NULL,
    subject_id text NOT NULL,
    consumer_role text NOT NULL,
    purpose_key text NOT NULL,
    combination_id text NOT NULL,
    policy_digest text NOT NULL CHECK (policy_digest ~ '^sha256:[0-9a-f]{64}$'),
    effective_at timestamptz NOT NULL,
    supersedes_id text,
    reason text NOT NULL,
    record jsonb NOT NULL,
    UNIQUE (tenant_id, view_revision_id),
    FOREIGN KEY (tenant_id, snapshot_id, subject_id)
        REFERENCES taedri.graph_subject(tenant_id, snapshot_id, subject_id),
    FOREIGN KEY (tenant_id, combination_id)
        REFERENCES taedri.representation_combination(tenant_id, combination_id)
);
CREATE INDEX IF NOT EXISTS preferred_view_current_idx
    ON taedri.preferred_view_revision(
        tenant_id, snapshot_id, subject_id, consumer_role, purpose_key, sequence DESC
    );

CREATE TABLE IF NOT EXISTS taedri.projection_epoch (
    tenant_id text NOT NULL,
    projection_epoch_id text NOT NULL CHECK (projection_epoch_id LIKE 'uceg:v1:%'),
    snapshot_id text NOT NULL,
    projection_kind text NOT NULL,
    configuration_digest text NOT NULL CHECK (configuration_digest ~ '^sha256:[0-9a-f]{64}$'),
    dependency_digest text NOT NULL CHECK (dependency_digest ~ '^sha256:[0-9a-f]{64}$'),
    state text NOT NULL CHECK (state IN ('building', 'candidate', 'published', 'superseded', 'failed')),
    built_at timestamptz,
    manifest jsonb NOT NULL,
    PRIMARY KEY (tenant_id, projection_epoch_id),
    FOREIGN KEY (tenant_id, snapshot_id)
        REFERENCES taedri.graph_snapshot(tenant_id, snapshot_id)
);
CREATE INDEX IF NOT EXISTS projection_epoch_lookup_idx
    ON taedri.projection_epoch(tenant_id, snapshot_id, projection_kind, state, built_at DESC);

CREATE TABLE IF NOT EXISTS taedri.exact_projection (
    tenant_id text NOT NULL,
    projection_epoch_id text NOT NULL,
    lookup_key text NOT NULL,
    lookup_value text NOT NULL,
    subject_id text NOT NULL,
    assertion_id text NOT NULL,
    PRIMARY KEY (tenant_id, projection_epoch_id, lookup_key, lookup_value, subject_id, assertion_id),
    FOREIGN KEY (tenant_id, projection_epoch_id)
        REFERENCES taedri.projection_epoch(tenant_id, projection_epoch_id)
);
CREATE INDEX IF NOT EXISTS exact_projection_lookup_idx
    ON taedri.exact_projection(tenant_id, lookup_key, lookup_value, projection_epoch_id);

CREATE TABLE IF NOT EXISTS taedri.lexical_projection (
    tenant_id text NOT NULL,
    projection_epoch_id text NOT NULL,
    subject_id text NOT NULL,
    descriptor_key text NOT NULL,
    document tsvector NOT NULL,
    assertion_ids jsonb NOT NULL CHECK (jsonb_typeof(assertion_ids) = 'array'),
    PRIMARY KEY (tenant_id, projection_epoch_id, subject_id, descriptor_key),
    FOREIGN KEY (tenant_id, projection_epoch_id)
        REFERENCES taedri.projection_epoch(tenant_id, projection_epoch_id)
);
CREATE INDEX IF NOT EXISTS lexical_projection_gin_idx
    ON taedri.lexical_projection USING gin(document);

CREATE TABLE IF NOT EXISTS taedri.scalar_projection (
    tenant_id text NOT NULL,
    projection_epoch_id text NOT NULL,
    descriptor_key text NOT NULL,
    subject_id text NOT NULL,
    assertion_id text NOT NULL,
    integer_value bigint,
    numeric_value numeric,
    timestamp_value timestamptz,
    keyword_value text,
    PRIMARY KEY (tenant_id, projection_epoch_id, descriptor_key, subject_id, assertion_id),
    FOREIGN KEY (tenant_id, projection_epoch_id)
        REFERENCES taedri.projection_epoch(tenant_id, projection_epoch_id),
    CHECK (num_nonnulls(integer_value, numeric_value, timestamp_value, keyword_value) = 1)
);
CREATE INDEX IF NOT EXISTS scalar_projection_integer_idx
    ON taedri.scalar_projection(tenant_id, descriptor_key, integer_value, subject_id);
CREATE INDEX IF NOT EXISTS scalar_projection_numeric_idx
    ON taedri.scalar_projection(tenant_id, descriptor_key, numeric_value, subject_id);
CREATE INDEX IF NOT EXISTS scalar_projection_keyword_idx
    ON taedri.scalar_projection(tenant_id, descriptor_key, keyword_value, subject_id);

CREATE TABLE IF NOT EXISTS taedri.blocking_projection (
    tenant_id text NOT NULL,
    projection_epoch_id text NOT NULL,
    profile_key text NOT NULL,
    block_key text NOT NULL,
    subject_id text NOT NULL,
    assertion_id text NOT NULL,
    PRIMARY KEY (tenant_id, projection_epoch_id, profile_key, block_key, subject_id, assertion_id),
    FOREIGN KEY (tenant_id, projection_epoch_id)
        REFERENCES taedri.projection_epoch(tenant_id, projection_epoch_id)
);
CREATE INDEX IF NOT EXISTS blocking_projection_lookup_idx
    ON taedri.blocking_projection(tenant_id, profile_key, block_key, projection_epoch_id);

CREATE TABLE IF NOT EXISTS taedri.embedding_projection (
    tenant_id text NOT NULL,
    projection_epoch_id text NOT NULL,
    descriptor_key text NOT NULL,
    subject_id text NOT NULL,
    assertion_id text NOT NULL,
    provider_key text NOT NULL,
    model_key text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    vector_digest text NOT NULL CHECK (vector_digest ~ '^sha256:[0-9a-f]{64}$'),
    vector_values real[],
    vector_ref jsonb,
    PRIMARY KEY (tenant_id, projection_epoch_id, descriptor_key, subject_id, assertion_id),
    FOREIGN KEY (tenant_id, projection_epoch_id)
        REFERENCES taedri.projection_epoch(tenant_id, projection_epoch_id),
    CHECK ((vector_values IS NOT NULL) <> (vector_ref IS NOT NULL)),
    CHECK (vector_values IS NULL OR cardinality(vector_values) = dimensions)
);
CREATE INDEX IF NOT EXISTS embedding_projection_provider_idx
    ON taedri.embedding_projection(
        tenant_id, descriptor_key, provider_key, model_key, projection_epoch_id
    );

CREATE TABLE IF NOT EXISTS taedri.graph_projection (
    tenant_id text NOT NULL,
    projection_epoch_id text NOT NULL,
    predicate_key text NOT NULL,
    source_subject_id text NOT NULL,
    target_subject_id text NOT NULL,
    assertion_id text NOT NULL,
    weight_ppm integer CHECK (weight_ppm BETWEEN 0 AND 1000000),
    PRIMARY KEY (tenant_id, projection_epoch_id, predicate_key, source_subject_id, target_subject_id, assertion_id),
    FOREIGN KEY (tenant_id, projection_epoch_id)
        REFERENCES taedri.projection_epoch(tenant_id, projection_epoch_id)
);
CREATE INDEX IF NOT EXISTS graph_projection_source_idx
    ON taedri.graph_projection(tenant_id, predicate_key, source_subject_id, projection_epoch_id);
CREATE INDEX IF NOT EXISTS graph_projection_target_idx
    ON taedri.graph_projection(tenant_id, predicate_key, target_subject_id, projection_epoch_id);

-- Serving projections are never authoritative. Drop/rebuild them from descriptor,
-- assertion, evidence, and lineage rows when a provider, policy, or index epoch changes.

COMMIT;
