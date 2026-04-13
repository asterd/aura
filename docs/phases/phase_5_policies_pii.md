# Fase 5 — Policies e PII
> AURA Backbone v4.3 · Fase 5 di 9
> **Prerequisito**: Fase 4 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.9: ModelPolicy; §8.10: PiiPolicy; §8.11: SandboxPolicy)
docs/spec/02_services.md    (§7.7: PiiService; §7.9: PolicyService; §16: PII specification)
docs/spec/07_db_schema.md   (§31.5: model_policies, pii_policies, sandbox_policies)
```

---

## Obiettivo

`ModelPolicy` e `PiiPolicy` come entità DB. `PolicyService` risolve la policy corretta per ogni request. `PiiService` con Presidio batch operativo. Log e traces rispettano la policy PII attiva.

---

## Tasks obbligatori

### 5.1 — Migration tabelle
Da `docs/spec/07_db_schema.md §31.5`: `model_policies`, `pii_policies`, `sandbox_policies`.
Seed di una policy default per tenant di test.

### 5.2 — PolicyService
`aura/services/policy_service.py`:
```python
async def resolve_model_policy(session, entity, context) -> ModelPolicy
async def resolve_pii_policy(session, entity, context) -> PiiPolicy | None
async def resolve_sandbox_policy(session, entity, context) -> SandboxPolicy
```
Precedenza: `agent manifest policy` > `space policy` > `tenant default`.

### 5.3 — ModelPolicy enforcement
In `ChatService.respond()`:
- Verificare che `request.model_override` (se presente) sia in `model_policy.allowed_models`
- Se non autorizzato: HTTP 422 con messaggio esplicito
- Passare `model_policy.default_model` a LiteLLM se nessun override

### 5.4 — PiiService batch
`aura/services/pii_service.py` con Presidio:
```python
async def transform_input_if_needed(session, context, text) -> PiiTransformResult
async def transform_output_if_needed(session, context, text) -> PiiTransformResult
async def transform_agent_input_if_needed(session, context, input_obj, policy) -> dict
async def transform_agent_output_if_needed(session, context, output_obj, policy) -> dict
```
Rispettare la tabella normativa da `docs/spec/01_contracts.md §8.10`.
Se `policy.mode == "off"`: restituire testo invariato senza chiamare Presidio.

### 5.5 — Sink-specific masking
- **Logs**: se `pii_policy.allow_raw_in_logs == False`, mascherare le entità rilevate prima di loggare
- **Traces**: stessa logica per Langfuse traces
- **Persistence**: rispettare la colonna `mode` per decidere cosa salvare in `messages.content`

### 5.6 — Streaming PII baseline
In `ChatService.respond_stream()`:
- Accumulare token finché non si raggiunge un boundary (`.`, `!`, `?`, `\n`)
- Applicare `transform_output_if_needed` sul chunk completo
- Emettere i token puliti

---

## Acceptance criteria (GATE)

```python
async def test_model_override_not_in_allowlist_rejected():
    token = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    # TENANT_A ha ModelPolicy con allowed_models=["gpt-4o"]
    r = await client.post("/api/v1/chat/respond", json={
        "message": "test",
        "space_ids": [str(SPACE_ID)],
        "model_override": "gpt-4-turbo"   # NON nella whitelist
    }, headers=auth(token))
    assert r.status_code == 422

async def test_no_raw_pii_in_logs():
    """Con PiiPolicy mode=mask_persist_and_inference, il log non deve contenere il CF."""
    import logging, io
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logging.getLogger("aura").addHandler(handler)

    token = generate_test_jwt(tenant_id=TENANT_WITH_PII_POLICY, user_id=USER_A)
    await client.post("/api/v1/chat/respond", json={
        "message": "Il mio codice fiscale è RSSMRA85M01H501Z",
        "space_ids": [str(SPACE_ID)]
    }, headers=auth(token))

    log_output = log_capture.getvalue()
    assert "RSSMRA85M01H501Z" not in log_output, "PII raw trovato nei log!"

async def test_pii_transform_off_returns_raw():
    """Mode=off: il testo non deve essere modificato."""
    from aura.services.pii_service import PiiService
    policy = PiiPolicy(mode=PiiMode.off, ...)
    result = await pii_service.transform_input_if_needed(
        session=mock_session, context=mock_context,
        text="Il mio CF è RSSMRA85M01H501Z"
    )
    assert result.transformed_text == "Il mio CF è RSSMRA85M01H501Z"
    assert not result.had_transformations

async def test_pii_mask_inference_only():
    """Mode=mask_inference_only: LLM riceve testo mascherato, output utente è raw."""
    policy = PiiPolicy(mode=PiiMode.mask_inference_only, ...)
    input_result = await pii_service.transform_input_if_needed(..., text="CF: RSSMRA85M01H501Z")
    assert "RSSMRA85M01H501Z" not in input_result.transformed_text
    assert input_result.had_transformations
```

---

## Note per Claude Code

- Presidio richiede spaCy. Scaricare il modello `it_core_news_sm` (o quello configurato) all'avvio del servizio, non al momento della prima richiesta.
- `PiiService` DEVE trattare input e output come pipeline **separate**. Non riusare lo stesso `PiiTransformResult`.
- Non implementare `pseudonymize_rehydratable` nella baseline — usare `raise NotImplementedError("mode not implemented in baseline")` se richiesto.
- `sandbox_policies` in questa fase serve solo come entità DB — non è ancora usato (Fase 8).
