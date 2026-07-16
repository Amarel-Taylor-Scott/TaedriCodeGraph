-- Taedri CodeGraph production control-plane contract.
-- PostgreSQL is authoritative for mutable tenant/ref/job state; graph epochs and
-- source payloads remain immutable objects addressed by digest outside this schema.

BEGIN;

CREATE SCHEMA IF NOT EXISTS taedri;

CREATE TABLE IF NOT EXISTS taedri.schema_migration (
    version bigint PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    artifact_digest text NOT NULL
);

CREATE TABLE IF NOT EXISTS taedri.tenant (
    tenant_id text PRIMARY KEY CHECK (tenant_id LIKE 'uceg:v1:tenant:%'),
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'),
    display_name text NOT NULL CHECK (length(btrim(display_name)) > 0),
    state text NOT NULL CHECK (state IN ('active', 'suspended')),
    created_at timestamptz NOT NULL,
    record jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS taedri.api_key (
    key_id text PRIMARY KEY CHECK (key_id ~ '^[a-f0-9]{24}$'),
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    token_prefix text NOT NULL,
    salt bytea NOT NULL,
    verifier bytea NOT NULL,
    iterations integer NOT NULL CHECK (iterations >= 100000),
    scopes jsonb NOT NULL CHECK (jsonb_typeof(scopes) = 'array'),
    created_at timestamptz NOT NULL,
    last_used_at timestamptz,
    revoked_at timestamptz,
    CHECK (position(token_prefix IN encode(verifier, 'hex')) = 0)
);
CREATE INDEX IF NOT EXISTS api_key_tenant_created_idx
    ON taedri.api_key(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS api_key_active_idx
    ON taedri.api_key(key_id) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS taedri.graph_mount (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    name text NOT NULL CHECK (name ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'),
    adapter_kind text NOT NULL CHECK (adapter_kind IN ('local-poc', 's3-epoch-store')),
    store_locator jsonb NOT NULL,
    current_epoch_id text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS taedri.audit_event (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id text NOT NULL UNIQUE CHECK (event_id LIKE 'sha256:%'),
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    actor text NOT NULL,
    action text NOT NULL,
    resource_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    detail jsonb NOT NULL,
    previous_event_id text,
    UNIQUE (tenant_id, previous_event_id)
);
CREATE INDEX IF NOT EXISTS audit_event_tenant_sequence_idx
    ON taedri.audit_event(tenant_id, sequence DESC);

CREATE TABLE IF NOT EXISTS taedri.job_payload (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    payload_ref text NOT NULL CHECK (payload_ref LIKE 'sha256:%'),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, payload_ref)
);

CREATE TABLE IF NOT EXISTS taedri.worker_job (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    job_id text NOT NULL CHECK (job_id LIKE 'uceg:v1:worker_job:%'),
    queue_name text NOT NULL,
    kind text NOT NULL CHECK (
        kind IN ('acquire', 'extract', 'describe', 'embed', 'index', 'verify',
                 'materialize', 'render', 'benchmark')
    ),
    idempotency_key text NOT NULL,
    priority integer NOT NULL CHECK (priority BETWEEN 0 AND 100),
    created_at timestamptz NOT NULL,
    state text NOT NULL CHECK (
        state IN ('pending', 'leased', 'succeeded', 'dead_letter', 'cancelled')
    ),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    cancellation_requested_at timestamptz,
    cancellation_actor text,
    required_capabilities jsonb NOT NULL CHECK (jsonb_typeof(required_capabilities) = 'array'),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE (tenant_id, queue_name, idempotency_key)
);
CREATE INDEX IF NOT EXISTS worker_job_claim_idx
    ON taedri.worker_job(queue_name, priority DESC, created_at, job_id)
    WHERE state = 'pending';

CREATE TABLE IF NOT EXISTS taedri.worker_lease (
    tenant_id text NOT NULL,
    job_id text NOT NULL,
    lease_id text NOT NULL UNIQUE CHECK (lease_id LIKE 'uceg:v1:worker_lease:%'),
    attempt integer NOT NULL CHECK (attempt > 0),
    worker_id text NOT NULL,
    expires_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, job_id),
    FOREIGN KEY (tenant_id, job_id)
        REFERENCES taedri.worker_job(tenant_id, job_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS worker_lease_expiry_idx
    ON taedri.worker_lease(expires_at);

CREATE TABLE IF NOT EXISTS taedri.worker_event (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id text NOT NULL UNIQUE CHECK (event_id LIKE 'uceg:v1:worker_event:%'),
    tenant_id text NOT NULL,
    job_id text NOT NULL,
    event_kind text NOT NULL CHECK (
        event_kind IN ('enqueued', 'leased', 'succeeded', 'failed_retryable',
                       'dead_lettered', 'lease_expired', 'heartbeat',
                       'cancellation_requested', 'cancelled')
    ),
    occurred_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    FOREIGN KEY (tenant_id, job_id)
        REFERENCES taedri.worker_job(tenant_id, job_id)
);
CREATE INDEX IF NOT EXISTS worker_event_job_idx
    ON taedri.worker_event(tenant_id, job_id, sequence);

CREATE TABLE IF NOT EXISTS taedri.primitive_handle (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    primitive_id text NOT NULL CHECK (primitive_id LIKE 'uceg:v1:primitive:%'),
    namespace text NOT NULL,
    name text NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, primitive_id),
    UNIQUE (tenant_id, namespace, name)
);
CREATE INDEX IF NOT EXISTS primitive_handle_search_idx
    ON taedri.primitive_handle(tenant_id, namespace, name);

CREATE TABLE IF NOT EXISTS taedri.primitive_blob (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    digest text NOT NULL CHECK (digest ~ '^sha256:[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    media_type text NOT NULL,
    object_key text NOT NULL,
    PRIMARY KEY (tenant_id, digest)
);

CREATE TABLE IF NOT EXISTS taedri.primitive_tree (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    tree_id text NOT NULL CHECK (tree_id LIKE 'uceg:v1:primitive_tree:%'),
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, tree_id)
);

CREATE TABLE IF NOT EXISTS taedri.primitive_revision (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    revision_id text NOT NULL CHECK (revision_id LIKE 'uceg:v1:primitive_revision:%'),
    primitive_id text NOT NULL,
    tree_id text NOT NULL,
    created_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, revision_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES taedri.primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, tree_id)
        REFERENCES taedri.primitive_tree(tenant_id, tree_id)
);
CREATE INDEX IF NOT EXISTS primitive_revision_history_idx
    ON taedri.primitive_revision(tenant_id, primitive_id, created_at, revision_id);

CREATE TABLE IF NOT EXISTS taedri.primitive_ref (
    tenant_id text NOT NULL,
    primitive_id text NOT NULL,
    ref_kind text NOT NULL CHECK (ref_kind IN ('branch', 'tag')),
    ref_name text NOT NULL,
    revision_id text NOT NULL,
    updated_sequence bigint NOT NULL CHECK (updated_sequence > 0),
    PRIMARY KEY (tenant_id, primitive_id, ref_kind, ref_name),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES taedri.primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES taedri.primitive_revision(tenant_id, revision_id)
);

CREATE TABLE IF NOT EXISTS taedri.primitive_ref_update (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    update_id text NOT NULL UNIQUE CHECK (update_id LIKE 'uceg:v1:primitive_ref_update:%'),
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    primitive_id text NOT NULL,
    ref_kind text NOT NULL CHECK (ref_kind IN ('branch', 'tag')),
    ref_name text NOT NULL,
    record jsonb NOT NULL,
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES taedri.primitive_handle(tenant_id, primitive_id)
);
CREATE INDEX IF NOT EXISTS primitive_ref_update_history_idx
    ON taedri.primitive_ref_update(tenant_id, primitive_id, sequence);

CREATE TABLE IF NOT EXISTS taedri.primitive_release (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    release_id text NOT NULL CHECK (release_id LIKE 'uceg:v1:primitive_release:%'),
    primitive_id text NOT NULL,
    revision_id text NOT NULL,
    tree_id text NOT NULL,
    ref_kind text NOT NULL CHECK (ref_kind IN ('branch', 'tag')),
    ref_name text NOT NULL,
    source_digest text NOT NULL CHECK (source_digest ~ '^sha256:[0-9a-f]{64}$'),
    language text NOT NULL,
    runtime_version text NOT NULL,
    search_document text NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', search_document)
    ) STORED,
    released_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, release_id),
    UNIQUE (tenant_id, primitive_id, ref_kind, ref_name, revision_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES taedri.primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES taedri.primitive_revision(tenant_id, revision_id),
    FOREIGN KEY (tenant_id, tree_id)
        REFERENCES taedri.primitive_tree(tenant_id, tree_id)
);
CREATE INDEX IF NOT EXISTS primitive_release_ref_idx
    ON taedri.primitive_release(
        tenant_id, primitive_id, ref_kind, ref_name, released_at DESC
    );
CREATE INDEX IF NOT EXISTS primitive_release_source_idx
    ON taedri.primitive_release(tenant_id, source_digest);

CREATE TABLE IF NOT EXISTS taedri.primitive_release_revocation (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    revocation_id text NOT NULL,
    release_id text NOT NULL,
    primitive_id text NOT NULL,
    revision_id text NOT NULL,
    revoked_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, revocation_id),
    UNIQUE (tenant_id, release_id),
    FOREIGN KEY (tenant_id, release_id)
        REFERENCES taedri.primitive_release(tenant_id, release_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES taedri.primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES taedri.primitive_revision(tenant_id, revision_id)
);
CREATE INDEX IF NOT EXISTS primitive_release_revocation_lookup_idx
    ON taedri.primitive_release_revocation(tenant_id, primitive_id, revoked_at);
CREATE INDEX IF NOT EXISTS primitive_release_search_idx
    ON taedri.primitive_release USING gin(search_vector);

CREATE TABLE IF NOT EXISTS taedri.candidate_submission (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    submission_id text NOT NULL CHECK (submission_id LIKE 'uceg:v1:candidate_submission:%'),
    primitive_id text NOT NULL,
    revision_id text NOT NULL,
    current_state text NOT NULL CHECK (
        current_state IN ('received', 'quarantined', 'structurally_valid',
                          'indexed_candidate', 'curated_candidate', 'rejected', 'revoked')
    ),
    visibility text NOT NULL CHECK (visibility IN ('private', 'organization', 'public')),
    license_evidence_state text NOT NULL CHECK (
        license_evidence_state IN ('unknown', 'declared', 'verified', 'conflicting')
    ),
    submitted_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, submission_id),
    FOREIGN KEY (tenant_id, primitive_id)
        REFERENCES taedri.primitive_handle(tenant_id, primitive_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES taedri.primitive_revision(tenant_id, revision_id)
);
CREATE INDEX IF NOT EXISTS candidate_submission_state_idx
    ON taedri.candidate_submission(tenant_id, current_state, submitted_at DESC);

CREATE TABLE IF NOT EXISTS taedri.candidate_state_event (
    tenant_id text NOT NULL,
    submission_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    event_id text NOT NULL CHECK (event_id LIKE 'uceg:v1:candidate_state_event:%'),
    to_state text NOT NULL,
    occurred_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, submission_id, sequence),
    UNIQUE (tenant_id, event_id),
    FOREIGN KEY (tenant_id, submission_id)
        REFERENCES taedri.candidate_submission(tenant_id, submission_id)
);
CREATE INDEX IF NOT EXISTS candidate_state_event_time_idx
    ON taedri.candidate_state_event(tenant_id, occurred_at, event_id);

CREATE TABLE IF NOT EXISTS taedri.prompt_session (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    session_id text NOT NULL CHECK (session_id LIKE 'uceg:v1:prompt_session:%'),
    workspace_id text NOT NULL,
    privacy_mode text NOT NULL CHECK (
        privacy_mode IN ('digest_only', 'encrypted_reference', 'explicit_capture')
    ),
    started_at timestamptz NOT NULL,
    closed_at timestamptz,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, session_id)
);
CREATE INDEX IF NOT EXISTS prompt_session_workspace_idx
    ON taedri.prompt_session(tenant_id, workspace_id, started_at DESC, session_id);

CREATE TABLE IF NOT EXISTS taedri.prompt_session_event (
    tenant_id text NOT NULL,
    session_id text NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    event_id text NOT NULL CHECK (event_id LIKE 'uceg:v1:prompt_session_event:%'),
    event_kind text NOT NULL CHECK (
        event_kind IN ('session_started', 'request_captured', 'search_receipt',
                       'candidate_selected', 'materialization_receipt', 'model_attempt',
                       'verification_receipt', 'result_accepted', 'abstained',
                       'session_closed')
    ),
    occurred_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, session_id, sequence),
    UNIQUE (tenant_id, event_id),
    FOREIGN KEY (tenant_id, session_id)
        REFERENCES taedri.prompt_session(tenant_id, session_id)
);
CREATE INDEX IF NOT EXISTS prompt_session_event_time_idx
    ON taedri.prompt_session_event(tenant_id, occurred_at, event_id);

CREATE TABLE IF NOT EXISTS taedri.usage_limit_revision (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    limit_id text NOT NULL CHECK (limit_id LIKE 'uceg:v1:usage_limit_revision:%'),
    metric text NOT NULL CHECK (metric ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'),
    window_seconds integer NOT NULL CHECK (window_seconds BETWEEN 1 AND 31536000),
    hard_limit bigint NOT NULL CHECK (hard_limit > 0),
    effective_at timestamptz NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, limit_id)
);
CREATE INDEX IF NOT EXISTS usage_limit_effective_idx
    ON taedri.usage_limit_revision(tenant_id, metric, effective_at DESC, limit_id DESC);

CREATE TABLE IF NOT EXISTS taedri.usage_event (
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    usage_id text NOT NULL CHECK (usage_id LIKE 'uceg:v1:usage_receipt:%'),
    metric text NOT NULL CHECK (metric ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'),
    quantity bigint NOT NULL CHECK (quantity > 0),
    occurred_at timestamptz NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL CHECK (window_end > window_start),
    idempotency_key text NOT NULL,
    resource_id text NOT NULL,
    record jsonb NOT NULL,
    PRIMARY KEY (tenant_id, usage_id),
    UNIQUE (tenant_id, metric, idempotency_key)
);
CREATE INDEX IF NOT EXISTS usage_event_window_idx
    ON taedri.usage_event(tenant_id, metric, occurred_at, usage_id);

CREATE TABLE IF NOT EXISTS taedri.subscription_revision (
    sequence bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    revision_id text NOT NULL CHECK (revision_id LIKE 'uceg:v1:subscription_revision:%'),
    plan_ref text NOT NULL,
    state text NOT NULL CHECK (
        state IN ('trialing', 'active', 'past_due', 'paused', 'cancelled', 'expired')
    ),
    provider text NOT NULL,
    provider_customer_ref text NOT NULL,
    provider_subscription_ref text NOT NULL,
    effective_at timestamptz NOT NULL,
    ends_at timestamptz,
    source_event_id text NOT NULL,
    record jsonb NOT NULL,
    UNIQUE (tenant_id, revision_id),
    UNIQUE (provider, provider_subscription_ref, source_event_id)
);
CREATE INDEX IF NOT EXISTS subscription_revision_current_idx
    ON taedri.subscription_revision(tenant_id, sequence DESC);

CREATE TABLE IF NOT EXISTS taedri.billing_event (
    provider text NOT NULL,
    source_event_id text NOT NULL,
    tenant_id text NOT NULL REFERENCES taedri.tenant(tenant_id),
    revision_id text NOT NULL,
    source_event_digest text NOT NULL CHECK (
        source_event_digest ~ '^sha256:[0-9a-f]{64}$'
    ),
    received_at timestamptz NOT NULL,
    PRIMARY KEY (provider, source_event_id),
    FOREIGN KEY (tenant_id, revision_id)
        REFERENCES taedri.subscription_revision(tenant_id, revision_id)
);
CREATE INDEX IF NOT EXISTS billing_event_tenant_idx
    ON taedri.billing_event(tenant_id, received_at, source_event_id);

-- PostgreSQL workers claim with SELECT ... FOR UPDATE SKIP LOCKED inside a short
-- transaction, then insert worker_lease and append worker_event before committing.
-- API roles receive only tenant-filtered repository methods. Cross-tenant workers use
-- a separately credentialed role and still preserve tenant_id on every operation.

COMMIT;
