# AURA Spec — §37: MCP Bridge
> Addendum v1.0 · Aprile 2026
> Estende §19 — aggiunge McpBridge come tipo di skill runtime

---

## 37. MCP Bridge

### 37.1 Scopo

Il MCP Bridge ha due direzioni:

| Direzione | Descrizione |
|---|---|
| **Inbound (MCP Server)** | AURA espone un MCP Server — agenti AURA e tool esterni (Cursor, Claude Desktop, Windsurf) possono usare AURA come context provider e action executor tramite protocollo MCP |
| **Outbound (MCP Client)** | Uno skill AURA di tipo `mcp_client` si connette a un MCP Server esterno e ne espone le capabilities come tool all'agente |

---

### 37.2 Inbound: AURA come MCP Server

AURA espone un MCP Server compatibile con lo standard [Model Context Protocol](https://modelcontextprotocol.io/).

**Endpoint MCP:**
```
/mcp/v1/sse       (transport: SSE — raccomandato)
/mcp/v1/ws        (transport: WebSocket — alternativo)
```

**Tools esposti dal MCP Server AURA:**

| Tool MCP | Mappa su | Descrizione |
|---|---|---|
| `aura_retrieve` | `RetrievalService.retrieve` | Retrieval ibrido su uno o più spaces |
| `aura_chat` | `ChatService.respond` | Chat non-streaming con history |
| `aura_agent_run` | `AgentService.run_agent` | Esecuzione di un agente pubblicato |
| `aura_list_spaces` | Query DB | Lista spaces accessibili dall'identità corrente |
| `aura_list_agents` | Query DB | Lista agenti pubblicati per il tenant |

**Autenticazione MCP inbound:**
- Il client MCP presenta un bearer token (JWT Okta o API key AURA).
- Il backend risolve `UserIdentity` dal token — stesso flow del normale middleware auth (§9).
- Ogni tool call è soggetta alle stesse policy e ACL della API REST.

**Contratto inizializzazione MCP (normativo):**

```python
# CONTRACT
class McpServerCapabilities(BaseModel):
    tools: list[str]              # nomi tool disponibili
    tenant_id: UUID
    identity_sub: str             # okta_sub dell'identità corrente
    server_version: str           # versione AURA
```

**Regole:**
- Il MCP Server NON bypassa RLS o policy. Ogni tool call avviene con la `UserIdentity` del token presentato.
- Il MCP Server non espone endpoint admin.
- I tool MCP restituiscono errori strutturati (`{"error": {"code": str, "message": str}}`) anziché eccezioni raw.

---

### 37.3 Outbound: Skill di tipo `mcp_client`

Un agente AURA può usare un MCP Server esterno come sorgente di tool tramite una skill di tipo `mcp_client`.

**Manifest skill mcp_client:**

```yaml
skill_name: github-mcp
skill_type: mcp_client                    # nuovo tipo in §19
version: "1.0.0"
mcp_server_url: "https://mcp.github.com/sse"
mcp_auth:
  credential_type: oauth2_bearer
  secret_ref: "github_mcp_token"
exposed_tools:                            # whitelist tools MCP da esporre all'agente
  - "github_search_code"
  - "github_create_issue"
  - "github_list_prs"
sandbox_policy_id: null                   # mcp_client non usa sandbox locale
timeout: 30
documentation:
  purpose: "Accesso a GitHub tramite MCP per operazioni su repository."
  limitations: "Solo repository a cui il token ha accesso."
  risk_level: "medium"
  owner: "dev-team"
```

**Regole skill mcp_client:**
- `exposed_tools` è obbligatorio e non può essere `[]` — almeno un tool deve essere esposto.
- I tool non nella whitelist `exposed_tools` non vengono mai registrati sull'agente.
- Le credenziali MCP outbound vengono risolte da secret store al momento del run — mai persistite.
- Il timeout della skill mcp_client include il round-trip verso il MCP Server esterno.
- Se il MCP Server esterno restituisce un errore, la skill restituisce `SandboxResult.status = "error"` con `stderr` contenente il messaggio di errore MCP.

---

### 37.4 McpBridgeAdapter

Il `McpBridgeAdapter` è il componente che implementa entrambe le direzioni.

**Protocol outbound (normativo):**

```python
class McpBridgeAdapter(Protocol):
    async def list_tools(self) -> list[McpToolDefinition]:
        """Recupera la lista di tool disponibili dal MCP Server remoto."""
        ...

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        credentials: ResolvedCredentials,
        timeout: int,
    ) -> McpToolResult:
        """Chiama un tool sul MCP Server remoto."""
        ...
```

**Contratti MCP:**

```python
# CONTRACT
class McpToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict            # JSON Schema del tool

# CONTRACT
class McpToolResult(BaseModel):
    tool_name: str
    content: list[dict]           # formato MCP standard: [{"type": "text", "text": ...}]
    is_error: bool = False
    error_message: str | None = None
```

**Integrazione con AgentDeps:**

Il `McpBridgeAdapter` viene iniettato in `AgentDeps` come parte degli `allowed_tools` dell'agente, se il manifest dell'agente riferisce uno skill di tipo `mcp_client`.

```python
# AgentDeps (esteso — §8.5)
@dataclass
class AgentDeps:
    # ... campi esistenti ...
    mcp_adapters: dict[str, "McpBridgeAdapter"] = field(default_factory=dict)
    # key = skill_name, value = adapter istanziato
```

Il `build(deps: AgentDeps)` dell'agente accede all'adapter tramite `deps.mcp_adapters["github-mcp"]` e registra i tool esposti come PydanticAI tools.

---

### 37.5 Posizione nella sequenza implementazione

Il MCP Bridge viene implementato in **Fase 8** (Skills & Sandbox), dopo l'implementazione base del SandboxProvider:

```
Fase 8 (estesa):
  8a. SandboxProvider Docker (già in spec)
  8b. RuntimeLoader + artifact verification (già in spec)
  8c. McpBridgeAdapter outbound (skill mcp_client)   ← nuovo
  8d. AURA MCP Server inbound                        ← nuovo
```

**REGOLA**: 8c è prerequisito per 8d. L'outbound permette di testare il protocollo MCP in isolamento prima di esporre AURA come server.

---

### 37.6 Anti-pattern MCP

- ❌ Il MCP Server AURA NON espone tool che modificano il DB direttamente — sempre via service layer.
- ❌ I tool MCP NON ricevono sessioni DB o session factories — usano le API interne via service.
- ❌ `McpBridgeAdapter` MUST NOT essere istanziato dentro un router — sempre via dependency injection.
- ❌ Le credenziali MCP outbound NON vengono loggati o serializzati (stesso pattern di `ResolvedCredentials`).
