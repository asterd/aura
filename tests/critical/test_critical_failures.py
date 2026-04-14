from __future__ import annotations

import asyncio
import io
import logging
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from arq import Retry
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sqlalchemy import select

from apps.api.config import settings
from apps.worker.jobs.ingestion import connector_sync_job
from aura.adapters.connectors import register_connector
from aura.adapters.connectors.base import ConnectorUnavailableError
from aura.adapters.connectors.sharepoint import SharePointConnector
from aura.adapters.db.models import User
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.adapters.langfuse.client import LangfuseUnavailableError
from aura.domain.contracts import JobPayload
from aura.services.connector_sync_service import ConnectorSyncService
from aura.services.identity_sync_service import (
    DirectoryGroup,
    DirectorySnapshot,
    DirectoryUser,
    IdentitySyncService,
    StaticDirectoryProvider,
)
from aura.services.ingestion_service import IngestionService
from aura.services.llm_service import LlmResult
from aura.utils.observability import get_trace_events
from aura.utils.secrets import MemorySecretStore
from tests.conftest import TENANT_A, generate_test_jwt, insert_test_group, wait_for_job
from tests.integration.test_agents import test_non_published_agent_not_executable as baseline_non_published_agent_not_executable
from tests.integration.test_chat import (
    create_space as create_chat_space,
    set_default_pii_policy,
    upload_text_doc,
)
from tests.integration.test_connectors import (
    auth,
    create_connector_datasource,
    create_space as create_connector_space,
    get_document_for_datasource,
    test_credentials_never_serialized as baseline_credentials_never_serialized,
    test_stale_acl_after_sync as baseline_stale_acl_after_sync,
)
from tests.integration.test_identity import test_cross_tenant_isolation as baseline_cross_tenant_isolation
from tests.integration.test_ingestion import count_document_versions, test_ingest_idempotent as baseline_ingest_idempotent, upload_test_doc
from tests.integration.test_skills_mcp import test_sandbox_network_blocked as baseline_sandbox_network_blocked


pytestmark = pytest.mark.asyncio


async def _get_user(tenant_id: UUID, okta_sub: str) -> User:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, tenant_id)
        user = await session.scalar(select(User).where(User.tenant_id == tenant_id, User.okta_sub == okta_sub))
        assert user is not None
        return user


def _count_indexed_chunks(*, space_id: UUID) -> int:
    client = QdrantClient(url=str(settings.qdrant_url))
    results, _ = client.scroll(
        "aura_chunks",
        scroll_filter=models.Filter(
            must=[models.FieldCondition(key="space_id", match=models.MatchValue(value=str(space_id)))]
        ),
        limit=100,
    )
    return len(results)


async def test_1_tenant_isolation(setup_tenants) -> None:
    await baseline_cross_tenant_isolation(setup_tenants)


async def test_2_stale_source_acl(app_client) -> None:
    await baseline_stale_acl_after_sync(app_client)


async def test_3_stale_identity_mapping(app_client) -> None:
    await insert_test_group(tenant_id=TENANT_A, external_id="hr-team@company.com")
    token = generate_test_jwt(
        tenant_id=TENANT_A,
        okta_sub="okta|identity-stale",
        email="identity-stale@example.com",
        groups=["hr-team@company.com"],
    )
    space_id = await create_connector_space(
        app_client,
        token,
        name="Identity ACL Space",
        slug="identity-acl-space",
        source_access_mode="source_acl_enforced",
    )
    user = await _get_user(TENANT_A, "okta|identity-stale")
    datasource_id = await create_connector_datasource(
        tenant_id=TENANT_A,
        space_id=space_id,
        secret_ref="sharepoint://identity-stale",
    )

    raw_documents: list[dict[str, object]] = [
        {
            "external_id": "identity-doc-001",
            "title": "Identity restricted policy",
            "source_path": "/sites/hr/identity-doc-001",
            "content_type": "text/plain",
            "raw_text": "Documento visibile solo al gruppo HR.",
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
                "sharepoint://identity-stale": (
                    '{"credential_type":"oauth2_bearer","token_or_key":"secret","extra":{}}'
                )
            }
        )
    )
    payload = JobPayload(
        tenant_id=TENANT_A,
        job_key=f"sync:{datasource_id}",
        requested_by_user_id=user.id,
        trace_id="trace-identity-stale",
    )

    await connector_service.sync_datasource(payload=payload, datasource_id=datasource_id, secret_ref="sharepoint://identity-stale")
    document = await get_document_for_datasource(TENANT_A, datasource_id, "identity-doc-001")
    await IngestionService().ingest_document(payload=payload, document_id=document.id)

    first_provider = StaticDirectoryProvider(
        DirectorySnapshot(
            users=[
                DirectoryUser(
                    okta_sub="okta|identity-stale",
                    email="identity-stale@example.com",
                    group_external_ids=["hr-team@company.com"],
                )
            ],
            groups=[DirectoryGroup(external_id="hr-team@company.com", display_name="HR Team")],
        )
    )
    await IdentitySyncService(provider=first_provider).sync_tenant(tenant_id=TENANT_A)

    second_provider = StaticDirectoryProvider(
        DirectorySnapshot(
            users=[
                DirectoryUser(
                    okta_sub="okta|identity-stale",
                    email="identity-stale@example.com",
                    group_external_ids=[],
                )
            ],
            groups=[DirectoryGroup(external_id="hr-team@company.com", display_name="HR Team")],
        )
    )
    await IdentitySyncService(provider=second_provider).sync_tenant(tenant_id=TENANT_A)

    token_without_group = generate_test_jwt(
        tenant_id=TENANT_A,
        okta_sub="okta|identity-stale",
        email="identity-stale@example.com",
        groups=[],
    )
    retrieval_response = await app_client.post(
        "/api/v1/chat/retrieve",
        json={"query": "HR", "space_ids": [str(space_id)]},
        headers=auth(token_without_group),
    )

    assert retrieval_response.status_code == 200, retrieval_response.text
    assert retrieval_response.json()["result"]["citations"] == []


async def test_4_no_raw_pii_in_logs(app_client) -> None:
    await set_default_pii_policy(
        tenant_id=TENANT_A,
        mode="mask_persist_and_inference",
        allow_raw_in_logs=False,
    )
    token = generate_test_jwt(
        tenant_id=TENANT_A,
        okta_sub="okta|pii-critical",
        email="pii-critical@example.com",
    )
    space_id = await create_chat_space(app_client, token, name="Critical PII Space", slug="critical-pii-space")
    await upload_text_doc(app_client, token, space_id, "Documento policy PII.")

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    aura_logger = logging.getLogger("aura")
    aura_logger.addHandler(handler)
    aura_logger.setLevel(logging.INFO)
    try:
        with patch(
            "aura.services.llm_service.LlmService.generate",
            new=AsyncMock(return_value=LlmResult(content="ok", model_used="mock-model", tokens_used=3)),
        ):
            response = await app_client.post(
                "/api/v1/chat/respond",
                json={
                    "message": "Il mio codice fiscale è RSSMRA85M01H501Z",
                    "space_ids": [str(space_id)],
                },
                headers=auth(token),
            )
    finally:
        aura_logger.removeHandler(handler)

    assert response.status_code == 200, response.text
    log_output = log_capture.getvalue()
    assert "RSSMRA85M01H501Z" not in log_output
    assert "[IT_FISCAL_CODE]" in log_output


async def test_5_retry_idempotency(app_client) -> None:
    await baseline_ingest_idempotent(app_client)


async def test_6_job_locks(app_client) -> None:
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|job-locks", email="job-locks@example.com")
    space_id = await create_chat_space(app_client, token, name="Job Locks Space", slug="job-locks-space")
    document_id = await upload_test_doc(app_client, token, space_id)
    payload = JobPayload(
        tenant_id=TENANT_A,
        job_key=f"ingest:{document_id}:lock-test",
        trace_id="trace-job-locks",
    )

    parse_calls = 0
    original_parse = IngestionService._parse_document

    async def _counting_parse(self, **kwargs):
        nonlocal parse_calls
        parse_calls += 1
        await asyncio.sleep(0.1)
        return await original_parse(self, **kwargs)

    with patch.object(IngestionService, "_parse_document", new=_counting_parse):
        await asyncio.gather(
            IngestionService().ingest_document(payload=payload, document_id=document_id),
            IngestionService().ingest_document(payload=payload, document_id=document_id),
        )

    assert parse_calls == 1
    assert await count_document_versions(TENANT_A, document_id) == 1


async def test_7_runtime_artifact_immutability(app_client) -> None:
    await baseline_non_published_agent_not_executable(app_client)


async def test_8_trace_propagation(app_client) -> None:
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|trace-worker", email="trace-worker@example.com")
    space_id = await create_chat_space(app_client, token, name="Trace Space", slug="trace-space")
    trace_id = "trace-critical-worker"
    response = await app_client.post(
        "/api/v1/datasources/upload",
        files={"file": ("trace.txt", b"trace document", "text/plain")},
        data={"space_id": str(space_id)},
        headers={**auth(token), "X-Trace-Id": trace_id},
    )

    assert response.status_code == 201, response.text
    assert response.headers["X-Trace-Id"] == trace_id
    await wait_for_job(UUID(response.json()["job_id"]))

    trace_events = get_trace_events(trace_id)
    assert any(event.endswith(":started") for event in trace_events)
    assert any(event.endswith(":completed") for event in trace_events)


async def test_9_fallback_prompt_correctness(app_client) -> None:
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|prompt-fallback", email="prompt-fallback@example.com")
    space_id = await create_chat_space(app_client, token, name="Prompt Fallback Space", slug="prompt-fallback-space")
    await upload_text_doc(app_client, token, space_id, "Documento per fallback prompt.")
    fallback_text = "Sei AURA. Rispondi usando solo il contesto recuperato quando disponibile."

    async def _assert_fallback_prompt(**kwargs):
        prompt = kwargs["prompt"]
        assert any(
            message["role"] == "system" and fallback_text in message["content"]
            for message in prompt
        )
        return LlmResult(content="ok", model_used="mock-model", tokens_used=3)

    with patch("aura.adapters.langfuse.client.LangfuseClient.get_prompt", new=AsyncMock(side_effect=LangfuseUnavailableError("platform_system_prompt"))):
        with patch("aura.adapters.langfuse.client.LangfuseClient.load_fallback_prompt", wraps=None) as fallback_loader:
            fallback_loader.side_effect = lambda prompt_id: (
                "Sei AURA. Rispondi usando solo il contesto recuperato quando disponibile."
                if prompt_id == "platform_system_prompt"
                else ""
            )
            with patch(
                "aura.services.llm_service.LlmService.generate",
                new=AsyncMock(side_effect=_assert_fallback_prompt),
            ):
                response = await app_client.post(
                    "/api/v1/chat/respond",
                    json={"message": "test", "space_ids": [str(space_id)], "stream": False},
                    headers=auth(token),
                )

    assert response.status_code == 200, response.text
    assert fallback_loader.call_args_list[0].args == ("platform_system_prompt",)


async def test_10_connector_temp_failure(app_client) -> None:
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|connector-temp", email="connector-temp@example.com")
    space_id = await create_connector_space(app_client, token, name="Connector Temp Space", slug="connector-temp-space")
    datasource_id = await create_connector_datasource(
        tenant_id=TENANT_A,
        space_id=space_id,
        secret_ref="sharepoint://connector-temp",
    )

    raw_documents = [
        {
            "external_id": "temp-failure-001",
            "title": "Stable index",
            "source_path": "/sites/hr/temp-failure-001",
            "content_type": "text/plain",
            "raw_text": "Indice valido preesistente.",
            "acl": None,
            "modified_at": "2026-04-13T10:00:00+00:00",
        }
    ]

    async def _fetch_documents(credentials, cursor):
        return list(raw_documents)

    register_connector(SharePointConnector(fetcher=_fetch_documents))
    connector_service = ConnectorSyncService(
        secret_store=MemorySecretStore(
            {"sharepoint://connector-temp": '{"credential_type":"oauth2_bearer","token_or_key":"secret"}'}
        )
    )
    user = await _get_user(TENANT_A, "okta|connector-temp")
    payload = JobPayload(
        tenant_id=TENANT_A,
        job_key=f"sync:{datasource_id}",
        requested_by_user_id=user.id,
        trace_id="trace-connector-temp",
    )

    await connector_service.sync_datasource(payload=payload, datasource_id=datasource_id, secret_ref="sharepoint://connector-temp")
    document = await get_document_for_datasource(TENANT_A, datasource_id, "temp-failure-001")
    await IngestionService().ingest_document(payload=payload, document_id=document.id)
    initial_count = _count_indexed_chunks(space_id=space_id)

    connector_job_payload = payload.model_dump(mode="json")
    real_sync = connector_service.sync_datasource
    attempts = 0

    async def _flaky_sync(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectorUnavailableError()
        return await real_sync(*args, **kwargs)

    with patch.dict(connector_sync_job.__globals__, {"connector_sync_service": connector_service}):
        with patch.object(connector_service, "sync_datasource", side_effect=_flaky_sync):
            with pytest.raises(Retry) as first_error:
                await connector_sync_job(
                    {"job_try": 1},
                    connector_job_payload,
                    str(datasource_id),
                    "sharepoint://connector-temp",
                )
            assert first_error.value.defer_score == 120000
            assert _count_indexed_chunks(space_id=space_id) == initial_count

            await connector_sync_job(
                {"job_try": 2},
                connector_job_payload,
                str(datasource_id),
                "sharepoint://connector-temp",
            )

    assert _count_indexed_chunks(space_id=space_id) == initial_count


async def test_11_secret_never_serialized(app_client) -> None:
    await baseline_credentials_never_serialized(app_client)


async def test_12_sandbox_escape_prevention(app_client) -> None:
    await baseline_sandbox_network_blocked(app_client)
