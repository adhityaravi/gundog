"""Vector store backends for gundog."""

from pathlib import Path
from typing import TYPE_CHECKING

from gundog._store._base import SearchResult

if TYPE_CHECKING:
    from gundog._store._base import VectorStore

__all__ = ["SearchResult", "create_store"]


def create_store(backend: str, path: str | Path) -> "VectorStore":
    """
    Factory function to create the appropriate vector store.

    Args:
        backend: "numpy" or "lancedb"
        path: Path to store data

    Returns:
        VectorStore instance
    """
    if backend == "numpy":
        from gundog._store._numpy_store import NumpyStore

        return NumpyStore(path)
    elif backend == "lancedb":
        from gundog._store._lance_store import LanceStore

        return LanceStore(path)
    else:
        raise ValueError(f"Unknown storage backend: {backend}. Use 'numpy' or 'lancedb'.")
