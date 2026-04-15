from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from aura.adapters.db.models import AgentRun, AgentTriggerRegistration, MessageAgentRun
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.services.trigger_scheduler_service import TriggerSchedulerService
from tests.conftest import TENANT_A, generate_test_jwt


pytestmark = pytest.mark.asyncio


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_agent_zip() -> bytes:
    source = """
from __future__ import annotations

class _Result:
    def __init__(self, output):
        self.output = output

class _Agent:
    async def run(self, input_data, deps=None):
        return _Result({"result": input_data.get("user_message") or input_data.get("query") or "ok"})

def build(deps):
    return _Agent()
""".strip()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("agent.py", source)
    return buffer.getvalue()


def build_manifest(
    *,
    name: str,
    status: str,
    agent_type: str = "single",
    triggers: list[dict] | None = None,
    version: str | None = None,
) -> str:
    payload = {
        "kind": "agent",
        "name": name,
        "version": version or f"1.0.{uuid4().hex[:8]}",
        "agent_type": agent_type,
        "runtime": "pydantic-ai",
        "entrypoint": "agent.py:build",
        "allowed_tools": [],
        "allowed_spaces": [],
        "model_policy": "default",
        "timeout_s": 60,
        "status": status,
    }
    if triggers is not None:
        payload["triggers"] = triggers
    return "\n".join(f"{key}: {json.dumps(value) if isinstance(value, (list, dict)) else value}" for key, value in payload.items())


async def upload_agent(app_client, token: str, *, name: str, status: str, agent_type: str = "single", triggers=None):
    response = await app_client.post(
        "/api/v1/admin/agents/upload",
        data={"manifest": build_manifest(name=name, status=status, agent_type=agent_type, triggers=triggers)},
        files={"artifact": ("agent.zip", build_agent_zip(), "application/zip")},
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def create_space(app_client, token: str, *, name: str, slug: str) -> UUID:
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


async def publish_agent(app_client, token: str, version_id: UUID):
    response = await app_client.post(
        f"/api/v1/admin/agents/{version_id}/publish",
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_non_published_agent_not_executable(app_client):
    token = generate_test_jwt(
        tenant_id=TENANT_A,
        okta_sub="okta|agent-draft",
        email="agent-draft@example.com",
        roles=["admin", "tenant_admin"],
    )
    uploaded = await upload_agent(app_client, token, name="draft-agent", status="draft")

    response = await app_client.post(
        f"/api/v1/agents/{uploaded['name']}/run",
        json={"input": {}},
        headers=auth(token),
    )

    assert response.status_code == 403, response.text


async def test_cron_trigger_fires_on_schedule(app_client):
    token = generate_test_jwt(
        tenant_id=TENANT_A,
        okta_sub="okta|agent-cron",
        email="agent-cron@example.com",
        roles=["admin", "tenant_admin"],
    )
    uploaded = await upload_agent(
        app_client,
        token,
        name="cron-agent",
        status="validated",
        agent_type="autonomous",
        triggers=[{"type": "cron", "cron_expression": "0 8 * * 1", "max_runs": 1, "run_as_service_identity": True}],
    )
    await publish_agent(app_client, token, UUID(uploaded["id"]))

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, TENANT_A)
            results = await TriggerSchedulerService().run_due_cron_triggers(
                session,
                TENANT_A,
                now=datetime(2026, 4, 13, 8, 0, tzinfo=UTC),
            )
            registrations = (
                await session.execute(
                    select(AgentTriggerRegistration).where(AgentTriggerRegistration.agent_version_id == UUID(uploaded["id"]))
                )
            ).scalars().all()
            runs = (
                await session.execute(select(AgentRun).where(AgentRun.agent_version_id == UUID(uploaded["id"])))
            ).scalars().all()

        matched_results = [result for result in results if result.agent_version == uploaded["version"]]
        assert len(matched_results) == 1
        assert len(registrations) == 1
        assert registrations[0].runs_count == 1
        assert len(runs) == 1
    assert runs[0].status == "succeeded"


async def test_agent_mention_invokes_agent(app_client):
    token = generate_test_jwt(
        tenant_id=TENANT_A,
        okta_sub="okta|agent-mention",
        email="agent-mention@example.com",
        roles=["admin", "tenant_admin"],
    )
    uploaded = await upload_agent(app_client, token, name="mention-agent", status="validated")
    await publish_agent(app_client, token, UUID(uploaded["id"]))
    space_id = await create_space(app_client, token, name="Agent Mention Space", slug="agent-mention-space")

    response = await app_client.post(
        "/api/v1/chat/respond",
        json={
            "message": "@mention-agent dimmi qualcosa",
            "space_ids": [str(space_id)],
            "stream": False,
        },
        headers=auth(token),
    )
    assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, TENANT_A)
            runs = (
                await session.execute(select(AgentRun).where(AgentRun.agent_version_id == UUID(uploaded["id"])))
            ).scalars().all()
            run_ids = [run.id for run in runs]
            links = (
                await session.execute(select(MessageAgentRun).where(MessageAgentRun.agent_run_id.in_(run_ids)))
            ).scalars().all()

    assert len(runs) == 1
    assert runs[0].status == "succeeded"
    assert len(links) == 1
