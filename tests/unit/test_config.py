"""Test configuration loading."""

from pathlib import Path

import pytest
import yaml

from gundog._config import (
    EmbeddingConfig,
    GraphConfig,
    GundogConfig,
    SourceConfig,
    StorageConfig,
)


def test_source_config_defaults():
    """Test SourceConfig has expected defaults."""
    source = SourceConfig(path="./adr", type="adr")
    assert source.glob == "**/*"
    assert source.exclude == []


def test_embedding_config_defaults():
    """Test EmbeddingConfig has expected defaults."""
    config = EmbeddingConfig()
    assert config.model == "BAAI/bge-small-en-v1.5"


def test_storage_config_defaults():
    """Test StorageConfig has expected defaults."""
    config = StorageConfig()
    assert config.backend == "numpy"
    assert config.path == ".gundog/index"


def test_graph_config_defaults():
    """Test GraphConfig has expected defaults."""
    config = GraphConfig()
    assert config.similarity_threshold == 0.65
    assert config.expand_threshold == 0.60
    assert config.max_expand_depth == 1


def test_gundog_config_load(temp_dir: Path):
    """Test loading config from YAML file."""
    config_path = temp_dir / "config.yaml"

    config_data = {
        "sources": [
            {"path": "./adr", "type": "adr", "glob": "**/*.md"},
            {"path": "./src", "type": "code", "glob": "**/*.py", "exclude": ["**/__pycache__/**"]},
        ],
        "embedding": {"model": "BAAI/bge-base-en-v1.5"},
        "storage": {"backend": "numpy", "path": ".gundog/index"},
        "graph": {
            "similarity_threshold": 0.70,
            "expand_threshold": 0.55,
            "max_expand_depth": 2,
        },
    }

    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    config = GundogConfig.load(config_path)

    assert len(config.sources) == 2
    assert config.sources[0].path == "./adr"
    assert config.sources[0].type == "adr"
    assert config.sources[1].exclude == ["**/__pycache__/**"]

    assert config.embedding.model == "BAAI/bge-base-en-v1.5"
    assert config.storage.backend == "numpy"
    assert config.graph.similarity_threshold == 0.70
    assert config.graph.max_expand_depth == 2


def test_gundog_config_load_missing_file(temp_dir: Path):
    """Test that loading from missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        GundogConfig.load(temp_dir / "nonexistent.yaml")


def test_gundog_config_load_minimal(temp_dir: Path):
    """Test loading config with only required fields."""
    config_path = temp_dir / "config.yaml"

    config_data = {
        "sources": [{"path": "./adr", "type": "adr"}],
    }

    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    config = GundogConfig.load(config_path)

    assert len(config.sources) == 1
    # Should use defaults for other fields
    assert config.embedding.model == "BAAI/bge-small-en-v1.5"
    assert config.storage.backend == "numpy"
    assert config.graph.similarity_threshold == 0.65
