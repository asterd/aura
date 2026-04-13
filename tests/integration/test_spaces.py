from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tests.conftest import TENANT_A, TENANT_B, generate_test_jwt


pytestmark = pytest.mark.asyncio


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_space(app_client, token: str, *, name: str, slug: str, visibility: str = "private") -> UUID:
    unique_slug = f"{slug}-{uuid4().hex[:8]}"
    response = await app_client.post(
        "/api/v1/spaces",
        json={
            "name": name,
            "slug": unique_slug,
            "space_type": "team",
            "visibility": visibility,
            "source_access_mode": "space_acl_only",
        },
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


async def test_user_sees_only_own_spaces(app_client):
    token_a = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|spaces_user_a", email="spaces_a@example.com")
    token_b = generate_test_jwt(tenant_id=TENANT_B, okta_sub="okta|spaces_user_b", email="spaces_b@example.com")

    await create_space(app_client, token_a, name="Space-A", slug="space-a")
    await create_space(app_client, token_b, name="Space-B", slug="space-b")

    response = await app_client.get("/api/v1/spaces", headers=auth(token_a))
    assert response.status_code == 200
    spaces = response.json()
    assert any(space["name"] == "Space-A" for space in spaces)
    assert all(space["tenant_id"] == str(TENANT_A) for space in spaces)
    assert all(space["name"] != "Space-B" for space in spaces)


async def test_non_member_cannot_access_space(app_client):
    token_owner = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|space_owner", email="owner@example.com")
    token_other = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|space_other", email="other@example.com")

    space_id = await create_space(app_client, token_owner, name="Private Space", slug="private-space")

    response = await app_client.get(f"/api/v1/spaces/{space_id}", headers=auth(token_other))
    assert response.status_code == 403


async def test_space_crud_lifecycle(app_client):
    token = generate_test_jwt(tenant_id=TENANT_A, okta_sub="okta|space_crud_user", email="crud@example.com")

    # Create — 201
    unique_slug = f"crud-space-{uuid4().hex[:8]}"
    response = await app_client.post(
        "/api/v1/spaces",
        json={
            "name": "CRUD Space",
            "slug": unique_slug,
            "space_type": "team",
            "visibility": "private",
            "source_access_mode": "space_acl_only",
        },
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    data = response.json()
    space_id = data["id"]
    assert data["name"] == "CRUD Space"
    assert data["slug"] == unique_slug
    assert data["status"] == "active"

    # Get — 200
    response = await app_client.get(f"/api/v1/spaces/{space_id}", headers=auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["id"] == space_id

    # Archive — 200 with status=archived
    response = await app_client.delete(f"/api/v1/spaces/{space_id}", headers=auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"
