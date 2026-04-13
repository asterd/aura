# Fase 2 — Spaces
> AURA Backbone v4.3 · Fase 2 di 9
> **Prerequisito**: Fase 1 acceptance criteria tutti verdi.

## File da leggere in questa sessione

```
CLAUDE.md
docs/spec/01_contracts.md   (§8.1: UserIdentity; §8.8: EmbeddingProfile, RetrievalProfile, ToneProfile)
docs/spec/03_knowledge.md   (§11.1: KnowledgeSpace contract)
docs/spec/07_db_schema.md   (§31.2: knowledge_spaces, space_memberships; §31.5: profile tables)
```

---

## Obiettivo

CRUD completo di KnowledgeSpace con ACL di membership. Un utente vede solo i propri spaces. Profile tables (EmbeddingProfile, RetrievalProfile, ToneProfile) seeded con defaults per tenant.

---

## Tasks obbligatori

### 2.1 — Migration tabelle
Da `docs/spec/07_db_schema.md §31.2 e §31.5`:
- `knowledge_spaces`, `space_memberships`
- `embedding_profiles`, `retrieval_profiles`, `tone_profiles`
Abilitare RLS + FORCE ROW LEVEL SECURITY su tutte.

### 2.2 — ORM models
`aura/adapters/db/models.py`: modelli SQLAlchemy per le tabelle di questa fase.
I modelli ORM sono SEPARATI dai contratti Pydantic — non mixare.

### 2.3 — SpaceRepository
`aura/adapters/db/space_repository.py`:
- `create(session, data, created_by)` → KnowledgeSpace
- `get_by_id(session, space_id)` → KnowledgeSpace | None
- `list_for_user(session, user_id)` → list[KnowledgeSpace]
- `archive(session, space_id)` → KnowledgeSpace
- `add_member(session, space_id, user_id, role)`

### 2.4 — SpaceService
`aura/services/space_service.py`:
- Thin wrapper su repository
- Valida che `embedding_profile_id` e `retrieval_profile_id` esistano per il tenant
- Autorizza l'operazione via membership role

### 2.5 — API router spaces
`apps/api/routers/spaces.py`:
```
POST   /api/v1/spaces
GET    /api/v1/spaces
GET    /api/v1/spaces/{space_id}
PATCH  /api/v1/spaces/{space_id}
DELETE /api/v1/spaces/{space_id}    (logico: status = archived)
POST   /api/v1/spaces/{space_id}/members
```
I router NON contengono business logic — chiamano solo SpaceService.

### 2.6 — Profile defaults seeder
Script o migration che inserisce per ogni nuovo tenant:
- 1 EmbeddingProfile default (`text-embedding-3-small`, dim 1536, chunk 512)
- 1 RetrievalProfile default (top_k=10, reranker=none)
- 1 ToneProfile default (formality=neutral)

---

## Acceptance criteria (GATE)

```python
async def test_user_sees_only_own_spaces():
    token_a = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    token_b = generate_test_jwt(tenant_id=TENANT_B, user_id=USER_B)

    # Crea uno space per tenant B
    await create_space(token_b, name="Space-B")

    # Tenant A non deve vederlo
    r = await client.get("/api/v1/spaces", headers=auth(token_a))
    spaces = r.json()
    assert all(s["tenant_id"] == str(TENANT_A) for s in spaces)

async def test_space_crud_lifecycle():
    token = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_A)
    # Create
    r = await client.post("/api/v1/spaces", json={
        "name": "Test Space", "slug": "test-space",
        "space_type": "team", "visibility": "team",
        "source_access_mode": "space_acl_only"
    }, headers=auth(token))
    assert r.status_code == 201
    space_id = r.json()["id"]

    # Get
    r = await client.get(f"/api/v1/spaces/{space_id}", headers=auth(token))
    assert r.status_code == 200

    # Archive
    r = await client.delete(f"/api/v1/spaces/{space_id}", headers=auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

async def test_non_member_cannot_access_space():
    token_other = generate_test_jwt(tenant_id=TENANT_A, user_id=USER_OTHER)
    # USER_OTHER non è membro dello space creato da USER_A
    r = await client.get(f"/api/v1/spaces/{PRIVATE_SPACE_ID}", headers=auth(token_other))
    assert r.status_code == 403
```

---

## Note per Claude Code

- `embedding_profile_id` e `retrieval_profile_id` sono OBBLIGATORI in KnowledgeSpace. Se non forniti nella request, usare il default del tenant.
- La visibilità `enterprise` significa che tutti gli utenti del tenant possono leggere lo space (ma non scrivere). Implementare questo con la policy RLS o con una query esplicita nel repository.
- In questa fase non si indicizza ancora nulla in Qdrant — solo la governance degli spaces.
