from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Protocol

from aura.domain.contracts import ConnectorCredentials, CredentialType, ResolvedCredentials


class CredentialResolutionError(RuntimeError):
    pass


class SecretStore(Protocol):
    async def get(self, ref: str) -> str: ...

    async def put(self, ref: str, value: str) -> None: ...


class EnvSecretStore:
    async def get(self, ref: str) -> str:
        key = _normalize_ref(ref)
        value = os.environ.get(key)
        if value is None:
            raise CredentialResolutionError(f"Secret ref {ref} not found.")
        return value

    async def put(self, ref: str, value: str) -> None:
        os.environ[_normalize_ref(ref)] = value


class MemorySecretStore:
    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        self._secrets = dict(initial or {})

    async def get(self, ref: str) -> str:
        if ref not in self._secrets:
            raise CredentialResolutionError(f"Secret ref {ref} not found.")
        return self._secrets[ref]

    async def put(self, ref: str, value: str) -> None:
        self._secrets[ref] = value


class VaultSecretStore:
    async def get(self, ref: str) -> str:
        raise NotImplementedError("VaultSecretStore is implemented in a later phase.")

    async def put(self, ref: str, value: str) -> None:
        raise NotImplementedError("VaultSecretStore is implemented in a later phase.")


async def resolve_credentials(
    connector_credentials: ConnectorCredentials,
    secret_store: SecretStore,
) -> ResolvedCredentials:
    raw_secret = await secret_store.get(connector_credentials.secret_ref)
    return _resolved_from_secret(
        raw_secret=raw_secret,
        credential_type=connector_credentials.credential_type,
        scopes=connector_credentials.scopes,
        tenant_domain=connector_credentials.tenant_domain,
        extra=connector_credentials.extra,
    )


async def resolve_credentials_from_ref(
    secret_ref: str,
    secret_store: SecretStore,
    *,
    default_credential_type: CredentialType = CredentialType.oauth2_bearer,
) -> ResolvedCredentials:
    raw_secret = await secret_store.get(secret_ref)
    return _resolved_from_secret(
        raw_secret=raw_secret,
        credential_type=default_credential_type,
        scopes=[],
        tenant_domain=None,
        extra={},
    )


def _resolved_from_secret(
    *,
    raw_secret: str,
    credential_type: CredentialType,
    scopes: list[str],
    tenant_domain: str | None,
    extra: dict,
) -> ResolvedCredentials:
    try:
        payload = json.loads(raw_secret)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        return ResolvedCredentials(
            credential_type=CredentialType(payload.get("credential_type", credential_type)),
            token_or_key=str(payload.get("token_or_key") or payload.get("secret_value") or ""),
            scopes=list(payload.get("scopes") or scopes),
            tenant_domain=payload.get("tenant_domain") or tenant_domain,
            extra=dict(payload.get("extra") or extra),
        )

    return ResolvedCredentials(
        credential_type=credential_type,
        token_or_key=raw_secret,
        scopes=list(scopes),
        tenant_domain=tenant_domain,
        extra=dict(extra),
    )


def _normalize_ref(ref: str) -> str:
    return ref.removeprefix("env://")
