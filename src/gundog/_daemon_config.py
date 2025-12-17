"""Daemon configuration loading and management."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "gundog" / "daemon.yaml"
DEFAULT_PID_PATH = Path.home() / ".local" / "state" / "gundog" / "daemon.pid"

CONFIG_TEMPLATE = """\
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
class AuthConfig:
    """Authentication configuration."""

    enabled: bool = False
    api_key: str | None = None

    def __post_init__(self) -> None:
        # Allow env var override
        if self.api_key is None:
            self.api_key = os.environ.get("GUNDOG_API_KEY")


@dataclass
class CorsConfig:
    """CORS configuration."""

    allowed_origins: list[str] = field(default_factory=list)


@dataclass
class DaemonSettings:
    """Daemon server settings."""

    host: str = "127.0.0.1"
    port: int = 7676
    serve_ui: bool = True
    auth: AuthConfig = field(default_factory=AuthConfig)
    cors: CorsConfig = field(default_factory=CorsConfig)


@dataclass
class DaemonConfig:
    """Root daemon configuration."""

    daemon: DaemonSettings = field(default_factory=DaemonSettings)
    indexes: dict[str, str] = field(default_factory=dict)
    default_index: str | None = None

    @classmethod
    def get_config_path(cls) -> Path:
        """Get config path, respecting XDG_CONFIG_HOME."""
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / "gundog" / "daemon.yaml"
        return DEFAULT_CONFIG_PATH

    @classmethod
    def get_pid_path(cls) -> Path:
        """Get PID file path, respecting XDG_STATE_HOME."""
        xdg_state = os.environ.get("XDG_STATE_HOME")
        if xdg_state:
            return Path(xdg_state) / "gundog" / "daemon.pid"
        return DEFAULT_PID_PATH

    @classmethod
    def load(cls, config_path: Path | None = None) -> "DaemonConfig":
        """Load config from file, creating default if not exists."""
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
    def load_or_create(cls, config_path: Path | None = None) -> tuple["DaemonConfig", bool]:
        """Load config, creating default if not exists. Returns (config, was_created)."""
        if config_path is None:
            config_path = cls.get_config_path()

        created = False
        if not config_path.exists():
            cls.bootstrap(config_path)
            created = True

        return cls.load(config_path), created

    @classmethod
    def bootstrap(cls, config_path: Path | None = None) -> Path:
        """Create default config file."""
        if config_path is None:
            config_path = cls.get_config_path()

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(CONFIG_TEMPLATE)
        return config_path

    @classmethod
    def _from_dict(cls, data: dict) -> "DaemonConfig":
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
        # First index becomes default
        if self.default_index is None:
            self.default_index = name

    def remove_index(self, name: str) -> bool:
        """Remove an index from the config. Returns True if removed."""
        if name not in self.indexes:
            return False

        del self.indexes[name]

        # Clear default if it was the removed index
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
