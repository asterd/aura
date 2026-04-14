# AURA Spec — §31: DB Schema Baseline
> Source: AURA Backbone v4.3
> ⚠️ Nomi di tabella e colonna sono VINCOLANTI. Non rinominare.

## 31. DB schema baseline

Questa sezione è normativa. I nomi di tabella e colonna sono vincolanti.

### 31.1 Tabelle core

```sql
-- TENANTS
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    okta_org_id TEXT UNIQUE,
    auth_mode TEXT NOT NULL DEFAULT 'okta' CHECK (auth_mode IN ('okta','local')),
    okta_jwks_url TEXT,
    okta_issuer TEXT,
    okta_audience TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- USERS
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    okta_sub TEXT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    roles TEXT[] NOT NULL DEFAULT '{}',
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, okta_sub)
);

-- GROUPS
CREATE TABLE groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    external_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, external_id)
);

-- USER_GROUP_MEMBERSHIPS
CREATE TABLE user_group_memberships (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, group_id)
);

-- LOCAL_AUTH_USERS
CREATE TABLE local_auth_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    roles TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, email)
);
```

### 31.2 Knowledge spaces e documenti

```sql
-- KNOWLEDGE_SPACES
CREATE TABLE knowledge_spaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    space_type TEXT NOT NULL CHECK (space_type IN ('personal','team','enterprise')),
    visibility TEXT NOT NULL CHECK (visibility IN ('private','team','enterprise')),
    source_access_mode TEXT NOT NULL DEFAULT 'space_acl_only'
        CHECK (source_access_mode IN ('space_acl_only','source_acl_enforced')),
    embedding_profile_id UUID NOT NULL,
    retrieval_profile_id UUID NOT NULL,
    pii_policy_id UUID,
    tone_profile_id UUID,
    system_instructions TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, slug)
);

-- SPACE_MEMBERSHIPS
CREATE TABLE space_memberships (
    space_id UUID NOT NULL REFERENCES knowledge_spaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'reader' CHECK (role IN ('reader','editor','admin')),
    PRIMARY KEY (space_id, user_id)
);

-- DATASOURCES
CREATE TABLE datasources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    space_id UUID NOT NULL REFERENCES knowledge_spaces(id),
    connector_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    credentials_ref TEXT NOT NULL,         -- secret_ref, mai il valore
    sync_cursor TEXT,
    last_sync_at TIMESTAMPTZ,
    last_sync_status TEXT CHECK (last_sync_status IN ('ok','partial','failed','auth_error','stale')),
    stale_threshold_s INT NOT NULL DEFAULT 86400,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- DOCUMENTS
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    space_id UUID NOT NULL REFERENCES knowledge_spaces(id),
    datasource_id UUID REFERENCES datasources(id),
    external_id TEXT,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_url TEXT,
    content_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'discovered'
        CHECK (status IN ('discovered','fetched','parsed','canonicalized','indexed','active','deleted','error')),
    current_version_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- DOCUMENT_VERSIONS
CREATE TABLE document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    version_hash TEXT NOT NULL,            -- SHA256 del canonical text
    s3_canonical_ref TEXT,                 -- S3 key del canonical text
    s3_original_ref TEXT,                  -- S3 key dell'originale
    chunk_count INT,
    indexed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 31.3 Conversazioni e messaggi

```sql
-- CONVERSATIONS
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL REFERENCES users(id),
    space_ids UUID[] NOT NULL DEFAULT '{}',
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- MESSAGES
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content TEXT NOT NULL,                 -- trasformato secondo PiiPolicy
    trace_id TEXT,
    model_used TEXT,
    tokens_used INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- MESSAGE_CITATIONS
CREATE TABLE message_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    citation_id TEXT NOT NULL,
    document_id UUID NOT NULL REFERENCES documents(id),
    document_version_id UUID NOT NULL REFERENCES document_versions(id),
    chunk_id UUID NOT NULL,
    score FLOAT NOT NULL,
    snippet TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 31.4 Agent e skill registry

```sql
-- AGENT_PACKAGES
CREATE TABLE agent_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    UNIQUE (tenant_id, name)
);

-- AGENT_VERSIONS
CREATE TABLE agent_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_package_id UUID NOT NULL REFERENCES agent_packages(id),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    version TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK (agent_type IN ('single','orchestrator')),
    entrypoint TEXT NOT NULL,
    manifest JSONB NOT NULL,
    artifact_ref TEXT NOT NULL,            -- S3 key del .zip immutabile
    artifact_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','validated','published','deprecated')),
    model_policy_id UUID,
    pii_policy_id UUID,
    sandbox_policy_id UUID,
    max_budget_usd NUMERIC(10,4),
    timeout_s INT NOT NULL DEFAULT 120,
    published_at TIMESTAMPTZ,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agent_package_id, version)
);

-- AGENT_RUNS
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    agent_version_id UUID NOT NULL REFERENCES agent_versions(id),
    user_id UUID NOT NULL REFERENCES users(id),
    conversation_id UUID REFERENCES conversations(id),
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
    input_ref TEXT,                        -- S3 key se input grande
    output_data JSONB,
    output_text TEXT,
    error_message TEXT,
    trace_id TEXT,
    cost_usd NUMERIC(10,6),
    artifact_refs TEXT[] DEFAULT '{}',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- SKILL_PACKAGES e SKILL_VERSIONS (struttura analoga ad AGENT)
CREATE TABLE skill_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    UNIQUE (tenant_id, name)
);

CREATE TABLE skill_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_package_id UUID NOT NULL REFERENCES skill_packages(id),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    version TEXT NOT NULL,
    entrypoint TEXT NOT NULL,
    manifest JSONB NOT NULL,
    artifact_ref TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','validated','published','deprecated')),
    sandbox_policy_id UUID,
    timeout_s INT NOT NULL DEFAULT 120,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (skill_package_id, version)
);
```

### 31.5 Policy e profile tables

```sql
-- Ogni policy/profile è una tabella separata.
-- Struttura comune: id, tenant_id, name, is_default, created_at, updated_at.
-- I campi specifici corrispondono ai contratti §8.8–8.11.

CREATE TABLE model_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    default_model TEXT NOT NULL,
    allowed_models TEXT[] NOT NULL DEFAULT '{}',
    max_tokens INT NOT NULL DEFAULT 4096,
    temperature FLOAT NOT NULL DEFAULT 0.2,
    context_window_limit INT NOT NULL DEFAULT 128000,
    rate_limit_rpm INT,
    rate_limit_tpd INT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE pii_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('off','detect_only','mask_inference_only','mask_persist_and_inference','pseudonymize_rehydratable')),
    entities_to_detect TEXT[] NOT NULL DEFAULT '{}',
    score_threshold FLOAT NOT NULL DEFAULT 0.7,
    persist_mapping BOOLEAN NOT NULL DEFAULT FALSE,
    mapping_ttl_days INT,
    allow_raw_in_logs BOOLEAN NOT NULL DEFAULT FALSE,
    allow_raw_in_traces BOOLEAN NOT NULL DEFAULT FALSE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE sandbox_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    network_egress TEXT NOT NULL DEFAULT 'none' CHECK (network_egress IN ('none','allowlist')),
    egress_allowlist TEXT[] NOT NULL DEFAULT '{}',
    max_cpu_seconds INT NOT NULL DEFAULT 60,
    max_memory_mb INT NOT NULL DEFAULT 512,
    max_wall_time_s INT NOT NULL DEFAULT 120,
    writable_paths TEXT[] NOT NULL DEFAULT '{"/workspace","/artifacts"}',
    env_vars_allowed TEXT[] NOT NULL DEFAULT '{}',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE retrieval_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    top_k INT NOT NULL DEFAULT 10,
    rerank_top_k INT NOT NULL DEFAULT 5,
    score_threshold FLOAT NOT NULL DEFAULT 0.0,
    dense_weight FLOAT NOT NULL DEFAULT 0.7,
    sparse_weight FLOAT NOT NULL DEFAULT 0.3,
    reranker TEXT NOT NULL DEFAULT 'none' CHECK (reranker IN ('none','cross-encoder-local','litellm-rerank')),
    reranker_model TEXT,
    query_rewrite_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    query_rewrite_model TEXT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE embedding_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    litellm_model TEXT NOT NULL,
    dimensions INT NOT NULL,
    chunk_size INT NOT NULL,
    chunk_overlap INT NOT NULL,
    splitter TEXT NOT NULL DEFAULT 'sentence' CHECK (splitter IN ('sentence','token','semantic')),
    batch_size INT NOT NULL DEFAULT 64,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE tone_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name TEXT NOT NULL,
    prompt_snippet TEXT NOT NULL,
    language TEXT,
    formality TEXT NOT NULL DEFAULT 'neutral' CHECK (formality IN ('formal','neutral','casual')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);
```

### 31.6 Audit log

```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,                  -- e.g. "chat.respond", "agent.run", "space.create"
    resource_type TEXT NOT NULL,
    resource_id UUID,
    trace_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',  -- no PII raw se policy lo vieta
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX audit_log_tenant_created ON audit_log (tenant_id, created_at DESC);
```

### 31.7 RLS policies

```sql
-- Abilitare RLS su tutte le tabelle business
ALTER TABLE knowledge_spaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
-- ... (tutte le tabelle con tenant_id)

-- FORCE ROW LEVEL SECURITY: obbligatorio per le tabelle dove il ruolo applicativo
-- potrebbe coincidere con il table owner. Per sicurezza difensiva, applicarlo su tutte.
ALTER TABLE knowledge_spaces FORCE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE messages FORCE ROW LEVEL SECURITY;
-- ... (tutte le tabelle con tenant_id)

-- Policy pattern (replicare per ogni tabella)
CREATE POLICY tenant_isolation ON knowledge_spaces
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- Ruolo applicativo runtime: MUST NOT essere il table owner.
-- Il table owner bypassa RLS per default, vanificando l'intera strategia di tenancy.
-- Creare un ruolo separato con GRANT espliciti, senza permessi di ownership.
CREATE ROLE aura_app NOINHERIT;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aura_app;
-- L'applicazione FastAPI e i worker ARQ DEVONO connettersi come aura_app, non come postgres o aura_service.

-- Service role bypassa RLS solo per migration e operazioni admin di sistema
CREATE ROLE aura_service;
ALTER ROLE aura_service BYPASSRLS;
-- aura_service è usato SOLO da Alembic e da script di admin. MAI dall'applicazione runtime.

## 31.8 LLM provider governance

Tabelle aggiuntive previste:

- `llm_providers`
- `tenant_provider_credentials`
- `tenant_model_configs`
- `cost_budgets`
- `llm_usage_records`

Vincoli minimi:

- provider canonicale unico per `provider_key`
- credential unica per `tenant_id + provider_id + name`
- model config unica per `tenant_id + provider_id + task_type + model_name`
- budget unico per `(tenant_id, scope_type, scope_ref, provider_id, model_name, window)`

Regole:

- `secret_ref` è persistito, mai la chiave in chiaro
- tutte le tabelle tenant-scoped devono essere coperte da RLS
- `llm_usage_records` deve supportare aggregazioni per tenant, user, provider, model e space
```

> ⚠️ **Pitfall critico verificato in produzione**: il pattern più comune di fallimento RLS è eseguire l'applicazione con il ruolo che ha creato le tabelle (spesso `postgres` o il ruolo owner). In quel caso RLS non viene applicato e le query restituiscono dati cross-tenant senza errori. Testare sempre con il ruolo `aura_app` in CI, non con il ruolo di migration.

> ⚠️ **Compatibilità pgbouncer**: `SET LOCAL app.current_tenant_id` è incompatibile con pgbouncer in `transaction` o `statement` pooling mode. AURA usa asyncpg nativo senza pgbouncer. Se pgbouncer viene aggiunto in futuro, MUST usare `session` mode. Vedere §10.8.

---
