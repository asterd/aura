from __future__ import annotations

from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from sqlalchemy import func, select

from apps.api.config import settings
from aura.adapters.db.models import Document, DocumentVersion
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.adapters.qdrant.setup import QdrantChunkStore
from aura.domain.contracts import JobPayload
from aura.services.ingestion_service import IngestionService
from tests.conftest import TENANT_A, TENANT_B, generate_test_jwt, wait_for_job


pytestmark = pytest.mark.asyncio


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_space(
    app_client,
    token: str,
    *,
    name: str,
    slug: str,
    source_access_mode: str = "space_acl_only",
):
    response = await app_client.post(
        "/api/v1/spaces",
        json={
            "name": name,
            "slug": f"{slug}-{uuid4().hex[:8]}",
            "space_type": "team",
            "visibility": "private",
            "source_access_mode": source_access_mode,
        },
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def get_document(tenant_id: UUID, document_id: UUID) -> Document:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, tenant_id)
        document = await session.scalar(select(Document).where(Document.id == document_id))
        assert document is not None
        return document


async def count_document_versions(tenant_id: UUID, document_id: UUID) -> int:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, tenant_id)
        return int(
            await session.scalar(
                select(func.count()).select_from(DocumentVersion).where(DocumentVersion.document_id == document_id)
            )
            or 0
        )


async def upload_test_doc(app_client, token: str, space_id: UUID) -> UUID:
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample.pdf"
    with fixture_path.open("rb") as file_handle:
        response = await app_client.post(
            "/api/v1/datasources/upload",
            files={"file": ("sample.pdf", file_handle, "application/pdf")},
            data={"space_id": str(space_id)},
            headers=auth(token),
        )
    assert response.status_code == 201, response.text
    await wait_for_job(UUID(response.json()["job_id"]))
    return UUID(response.json()["document_id"])


async def test_upload_and_ingest_e2e(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|ingest-a", email="ingest-a@example.com")
    space_id = await create_space(app_client, token, name="Ingestion Space", slug="ingestion-space")

    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "sample.pdf"
    with fixture_path.open("rb") as file_handle:
        response = await app_client.post(
            "/api/v1/datasources/upload",
            files={"file": ("sample.pdf", file_handle, "application/pdf")},
            data={"space_id": str(space_id)},
            headers=auth(token),
        )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert UUID(payload["job_id"]) == uuid5(NAMESPACE_URL, f"ingest:{payload['document_id']}")
    await wait_for_job(UUID(payload["job_id"]), timeout=30)

    document = await get_document(TENANT_A, UUID(payload["document_id"]))
    assert document.status == "active"

    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(url=str(settings.qdrant_url))
    results, _ = client.scroll(
        "aura_chunks",
        scroll_filter=models.Filter(
            must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document.id)))]
        ),
        limit=1,
    )
    assert results, "Nessun chunk indicizzato in Qdrant"
    chunk = results[0].payload
    assert chunk["tenant_id"] == str(TENANT_A)
    assert chunk["space_id"] == str(space_id)
    for field_name in QdrantChunkStore.required_payload_fields:
        assert field_name in chunk


async def test_ingest_idempotent(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|idempotent-a", email="idempotent-a@example.com")
    space_id = await create_space(app_client, token, name="Idempotent Space", slug="idempotent-space")
    document_id = await upload_test_doc(app_client, token, space_id)

    versions_before = await count_document_versions(TENANT_A, document_id)
    payload = JobPayload(
        tenant_id=TENANT_A,
        job_key=f"ingest:{document_id}:manual",
        requested_by_user_id=None,
        trace_id="test-trace",
    )
    await IngestionService().ingest_document(payload=payload, document_id=document_id)
    versions_after = await count_document_versions(TENANT_A, document_id)
    assert versions_before == versions_after


async def test_cross_tenant_qdrant_isolation(app_client):
    token_a = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|tenant-a", email="tenant-a@example.com")
    token_b = generate_test_jwt(tenant_id=TENANT_B, okta_sub="okta|tenant-b", email="tenant-b@example.com")
    space_a = await create_space(app_client, token_a, name="Tenant A Space", slug="tenant-a-space")
    space_b = await create_space(app_client, token_b, name="Tenant B Space", slug="tenant-b-space")

    document_a = await upload_test_doc(app_client, token_a, space_a)
    await upload_test_doc(app_client, token_b, space_b)

    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(url=str(settings.qdrant_url))
    tenant_b_results, _ = client.scroll(
        "aura_chunks",
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=str(TENANT_B))),
                models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document_a))),
            ]
        ),
        limit=5,
    )
    assert tenant_b_results == []


async def test_upload_uses_space_acl_only_payload_for_direct_files(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|acl-a", email="acl-a@example.com")
    space_id = await create_space(
        app_client,
        token,
        name="ACL Space",
        slug="acl-space",
        source_access_mode="source_acl_enforced",
    )

    document_id = await upload_test_doc(app_client, token, space_id)

    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(url=str(settings.qdrant_url))
    results, _ = client.scroll(
        "aura_chunks",
        scroll_filter=models.Filter(
            must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=str(document_id)))]
        ),
        limit=1,
    )
    assert results, "Nessun chunk indicizzato in Qdrant"
    assert results[0].payload["source_acl_mode"] == "space_acl_only"
