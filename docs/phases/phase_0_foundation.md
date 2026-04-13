# Fase 0 — Foundation
> AURA Backbone v4.3 · Fase 0 di 9

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/00_core.md
docs/spec/07_db_schema.md   (solo §31.1 tabelle tenants/users per riferimento)
```

Non caricare altri file spec in questa sessione.

---

## Obiettivo

Infrastruttura locale funzionante, settings tipizzati, DB connesso con RLS pronto, health check verde, ARQ skeleton avviabile.

---

## Tasks obbligatori

### 0.1 — Settings e config
- `apps/api/config.py` con `pydantic-settings`: DATABASE_URL, REDIS_URL, QDRANT_URL, S3_*, LITELLM_BASE_URL, OKTA_JWKS_URL, LANGFUSE_SECRET_KEY
- `.env.example` con tutti i valori placeholder documentati
- Validazione fail-fast: se una variabile obbligatoria manca, l'app non parte

### 0.2 — DB engine + session factory + RLS connect hook
Implementare esattamente il pattern da `docs/spec/02_services.md §10.3-10.4`:
```python
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET app.current_tenant_id = ''")
    cursor.close()
```

### 0.3 — Alembic
- `infra/alembic/env.py` configurato per async + ruolo `aura_service` (BYPASSRLS)
- Prima migration: tabella `tenants` (schema da `docs/spec/07_db_schema.md §31.1`)
- `alembic upgrade head` deve completare senza errori

### 0.4 — Health endpoint
`GET /api/v1/health` → `HealthResponse` con check reali su postgres, redis, qdrant, s3, litellm, langfuse.
Risponde `degraded` se qualche componente non risponde, non `down` del processo.

### 0.5 — ARQ skeleton
- `apps/worker/worker_settings.py` con `WorkerSettings`
- Due funzioni placeholder: `ingest_document_job` e `agent_run_job` con `raise NotImplementedError`
- Worker avviabile con `arq apps.worker.worker_settings.WorkerSettings`

### 0.6 — Docker Compose local infra
`infra/docker-compose.yml` con:
- postgres:16 (con ruoli `aura_service` e `aura_app` creati al primo avvio via init script)
- redis:7
- qdrant:latest
- minio (S3-compatible)
- litellm-proxy (immagine ufficiale, config minimale con un modello mock)

---

## Struttura file attesa a fine fase

```
apps/api/
  main.py           # FastAPI app con /health
  config.py         # Settings pydantic
apps/worker/
  main.py
  worker_settings.py
infra/
  docker-compose.yml
  init/
    01_roles.sql    # CREATE ROLE aura_app, aura_service
  alembic/
    env.py
    versions/
      001_initial_tenants.py
.env.example
```

---

## Acceptance criteria (GATE — tutti MUST passare prima di Fase 1)

```bash
# 1. Docker Compose up
docker compose up -d
# attende che tutti i servizi siano healthy

# 2. Migration
alembic upgrade head
# exit 0

# 3. Health check verde
curl http://localhost:8000/api/v1/health
# {"status":"ok","components":{"postgres":"ok","redis":"ok",...}}

# 4. Worker avviabile
arq apps.worker.worker_settings.WorkerSettings &
# nessun errore di import o connessione

# 5. RLS smoke test
python -c "
import asyncio
from apps.api.config import settings
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from sqlalchemy import text

async def test():
    async with AsyncSessionLocal() as s:
        async with s.begin():
            await set_tenant_rls(s, '00000000-0000-0000-0000-000000000001')
            val = await s.scalar(text(\"SELECT current_setting('app.current_tenant_id')\"))
            assert val == '00000000-0000-0000-0000-000000000001', f'RLS non impostato: {val}'
    print('RLS OK')

asyncio.run(test())
"
```

---

## Note per Claude Code

- `set_tenant_rls` è una funzione da implementare in `aura/adapters/db/session.py`. Signature: `async def set_tenant_rls(session: AsyncSession, tenant_id: UUID) -> None`. Usa `SET LOCAL` (non `SET`) per garantire il reset a fine transazione.
- Il ruolo `aura_app` NON deve essere il table owner. Il role `aura_service` bypassa RLS ed è usato SOLO da Alembic.
- Non implementare ancora nessuna tabella business oltre `tenants` — questa fase è solo foundation.
