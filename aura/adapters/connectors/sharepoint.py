from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import or_, select

from aura.adapters.connectors.base import ConnectorAclError, ConnectorAuthError, ConnectorWrapper
from aura.adapters.db.models import Datasource, Group
from aura.adapters.db.session import AsyncSessionLocal, set_tenant_rls
from aura.domain.contracts import DocumentMetadata, LoadedDocument, NormalizedACL, ResolvedCredentials

logger = logging.getLogger(__name__)

RawSharePointDocument = dict[str, object]
RawDocumentFetcher = Callable[[ResolvedCredentials, str | None], Awaitable[Iterable[RawSharePointDocument]]]


class _AclEntries(TypedDict):
    allow_users: list[str]
    allow_group_keys: list[str]
    deny_users: list[str]
    deny_group_keys: list[str]
    inherited: bool


class SharePointConnector(ConnectorWrapper):
    connector_type = "sharepoint"
    supports_access_control = True
    supports_incremental_sync = True
    supports_remote_delete_detection = True

    def __init__(self, *, fetcher: RawDocumentFetcher | None = None) -> None:
        self._fetcher = fetcher

    async def load_documents(
        self,
        datasource_id: UUID,
        credentials: ResolvedCredentials,
        cursor: str | None,
    ) -> AsyncIterator[LoadedDocument]:
        tenant_id = (
            UUID(str(credentials.extra.get("aura_tenant_id")))
            if credentials.extra and credentials.extra.get("aura_tenant_id")
            else await self._get_tenant_id(datasource_id)
        )
        async for raw in self._fetch_documents(credentials, cursor):
            acl = await self._normalize_acl_async(raw.get("acl"), tenant_id=tenant_id)
            if bool(raw.get("acl_required")) and acl is None:
                raise ConnectorAclError("Source ACL required but not recoverable.")
            raw_tags = raw.get("tags", [])
            tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
            metadata = DocumentMetadata(
                title=str(raw.get("title") or raw.get("name") or raw.get("external_id") or "Untitled"),
                source_path=str(raw.get("source_path") or raw.get("path") or raw.get("external_id") or ""),
                source_url=str(raw["source_url"]) if raw.get("source_url") else None,
                content_type=str(raw.get("content_type") or "text/plain"),
                language=str(raw["language"]) if raw.get("language") else None,
                classification=str(raw["classification"]) if raw.get("classification") else None,
                tags=tags,
                modified_at=_coerce_datetime(raw.get("modified_at")),
            )
            yield LoadedDocument(
                external_id=str(raw.get("external_id") or metadata.source_path),
                metadata=metadata,
                raw_text=str(raw["raw_text"]) if raw.get("raw_text") is not None else None,
                raw_bytes_ref=str(raw["raw_bytes_ref"]) if raw.get("raw_bytes_ref") else None,
                acl=acl,
                is_deleted=bool(raw.get("is_deleted", False)),
            )

    def update_cursor(self, current_cursor: str | None, loaded: LoadedDocument) -> str | None:
        modified_at = loaded.metadata.modified_at
        if modified_at is None:
            return current_cursor
        candidate = modified_at.astimezone(UTC).replace(microsecond=0).isoformat()
        if current_cursor is None or candidate > current_cursor:
            return candidate
        return current_cursor

    def normalize_acl(self, raw_acl: object, *, tenant_id: UUID) -> NormalizedACL | None:
        if raw_acl is None:
            return None
        entries = _parse_acl_entries(raw_acl)
        return NormalizedACL(
            mode="source_acl_enforced",
            allow_users=entries["allow_users"],
            allow_groups=[
                uuid5(NAMESPACE_URL, f"{tenant_id}:group:{group_key}")
                for group_key in entries["allow_group_keys"]
            ],
            deny_users=entries["deny_users"],
            deny_groups=[
                uuid5(NAMESPACE_URL, f"{tenant_id}:group:{group_key}")
                for group_key in entries["deny_group_keys"]
            ],
            inherited=bool(entries["inherited"]),
        )

    async def _normalize_acl_async(self, raw_acl: object, *, tenant_id: UUID) -> NormalizedACL | None:
        if raw_acl is None:
            return None
        entries = _parse_acl_entries(raw_acl)
        allow_groups = await self._resolve_group_ids(
            tenant_id=tenant_id,
            external_ids=entries["allow_group_keys"],
        )
        deny_groups = await self._resolve_group_ids(
            tenant_id=tenant_id,
            external_ids=entries["deny_group_keys"],
        )
        return NormalizedACL(
            mode="source_acl_enforced",
            allow_users=entries["allow_users"],
            allow_groups=allow_groups,
            deny_users=entries["deny_users"],
            deny_groups=deny_groups,
            inherited=bool(entries["inherited"]),
        )

    async def _resolve_group_ids(self, *, tenant_id: UUID, external_ids: list[str]) -> list[UUID]:
        if not external_ids:
            return []
        async with AsyncSessionLocal() as session:
            await set_tenant_rls(session, tenant_id)
            rows = await session.execute(
                select(Group.id, Group.external_id, Group.display_name).where(
                    Group.tenant_id == tenant_id,
                    or_(Group.external_id.in_(external_ids), Group.display_name.in_(external_ids)),
                )
            )
            mapping: dict[str, UUID] = {}
            for group_id, external_id, display_name in rows.all():
                mapping[str(external_id)] = group_id
                mapping[str(display_name)] = group_id
        return [mapping[group_key] for group_key in external_ids if group_key in mapping]

    async def _fetch_documents(
        self,
        credentials: ResolvedCredentials,
        cursor: str | None,
    ) -> AsyncIterator[RawSharePointDocument]:
        # Priority 1: injected fetcher (for tests and mock environments)
        if self._fetcher is not None:
            docs = await self._fetcher(credentials, cursor)
            for doc in docs:
                yield doc
            return

        # Priority 2: static documents embedded in credentials.extra (dev/test)
        extra = credentials.extra or {}
        static_docs = extra.get("documents")
        if isinstance(static_docs, list):
            for item in static_docs:
                if isinstance(item, dict):
                    yield dict(item)
            return

        # Priority 3: Microsoft Graph API (production)
        required_fields = ("client_id", "client_secret", "site_url")
        missing = [k for k in required_fields if not extra.get(k)]
        if missing:
            raise ConnectorAuthError(
                f"SharePoint credentials missing required fields: {missing}. "
                "Configure the datasource with client_id, client_secret, site_url "
                "(and optionally tenant_id, drive_id, folder_path) via SecretStore."
            )

        # Use the Azure AD tenant for Graph auth. The AURA tenant id is passed
        # separately as aura_tenant_id for ACL normalization/RLS purposes.
        graph_tenant_id = str(extra.get("azure_tenant_id") or extra.get("tenant_id", ""))
        if not graph_tenant_id:
            raise ConnectorAuthError(
                "SharePoint credentials missing Azure AD tenant id. "
                "Provide 'azure_tenant_id' (preferred) or 'tenant_id' in the datasource secret."
            )

        from aura.adapters.connectors.graph_client import GraphApiClient
        from aura.adapters.connectors.sharepoint_graph import SharePointGraphFetcher

        graph_client = GraphApiClient(
            tenant_id=graph_tenant_id,
            client_id=str(extra["client_id"]),
            client_secret=str(extra["client_secret"]),
        )
        try:
            fetcher = SharePointGraphFetcher(graph_client=graph_client)
            async for doc in fetcher.fetch(credentials, cursor):
                yield doc
        except ConnectorAuthError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error during SharePoint Graph fetch")
            raise ConnectorAuthError(f"SharePoint Graph API error: {exc}") from exc
        finally:
            await graph_client.aclose()

    async def _get_tenant_id(self, datasource_id: UUID) -> UUID:
        async with AsyncSessionLocal() as session:
            datasource = await session.scalar(select(Datasource).where(Datasource.id == datasource_id))
            if datasource is None:
                raise ValueError(f"Datasource {datasource_id} not found.")
            return datasource.tenant_id


def _coerce_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _parse_acl_entries(raw_acl: object) -> _AclEntries:
    payload = cast(dict[str, Any], raw_acl) if isinstance(raw_acl, dict) else {}
    raw_allow = payload.get("allow", [])
    raw_deny = payload.get("deny", [])
    allow = [str(item) for item in raw_allow] if isinstance(raw_allow, list) else []
    deny = [str(item) for item in raw_deny] if isinstance(raw_deny, list) else []
    public_markers = {"group:everyone", "group:organization"}

    def _group_keys(values: list[str]) -> list[str]:
        keys: list[str] = []
        for value in values:
            if value.startswith("group:") and value not in public_markers:
                keys.append(value.removeprefix("group:"))
        return keys

    def _user_keys(values: list[str]) -> list[str]:
        keys: list[str] = []
        for value in values:
            if value.startswith("user:"):
                keys.append(value.removeprefix("user:"))
            elif value in public_markers:
                keys.append("*")
            elif not value.startswith("group:"):
                keys.append(value)
        return keys

    return {
        "allow_users": _user_keys(allow),
        "allow_group_keys": _group_keys(allow),
        "deny_users": _user_keys(deny),
        "deny_group_keys": _group_keys(deny),
        "inherited": bool(payload.get("inherited", True)),
    }
