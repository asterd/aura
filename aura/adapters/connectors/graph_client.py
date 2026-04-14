from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


@dataclass
class _TokenCache:
    access_token: str = ""
    expires_at: float = field(default=0.0)


class GraphApiClient:
    """Async client for Microsoft Graph API.

    Handles OAuth2 client-credentials flow with in-memory token cache.
    Safe for single-process asyncio use (no cross-thread sharing).
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client or httpx.AsyncClient(timeout=30.0)
        self._cache = _TokenCache()
        self._token_lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Return a valid access token, refreshing if within 60s of expiry."""
        async with self._token_lock:
            if self._cache.access_token and time.monotonic() < self._cache.expires_at - 60:
                return self._cache.access_token

            url = _TOKEN_URL.format(tenant_id=self._tenant_id)
            resp = await self._http.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._cache.access_token = str(data["access_token"])
            self._cache.expires_at = time.monotonic() + int(data.get("expires_in", 3600))
            logger.debug("Graph API token acquired, expires in %ds", data.get("expires_in"))
            return self._cache.access_token

    async def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """GET a Graph API path. Handles 429 rate-limit with a single retry."""
        token = await self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._http.get(f"{GRAPH_BASE}{path}", headers=headers, params=params)

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "10"))
            logger.warning("Graph API rate-limited, retrying after %ds", retry_after)
            await asyncio.sleep(retry_after)
            token = await self.get_token()
            headers = {"Authorization": f"Bearer {token}"}
            resp = await self._http.get(f"{GRAPH_BASE}{path}", headers=headers, params=params)

        resp.raise_for_status()
        return resp.json()  # type: ignore[return-value]

    async def paginate(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate over all pages of a Graph paginated response (@odata.nextLink)."""
        data = await self.get(path, params)
        while True:
            for item in data.get("value", []):
                yield item
            next_link: str | None = data.get("@odata.nextLink")
            if not next_link:
                break
            token = await self.get_token()
            resp = await self._http.get(next_link, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "10"))
                await asyncio.sleep(retry_after)
                token = await self.get_token()
                resp = await self._http.get(next_link, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            data = resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()
