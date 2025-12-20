"""Shared configuration schemas for daemon and client.

Both gundog (daemon) and gundog-client use this same code to parse configs.
This ensures the config formats never diverge.

Config files:
    ~/.config/gundog/daemon.yaml  - Server configuration
    ~/.config/gundog/client.yaml  - Client/TUI configuration
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml


def get_config_dir() -> Path:
    """Get config directory, respecting XDG_CONFIG_HOME."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "gundog"
    return Path.home() / ".config" / "gundog"


def get_state_dir() -> Path:
    """Get state directory, respecting XDG_STATE_HOME."""
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        return Path(xdg_state) / "gundog"
    return Path.home() / ".local" / "state" / "gundog"


# =============================================================================
# SHARED TYPES (used by both daemon and client configs)
# =============================================================================


@dataclass
class DaemonAddress:
    """Daemon connection address - shared between daemon and client."""

    host: str = "127.0.0.1"
    port: int = 7676
    use_tls: bool = False

    @property
    def http_url(self) -> str:
        """Get HTTP URL for the daemon."""
        scheme = "https" if self.use_tls else "http"
        return f"{scheme}://{self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        """Get WebSocket URL for the daemon."""
        scheme = "wss" if self.use_tls else "ws"
        return f"{scheme}://{self.host}:{self.port}/ws"

    @classmethod
    def from_url(cls, url: str) -> DaemonAddress:
        """Parse a URL into a DaemonAddress.

        Args:
            url: URL like 'http://127.0.0.1:7676' or 'https://gundog.example.com'

        Returns:
            DaemonAddress with parsed host, port, and TLS setting.

        Raises:
            ValueError: If URL is invalid or has unsupported scheme.
        """
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. Use 'http://' or 'https://'")

        use_tls = parsed.scheme == "https"
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if use_tls else 7676)

        return cls(host=host, port=port, use_tls=use_tls)


@dataclass
class AuthConfig:
    """Authentication configuration."""

    enabled: bool = False
    api_key: str | None = None

    def __post_init__(self) -> None:
        """Allow env var override for API key."""
        if self.api_key is None:
            self.api_key = os.environ.get("GUNDOG_API_KEY")


@dataclass
class CorsConfig:
    """CORS configuration."""

    allowed_origins: list[str] = field(default_factory=list)


# =============================================================================
# DAEMON CONFIG (~/.config/gundog/daemon.yaml)
# =============================================================================

DAEMON_CONFIG_TEMPLATE = """\
# Gundog daemon configuration

daemon:
  host: 127.0.0.1
  port: 7676
  serve_ui: true
  auth:
    enabled: false
    # Set via GUNDOG_API_KEY env var or directly here
    api_key: null
  cors:
    allowed_origins: []

# Register indexes with: gundog daemon add <name> <path>
indexes: {}

default_index: null
"""


@dataclass
class DaemonSettings:
    """Daemon server settings."""

    host: str = "127.0.0.1"
    port: int = 7676
    serve_ui: bool = True
    auth: AuthConfig = field(default_factory=AuthConfig)
    cors: CorsConfig = field(default_factory=CorsConfig)

    def to_address(self) -> DaemonAddress:
        """Convert to DaemonAddress for client use."""
        return DaemonAddress(host=self.host, port=self.port)


@dataclass
class DaemonConfig:
    """Daemon configuration (daemon.yaml)."""

    daemon: DaemonSettings = field(default_factory=DaemonSettings)
    indexes: dict[str, str] = field(default_factory=dict)
    default_index: str | None = None

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the default daemon config path."""
        return get_config_dir() / "daemon.yaml"

    @classmethod
    def get_pid_path(cls) -> Path:
        """Get the daemon PID file path."""
        return get_state_dir() / "daemon.pid"

    @classmethod
    def load(cls, config_path: Path | None = None) -> DaemonConfig:
        """Load config from file.

        Args:
            config_path: Path to config file. Defaults to ~/.config/gundog/daemon.yaml

        Raises:
            FileNotFoundError: If config file doesn't exist.
        """
        if config_path is None:
            config_path = cls.get_config_path()

        if not config_path.exists():
            raise FileNotFoundError(
                f"Daemon config not found: {config_path}\nRun 'gundog daemon start' to create it."
            )

        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

        return cls._from_dict(data)

    @classmethod
    def load_or_create(cls, config_path: Path | None = None) -> tuple[DaemonConfig, bool]:
        """Load config, creating default if not exists.

        Returns:
            Tuple of (config, was_created).
        """
        if config_path is None:
            config_path = cls.get_config_path()

        created = False
        if not config_path.exists():
            cls.bootstrap(config_path)
            created = True

        return cls.load(config_path), created

    @classmethod
    def bootstrap(cls, config_path: Path | None = None) -> Path:
        """Create default config file.

        Returns:
            Path to the created config file.
        """
        if config_path is None:
            config_path = cls.get_config_path()

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(DAEMON_CONFIG_TEMPLATE)
        return config_path

    @classmethod
    def _from_dict(cls, data: dict) -> DaemonConfig:
        """Parse config from dict."""
        daemon_data = data.get("daemon", {})
        auth_data = daemon_data.get("auth", {})
        cors_data = daemon_data.get("cors", {})

        auth = AuthConfig(
            enabled=auth_data.get("enabled", False),
            api_key=auth_data.get("api_key"),
        )
        cors = CorsConfig(
            allowed_origins=cors_data.get("allowed_origins", []),
        )
        daemon = DaemonSettings(
            host=daemon_data.get("host", "127.0.0.1"),
            port=daemon_data.get("port", 7676),
            serve_ui=daemon_data.get("serve_ui", True),
            auth=auth,
            cors=cors,
        )

        return cls(
            daemon=daemon,
            indexes=data.get("indexes", {}) or {},
            default_index=data.get("default_index"),
        )

    def save(self, config_path: Path | None = None) -> None:
        """Save config to file."""
        if config_path is None:
            config_path = self.get_config_path()

        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "daemon": {
                "host": self.daemon.host,
                "port": self.daemon.port,
                "serve_ui": self.daemon.serve_ui,
                "auth": {
                    "enabled": self.daemon.auth.enabled,
                    "api_key": self.daemon.auth.api_key,
                },
                "cors": {
                    "allowed_origins": self.daemon.cors.allowed_origins,
                },
            },
            "indexes": self.indexes,
            "default_index": self.default_index,
        }

        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def add_index(self, name: str, path: str) -> None:
        """Add an index to the config."""
        self.indexes[name] = path
        if self.default_index is None:
            self.default_index = name

    def remove_index(self, name: str) -> bool:
        """Remove an index from the config.

        Returns:
            True if the index was removed, False if it didn't exist.
        """
        if name not in self.indexes:
            return False
        del self.indexes[name]
        if self.default_index == name:
            self.default_index = next(iter(self.indexes), None)
        return True

    def get_index_path(self, name: str | None = None) -> str | None:
        """Get path for an index by name, or default index."""
        if name is None:
            name = self.default_index
        if name is None:
            return None
        return self.indexes.get(name)


# =============================================================================
# CLIENT CONFIG (~/.config/gundog/client.yaml)
# =============================================================================

CLIENT_CONFIG_TEMPLATE = """\
# Gundog client configuration

# Daemon URL (e.g., http://127.0.0.1:7676 or https://gundog.example.com)
daemon_url: http://127.0.0.1:7676

# Default index to use (optional, uses daemon's default if not set)
default_index: null

# TUI settings
tui:
  search_debounce_ms: 300
  theme: dark
  graph_layout: spring  # spring, kamada_kawai, circular

# Auto-reconnect settings
connection:
  auto_reconnect: true
  reconnect_max_delay: 30

# Local paths for file preview (index_name: local_path)
# Example:
#   my-project: ~/code/my-project
local_paths: {}

# Editor for opening files
editor: null  # Falls back to $EDITOR
editor_line_flag: "+{line}"  # How to pass line number to editor
"""


@dataclass
class TuiSettings:
    """TUI-specific settings."""

    search_debounce_ms: int = 300
    theme: str = "dark"
    graph_layout: str = "spring"


@dataclass
class ConnectionSettings:
    """Connection/reconnect settings."""

    auto_reconnect: bool = True
    reconnect_max_delay: int = 30


@dataclass
class ClientConfig:
    """Client configuration (client.yaml)."""

    daemon: DaemonAddress = field(default_factory=DaemonAddress)
    default_index: str | None = None
    tui: TuiSettings = field(default_factory=TuiSettings)
    connection: ConnectionSettings = field(default_factory=ConnectionSettings)
    local_paths: dict[str, str] = field(default_factory=dict)
    editor: str | None = None
    editor_line_flag: str = "+{line}"

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the default client config path."""
        return get_config_dir() / "client.yaml"

    @classmethod
    def load(cls, config_path: Path | None = None) -> ClientConfig:
        """Load config from file or return defaults.

        Unlike DaemonConfig, this returns defaults if file doesn't exist.
        """
        if config_path is None:
            config_path = cls.get_config_path()

        if not config_path.exists():
            return cls()

        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

        return cls._from_dict(data)

    @classmethod
    def load_or_create(cls, config_path: Path | None = None) -> tuple[ClientConfig, bool]:
        """Load config, creating default if not exists.

        Returns:
            Tuple of (config, was_created).
        """
        if config_path is None:
            config_path = cls.get_config_path()

        created = False
        if not config_path.exists():
            cls.bootstrap(config_path)
            created = True

        return cls.load(config_path), created

    @classmethod
    def bootstrap(cls, config_path: Path | None = None) -> Path:
        """Create default config file.

        Returns:
            Path to the created config file.
        """
        if config_path is None:
            config_path = cls.get_config_path()

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(CLIENT_CONFIG_TEMPLATE)
        return config_path

    @classmethod
    def _from_dict(cls, data: dict) -> ClientConfig:
        """Parse config from dict."""
        tui_data = data.get("tui", {})
        conn_data = data.get("connection", {})

        # Support both new daemon_url format and legacy daemon dict
        daemon_url = data.get("daemon_url")
        if daemon_url:
            daemon = DaemonAddress.from_url(daemon_url)
        else:
            # Legacy format support
            daemon_data = data.get("daemon", {})
            daemon = DaemonAddress(
                host=daemon_data.get("host", "127.0.0.1"),
                port=daemon_data.get("port", 7676),
                use_tls=daemon_data.get("use_tls", False),
            )

        tui = TuiSettings(
            search_debounce_ms=tui_data.get("search_debounce_ms", 300),
            theme=tui_data.get("theme", "dark"),
            graph_layout=tui_data.get("graph_layout", "spring"),
        )

        connection = ConnectionSettings(
            auto_reconnect=conn_data.get("auto_reconnect", True),
            reconnect_max_delay=conn_data.get("reconnect_max_delay", 30),
        )

        return cls(
            daemon=daemon,
            default_index=data.get("default_index"),
            tui=tui,
            connection=connection,
            local_paths=data.get("local_paths", {}),
            editor=data.get("editor"),
            editor_line_flag=data.get("editor_line_flag", "+{line}"),
        )

    def save(self, config_path: Path | None = None) -> None:
        """Save config to file."""
        if config_path is None:
            config_path = self.get_config_path()

        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "daemon_url": self.daemon.http_url,
            "default_index": self.default_index,
            "tui": {
                "search_debounce_ms": self.tui.search_debounce_ms,
                "theme": self.tui.theme,
                "graph_layout": self.tui.graph_layout,
            },
            "connection": {
                "auto_reconnect": self.connection.auto_reconnect,
                "reconnect_max_delay": self.connection.reconnect_max_delay,
            },
            "local_paths": self.local_paths,
            "editor": self.editor,
            "editor_line_flag": self.editor_line_flag,
        }

        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def set_local_path(self, index_name: str, path: str) -> None:
        """Set local path for an index."""
        self.local_paths[index_name] = path

    def get_local_path(self, index_name: str) -> str | None:
        """Get local path for an index."""
        return self.local_paths.get(index_name)

    def set_daemon_url(self, url: str) -> None:
        """Set daemon URL from a URL string.

        Args:
            url: URL like 'http://127.0.0.1:7676' or 'https://gundog.example.com'

        Raises:
            ValueError: If URL is invalid.
        """
        self.daemon = DaemonAddress.from_url(url)
