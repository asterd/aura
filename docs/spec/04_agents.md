# AURA Spec — §17-20: Agent Backbone, Registry, Sandbox, Connectors
> Source: AURA Backbone v4.3

## 17. Agent backbone

### 17.1 Tipi supportati

- `single` — agente con tools, esecuzione diretta
- `orchestrator` — agente che invoca altri agenti via tool `agent.delegate`

`workflow` non è un tipo separato nella baseline; si modella come orchestrator con stato esplicito.

### 17.2 Manifest schema

```yaml
# ILLUSTRATIVE EXAMPLE
kind: agent
name: contract-reviewer
version: 1.2.0
agent_type: single
runtime: pydantic-ai
entrypoint: agent.py:build
summary: "Analizza contratti e produce un report rischi."
input_schema: schemas/input.json
output_schema: schemas/output.json
allowed_tools:
  - knowledge.search
  - file.read
allowed_spaces:
  - legal-shared-kb
model_policy: legal-default
pii_policy: standard-mask
sandbox_policy: no-network-readonly
max_budget_usd: 2.0
timeout_s: 120
status: published
documentation:
  purpose: "Screening iniziale di contratti"
  touches_data:
    - legal-shared-kb
  systems_touched:
    - knowledge-service
    - object-storage
  limitations:
    - "Non sostituisce revisione legale umana"
  risk_level: medium
  owner: "legal-team@company.com"
```

### 17.3 NORMATIVE PSEUDOCODE — AgentService.run_agent

```python
# NORMATIVE PSEUDOCODE
async def run_agent(
    session: AsyncSession,
    request: AgentRunRequest,
    context: RequestContext,
) -> AgentRunResult:
    version = await registry_service.resolve_agent_version(
        session=session,
        agent_name=request.agent_name,
        requested_version=request.agent_version,
    )

    await authz_service.ensure_can_run_agent(
        session=session,
        identity=context.identity,
        agent_version=version,
    )

    model_policy = await policy_service.resolve_model_policy(session, version, context)
    pii_policy = await policy_service.resolve_pii_policy(session, version, context)
    system_prompt = await prompt_service.resolve_agent_prompt(session, version, context)

    deps = AgentDeps(
        identity=context.identity,
        model_policy=model_policy,
        pii_policy=pii_policy,
        allowed_spaces=version.allowed_space_ids,
        allowed_tools=version.allowed_tools,
        litellm_base_url=settings.LITELLM_BASE_URL,
        litellm_virtual_key=await authz_service.resolve_virtual_key(session, version, context),
        knowledge_service=knowledge_service,
        artifact_writer=artifact_writer,
        resolve_system_prompt=lambda _: system_prompt,
    )

    artifact_ref = await registry_service.get_runtime_artifact_ref(session, version)
    build_fn = await runtime_loader.load_build_fn(artifact_ref, version.entrypoint)

    transformed_input = await pii_service.transform_agent_input_if_needed(
        session=session,
        context=context,
        input_obj=request.input,
        policy=pii_policy,
    )

    agent = build_fn(deps)
    raw_result = await agent.run(transformed_input, deps=deps)

    transformed_output = await pii_service.transform_agent_output_if_needed(
        session=session,
        context=context,
        output_obj=raw_result.output,
        policy=pii_policy,
    )

    persisted = await agent_run_repository.create_succeeded_run(
        session=session,
        context=context,
        version=version,
        request=request,
        output=transformed_output,
    )

    await audit_service.emit_agent_run(session=session, context=context, run_id=persisted.run_id)

    return AgentRunResult(
        run_id=persisted.run_id,
        agent_name=version.name,
        agent_version=version.version,
        status="succeeded",
        output_data=transformed_output if isinstance(transformed_output, dict) else None,
        output_text=transformed_output if isinstance(transformed_output, str) else None,
        trace_id=context.trace_id,
        artifacts=persisted.artifact_names,
    )
```

### 17.4 Regole agentiche

MUST:
- tools e spaces devono essere espliciti nel manifest
- input/output schema obbligatori nel manifest
- agent code caricato solo da artifact `published`

MUST NOT:
- accedere direttamente al DB dall'agent code
- usare tools non dichiarati nel manifest
- eseguire da versioni non `published`

### 17.5 REFERENCE IMPLEMENTATION — PydanticAI agent minimale conforme

Questo è il pattern obbligatorio per qualsiasi agente AURA. Il file `agent.py` dentro il package deve esporre una funzione `build(deps: AgentDeps) -> Agent`.

```python
# REFERENCE IMPLEMENTATION
# agent.py — struttura obbligatoria per ogni agente AURA
from __future__ import annotations

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel

from aura.domain.contracts import AgentDeps


def build(deps: AgentDeps) -> Agent[AgentDeps]:
    """
    Entry point obbligatorio. Viene chiamato da RuntimeLoader.
    Riceve AgentDeps già risolto. Non deve accedere a config globale.
    """
    model = OpenAIModel(
        model_name=deps.model_policy.default_model,
        base_url=deps.litellm_base_url,
        api_key=deps.litellm_virtual_key,
    )

    agent: Agent[AgentDeps] = Agent(
        model=model,
        system_prompt=deps.resolve_system_prompt("agent"),
        deps_type=AgentDeps,
        # tools registrati sotto
    )

    @agent.tool
    async def knowledge_search(ctx: RunContext[AgentDeps], query: str, space_id: str) -> str:
        """Cerca nella knowledge base. space_id deve essere in allowed_spaces."""
        from uuid import UUID
        sid = UUID(space_id)
        if sid not in ctx.deps.allowed_spaces:
            raise PermissionError(f"Space {space_id} not in allowed_spaces")
        result = await ctx.deps.knowledge_service.search(
            query=query,
            space_id=sid,
            identity=ctx.deps.identity,
        )
        return result.context_text

    @agent.tool
    async def write_artifact(ctx: RunContext[AgentDeps], name: str, content: str, content_type: str) -> str:
        """Scrive un artifact e restituisce il riferimento S3."""
        ref = await ctx.deps.artifact_writer.write(
            name=name,
            content=content.encode(),
            content_type=content_type,
            identity=ctx.deps.identity,
        )
        return ref

    return agent
```

**Note vincolanti**:
- la funzione `build` MUST ricevere solo `AgentDeps` come parametro
- i tool MUST verificare che space_id sia in `allowed_spaces`
- i tool MUST NOT importare ORM o SessionFactory
- qualsiasi tool non dichiarato in `allowed_tools` nel manifest viene rimosso prima del run da `AgentService`

---

## 18. Registry e publish flow

### 18.1 Flow canonico

1. upload package (multipart)
2. validate manifest (schema + smoke test)
3. smoke test sandbox
4. upload artifact immutabile su S3
5. create version record DB (status: `draft`)
6. publish esplicito (status: `published`)
7. runtime solo da versioni `published`

### 18.2 Invarianti

- artifact published è immutabile
- publish fallisce se manifest non valido
- publish fallisce se smoke test non passa
- una versione pubblicata non viene mutata in-place

### 18.3 Source of truth runtime

Record DB (`agent_versions.status = 'published'`) + artifact immutabile su S3 con hash verificato.

---

## 19. Skill e sandbox

### 19.1 Skill manifest

```yaml
# ILLUSTRATIVE EXAMPLE
kind: skill
name: tabular-profiler
version: 1.0.0
runtime: sandbox-python
entrypoint: main.py
summary: "Profilazione rapida di file CSV/XLSX."
input_schema: schemas/input.json
output_schema: schemas/output.json
sandbox_policy: data-analysis-no-egress
base_image: python:3.12-slim
pip_packages:
  - pandas==2.2.0
  - openpyxl==3.1.2
smoke_test:
  command: "python tests/smoke.py"
  timeout_s: 30
status: published
```

### 19.2 NORMATIVE PSEUDOCODE — Skill run

```python
# NORMATIVE PSEUDOCODE
async def run_skill(
    session: AsyncSession,
    skill_version: SkillVersion,
    input_obj: dict,
    context: RequestContext,
) -> dict:
    policy = await policy_service.resolve_sandbox_policy(session, skill_version, context)
    sandbox = sandbox_provider_factory.get_default()
    sandbox_input = SandboxInput(
        skill_version_id=skill_version.id,
        artifact_ref=skill_version.artifact_ref,
        entrypoint=skill_version.entrypoint,
        input_obj=input_obj,
        profile=policy,
        trace_id=context.trace_id,
    )
    result = await sandbox.run(sandbox_input)
    if result.status != "succeeded":
        raise SkillExecutionError(result.error_message, exit_code=result.exit_code)
    await artifact_writer.persist_skill_artifacts(session=session, context=context, sandbox_result=result)
    return result.output
```

### 19.3 SandboxProvider contract

```python
# CONTRACT
class SandboxInput(BaseModel):
    skill_version_id: UUID
    artifact_ref: str           # S3 key del package immutabile
    entrypoint: str             # e.g. "main.py"
    input_obj: dict
    profile: SandboxPolicy
    trace_id: str

class SandboxArtifact(BaseModel):
    name: str
    content_type: str
    size_bytes: int
    s3_ref: str                 # riferimento S3 dopo upload

class SandboxResult(BaseModel):
    status: Literal["succeeded", "failed", "timeout"]
    output: dict | None = None
    error_message: str | None = None
    artifacts: list[SandboxArtifact] = Field(default_factory=list)
    wall_time_s: float
    exit_code: int | None = None

class SandboxProvider(Protocol):
    """
    Contract per provider di esecuzione sandboxed.
    Implementazioni: DockerSandboxProvider (dev), K8sJobSandboxProvider (prod).
    """
    async def run(self, sandbox_input: SandboxInput) -> SandboxResult: ...
    async def health_check(self) -> bool: ...
```

### 19.4 Implementazione DockerSandboxProvider (dev)

```python
# REFERENCE IMPLEMENTATION — DockerSandboxProvider
class DockerSandboxProvider:
    """Provider Docker effimero per dev locale."""

    async def run(self, inp: SandboxInput) -> SandboxResult:
        # 1. Scarica artifact da S3 in temp dir locale
        # 2. Scrivi input_obj come JSON in /workspace/input.json
        # 3. docker run con:
        #    - volume mount della temp dir su /workspace
        #    - env vars consentite da profile.env_vars_allowed
        #    - --network none (se profile.network_egress == "none")
        #    - --memory={profile.max_memory_mb}m
        #    - timeout = profile.max_wall_time_s
        # 4. Leggi /artifacts/* e carica su S3
        # 5. Leggi stdout come JSON per output
        # 6. Rimuovi temp dir
        raise NotImplementedError("DockerSandboxProvider.run")

    async def health_check(self) -> bool:
        raise NotImplementedError("DockerSandboxProvider.health_check")
```

### 19.5 RuntimeLoader contract

Il RuntimeLoader carica la funzione `build` da un artifact agent. Non esegue `exec()` diretto.

```python
# CONTRACT
class RuntimeLoader:
    """
    Carica la build function da un artifact immutabile.
    Ogni invocazione di load_build_fn estrae l'artifact in una temp dir isolata.
    La temp dir viene rimossa al termine del run da AgentService.
    """

    async def load_build_fn(
        self,
        artifact_ref: str,      # S3 key del .zip immutabile
        entrypoint: str,        # formato "module.py:function_name"
    ) -> Callable[[AgentDeps], Any]:
        """
        1. Download artifact_ref da S3 a temp dir (con caching locale SHA-verificato)
        2. Estrai zip in temp_dir/
        3. Valida che entrypoint esista (path check, no exec)
        4. Usa importlib.util per caricare il modulo
        5. Estrai la funzione per nome
        6. Verifica signature: Callable[[AgentDeps], Agent]
        7. Return funzione
        """
        raise NotImplementedError("RuntimeLoader.load_build_fn")

    async def cleanup_temp_dir(self, temp_dir: str) -> None:
        """Rimuove la temp dir dopo il run. Chiamata da AgentService."""
        raise NotImplementedError("RuntimeLoader.cleanup_temp_dir")
```

**Regole RuntimeLoader**:

MUST:
- verificare SHA256 dell'artifact prima di caricare
- usare una temp dir per-run (mai riuso cross-run)
- chiamare `cleanup_temp_dir` anche in caso di eccezione

MUST NOT:
- usare `exec()` o `eval()` direttamente sul source
- lasciare temp dir su disco in caso di errore
- fare import globali del codice agente nel processo worker

---

## 20. Connector model

### 20.1 CONTRACT — connector wrapper

```python
# CONTRACT
class ConnectorWrapper(Protocol):
    connector_type: str
    supports_access_control: bool
    supports_incremental_sync: bool
    supports_remote_delete_detection: bool

    async def load_documents(
        self,
        datasource_id: UUID,
        credentials: ResolvedCredentials,  # sempre ResolvedCredentials, mai dict
        cursor: str | None,
    ) -> AsyncIterator[LoadedDocument]: ...

    def update_cursor(
        self,
        current_cursor: str | None,
        loaded: LoadedDocument,
    ) -> str | None: ...
```

### 20.2 Failure behavior

Ogni connector MUST definire comportamento per:

| Scenario | Comportamento obbligatorio |
|---|---|
| Auth fallisce | Raise `ConnectorAuthError`; job fallisce; datasource marcato `auth_error` |
| Source temporaneamente indisponibile | Retry con backoff; dopo N tentativi raise `ConnectorUnavailableError` |
| ACL non recuperabili | Se `source_acl_enforced`, raise `ConnectorAclError`; documento NON indicizzato |
| Remote delete non supportato | Se `supports_remote_delete_detection = False`, emette warning; no purge automatica |

### 20.3 Credential resolution flow

```python
# NORMATIVE PSEUDOCODE
async def resolve_and_use_credentials(
    connector_credentials: ConnectorCredentials,
    secret_store: SecretStore,
) -> ResolvedCredentials:
    """
    Il secret_ref viene risolto a runtime dal secret store.
    Il valore non viene mai persistito o loggato.
    """
    raw_secret = await secret_store.get(connector_credentials.secret_ref)
    return ResolvedCredentials(
        credential_type=connector_credentials.credential_type,
        token_or_key=raw_secret,
        scopes=connector_credentials.scopes,
        tenant_domain=connector_credentials.tenant_domain,
        extra=connector_credentials.extra,
    )
    # ResolvedCredentials è in-memory only.
    # Non viene mai passato a un ARQ job come payload.
    # Il job riceve solo secret_ref; risolve autonomamente all'avvio.
```

---
