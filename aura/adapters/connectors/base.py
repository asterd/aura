from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from aura.domain.contracts import LoadedDocument, ResolvedCredentials


class ConnectorError(RuntimeError):
    pass


class ConnectorAuthError(ConnectorError):
    pass


class ConnectorUnavailableError(ConnectorError):
    pass


class ConnectorAclError(ConnectorError):
    pass


class ConnectorWrapper(Protocol):
    connector_type: str
    supports_access_control: bool
    supports_incremental_sync: bool
    supports_remote_delete_detection: bool

    def load_documents(
        self,
        datasource_id: UUID,
        credentials: ResolvedCredentials,
        cursor: str | None,
    ) -> AsyncIterator[LoadedDocument]: ...

    def update_cursor(
        self,
        current_cursor: str | None,
        loaded: LoadedDocument,
    ) -> str | None: ...
