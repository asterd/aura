from __future__ import annotations

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def apply_migrations():
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_test_services():
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_external_state():
    yield
