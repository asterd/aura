# AURA Spec — §36: Triggered & Autonomous Agents
> Addendum v1.0 · Aprile 2026
> Estende §17.1 — aggiunge tipo `triggered` e `autonomous` al runtime agenti

---

## 36. Triggered & Autonomous Agents

### 36.1 Classificazione tipi agente (estesa)

Estende la classificazione di §17.1:

| Tipo | Esecuzione | Trigger | Use case |
|---|---|---|---|
| `single` | Puntuale su request | API call o chat | Analisi contratto, risposta domanda |
| `orchestrator` | Puntuale, delega | API call o chat | Workflow multi-step con sub-agenti |
| `triggered` | Event-driven | Webhook, evento documento, cambio ACL | Notifica su nuovo documento, sync automatico |
| `autonomous` | Schedule-based | Cron expression | Report periodici, data quality check |

---

### 36.2 Contratti trigger

```python
# CONTRACT — aggiunto a aura/domain/contracts.py
class CronTrigger(BaseModel):
    type: Literal["cron"] = "cron"
    cron_expression: str          # standard 5-field cron (UTC)
    max_runs: int | None = None   # None = illimitato
    run_as_service_identity: bool = True

class EventTrigger(BaseModel):
    type: Literal["event"] = "event"
    event_type: Literal[
        "document.ingested",
        "document.updated",
        "document.deleted",
        "space.member_added",
        "space.member_removed",
        "webhook.inbound",
    ]
    space_ids: list[UUID] = Field(default_factory=list)  # vuota = tutti gli spaces
    filter_tags: list[str] = Field(default_factory=list)  # filtra per tag documento
    webhook_secret_ref: str | None = None  # per event_type="webhook.inbound"

AgentTrigger = CronTrigger | EventTrigger
```

---

### 36.3 Manifest esteso per agenti triggered/autonomous

Il manifest YAML degli agenti (§17.2) viene esteso con il campo opzionale `triggers`:

```yaml
# Esempio manifest agente autonomous
agent_name: weekly-space-report
agent_type: autonomous            # nuovo tipo
version: "1.0.0"
entrypoint: "weekly_report.agent:build"
allowed_tools: ["retrieval", "document_list"]
allowed_spaces: []                # [] = tutti gli spaces del tenant
triggers:
  - type: cron
    cron_expression: "0 8 * * 1"  # ogni lunedì alle 08:00 UTC
    max_runs: null
    run_as_service_identity: true
policy_ids: []
max_budget: 0.50
timeout: 300
documentation:
  purpose: "Genera un report settimanale sullo stato degli spaces."
  limitations: "Non invia email — produce solo artifact markdown."
  risk_level: "low"
  owner: "platform-team"
```

```yaml
# Esempio manifest agente triggered
agent_name: contract-ingestion-notifier
agent_type: triggered
version: "1.0.0"
entrypoint: "contract_notifier.agent:build"
allowed_tools: ["retrieval", "send_notification"]
allowed_spaces: ["contracts-space-uuid"]
triggers:
  - type: event
    event_type: document.ingested
    space_ids: ["contracts-space-uuid"]
    filter_tags: ["contract", "legal"]
policy_ids: []
max_budget: 0.10
timeout: 60
```

**Regole manifest:**
- `triggers` è obbligatorio per `autonomous` e `triggered`, proibito per `single` e `orchestrator`.
- `cron_expression` deve essere una stringa cron 5-field valida; il backend la valida al publish.
- `run_as_service_identity: true` (default per cron) — il run avviene con una `UserIdentity` di tipo `is_service_identity=True` associata al tenant.

---

### 36.4 TriggerSchedulerService

**Responsabilità:**
- Al publish di un agente con `CronTrigger`: registrare il cron in ARQ (tramite `arq.cron`).
- Al retire/unpublish: de-registrare il cron.
- Gestire il `max_runs` decrementando un counter su Redis; quando `max_runs` è raggiunto, de-registrare automaticamente.

**Pseudocodice normativo:**

```python
class TriggerSchedulerService:
    async def register_cron(self, agent_version_id: UUID, trigger: CronTrigger) -> None:
        # 1. Costruire job key unico: f"agent_cron:{agent_version_id}"
        # 2. Registrare ARQ cron job con la cron_expression
        # 3. Persistere su DB: tabella agent_trigger_registrations
        # 4. Log: trigger registered

    async def deregister_cron(self, agent_version_id: UUID) -> None:
        # 1. Rimuovere ARQ cron job
        # 2. Aggiornare DB: status = "deregistered"
        # 3. Log: trigger deregistered

    async def execute_cron_run(self, agent_version_id: UUID) -> None:
        # 1. Verificare max_runs non raggiunto
        # 2. Costruire service identity per il tenant
        # 3. Costruire AgentRunRequest con input = {} (o input_template dal manifest)
        # 4. Delegare ad AgentService.run_agent
        # 5. Incrementare counter runs su Redis
        # 6. Loggare run result
```

**MUST NOT:**
- `TriggerSchedulerService` MUST NOT aprire una sessione DB autonoma — ricevere session iniettata.
- Non usare Celery beat — esclusivamente ARQ cron.

---

### 36.5 EventDispatcherService

**Responsabilità:**
- Pubblicare eventi interni su un canale Redis Pub/Sub (non Kafka, non RabbitMQ — §3).
- Ricevere eventi pubblicati e fare match con i trigger registrati.
- Per ciascun match, accodare un job ARQ per l'esecuzione dell'agente.

**Canali Redis:**

```
aura:events:{tenant_id}:{event_type}
```

**Pseudocodice normativo:**

```python
class EventDispatcherService:
    async def publish(self, tenant_id: UUID, event: InternalEvent) -> None:
        channel = f"aura:events:{tenant_id}:{event.event_type}"
        await redis.publish(channel, event.model_dump_json())

    async def subscribe_and_dispatch(self) -> None:
        # Worker ARQ separato, non nel processo API
        # 1. Subscribe a aura:events:*
        # 2. Per ogni messaggio: deserializzare InternalEvent
        # 3. Query DB: agent_trigger_registrations con event_type matching
        # 4. Per ciascun trigger attivo: verificare space_ids e filter_tags
        # 5. Accodare job ARQ: execute_event_triggered_run(agent_version_id, event)
```

**Contratto evento interno:**

```python
# CONTRACT
class InternalEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    event_type: str
    source_entity_id: UUID | None = None  # es. document_id per document.ingested
    source_space_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime
```

---

### 36.6 Webhook inbound

Per `event_type: webhook.inbound`:

1. Il tenant registra un endpoint `/api/v1/webhooks/{agent_name}/inbound`.
2. Il backend verifica l'HMAC-SHA256 della request contro `webhook_secret_ref` (risolto da secret store).
3. Se valido, pubblica un `InternalEvent` con `event_type="webhook.inbound"` e `payload=request.json()`.
4. Il flusso prosegue via `EventDispatcherService`.

**Endpoint aggiunto alla specifica API:**

```
POST /api/v1/webhooks/{agent_name}/inbound
```
- Auth: HMAC-SHA256 header `X-Aura-Webhook-Signature`.
- Response: `{"status": "accepted", "event_id": "<uuid>"}` — sempre 202 se firma valida.
- Il backend NON aspetta il completamento del run (fire-and-forget tramite ARQ).

---

### 36.7 Schema DB aggiuntivo

```sql
-- Registrazioni trigger attive
CREATE TABLE agent_trigger_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    agent_version_id UUID NOT NULL REFERENCES agent_versions(id),
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('cron', 'event')),
    trigger_config JSONB NOT NULL,      -- serializzazione di CronTrigger | EventTrigger
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'deregistered')),
    runs_count INT NOT NULL DEFAULT 0,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON agent_trigger_registrations (tenant_id, trigger_type, status);
CREATE INDEX ON agent_trigger_registrations (agent_version_id);
```

RLS: solo il tenant corrente vede le proprie registrazioni (stesso pattern di tutte le tabelle AURA — §31).

---

### 36.8 Posizione nella sequenza implementazione

Triggered & Autonomous agents vengono implementati come estensione della **Fase 7** (Agent Registry):

```
Fase 7 (estesa):
  7a. Manifest validation (già in spec)
  7b. Registry & publish flow (già in spec)
  7c. AgentService.run_agent (già in spec)
  7d. TriggerSchedulerService + cron registration  ← nuovo
  7e. EventDispatcherService + Redis Pub/Sub        ← nuovo
  7f. Webhook inbound endpoint                      ← nuovo
```

**REGOLA**: 7d-7f sono opzionali per il DoD della Fase 7 base. Diventano obbligatori prima dell'inizio della Fase 8.
