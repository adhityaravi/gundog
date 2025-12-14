"""Common step definitions shared across all integration tests."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
from pytest_bdd import given, parsers

from gundog._config import (
    ChunkingConfig,
    EmbeddingConfig,
    GraphConfig,
    GundogConfig,
    HybridConfig,
    SourceConfig,
    StorageConfig,
)


@pytest.fixture
def test_context():
    """Shared test context for storing state between steps."""
    return {
        "temp_dir": None,
        "config": None,
        "store": None,
        "indexer": None,
        "query_engine": None,
        "query_result": None,
        "index_summary": None,
        "vectors": {},
        "backend": "numpy",
        "chunking_enabled": False,
        "chunking_max_tokens": 512,
        "hybrid_enabled": True,
        "exclusion_template": None,
        "custom_excludes": [],
    }


@pytest.fixture
def temp_directory():
    """Create a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@given("a clean gundog environment")
def clean_environment(test_context, temp_directory):
    """Set up a clean temporary environment for testing."""
    test_context["temp_dir"] = temp_directory
    test_context["adr_dir"] = temp_directory / "adr"
    test_context["src_dir"] = temp_directory / "src"
    test_context["index_dir"] = temp_directory / "index"

    # Create directories
    test_context["adr_dir"].mkdir(parents=True, exist_ok=True)
    test_context["src_dir"].mkdir(parents=True, exist_ok=True)


@given(parsers.parse('the storage backend is "{backend}"'))
def set_storage_backend(test_context, backend):
    """Set the storage backend to use."""
    test_context["backend"] = backend


def create_config(test_context) -> GundogConfig:
    """Helper to create a GundogConfig from test context."""
    sources = []

    if test_context["adr_dir"].exists() and any(test_context["adr_dir"].iterdir()):
        sources.append(
            SourceConfig(
                path=str(test_context["adr_dir"]),
                type="adr",
                glob="**/*.md",
                exclusion_template=test_context.get("exclusion_template"),
                exclude=test_context.get("custom_excludes", []),
            )
        )

    if test_context["src_dir"].exists() and any(test_context["src_dir"].iterdir()):
        sources.append(
            SourceConfig(
                path=str(test_context["src_dir"]),
                type="code",
                glob="**/*.py",
                exclusion_template=test_context.get("exclusion_template"),
                exclude=test_context.get("custom_excludes", []),
            )
        )

    return GundogConfig(
        sources=sources,
        embedding=EmbeddingConfig(model="BAAI/bge-small-en-v1.5"),
        storage=StorageConfig(
            backend=test_context["backend"],
            path=str(test_context["index_dir"]),
        ),
        graph=GraphConfig(
            similarity_threshold=0.5,
            expand_threshold=0.4,
            max_expand_depth=1,
        ),
        hybrid=HybridConfig(
            enabled=test_context.get("hybrid_enabled", True),
        ),
        chunking=ChunkingConfig(
            enabled=test_context.get("chunking_enabled", False),
            max_tokens=test_context.get("chunking_max_tokens", 512),
        ),
    )


def generate_random_vector(seed: int | None = None) -> np.ndarray:
    """Generate a random normalized vector for testing."""
    rng = np.random.default_rng(seed)
    vec = rng.random(384).astype(np.float32)
    return vec / np.linalg.norm(vec)


def parse_datatable(datatable: list) -> list[dict]:
    """Parse a pytest-bdd datatable into a list of dicts.

    pytest-bdd passes datatables as list of lists where
    the first row contains the headers.
    """
    if not datatable:
        return []
    headers = datatable[0]
    return [dict(zip(headers, row, strict=True)) for row in datatable[1:]]
