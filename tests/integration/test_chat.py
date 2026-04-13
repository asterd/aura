from __future__ import annotations

import logging
import io
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from aura.adapters.db.models import Message
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from tests.conftest import TENANT_A, TENANT_WITH_PII_POLICY, TEST_DATABASE_URL, generate_test_jwt, wait_for_job


pytestmark = pytest.mark.asyncio


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_space(
    app_client,
    token: str,
    *,
    name: str,
    slug: str,
) -> UUID:
    response = await app_client.post(
        "/api/v1/spaces",
        json={
            "name": name,
            "slug": f"{slug}-{uuid4().hex[:8]}",
            "space_type": "team",
            "visibility": "private",
            "source_access_mode": "space_acl_only",
        },
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def upload_text_doc(app_client, token: str, space_id: UUID, text: str, filename: str = "policy.txt") -> None:
    response = await app_client.post(
        "/api/v1/datasources/upload",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
        data={"space_id": str(space_id)},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    await wait_for_job(UUID(response.json()["job_id"]))


async def get_message(message_id: UUID) -> Message | None:
    async with AsyncSessionLocal() as session:
        await set_tenant_rls(session, TENANT_A)
        return await session.scalar(select(Message).where(Message.id == message_id))


async def set_default_pii_policy(
    *,
    tenant_id: UUID,
    mode: str,
    allow_raw_in_logs: bool = False,
    allow_raw_in_traces: bool = False,
) -> None:
    owner_url = TEST_DATABASE_URL.replace("://aura_app:aura_app@", "://aura_service:aura_service@", 1)
    owner_engine = create_async_engine(owner_url)
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE pii_policies
                SET mode = :mode,
                    allow_raw_in_logs = :allow_raw_in_logs,
                    allow_raw_in_traces = :allow_raw_in_traces
                WHERE tenant_id = :tenant_id AND is_default = TRUE
                """
            ),
            {
                "tenant_id": tenant_id,
                "mode": mode,
                "allow_raw_in_logs": allow_raw_in_logs,
                "allow_raw_in_traces": allow_raw_in_traces,
            },
        )
    await owner_engine.dispose()


async def test_chat_respond_with_citations(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|chat-user-a", email="chat-a@example.com")
    space_id = await create_space(app_client, token, name="Chat Space", slug="chat-space")
    await upload_text_doc(app_client, token, space_id, "La policy ferie e 25 giorni.")

    response = await app_client.post(
        "/api/v1/chat/respond",
        json={
            "message": "Quanti giorni di ferie ho?",
            "space_ids": [str(space_id)],
            "stream": False,
        },
        headers=auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"]
    assert len(body["citations"]) > 0
    assert body["trace_id"]


async def test_chat_stream_events_typed(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|chat-stream-a", email="chat-stream-a@example.com")
    space_id = await create_space(app_client, token, name="Chat Stream Space", slug="chat-stream-space")
    await upload_text_doc(app_client, token, space_id, "La policy ferie e 25 giorni.")

    async with app_client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "test", "space_ids": [str(space_id)], "stream": True},
        headers=auth(token),
    ) as response:
        assert response.status_code == 200, response.text
        events = [
            json.loads(line.removeprefix("data: ").strip())
            async for line in response.aiter_lines()
            if line.startswith("data:")
        ]

    types = [event["type"] for event in events]
    assert "token" in types
    assert types[-1] in ("done", "error")


async def test_retrieval_acl_respected(app_client):
    member_token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|member-a", email="member-a@example.com")
    non_member_token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|not-member-a", email="not-member-a@example.com")
    space_id = await create_space(app_client, member_token, name="Private Space", slug="private-space")
    await upload_text_doc(app_client, member_token, space_id, "Documento privato.")

    response = await app_client.post(
        "/api/v1/chat/retrieve",
        json={"query": "test", "space_ids": [str(space_id)]},
        headers=auth(non_member_token),
    )
    assert response.status_code == 403, response.text


async def test_conversation_persisted(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|persist-a", email="persist-a@example.com")
    space_id = await create_space(app_client, token, name="Persist Space", slug="persist-space")
    await upload_text_doc(app_client, token, space_id, "Contesto persistente.")

    response = await app_client.post(
        "/api/v1/chat/respond",
        json={"message": "ciao", "space_ids": [str(space_id)], "stream": False},
        headers=auth(token),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    message = await get_message(UUID(payload["message_id"]))
    assert message is not None
    assert message.conversation_id == UUID(payload["conversation_id"])
    assert message.role == "assistant"


async def test_chat_respond_reuses_existing_conversation(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|reuse-a", email="reuse-a@example.com")
    space_id = await create_space(app_client, token, name="Reuse Space", slug="reuse-space")
    await upload_text_doc(app_client, token, space_id, "Contesto per conversazione esistente.")

    first = await app_client.post(
        "/api/v1/chat/respond",
        json={"message": "prima", "space_ids": [str(space_id)], "stream": False},
        headers=auth(token),
    )
    assert first.status_code == 200, first.text
    conversation_id = first.json()["conversation_id"]

    second = await app_client.post(
        "/api/v1/chat/respond",
        json={
            "conversation_id": conversation_id,
            "message": "seconda",
            "space_ids": [str(space_id)],
            "stream": False,
        },
        headers=auth(token),
    )

    assert second.status_code == 200, second.text
    assert second.json()["conversation_id"] == conversation_id


async def test_model_override_not_in_allowlist_rejected(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|model-a", email="model-a@example.com")
    space_id = await create_space(app_client, token, name="Model Space", slug="model-space")
    await upload_text_doc(app_client, token, space_id, "Contesto model policy.")

    response = await app_client.post(
        "/api/v1/chat/respond",
        json={
            "message": "test",
            "space_ids": [str(space_id)],
            "model_override": "gpt-4-turbo",
        },
        headers=auth(token),
    )

    assert response.status_code == 422, response.text
    assert "not allowed" in response.text


async def test_no_raw_pii_in_logs(app_client):
    await set_default_pii_policy(tenant_id=TENANT_WITH_PII_POLICY, mode="mask_persist_and_inference", allow_raw_in_logs=False)

    token = generate_test_jwt(
        tenant_id=TENANT_WITH_PII_POLICY,
        okta_sub="okta|pii-log-a",
        email="pii-log-a@example.com",
    )
    space_id = await create_space(app_client, token, name="PII Space", slug="pii-space")
    await upload_text_doc(app_client, token, space_id, "Documento policy PII.")

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    aura_logger = logging.getLogger("aura")
    aura_logger.addHandler(handler)
    aura_logger.setLevel(logging.INFO)
    try:
        response = await app_client.post(
            "/api/v1/chat/respond",
            json={
                "message": "Il mio codice fiscale è RSSMRA85M01H501Z",
                "space_ids": [str(space_id)],
            },
            headers=auth(token),
        )
        assert response.status_code == 200, response.text
    finally:
        aura_logger.removeHandler(handler)

    log_output = log_capture.getvalue()
    assert "RSSMRA85M01H501Z" not in log_output
    assert "[IT_FISCAL_CODE]" in log_output
