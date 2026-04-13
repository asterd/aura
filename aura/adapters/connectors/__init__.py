from aura.adapters.connectors.base import (
    ConnectorAclError,
    ConnectorAuthError,
    ConnectorUnavailableError,
    ConnectorWrapper,
)
from aura.adapters.connectors.sharepoint import SharePointConnector


_CONNECTORS: dict[str, ConnectorWrapper] = {
    "sharepoint": SharePointConnector(),
}


def get_connector(connector_type: str) -> ConnectorWrapper:
    try:
        return _CONNECTORS[connector_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported connector type: {connector_type}") from exc


def register_connector(connector: ConnectorWrapper) -> None:
    _CONNECTORS[connector.connector_type] = connector


__all__ = [
    "ConnectorAclError",
    "ConnectorAuthError",
    "ConnectorUnavailableError",
    "ConnectorWrapper",
    "SharePointConnector",
    "get_connector",
    "register_connector",
]
