# Fase 8 — Skills e Sandbox
> AURA Backbone v4.3 · Fase 8 di 9
> **Prerequisito**: Fase 7 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.11: SandboxPolicy)
docs/spec/04_agents.md      (§19: Skill manifest, SandboxProvider, DockerSandboxProvider, SandboxInput/Result)
docs/spec/07_db_schema.md   (§31.4: skill_packages, skill_versions)
```

---

## Obiettivo

`SandboxProvider` Protocol con `DockerSandboxProvider` funzionante in dev. Skill uploadabile, pubblicabile, eseguibile in container Docker isolato. Network egress bloccato per default. Timeout rispettato.

---

## Tasks obbligatori

### 8.1 — Migration tabelle
Da `docs/spec/07_db_schema.md §31.4`: `skill_packages`, `skill_versions`.
Struttura analoga a `agent_versions`.

### 8.2 — SandboxProvider Protocol
`aura/adapters/sandbox/provider.py` — implementare il contratto da `docs/spec/04_agents.md §19.3`:
```python
class SandboxProvider(Protocol):
    async def run(self, sandbox_input: SandboxInput) -> SandboxResult: ...
    async def health_check(self) -> bool: ...
```

### 8.3 — DockerSandboxProvider (dev)
`aura/adapters/sandbox/docker.py` — implementare la REFERENCE IMPLEMENTATION da `docs/spec/04_agents.md §19.4`:
1. Download artifact da S3 in `tempfile.mkdtemp()`
2. Scrivi `input.json` in `/workspace/`
3. `docker run` con:
   - `--network none` (se `profile.network_egress == "none"`)
   - `--memory={profile.max_memory_mb}m`
   - `--cpus={profile.max_cpu_seconds / profile.max_wall_time_s}`
   - volume mount su `/workspace` e `/artifacts`
   - env vars da `profile.env_vars_allowed` only
   - timeout = `profile.max_wall_time_s` (kill dopo)
4. Leggi stdout come JSON per `output`
5. Upload `/artifacts/*` su S3
6. Cleanup temp dir sempre (anche su errore)
7. Restituire `SandboxResult`

Se Docker non disponibile: `health_check()` → False, `run()` → `SandboxResult(status="failed", error_message="Docker not available")`

### 8.4 — K8sJobSandboxProvider (prod stub)
`aura/adapters/sandbox/k8s.py`:
- Stub con `raise NotImplementedError("K8s sandbox: implement for prod deployment")`
- `health_check()` → False in baseline

### 8.5 — SandboxProviderFactory
`aura/adapters/sandbox/factory.py`:
```python
def get_default() -> SandboxProvider:
    if settings.SANDBOX_PROVIDER == "docker":
        return DockerSandboxProvider()
    elif settings.SANDBOX_PROVIDER == "k8s":
        return K8sJobSandboxProvider()
    raise ValueError(f"Unknown sandbox provider: {settings.SANDBOX_PROVIDER}")
```

### 8.6 — SkillService
`aura/services/skill_service.py` — implementare `run_skill()` esattamente dal pseudocodice di `docs/spec/04_agents.md §19.2`.

### 8.7 — Skill APIs
```
POST /api/v1/admin/skills/upload          → SkillUploadResponse (multipart)
POST /api/v1/admin/skills/{id}/publish    → SkillVersion
GET  /api/v1/admin/skills                 → list[SkillVersion]
POST /api/v1/skills/{name}/run            → SkillRunResponse
```

### 8.8 — Integrazione con AgentService
Skill callable come tool da agenti:
```python
@agent.tool
async def run_skill(ctx, skill_name: str, input_data: dict) -> dict:
    if f"skill.{skill_name}" not in ctx.deps.allowed_tools:
        raise PermissionError(...)
    return await skill_service.run_skill(skill_name=skill_name, input_obj=input_data, ...)
```

---

## Acceptance criteria (GATE)

```python
async def test_sandbox_network_blocked():
    """Una skill che tenta una richiesta HTTP deve essere bloccata dal sandbox."""
    skill = await upload_and_publish_skill("""
import urllib.request
try:
    urllib.request.urlopen("http://example.com", timeout=2)
    print('{"success": true}')
except Exception as e:
    print('{"success": false, "error": "' + str(e) + '"}')
""")
    result = await run_skill(skill.name, input_obj={})
    # Con network=none, la richiesta deve fallire
    assert result["success"] == False or "network" in result.get("error", "").lower()

async def test_sandbox_timeout_respected():
    """Una skill che va in loop deve essere terminata entro max_wall_time_s."""
    import time
    skill = await upload_and_publish_skill("""
import time
time.sleep(999)
print('{"output": "done"}')
""", sandbox_policy=SandboxPolicy(max_wall_time_s=3))

    start = time.time()
    result = await run_skill(skill.name, input_obj={})
    elapsed = time.time() - start

    assert result.status == "timeout"
    assert elapsed < 10  # dovrebbe terminare entro pochi secondi dal timeout

async def test_skill_artifacts_persisted():
    """Gli artifact scritti in /artifacts dalla skill devono essere su S3."""
    skill = await upload_and_publish_skill("""
import json, os
os.makedirs('/artifacts', exist_ok=True)
with open('/artifacts/report.csv', 'w') as f:
    f.write('col1,col2\\n1,2\\n')
print(json.dumps({"status": "ok"}))
""")
    result = await run_skill(skill.name, input_obj={})
    assert result.status == "succeeded"
    assert any(a.name == "report.csv" for a in result.artifacts)
    # Verifica che sia effettivamente su S3
    content = await s3_download(result.artifacts[0].s3_ref)
    assert b"col1,col2" in content

async def test_skill_not_published_blocked():
    """Una skill in draft non può essere eseguita."""
    draft_skill = await upload_skill_only()  # no publish
    r = await client.post(f"/api/v1/skills/{draft_skill.name}/run",
        json={"input": {}}, headers=auth(user_token))
    assert r.status_code == 403

async def test_docker_health_check():
    """DockerSandboxProvider.health_check() deve rispondere True se Docker è disponibile."""
    provider = DockerSandboxProvider()
    healthy = await provider.health_check()
    # In CI con Docker: True; senza Docker: False (non deve lanciare eccezione)
    assert isinstance(healthy, bool)
```

---

## Note per Claude Code

- Il container Docker delle skill NON deve avere accesso al filesystem host oltre i volumi esplicitamente montati (`/workspace`, `/artifacts`).
- Lo stdout del container deve essere l'unico canale di output. La skill scrive JSON su stdout, non su file. Gli artifact vanno in `/artifacts/`.
- `max_cpu_seconds` è il limite CPU totale, `max_wall_time_s` è il timeout wall-clock. Usare `--cpus` per il primo e `timeout` del processo Docker per il secondo.
- In dev con `SANDBOX_PROVIDER=docker`, il health endpoint deve mostrare il provider sandbox come `ok` se Docker risponde, `down` altrimenti — ma l'API non deve andare down per questo.
