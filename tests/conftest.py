"""Shared pytest fixtures."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from gundog._config import (
    EmbeddingConfig,
    GraphConfig,
    GundogConfig,
    SourceConfig,
    StorageConfig,
)

# Register step definition modules as pytest plugins (must be at root conftest)
pytest_plugins = [
    "tests.integration.steps.common",
    "tests.integration.steps.indexing_steps",
    "tests.integration.steps.querying_steps",
    "tests.integration.steps.storage_steps",
    "tests.integration.steps.feature_steps",
]


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config(temp_dir: Path) -> GundogConfig:
    """Create a sample config for testing."""
    return GundogConfig(
        sources=[
            SourceConfig(path=str(temp_dir / "adr"), type="adr", glob="**/*.md"),
            SourceConfig(path=str(temp_dir / "src"), type="code", glob="**/*.py"),
        ],
        embedding=EmbeddingConfig(model="BAAI/bge-small-en-v1.5"),
        storage=StorageConfig(backend="numpy", path=str(temp_dir / "index")),
        graph=GraphConfig(
            similarity_threshold=0.65,
            expand_threshold=0.60,
            max_expand_depth=1,
        ),
    )


@pytest.fixture
def sample_vectors() -> dict[str, np.ndarray]:
    """Create sample normalized vectors for testing."""
    # Create random but deterministic vectors
    rng = np.random.default_rng(42)
    vectors = {}

    # Create 5 sample vectors
    for i in range(5):
        vec = rng.random(384).astype(np.float32)
        vec = vec / np.linalg.norm(vec)  # Normalize
        vectors[f"file_{i}.md"] = vec

    return vectors


@pytest.fixture
def sample_metadata() -> dict[str, dict]:
    """Create sample metadata for testing."""
    return {
        "file_0.md": {"type": "adr", "mtime": 1000.0, "content_hash": "abc123"},
        "file_1.md": {"type": "adr", "mtime": 1001.0, "content_hash": "def456"},
        "file_2.md": {"type": "code", "mtime": 1002.0, "content_hash": "ghi789"},
        "file_3.md": {"type": "code", "mtime": 1003.0, "content_hash": "jkl012"},
        "file_4.md": {"type": "doc", "mtime": 1004.0, "content_hash": "mno345"},
    }
