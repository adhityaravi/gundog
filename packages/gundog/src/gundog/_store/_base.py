"""Base protocol for vector storage backends."""

from typing import NamedTuple, Protocol

import numpy as np


class SearchResult(NamedTuple):
    """Single search result."""

    id: str
    score: float
    metadata: dict


class VectorStore(Protocol):
    """Protocol for vector storage backends."""

    def upsert(self, id: str, vector: np.ndarray, metadata: dict) -> None:
        """Insert or update a vector with metadata."""
        ...

    def get(self, id: str) -> tuple[np.ndarray, dict] | None:
        """Get vector and metadata by ID."""
        ...

    def get_batch(self, ids: list[str]) -> dict[str, tuple[np.ndarray, dict]]:
        """Get multiple vectors and metadata by IDs."""
        ...

    def delete(self, id: str) -> bool:
        """Delete vector by ID. Returns True if existed."""
        ...

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[SearchResult]:
        """Find top-k most similar vectors."""
        ...

    def all_ids(self) -> list[str]:
        """Return all stored IDs."""
        ...

    def all_vectors(self) -> dict[str, np.ndarray]:
        """Return all vectors for graph building."""
        ...

    def save(self) -> None:
        """Persist to disk."""
        ...

    def load(self) -> None:
        """Load from disk."""
        ...
