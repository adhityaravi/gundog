"""Gundog Core - Shared types, protocols, and client implementation.

This package provides the foundation for gundog:
- Data types for search results, graphs, and indexes
- HTTP and WebSocket client for daemon communication
- Configuration parsing for both daemon and client configs
- Shared error types

Both gundog (server) and gundog-client (TUI) depend on this package.
"""

from gundog_core.client import DaemonClient
from gundog_core.config import (
    # Shared types
    AuthConfig,
    # Client config
    ClientConfig,
    ConnectionSettings,
    CorsConfig,
    DaemonAddress,
    # Daemon config
    DaemonConfig,
    DaemonSettings,
    TuiSettings,
    # Shared utilities
    get_config_dir,
    get_state_dir,
)
from gundog_core.errors import (
    AuthenticationError,
    ConfigError,
    ConnectionError,
    GundogError,
    IndexNotFoundError,
    QueryError,
)
from gundog_core.types import (
    GraphData,
    GraphEdge,
    GraphNode,
    IndexInfo,
    QueryResponse,
    RelatedHit,
    SearchHit,
)

__all__ = [
    "AuthConfig",
    "AuthenticationError",
    "ClientConfig",
    "ConfigError",
    "ConnectionError",
    "ConnectionSettings",
    "CorsConfig",
    "DaemonAddress",
    "DaemonClient",
    "DaemonConfig",
    "DaemonSettings",
    "GraphData",
    "GraphEdge",
    "GraphNode",
    "GundogError",
    "IndexInfo",
    "IndexNotFoundError",
    "QueryError",
    "QueryResponse",
    "RelatedHit",
    "SearchHit",
    "TuiSettings",
    "get_config_dir",
    "get_state_dir",
]
