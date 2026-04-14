from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from aura.adapters.connectors.graph_client import GraphApiClient
from aura.domain.contracts import ResolvedCredentials

logger = logging.getLogger(__name__)

# MIME types that LlamaIndex can parse into text
INDEXABLE_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/msword",
        "application/vnd.ms-excel",
        "application/vnd.ms-powerpoint",
        "text/plain",
        "text/html",
        "text/markdown",
        "text/csv",
        "application/json",
    }
)

# Maximum file size to index (50 MB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024


class SharePointGraphFetcher:
    """
    Fetches SharePoint documents via Microsoft Graph API.

    Returns raw document dicts compatible with SharePointConnector.load_documents:
    {
        external_id: str,          # Graph item ID
        title: str,
        source_path: str,
        source_url: str | None,
        content_type: str,
        modified_at: str,          # ISO-8601 from Graph
        raw_text: None,            # LlamaIndex handles extraction from raw_bytes_ref
        raw_bytes_ref: str | None, # "@microsoft.graph.downloadUrl" for binary files
        acl: dict,                 # {allow: [...], deny: [], inherited: bool}
        acl_required: bool,
        is_deleted: bool,
    }

    ACL approach: Graph /permissions are fetched per item at ingest time and stored
    in Qdrant payload. Retrieval filters by allow_users/allow_groups from UserIdentity.
    """

    def __init__(self, *, graph_client: GraphApiClient) -> None:
        self._graph = graph_client

    async def fetch(
        self,
        credentials: ResolvedCredentials,
        cursor: str | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Entry point: yields raw document dicts for SharePointConnector."""
        extra = credentials.extra or {}
        site_url: str = str(extra["site_url"])
        drive_id: str | None = str(extra["drive_id"]) if extra.get("drive_id") else None
        folder_path: str = str(extra.get("folder_path", "/"))

        site_id = await self._resolve_site_id(site_url)
        if drive_id is None:
            drive_id = await self._resolve_default_drive(site_id)

        base_path = f"/sites/{site_id}/drives/{drive_id}"

        if folder_path and folder_path not in ("/", ""):
            items_path = f"{base_path}/root:{folder_path}:/children"
        else:
            items_path = f"{base_path}/root/children"

        async for doc in self._walk_items(
            base_path=base_path,
            items_path=items_path,
            cursor=cursor,
        ):
            yield doc

    async def _walk_items(
        self,
        *,
        base_path: str,
        items_path: str,
        cursor: str | None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Recursively walk Drive items, yielding indexable files."""
        async for item in self._graph.paginate(items_path, params={"$top": "200"}):
            if "folder" in item:
                child_path = f"{base_path}/items/{item['id']}/children"
                async for child in self._walk_items(
                    base_path=base_path,
                    items_path=child_path,
                    cursor=cursor,
                ):
                    yield child
                continue

            if "file" not in item:
                continue

            mime: str = item.get("file", {}).get("mimeType", "")
            if mime not in INDEXABLE_MIME_TYPES:
                logger.debug("Skipping non-indexable: %s (%s)", item.get("name"), mime)
                continue

            size: int = item.get("size", 0)
            if size > MAX_FILE_SIZE_BYTES:
                logger.warning(
                    "Skipping oversized file: %s (%d bytes > %d limit)",
                    item.get("name"),
                    size,
                    MAX_FILE_SIZE_BYTES,
                )
                continue

            modified_str: str = item.get("lastModifiedDateTime", "")
            if cursor and modified_str and modified_str <= cursor:
                logger.debug("Skipping unmodified (cursor=%s): %s", cursor, item.get("name"))
                continue

            item_id: str = item["id"]
            acl = await self._fetch_acl(base_path, item_id)

            # Download URL — Graph provides a pre-signed URL for content access
            download_url: str | None = item.get("@microsoft.graph.downloadUrl")

            parent_path: str = item.get("parentReference", {}).get("path", "")
            item_name: str = item.get("name", "")
            source_path = f"{parent_path}/{item_name}".lstrip("/")

            yield {
                "external_id": item_id,
                "title": item_name,
                "source_path": source_path,
                "source_url": item.get("webUrl"),
                "content_type": mime,
                "modified_at": modified_str,
                "raw_text": None,
                "raw_bytes_ref": download_url,
                "acl": acl,
                "acl_required": True,
                "is_deleted": False,
            }

    async def _resolve_site_id(self, site_url: str) -> str:
        """Resolve SharePoint site ID from its URL."""
        parsed = urlparse(site_url)
        hostname = parsed.hostname or ""
        path = parsed.path.rstrip("/")
        data = await self._graph.get(f"/sites/{hostname}:{path}")
        return str(data["id"])

    async def _resolve_default_drive(self, site_id: str) -> str:
        """Get the primary Drive of a SharePoint site."""
        data = await self._graph.get(f"/sites/{site_id}/drive")
        return str(data["id"])

    async def _fetch_acl(
        self, base_path: str, item_id: str
    ) -> dict[str, list[str] | bool]:
        """
        Fetch Graph permissions for an item and normalize to AURA ACL format.

        Output: {"allow": ["user:<email>", "group:<name>"], "deny": [], "inherited": bool}

        Rules:
        - Anonymous/organisation-wide links → included in allow as "group:everyone"
        - Direct user grants → "user:<email>" or "user:<id>"
        - Group grants → "group:<displayName>"
        - read/write/owner roles are all treated as allow
        """
        try:
            data = await self._graph.get(f"{base_path}/items/{item_id}/permissions")
        except Exception as exc:
            logger.warning("Failed to fetch ACL for item %s: %s — defaulting to no access", item_id, exc)
            return {"allow": [], "deny": [], "inherited": True}

        allow: list[str] = []
        inherited = True

        for perm in data.get("value", []):
            link = perm.get("link", {})

            # Anonymous links — publicly accessible
            if link.get("scope") == "anonymous":
                allow.append("group:everyone")
                continue

            # Org-wide links (all authenticated users in tenant)
            if link.get("scope") == "organization":
                allow.append("group:organization")
                continue

            if not perm.get("inheritedFrom"):
                inherited = False

            roles: list[str] = perm.get("roles", [])
            if not any(r in roles for r in ("read", "write", "owner")):
                continue

            # Single grantee
            granted_to = perm.get("grantedTo") or {}
            if granted_to:
                _extract_identity(granted_to, allow)

            # Multiple grantees (sharing links to specific people)
            for identity in perm.get("grantedToIdentities") or []:
                _extract_identity(identity, allow)

        return {"allow": allow, "deny": [], "inherited": inherited}


def _extract_identity(identity: dict[str, Any], allow: list[str]) -> None:
    """Extract user/group identifiers from a Graph identity object into allow list."""
    user = identity.get("user", {})
    group = identity.get("group", {})

    if user:
        email = user.get("email") or user.get("userPrincipalName")
        if email:
            allow.append(f"user:{email.lower()}")
        elif user.get("id"):
            allow.append(f"user:{user['id']}")

    if group:
        display_name = group.get("displayName")
        if display_name:
            allow.append(f"group:{display_name}")
        elif group.get("id"):
            allow.append(f"group:{group['id']}")
