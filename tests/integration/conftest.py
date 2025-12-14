"""Pytest configuration for integration tests."""

import pytest

# Register step definition modules as pytest plugins
pytest_plugins = [
    "tests.integration.steps.common",
    "tests.integration.steps.indexing_steps",
    "tests.integration.steps.querying_steps",
    "tests.integration.steps.storage_steps",
    "tests.integration.steps.feature_steps",
]


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "requires_lancedb: mark test as requiring LanceDB")


def pytest_collection_modifyitems(config, items):
    """Skip tests that require lancedb if it's not installed."""
    try:
        import lancedb  # noqa: F401

        has_lancedb = True
    except ImportError:
        has_lancedb = False

    skip_lancedb = pytest.mark.skip(reason="LanceDB not installed")

    for item in items:
        if "requires_lancedb" in item.keywords and not has_lancedb:
            item.add_marker(skip_lancedb)
