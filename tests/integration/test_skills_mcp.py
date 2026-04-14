from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from tests.conftest import TEST_DATABASE_URL, TENANT_A, TENANT_B, generate_test_jwt


pytestmark = pytest.mark.asyncio


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def build_skill_zip(source: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("main.py", source.strip())
    return buffer.getvalue()


def build_skill_manifest(*, name: str, version: str | None = None, sandbox_policy: str | None = None) -> str:
    payload = {
        "kind": "skill",
        "name": name,
        "version": version or f"1.0.{uuid4().hex[:8]}",
        "runtime": "sandbox-python",
        "entrypoint": "main.py",
        "status": "validated",
    }
    if sandbox_policy is not None:
        payload["sandbox_policy"] = sandbox_policy
    return "\n".join(f"{key}: {json.dumps(value) if isinstance(value, (list, dict)) else value}" for key, value in payload.items())


async def upload_skill(app_client, token: str, *, name: str, source: str, sandbox_policy: str | None = None) -> dict:
    response = await app_client.post(
        "/api/v1/admin/skills/upload",
        data={"manifest": build_skill_manifest(name=name, sandbox_policy=sandbox_policy)},
        files={"artifact": ("skill.zip", build_skill_zip(source), "application/zip")},
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    publish = await app_client.post(
        f"/api/v1/admin/skills/{response.json()['id']}/publish",
        headers=auth(token),
    )
    assert publish.status_code == 200, publish.text
    return publish.json()


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


async def insert_sandbox_policy(*, tenant_id: UUID, name: str, max_wall_time_s: int) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    owner_url = TEST_DATABASE_URL.replace("://aura_app:aura_app@", "://aura_service:aura_service@", 1)
    owner_engine = create_async_engine(owner_url)
    now = datetime.now(UTC)
    try:
        async with owner_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO sandbox_policies (
                        id, tenant_id, name, network_egress, egress_allowlist, max_cpu_seconds,
                        max_memory_mb, max_wall_time_s, writable_paths, env_vars_allowed,
                        is_default, created_at, updated_at
                    )
                    VALUES (
                        :id, :tenant_id, :name, 'none', '{}'::text[], 60,
                        512, :max_wall_time_s, ARRAY['/workspace','/artifacts'], '{}'::text[],
                        FALSE, :created_at, :updated_at
                    )
                    ON CONFLICT (tenant_id, name) DO UPDATE
                    SET max_wall_time_s = EXCLUDED.max_wall_time_s,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "name": name,
                    "max_wall_time_s": max_wall_time_s,
                    "created_at": now,
                    "updated_at": now,
                },
            )
    finally:
        await owner_engine.dispose()


async def test_sandbox_network_blocked(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|skill-network", email="skill-network@example.com")
    await upload_skill(
        app_client,
        token,
        name="network-blocked",
        source="""
import json
import urllib.request

try:
    urllib.request.urlopen("http://example.com", timeout=2)
    print(json.dumps({"success": True}))
except Exception as exc:
    print(json.dumps({"success": False, "error": str(exc)}))
""",
    )

    response = await app_client.post(
        "/api/v1/skills/network-blocked/run",
        json={"input": {}},
        headers=auth(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["output"]["success"] is False


async def test_sandbox_timeout_respected(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|skill-timeout", email="skill-timeout@example.com")
    await insert_sandbox_policy(tenant_id=TENANT_A, name="short-timeout", max_wall_time_s=3)
    await upload_skill(
        app_client,
        token,
        name="timeout-skill",
        sandbox_policy="short-timeout",
        source="""
import time

time.sleep(999)
print("{\\"output\\": \\"done\\"}")
""",
    )

    started_at = datetime.now(UTC)
    response = await app_client.post(
        "/api/v1/skills/timeout-skill/run",
        json={"input": {}},
        headers=auth(token),
    )
    elapsed = (datetime.now(UTC) - started_at).total_seconds()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "timeout", body
    assert elapsed < 10


async def test_mcp_server_rls_enforced(app_client):
    token_a = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|mcp-a", email="mcp-a@example.com")
    token_b = generate_test_jwt(tenant_id=TENANT_B, okta_sub="okta|mcp-b", email="mcp-b@example.com")
    space_a = await create_space(app_client, token_a, name="Tenant A Space", slug="tenant-a-space")
    space_b = await create_space(app_client, token_b, name="Tenant B Space", slug="tenant-b-space")
    assert space_a != space_b

    async def _call_list_spaces(token: str) -> list[dict]:
        bootstrap = await app_client.get(
            "/mcp/v1/sse",
            headers={**auth(token), "x-aura-mcp-bootstrap": "1"},
        )
        assert bootstrap.status_code == 200, bootstrap.text
        endpoint = bootstrap.json()["message_endpoint"]

        initialize = await app_client.post(
            endpoint,
            headers=auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "test", "version": "0.1.0"},
                },
            },
        )
        assert initialize.status_code == 202, initialize.text

        response = await app_client.post(
            endpoint,
            headers=auth(token),
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "aura_list_spaces", "arguments": {}},
            },
        )
        assert response.status_code == 202, response.text
        body = response.json()
        return json.loads(body["result"]["content"][0]["text"])

    spaces_a = await _call_list_spaces(token_a)
    spaces_b = await _call_list_spaces(token_b)
    ids_a = {item["id"] for item in spaces_a}
    ids_b = {item["id"] for item in spaces_b}

    assert str(space_a) in ids_a
    assert str(space_b) not in ids_a
    assert str(space_b) in ids_b
    assert str(space_a) not in ids_b


async def test_mcp_session_cannot_be_hijacked(app_client):
    token_a = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|mcp-owner", email="mcp-owner@example.com")
    token_b = generate_test_jwt(tenant_id=TENANT_B, okta_sub="okta|mcp-intruder", email="mcp-intruder@example.com")

    bootstrap = await app_client.get(
        "/mcp/v1/sse",
        headers={**auth(token_a), "x-aura-mcp-bootstrap": "1"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    endpoint = bootstrap.json()["message_endpoint"]

    response = await app_client.post(
        endpoint,
        headers=auth(token_b),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "test", "version": "0.1.0"},
            },
        },
    )

    assert response.status_code == 403, response.text
