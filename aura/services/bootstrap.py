from __future__ import annotations

import logging
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import select

from apps.api.config import settings
from aura.adapters.db.models import LocalAuthUser, Tenant
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.utils.passwords import hash_password


logger = logging.getLogger("aura")


async def ensure_s3_bucket() -> None:
    def _ensure() -> None:
        client = boto3.client(
            "s3",
            endpoint_url=str(settings.s3_endpoint_url),
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            region_name=settings.s3_region,
            use_ssl=settings.s3_secure,
        )
        try:
            client.head_bucket(Bucket=settings.s3_bucket_name)
            return
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code not in {"404", "NoSuchBucket"}:
                raise

        client.create_bucket(Bucket=settings.s3_bucket_name)
        logger.info("default_s3_bucket_created bucket=%s", settings.s3_bucket_name)

    await asyncio.to_thread(_ensure)


async def ensure_default_tenant() -> None:
    if not settings.default_tenant_enabled:
        return

    async with AsyncSessionLocal() as session:
        async with session.begin():
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
            if tenant is None:
                tenant_id = uuid4()
                await set_tenant_rls(session, tenant_id)
                tenant = Tenant(
                    id=tenant_id,
                    slug=settings.default_tenant_slug,
                    display_name=settings.default_tenant_display_name,
                    auth_mode=settings.default_tenant_auth_mode,
                    okta_jwks_url=str(settings.okta_jwks_url) if settings.default_tenant_auth_mode == "okta" else None,
                    okta_issuer=settings.okta_issuer if settings.default_tenant_auth_mode == "okta" else None,
                    okta_audience=settings.okta_audience if settings.default_tenant_auth_mode == "okta" else None,
                    status="active",
                )
                session.add(tenant)
                await session.flush()
                logger.info("default_tenant_created slug=%s tenant_id=%s", tenant.slug, tenant.id)
            else:
                await set_tenant_rls(session, tenant.id)

            if tenant.auth_mode != "local":
                return

            admin_email = settings.default_tenant_admin_email
            admin_password = settings.default_tenant_admin_password.get_secret_value() if settings.default_tenant_admin_password else None
            if not admin_email or not admin_password:
                logger.warning("default_tenant_local_admin_skipped slug=%s reason=missing_credentials", tenant.slug)
                return

            local_user = await session.scalar(
                select(LocalAuthUser).where(
                    LocalAuthUser.tenant_id == tenant.id,
                    LocalAuthUser.email == admin_email.lower(),
                )
            )
            desired_roles = ["admin", "tenant_admin", "platform_admin"]
            if local_user is not None:
                existing_roles = list(local_user.roles or [])
                if set(existing_roles) != set(desired_roles):
                    local_user.roles = desired_roles
                    local_user.updated_at = datetime.now(UTC)
                return

            session.add(
                LocalAuthUser(
                    tenant_id=tenant.id,
                    email=admin_email.lower(),
                    password_hash=hash_password(admin_password),
                    display_name=settings.default_tenant_admin_display_name or admin_email.split("@", 1)[0],
                    roles=desired_roles,
                    is_active=True,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.flush()
            logger.info("default_tenant_local_admin_created slug=%s email=%s", tenant.slug, admin_email.lower())
