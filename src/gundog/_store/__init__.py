"""Vector store backends for gundog."""

from pathlib import Path

from gundog._store._base import SearchResult, VectorStore
from gundog._store._hnsw_store import HNSWStore
from gundog._store._numpy_store import NumpyStore

__all__ = ["HNSWStore", "NumpyStore", "SearchResult", "VectorStore", "create_store"]


def create_store(use_hnsw: bool, path: str | Path) -> VectorStore:
    """
    Factory function to create the appropriate vector store.

    Args:
        use_hnsw: Use HNSW index (default: True, O(log n) search)
        path: Path to store data

    Returns:
        VectorStore instance

    Backends:
        - hnsw: Approximate nearest neighbor via HNSW, ~1ms search, scales to millions
        - numpy: Simple brute-force search, only for small indexes (<1k vectors)
    """
    if use_hnsw:
        return HNSWStore(path)
    return NumpyStore(path)
