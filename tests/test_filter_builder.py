from __future__ import annotations

from uuid import UUID

from qdrant_client.http import models

from aura.adapters.qdrant.filter_builder import build_retrieval_filter
from aura.domain.contracts import UserIdentity


def test_build_retrieval_filter_source_acl_enforced_adds_deny_clauses():
    identity = UserIdentity(
        user_id=UUID("aaaaaaaa-0000-0000-0000-000000000010"),
        tenant_id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
        okta_sub="okta|filter-user",
        email="filter@example.com",
        group_ids=[UUID("aaaaaaaa-0000-0000-0000-000000000020")],
    )

    result = build_retrieval_filter(
        tenant_id=identity.tenant_id,
        space_ids=[UUID("aaaaaaaa-0000-0000-0000-000000000030")],
        identity=identity,
        acl_mode="source_acl_enforced",
    )

    assert isinstance(result, models.Filter)
    acl_filter = result.must[-1]
    assert isinstance(acl_filter, models.Filter)
    assert acl_filter.must_not is not None
    deny_keys = [condition.key for condition in acl_filter.must_not if isinstance(condition, models.FieldCondition)]
    assert "acl_deny_users" in deny_keys
    assert "acl_deny_groups" in deny_keys


def test_build_retrieval_filter_source_acl_enforced_allows_public_marker():
    identity = UserIdentity(
        user_id=UUID("aaaaaaaa-0000-0000-0000-000000000010"),
        tenant_id=UUID("aaaaaaaa-0000-0000-0000-000000000001"),
        okta_sub="okta|filter-user",
        email="filter@example.com",
    )

    result = build_retrieval_filter(
        tenant_id=identity.tenant_id,
        space_ids=[UUID("aaaaaaaa-0000-0000-0000-000000000030")],
        identity=identity,
        acl_mode="source_acl_enforced",
    )

    acl_filter = result.must[-1]
    assert isinstance(acl_filter, models.Filter)
    nested_acl_filter = next(
        condition for condition in acl_filter.should or [] if isinstance(condition, models.Filter)
    )
    public_or_user_condition = next(
        condition
        for condition in nested_acl_filter.should or []
        if isinstance(condition, models.FieldCondition) and condition.key == "acl_allow_users"
    )
    assert isinstance(public_or_user_condition.match, models.MatchAny)
    assert "*" in public_or_user_condition.match.any
