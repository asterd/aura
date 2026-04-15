from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

import aura.services.identity as identity_module
from aura.services.identity import JwksCache


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, list[dict[str, str]]]:
        return {"keys": [{"kid": "k1", "kty": "RSA"}]}


@pytest.mark.asyncio
async def test_jwks_cache_deduplicates_concurrent_fetches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class _FakeAsyncClient:
        def __init__(self, *, timeout) -> None:
            self._timeout = timeout

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def get(self, url: str) -> _FakeResponse:
            nonlocal calls
            assert url == "https://example.test/jwks"
            calls += 1
            await asyncio.sleep(0.01)
            return _FakeResponse()

    monkeypatch.setattr(identity_module.httpx, "AsyncClient", _FakeAsyncClient)
    cache = JwksCache(ttl=timedelta(minutes=5))

    results = await asyncio.gather(*[cache.get_keys("https://example.test/jwks") for _ in range(5)])

    assert calls == 1
    assert all(result == [{"kid": "k1", "kty": "RSA"}] for result in results)

