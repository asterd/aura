from __future__ import annotations

import json
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from aura.adapters.connectors import register_connector
from aura.adapters.connectors.base import ConnectorAuthError
from aura.adapters.connectors.sharepoint import SharePointConnector
from aura.adapters.db.models import Datasource, Document, User
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import IdentitySyncResult, JobPayload, RequestContext, RetrievalRequest, UserIdentity
from aura.services.connector_sync_service import ConnectorSyncService
from aura.services.datasource_service import DatasourceService
from aura.services.identity_sync_service import (
    DirectoryGroup,
    DirectorySnapshot,
    DirectoryUser,
    IdentitySyncService,
    StaticDirectoryProvider,
)
from aura.services.ingestion_service import IngestionService
from aura.services.retrieval import RetrievalService
from aura.utils.secrets import MemorySecretStore
from tests.conftest import TENANT_A, generate_test_jwt, insert_test_group


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
) -> UUID:
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


async def create_connector_datasource(*, tenant_id: UUID, space_id: UUID, secret_ref: str) -> UUID:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, tenant_id)
        datasource = Datasource(
            tenant_id=tenant_id,
            space_id=space_id,
            connector_type="sharepoint",
            display_name="HR SharePoint",
            credentials_ref=secret_ref,
        )
        session.add(datasource)
        await session.flush()
        datasource_id = datasource.id
        await session.commit()
    return datasource_id


async def get_user(tenant_id: UUID, okta_sub: str) -> User:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, tenant_id)
        user = await session.scalar(select(User).where(User.tenant_id == tenant_id, User.okta_sub == okta_sub))
        assert user is not None
        return user


async def get_document_for_datasource(tenant_id: UUID, datasource_id: UUID, external_id: str) -> Document:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, tenant_id)
        document = await session.scalar(
            select(Document).where(
                Document.datasource_id == datasource_id,
                Document.external_id == external_id,
            )
        )
        assert document is not None
        return document


async def get_datasource(tenant_id: UUID, datasource_id: UUID) -> Datasource:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, tenant_id)
        datasource = await session.scalar(select(Datasource).where(Datasource.id == datasource_id))
        assert datasource is not None
        return datasource


async def test_credentials_never_serialized(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|connector-queue", email="connector-queue@example.com")
    space_id = await create_space(app_client, token, name="Connector Queue", slug="connector-queue")
    datasource_id = await create_connector_datasource(
        tenant_id=TENANT_A,
        space_id=space_id,
        secret_ref="env://SHAREPOINT_PHASE6_SECRET",
    )
    payload = JobPayload(
        tenant_id=TENANT_A,
        job_key=f"sync:{datasource_id}",
        trace_id="trace-phase6",
    )

    captured: list[tuple] = []

    class _FakeRedis:
        async def enqueue_job(self, *args, **kwargs):
            captured.append(args)

        async def aclose(self):
            return None

    async def _fake_create_pool(*args, **kwargs):
        return _FakeRedis()

    with patch("aura.services.connector_sync_service.create_pool", side_effect=_fake_create_pool):
        await ConnectorSyncService().enqueue_sync(payload=payload, datasource_id=datasource_id)

    assert captured
    serialized = json.dumps(captured)
    assert "token_or_key" not in serialized
    assert "client_secret" not in serialized.lower()
    assert "SHAREPOINT_PHASE6_SECRET" in serialized


async def test_stale_acl_after_sync(app_client):
    allowed_group = await insert_test_group(tenant_id=TENANT_A, external_id="hr-team@company.com")
    await insert_test_group(tenant_id=TENANT_A, external_id="finance-team@company.com")

    token = generate_test_jwt(
        tenant_id=TENANT_A,
        okta_sub="okta|connector-user",
        email="connector-user@example.com",
        groups=["hr-team@company.com"],
    )
    space_id = await create_space(
        app_client,
        token,
        name="Enterprise Connector Space",
        slug="enterprise-connector-space",
        source_access_mode="source_acl_enforced",
    )
    user = await get_user(TENANT_A, "okta|connector-user")
    datasource_id = await create_connector_datasource(
        tenant_id=TENANT_A,
        space_id=space_id,
        secret_ref="sharepoint://tenant-a",
    )

    raw_documents: list[dict[str, object]] = [
        {
            "external_id": "policy-001",
            "title": "Enterprise policy",
            "source_path": "/sites/hr/policy-001",
            "content_type": "text/plain",
            "raw_text": "Enterprise policy handbook for connector testing.",
            "acl": {"allow": ["group:hr-team@company.com"]},
            "modified_at": "2026-04-13T10:00:00+00:00",
        }
    ]

    async def _fetch_documents(credentials, cursor):
        return list(raw_documents)

    register_connector(SharePointConnector(fetcher=_fetch_documents))
    connector_service = ConnectorSyncService(
        secret_store=MemorySecretStore(
            {
                "sharepoint://tenant-a": json.dumps(
                    {
                        "credential_type": "oauth2_bearer",
                        "token_or_key": "top-secret-token",
                    }
                )
            }
        )
    )
    payload = JobPayload(
        tenant_id=TENANT_A,
        job_key=f"sync:{datasource_id}",
        requested_by_user_id=user.id,
        trace_id="trace-stale-acl",
    )

    await connector_service.sync_datasource(payload=payload, datasource_id=datasource_id, secret_ref="sharepoint://tenant-a")
    document = await get_document_for_datasource(TENANT_A, datasource_id, "policy-001")
    await IngestionService().ingest_document(payload=payload, document_id=document.id)

    retrieval_request = RetrievalRequest(query="Enterprise policy", space_ids=[space_id])
    context = RequestContext(
        request_id="req-phase6",
        trace_id="trace-phase6-retrieval",
        tenant_id=TENANT_A,
        identity=UserIdentity(
            user_id=user.id,
            tenant_id=TENANT_A,
            okta_sub=user.okta_sub,
            email=user.email,
            display_name=user.display_name,
            roles=user.roles,
            group_ids=[allowed_group.id],
        ),
        now_utc=user.updated_at,
    )
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, TENANT_A)
        first_result = await RetrievalService().retrieve(session=session, request=retrieval_request, context=context)
    assert len(first_result.citations) > 0

    raw_documents[0]["acl"] = {"allow": ["group:finance-team@company.com"]}
    await connector_service.sync_datasource(payload=payload, datasource_id=datasource_id, secret_ref="sharepoint://tenant-a")
    document = await get_document_for_datasource(TENANT_A, datasource_id, "policy-001")
    await IngestionService().ingest_document(payload=payload, document_id=document.id)

    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, TENANT_A)
        second_result = await RetrievalService().retrieve(session=session, request=retrieval_request, context=context)
    assert len(second_result.citations) == 0


async def test_acl_normalization() -> None:
    group = await insert_test_group(tenant_id=TENANT_A, external_id="hr-team@company.com")
    connector = SharePointConnector()

    normalized = await connector._normalize_acl_async(  # noqa: SLF001 - integration contract check
        {"allow": ["group:hr-team@company.com"]},
        tenant_id=TENANT_A,
    )

    assert normalized is not None
    assert normalized.allow_groups == [group.id]
    assert all(isinstance(group_id, UUID) for group_id in normalized.allow_groups)


async def test_connector_auth_failure_marks_datasource(app_client) -> None:
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|connector-auth", email="connector-auth@example.com")
    space_id = await create_space(app_client, token, name="Connector Auth", slug="connector-auth")
    datasource_id = await create_connector_datasource(
        tenant_id=TENANT_A,
        space_id=space_id,
        secret_ref="sharepoint://tenant-auth",
    )
    payload = JobPayload(
        tenant_id=TENANT_A,
        job_key=f"sync:{datasource_id}",
        trace_id="trace-auth-failure",
    )

    with pytest.raises(ConnectorAuthError):
        with patch.object(ConnectorSyncService, "sync_datasource", side_effect=ConnectorAuthError()):
            from apps.worker.jobs.ingestion import connector_sync_job

            await connector_sync_job({}, payload.model_dump(mode="json"), str(datasource_id), "sharepoint://tenant-auth")

    datasource = await get_datasource(TENANT_A, datasource_id)
    assert datasource.last_sync_status == "auth_error"


async def test_identity_sync_result() -> None:
    service = IdentitySyncService(
        provider=StaticDirectoryProvider(
            DirectorySnapshot(
                users=[
                    DirectoryUser(
                        okta_sub="okta|identity-phase6",
                        email="identity-phase6@example.com",
                        group_external_ids=["hr-team@company.com"],
                    )
                ],
                groups=[DirectoryGroup(external_id="hr-team@company.com", display_name="HR Team")],
                partial_failures=0,
            )
        )
    )

    result = await service.sync_tenant(tenant_id=TENANT_A)

    assert isinstance(result, IdentitySyncResult)
    assert result.completed_at is not None
    assert result.partial_failures == 0
