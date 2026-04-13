from __future__ import annotations

from uuid import UUID

from qdrant_client.http import models

from aura.domain.contracts import UserIdentity


def build_retrieval_filter(
    tenant_id: UUID,
    space_ids: list[UUID],
    identity: UserIdentity,
    acl_mode: str,
) -> models.Filter:
    must: list[models.Condition] = [
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=str(tenant_id))),
        models.FieldCondition(key="space_id", match=models.MatchAny(any=[str(space_id) for space_id in space_ids])),
    ]

    if acl_mode == "source_acl_enforced":
        should: list[models.Condition] = [
            models.FieldCondition(key="source_acl_mode", match=models.MatchValue(value="space_acl_only")),
            models.Filter(
                must=[
                    models.FieldCondition(key="source_acl_mode", match=models.MatchValue(value="source_acl_enforced")),
                    models.FieldCondition(key="acl_allow_users", match=models.MatchValue(value=identity.okta_sub)),
                ]
            ),
        ]
        if identity.group_ids:
            should.append(
                models.Filter(
                    must=[
                        models.FieldCondition(key="source_acl_mode", match=models.MatchValue(value="source_acl_enforced")),
                        models.FieldCondition(
                            key="acl_allow_groups",
                            match=models.MatchAny(any=[str(group_id) for group_id in identity.group_ids]),
                        ),
                    ]
                )
            )
        must_not: list[models.Condition] = [
            models.FieldCondition(key="acl_deny_users", match=models.MatchValue(value=identity.okta_sub))
        ]
        if identity.group_ids:
            must_not.append(
                models.FieldCondition(
                    key="acl_deny_groups",
                    match=models.MatchAny(any=[str(group_id) for group_id in identity.group_ids]),
                )
            )
        must.append(models.Filter(should=should, min_should=models.MinShould(conditions=should, min_count=1), must_not=must_not))

    return models.Filter(must=must)
