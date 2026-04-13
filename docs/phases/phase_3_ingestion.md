# Fase 3 — Upload e Ingestion
> AURA Backbone v4.3 · Fase 3 di 9
> **Prerequisito**: Fase 2 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.4: LoadedDocument, DocumentMetadata, NormalizedACL)
docs/spec/03_knowledge.md   (§11.2: document lifecycle; §11.3: Qdrant payload)
docs/spec/07_db_schema.md   (§31.2: datasources, documents, document_versions)
docs/spec/06_ops.md         (§22: jobs, retries, idempotenza)
```

⚠️ Prima di iniziare: `pip show llama-index` deve rispondere "not found". Usare solo `llama-index-core`, `llama-index-readers-file`, `llama-index-embeddings-litellm`.

---

## Obiettivo

Upload di file → job ARQ → parsing LlamaIndex → embedding via LiteLLM → upsert Qdrant con payload standard. Un documento caricato deve essere recuperabile via search Qdrant entro la fine della fase.

---

## Tasks obbligatori

### 3.1 — Migration tabelle
Da `docs/spec/07_db_schema.md §31.2`: `datasources`, `documents`, `document_versions`.
RLS abilitato su tutte.

### 3.2 — S3 adapter
`aura/adapters/s3/client.py`:
- `upload_file(bucket, key, data, content_type)` → str (S3 URL)
- `download_file(bucket, key)` → bytes
- `get_presigned_url(bucket, key, expires_in)` → str
Usare `boto3` con endpoint configurabile (MinIO in dev).

### 3.3 — Upload API
`POST /api/v1/datasources/upload` (multipart: `space_id`, `file`):
1. Validare che l'utente sia membro dello space
2. Upload file originale su S3 (`originals/{tenant_id}/{space_id}/{uuid}.{ext}`)
3. Creare record `documents` (status: `discovered`) e `datasources`
4. Enqueue job ARQ `ingest_document_job` con `JobPayload`
5. Rispondere `UploadDatasourceResponse` (da `docs/spec/05_api.md §21.5`)

### 3.4 — Ingestion job
`apps/worker/jobs/ingestion.py` — `ingest_document_job(ctx, payload: JobPayload)`:

**Pipeline obbligatoria** (rispettare l'ordine):
1. `fetched`: download originale da S3
2. `parsed`: LlamaIndex `SimpleDirectoryReader` o `PDFReader` → testo canonico
3. `canonicalized`: salva canonical text su S3 (`canonical/{tenant_id}/{doc_id}/{version_hash}.txt`)
4. Calcola `version_hash` (SHA256 del canonical text)
5. Se `version_hash` uguale all'ultima versione: skip (idempotenza)
6. Crea `document_versions` record
7. Split in chunk secondo `EmbeddingProfile` dello space
8. Embedding batch via LiteLLM (`/embeddings`)
9. Qdrant upsert con **payload standard completo** (da `docs/spec/03_knowledge.md §11.3`)
10. `indexed` → `active`: aggiorna `documents.status`
11. Aggiorna `documents.current_version_id`

**Job key**: `ingest:{document_id}:{version_hash}` (idempotente)
**Retry**: max 3, backoff 30s esponenziale
**Lock Redis**: `lock:ingest:{document_id}` per evitare doppia elaborazione

### 3.5 — Qdrant collection setup
`aura/adapters/qdrant/setup.py`: crea collection `aura_chunks` con:
- Vector config: dimensioni da EmbeddingProfile
- Payload indices obbligatori: `tenant_id`, `space_id`, `source_acl_mode`

---

## Acceptance criteria (GATE)

```python
async def test_upload_and_ingest_e2e():
    token = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)

    # Upload
    with open("tests/fixtures/sample.pdf", "rb") as f:
        r = await client.post("/api/v1/datasources/upload",
            files={"file": f},
            data={"space_id": str(SPACE_ID)},
            headers=auth(token))
    assert r.status_code == 201
    job_id = r.json()["job_id"]

    # Attendi completamento job (max 30s)
    await wait_for_job(job_id, timeout=30)

    # Verifica documento active nel DB
    doc = await get_document(r.json()["document_id"])
    assert doc.status == "active"

    # Verifica chunk in Qdrant
    from qdrant_client import QdrantClient
    qc = QdrantClient(url=settings.QDRANT_URL)
    results = qc.scroll("aura_chunks",
        scroll_filter={"must": [{"key": "document_id", "match": {"value": str(doc.id)}}]},
        limit=1)
    assert len(results[0]) > 0, "Nessun chunk indicizzato in Qdrant"
    chunk = results[0][0].payload
    assert chunk["tenant_id"] == str(TENANT_A)
    assert chunk["space_id"] == str(SPACE_ID)

async def test_ingest_idempotent():
    """Lo stesso documento caricato due volte produce lo stesso version_hash, nessun duplicato."""
    doc_id = await upload_test_doc(SPACE_ID)
    versions_before = await count_document_versions(doc_id)
    await trigger_ingest_job(doc_id)  # secondo run con stesso contenuto
    versions_after = await count_document_versions(doc_id)
    assert versions_before == versions_after, "Ingest non è idempotente"

async def test_cross_tenant_qdrant_isolation():
    """Chunk di TENANT_A non devono essere visibili con filter di TENANT_B."""
    # Inserisci doc per TENANT_A
    await upload_and_ingest(TENANT_A, SPACE_A)
    # Query con tenant_id di TENANT_B
    results = qdrant_search(tenant_id=TENANT_B, query="test")
    assert len(results) == 0
```

---

## Note per Claude Code

- Il `version_hash` è SHA256 del canonical text (bytes), non del file originale.
- Il job ARQ deve persistere lo stato nel DB ad ogni step significativo (`fetched`, `parsed`, etc.) — non solo alla fine. Questo permette il debug e il retry parziale.
- Il payload Qdrant DEVE includere tutti i campi di `docs/spec/03_knowledge.md §11.3`. Mancarne anche uno è una violazione del contratto.
- `acl_allow_users`, `acl_allow_groups` per file uploadati direttamente (non connettori enterprise) sono vuoti — si usa `source_acl_mode: "space_acl_only"`.
