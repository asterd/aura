# AURA Spec — §11-12: Knowledge Backbone e Retrieval Architecture
> Source: AURA Backbone v4.3

## 11. Knowledge backbone

### 11.1 KnowledgeSpace contract

```python
# CONTRACT
class KnowledgeSpace(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    space_type: Literal["personal", "team", "enterprise"]
    visibility: Literal["private", "team", "enterprise"]
    source_access_mode: Literal["space_acl_only", "source_acl_enforced"]
    embedding_profile_id: UUID       # riferimento a EmbeddingProfile
    retrieval_profile_id: UUID       # riferimento a RetrievalProfile
    pii_policy_id: UUID | None = None
    tone_profile_id: UUID | None = None
    system_instructions: str | None = None
    status: Literal["active", "archived"]
    created_by: UUID
    created_at: datetime
    updated_at: datetime
```

### 11.2 Document lifecycle

```
discovered → fetched → parsed → canonicalized → indexed → active
                                                 ↘ deleted
                                                 ↘ error
```

Regole:
- ogni stato deve essere persistito in `documents.status`
- ogni transizione importante deve emettere audit
- indexing e versioning devono essere idempotenti

### 11.3 Payload Qdrant standard

```json
{
  "tenant_id": "uuid",
  "space_id": "uuid",
  "document_id": "uuid",
  "document_version_id": "uuid",
  "chunk_id": "uuid",
  "chunk_index": 0,
  "source_id": "uuid",
  "source_system": "sharepoint",
  "source_path": "/sites/hr/policy.pdf",
  "source_url": "https://...",
  "title": "Policy HR 2026",
  "content_type": "application/pdf",
  "language": "it",
  "classification": "internal",
  "tags": ["hr", "policy"],
  "hash": "sha256:...",
  "updated_at": "2026-04-11T10:00:00Z",
  "source_acl_mode": "source_acl_enforced",
  "acl_allow_users": ["okta_sub_1"],
  "acl_allow_groups": ["aura_group_uuid_1"],
  "acl_deny_users": [],
  "acl_deny_groups": [],
  "acl_inherited": true,
  "page_number": 3,
  "section_title": "Sezione 2",
  "char_start": 1024,
  "char_end": 2048
}
```

Regole payload:

MUST:
- includere `tenant_id`, `space_id`, `document_id`, `chunk_id`, `source_acl_mode`
- usare payload filtering sempre esplicito
- usare group ids canonici AURA

SHOULD:
- indicizzare i campi più filtranti: `tenant_id`, `space_id`, `source_acl_mode`, `acl_allow_users`, `acl_allow_groups`

---

## 12. Retrieval architecture

### 12.1 NORMATIVE PSEUDOCODE — RetrievalService

```python
# NORMATIVE PSEUDOCODE
async def retrieve(
    session: AsyncSession,
    request: RetrievalRequest,
    context: RequestContext,
) -> RetrievalResult:
    # 1. validate request and spaces
    # 2. resolve retrieval profile (da DB, con fallback a default del tenant)
    # 3. build tenant/space/source ACL filters (Qdrant Filter object)
    # 4. optional query rewrite (se profile.query_rewrite_enabled)
    # 5. candidate retrieval: dense + sparse (hybrid search Qdrant)
    # 6. reranking (se profile.reranker != "none")
    # 7. context assembly (concatenazione dei chunk top-k)
    # 8. citation normalization
    # 9. return RetrievalResult
```

### 12.2 Invarianti

`RetrievalService`:

- non persiste messages
- non esegue model calls generative
- non emette eventi stream
- non fa masking output

### 12.3 Filter builder

Ogni retrieval MUST filtrare per:

- `tenant_id` (sempre)
- `space_id` (sempre; lista di space_ids autorizzati)

Se `source_acl_enforced`:
- `acl_allow_users` (MUST contenere `identity.okta_sub`)
- `acl_allow_groups` (MUST contenere almeno un group_id dell'utente)
- `acl_deny_users` MUST NOT contenere `identity.okta_sub`

---
