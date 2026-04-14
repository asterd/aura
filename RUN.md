# RUN.md

Guida operativa per avviare AURA in locale nelle varie modalità, con comandi, porte, URL, prerequisiti e limiti noti emersi dal codice attuale del repository.

## 1. Panorama rapido

L'architettura runtime del repo è composta da:

- `Postgres` per persistenza e RLS
- `Redis` per coda job ARQ / scheduling
- `Qdrant` per retrieval vettoriale
- `MinIO` per storage documenti e artifact
- `LiteLLM Proxy` per chat / embeddings verso modelli LLM
- `FastAPI` (`apps/api/main.py`) come backend
- `ARQ Worker` (`apps/worker/worker_settings.py`) per ingestion, sync, trigger, agent jobs
- `Next.js` (`apps/web`) come frontend

La modalità consigliata per sviluppo è:

1. Infra in Docker
2. API in locale
3. Worker in locale
4. Frontend in locale

## 2. Prerequisiti

Servono almeno:

- Python `3.12.x`
- Node.js `>= 20`
- Docker + Docker Compose
- `npm`

Il progetto usa dipendenze Python da [pyproject.toml](/Users/ddurzo/Development/ai/aura/pyproject.toml:1) e frontend Next da [apps/web/package.json](/Users/ddurzo/Development/ai/aura/apps/web/package.json:1).

## 3. Variabili ambiente

Base env:

1. Copiare `.env.example` su `.env` se necessario.
2. Verificare che le URL puntino ai servizi locali.

Il file attuale [.env](/Users/ddurzo/Development/ai/aura/.env:1) contiene già i valori locali minimi per:

- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- Qdrant: `localhost:6333`
- MinIO API: `localhost:9000`
- MinIO Console: `localhost:9001`
- LiteLLM: `localhost:4000`

Variabili importanti:

- `DATABASE_URL`: runtime API/worker con ruolo `aura_app`
- `ALEMBIC_DATABASE_URL`: migrazioni con ruolo `aura_service`
- `OKTA_JWKS_URL`, `OKTA_ISSUER`, `OKTA_AUDIENCE`: autenticazione JWT
- `LANGFUSE_BASE_URL`, `LANGFUSE_SECRET_KEY`: health/prompt fallback
- `SANDBOX_PROVIDER`: default `docker`

## 4. Porte e URL

Servizi locali previsti:

- API FastAPI: `http://localhost:8000`
- Swagger/OpenAPI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/v1/health`
- Frontend Next.js: `http://localhost:3000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- Qdrant HTTP: `http://localhost:6333`
- Qdrant gRPC: `localhost:6334`
- MinIO API: `http://localhost:9000`
- MinIO Console: `http://localhost:9001`
- LiteLLM Proxy: `http://localhost:4000`

Nota importante: il compose incluso **non** avvia Langfuse né un provider JWKS/Okta locale.

## 5. Setup locale iniziale

### 5.1 Python backend

Dal root repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[test]"
```

### 5.2 Frontend

```bash
cd apps/web
npm install
cd ../..
```

## 6. Modalità di avvio

### Modalità A: solo infrastruttura

Avvia solo i servizi containerizzati:

```bash
docker compose up -d
```

In alternativa:

```bash
docker compose -f infra/docker-compose.yml up -d
```

Il file root [compose.yaml](/Users/ddurzo/Development/ai/aura/compose.yaml:1) e [infra/docker-compose.yml](/Users/ddurzo/Development/ai/aura/infra/docker-compose.yml:1) espongono gli stessi componenti base.

Questa modalità è utile per:

- preparare DB/queue/vector store/storage
- fare smoke test dell'infra
- sviluppare API/worker in locale

### Modalità B: backend API locale

Dopo aver avviato l'infra:

```bash
source .venv/bin/activate
alembic upgrade head
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

Verifiche:

```bash
curl http://localhost:8000/api/v1/health
```

### Modalità C: worker locale

In una seconda shell:

```bash
source .venv/bin/activate
arq apps.worker.worker_settings.WorkerSettings
```

Il worker serve per:

- ingestion documenti
- connector sync
- identity sync schedulato
- run di agenti
- cron trigger / event trigger

### Modalità D: frontend locale

In una terza shell:

```bash
cd apps/web
npm run dev
```

Il frontend usa una rewrite Next definita in [apps/web/next.config.ts](/Users/ddurzo/Development/ai/aura/apps/web/next.config.ts:1) che inoltra `/api/v1/*` verso `http://localhost:8000`.

### Modalità E: stack completo consigliato

Aprire 4 terminali:

1. `docker compose up -d`
2. `source .venv/bin/activate && alembic upgrade head && uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000`
3. `source .venv/bin/activate && arq apps.worker.worker_settings.WorkerSettings`
4. `cd apps/web && npm run dev`

## 7. Autenticazione locale

Il backend protegge quasi tutti gli endpoint tramite bearer JWT. Solo `/api/v1/health` è realmente utilizzabile senza token.

Il frontend:

- legge il token dal cookie `aura_token`
- permette di incollarlo manualmente nella pagina `/login`
- inoltra il token come header `Authorization: Bearer ...`

Riferimenti:

- [apps/api/dependencies/auth.py](/Users/ddurzo/Development/ai/aura/apps/api/dependencies/auth.py:1)
- [apps/web/src/middleware.ts](/Users/ddurzo/Development/ai/aura/apps/web/src/middleware.ts:1)
- [apps/web/src/app/login/page.tsx](/Users/ddurzo/Development/ai/aura/apps/web/src/app/login/page.tsx:1)

Claim minimi richiesti dal JWT:

- `exp`
- `iss`
- `aud`
- `sub`
- `email`
- `tenant_id` oppure `tid`

Claim opzionali usati dal sistema:

- `name`
- `roles`
- `groups`

### Per usare davvero i flussi autenticati hai 2 opzioni

1. Configurare `OKTA_JWKS_URL` / `OKTA_ISSUER` / `OKTA_AUDIENCE` contro un IdP reale.
2. Esporre un JWKS locale compatibile e firmare token coerenti con quei valori.

Senza questa parte:

- il backend si avvia
- `/health` funziona
- gli endpoint autenticati rispondono `401`
- il frontend arriva a `/login` ma non completa i flussi applicativi

## 8. Dipendenze esterne che impattano i flussi

### 8.1 LiteLLM / modelli

Il proxy LiteLLM locale viene avviato dal compose, ma il file [infra/litellm/config.yaml](/Users/ddurzo/Development/ai/aura/infra/litellm/config.yaml:1) contiene un modello placeholder:

- `model_name: mock-model`
- backend provider `gpt-4o-mini`
- `api_key: sk-placeholder`

Quindi:

- il proxy parte
- l'health del proxy può risultare verde
- chat/embeddings reali richiedono una configurazione valida del provider LLM

Per usare retrieval/chat/ingestion reali serve aggiornare `infra/litellm/config.yaml` con credenziali vere del provider.

### 8.2 Langfuse

`LANGFUSE_BASE_URL` punta a `http://localhost:3000`, ma quel porto è usato dal frontend Next e nel compose non esiste un servizio Langfuse.

Effetto pratico:

- il backend si avvia comunque
- `/health` risulta verosimilmente `degraded` sul componente `langfuse`

### 8.3 Sandbox skill

Il provider sandbox di default è `docker`.

Per i run skill:

- Docker deve essere disponibile anche fuori dai container
- il componente `sandbox` del health può andare `down` senza far cadere l'API

## 9. Capability operative per modalità

### Infra only

Disponibile:

- Postgres
- Redis
- Qdrant
- MinIO
- LiteLLM proxy

Non disponibile:

- API
- worker
- UI

### API only

Disponibile:

- `GET /api/v1/health`
- Swagger `/docs`
- endpoint autenticati se hai JWT valido

Non disponibile completamente:

- ingestion async
- trigger/cron
- background jobs ARQ

### API + worker

Disponibile:

- upload datasource con job enqueue
- ingestion documenti
- connector sync
- identity sync
- cron/event triggered runs
- run skill/agent che dipendono dal worker

### API + worker + web

Disponibile come shell applicativa:

- login locale via token
- chat UI
- sidebar UI
- upload UI
- settings/logout

Caveat attuale: il frontend non è completamente allineato con tutti gli endpoint esposti dal backend. In particolare dal codice emergono aspettative UI per endpoint/shape non presenti o non coincidenti, ad esempio:

- lista agenti UI su `/api/v1/agents`
- conversazioni/messaggi con shape paginata
- signed URL artifact `/api/v1/artifacts/{id}/signed-url`

Quindi, allo stato attuale, la modalità più affidabile per validare le capability core resta `API + worker`, con test via Swagger/curl/client HTTP.

## 10. Endpoint backend principali

Endpoint certamente esposti:

- `GET /api/v1/health`
- `GET /api/v1/me`
- `POST /api/v1/chat/retrieve`
- `POST /api/v1/chat/respond`
- `POST /api/v1/chat/stream`
- `GET /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`
- `POST /api/v1/datasources/upload`
- CRUD base spazi sotto `/api/v1/spaces`
- `POST /api/v1/agents/{name}/run`
- admin agent upload/publish/list sotto `/api/v1/admin/agents`
- admin skill upload/publish/list sotto `/api/v1/admin/skills`
- `POST /api/v1/skills/{name}/run`
- `GET /mcp/v1/sse`
- `POST /mcp/v1/sse/messages/{session_id}`
- `POST /api/v1/webhooks/{agent_name}/inbound`

## 11. Smoke test consigliato

### Step 1

```bash
docker compose up -d
```

### Step 2

```bash
source .venv/bin/activate
alembic upgrade head
```

### Step 3

```bash
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4

```bash
curl http://localhost:8000/api/v1/health
```

### Step 5

```bash
arq apps.worker.worker_settings.WorkerSettings
```

### Step 6

```bash
cd apps/web
npm run dev
```

### Step 7

Aprire `http://localhost:3000`.

## 12. Troubleshooting rapido

### Health `degraded`

Atteso se manca uno di questi:

- JWKS/Okta raggiungibile
- Langfuse raggiungibile
- Docker disponibile per sandbox

### `401 Authentication required`

Cause tipiche:

- nessun bearer token
- JWT non valido
- `iss` / `aud` non coerenti con `.env`
- token senza `tenant_id`

### Upload fermo / ingestion non parte

Controllare:

- worker ARQ attivo
- Redis attivo
- LiteLLM configurato davvero
- bucket MinIO creato

### Frontend aperto ma flussi rotti

Verificare prima backend/API via `/docs`: al momento il frontend non è perfettamente allineato a tutti gli endpoint realmente implementati.

## 13. Modalità consigliata per lavorare oggi

Se vuoi la modalità più solida:

1. `docker compose up -d`
2. `alembic upgrade head`
3. API locale
4. worker locale
5. test dei flussi via Swagger/curl

Se vuoi anche ispezionare la UI:

6. avvia anche `apps/web`
7. considera il frontend come shell in progresso, non come superficie totalmente validata end-to-end
