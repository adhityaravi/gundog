"""Test daemon configuration."""

from pathlib import Path

from gundog_core import DaemonConfig, DaemonSettings


def test_daemon_config_defaults():
    """Test default daemon configuration values."""
    config = DaemonConfig()

    assert config.daemon.host == "127.0.0.1"
    assert config.daemon.port == 7676
    assert config.indexes == {}
    assert config.default_index is None


def test_daemon_settings_defaults():
    """Test default daemon settings."""
    settings = DaemonSettings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 7676


def test_daemon_config_save_and_load(temp_dir: Path):
    """Test saving and loading daemon config."""
    config_path = temp_dir / "config.yaml"

    config = DaemonConfig(
        daemon=DaemonSettings(host="0.0.0.0", port=8080),
        indexes={"myproject": "/path/to/project/.gundog"},
        default_index="myproject",
    )
    config.save(config_path)

    loaded = DaemonConfig.load(config_path)

    assert loaded.daemon.host == "0.0.0.0"
    assert loaded.daemon.port == 8080
    assert loaded.indexes == {"myproject": "/path/to/project/.gundog"}
    assert loaded.default_index == "myproject"


def test_daemon_config_load_or_create_new(temp_dir: Path):
    """Test load_or_create creates default config."""
    config_path = temp_dir / "config.yaml"

    config, created = DaemonConfig.load_or_create(config_path)

    assert created is True
    assert config_path.exists()
    assert config.daemon.port == 7676


def test_daemon_config_load_or_create_existing(temp_dir: Path):
    """Test load_or_create loads existing config."""
    config_path = temp_dir / "config.yaml"

    # Create config first
    original = DaemonConfig(
        daemon=DaemonSettings(port=9999),
        indexes={"test": "/test/path"},
    )
    original.save(config_path)

    # Load it
    config, created = DaemonConfig.load_or_create(config_path)

    assert created is False
    assert config.daemon.port == 9999
    assert config.indexes == {"test": "/test/path"}


def test_daemon_config_add_index(temp_dir: Path):
    """Test adding an index to config."""
    config = DaemonConfig()

    config.indexes["myproject"] = "/path/to/project/.gundog"
    config.default_index = "myproject"

    assert "myproject" in config.indexes
    assert config.default_index == "myproject"


def test_daemon_config_remove_index():
    """Test removing an index from config."""
    config = DaemonConfig(
        indexes={"proj1": "/path1", "proj2": "/path2"},
        default_index="proj1",
    )

    del config.indexes["proj1"]
    config.default_index = "proj2"

    assert "proj1" not in config.indexes
    assert config.default_index == "proj2"


def test_daemon_config_yaml_format(temp_dir: Path):
    """Test that saved config is valid YAML."""
    config_path = temp_dir / "config.yaml"

    config = DaemonConfig(
        indexes={"myproject": "/home/user/project/.gundog"},
    )
    config.save(config_path)

    content = config_path.read_text()
    assert "daemon:" in content
    assert "host:" in content
    assert "port:" in content
    assert "indexes:" in content
