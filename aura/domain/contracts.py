from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class UserIdentity(BaseModel):
    user_id: UUID
    tenant_id: UUID
    okta_sub: str
    email: EmailStr
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)
    group_ids: list[UUID] = Field(default_factory=list)
    is_service_identity: bool = False


class RequestContext(BaseModel):
    request_id: str
    trace_id: str
    tenant_id: UUID
    identity: UserIdentity
    now_utc: datetime
