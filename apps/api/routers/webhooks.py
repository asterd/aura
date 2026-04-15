from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel

from apps.api.dependencies.services import event_dispatcher_service
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls


router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


class WebhookAcceptedResponse(BaseModel):
    status: str
    event_id: str


@router.post("/{agent_name}/inbound", response_model=WebhookAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def inbound_webhook(
    agent_name: str,
    request: Request,
    signature: str = Header(..., alias="X-Aura-Webhook-Signature"),
    tenant_id: UUID = Header(..., alias="X-Aura-Tenant-Id"),
) -> WebhookAcceptedResponse:
    body = await request.body()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await set_tenant_rls(session, tenant_id)
            event = await event_dispatcher_service.resolve_webhook_target(
                session=session,
                tenant_id=tenant_id,
                agent_name=agent_name,
                body=body,
                signature=signature,
            )
    await event_dispatcher_service.publish(tenant_id, event)
    return WebhookAcceptedResponse(status="accepted", event_id=str(event.event_id))
