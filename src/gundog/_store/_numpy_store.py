"""Simple vector store using numpy arrays and JSON persistence."""

import json
from pathlib import Path
from typing import Any

import numpy as np

from gundog._store._base import SearchResult


class NumpyStore:
    """
    Simple vector store using numpy arrays and JSON persistence.

    Suitable for up to ~10k documents. For larger corpora, use LanceDB.

    Storage format:
        .gundog/index/
        ├── vectors.npy      # numpy array of all vectors
        ├── metadata.json    # id -> {metadata, vector_index}
        └── index.json       # dimensions, count, id mappings
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

        self._vectors: np.ndarray | None = None  # (n, dimensions)
        self._metadata: dict[str, dict[str, Any]] = {}  # id -> {meta, idx}
        self._id_to_idx: dict[str, int] = {}  # id -> vector index
        self._idx_to_id: dict[int, str] = {}  # vector index -> id
        self._dirty = False

    def upsert(self, id: str, vector: np.ndarray, metadata: dict) -> None:
        """Insert or update a vector."""
        vector = np.asarray(vector, dtype=np.float32)

        if id in self._id_to_idx:
            # Update existing
            idx = self._id_to_idx[id]
            if self._vectors is not None:
                self._vectors[idx] = vector
            self._metadata[id] = {**metadata, "_idx": idx}
        else:
            # Insert new
            idx = len(self._id_to_idx)
            if self._vectors is None:
                self._vectors = vector.reshape(1, -1)
            else:
                self._vectors = np.vstack([self._vectors, vector])

            self._id_to_idx[id] = idx
            self._idx_to_id[idx] = id
            self._metadata[id] = {**metadata, "_idx": idx}

        self._dirty = True

    def get(self, id: str) -> tuple[np.ndarray, dict] | None:
        """Get vector and metadata by ID."""
        if id not in self._id_to_idx:
            return None
        idx = self._id_to_idx[id]
        meta = {k: v for k, v in self._metadata[id].items() if k != "_idx"}
        if self._vectors is None:
            return None
        return self._vectors[idx], meta

    def get_batch(self, ids: list[str]) -> dict[str, tuple[np.ndarray, dict]]:
        """Get multiple vectors and metadata by IDs."""
        if self._vectors is None or not ids:
            return {}

        result = {}
        for item_id in ids:
            if item_id in self._id_to_idx:
                idx = self._id_to_idx[item_id]
                meta = {k: v for k, v in self._metadata[item_id].items() if k != "_idx"}
                result[item_id] = (self._vectors[idx], meta)
        return result

    def delete(self, id: str) -> bool:
        """Delete vector by ID."""
        if id not in self._id_to_idx:
            return False

        # Mark as dirty - actual removal happens on save/compact
        idx = self._id_to_idx[id]
        del self._metadata[id]
        del self._id_to_idx[id]
        del self._idx_to_id[idx]
        self._dirty = True
        return True

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[SearchResult]:
        """
        Find top-k most similar vectors using cosine similarity.

        Since vectors are normalized, dot product = cosine similarity.
        """
        if self._vectors is None or len(self._vectors) == 0:
            return []

        query_vector = np.asarray(query_vector, dtype=np.float32)

        # Only search over valid indices (exclude deleted)
        valid_indices = list(self._idx_to_id.keys())
        if not valid_indices:
            return []

        valid_vectors = self._vectors[valid_indices]

        # Dot product with valid vectors (cosine similarity for normalized vectors)
        scores = valid_vectors @ query_vector

        # Get top-k indices
        k = min(top_k, len(scores))
        top_local_indices = np.argpartition(scores, -k)[-k:]
        top_local_indices = top_local_indices[np.argsort(scores[top_local_indices])[::-1]]

        results = []
        for local_idx in top_local_indices:
            actual_idx = valid_indices[local_idx]
            item_id = self._idx_to_id.get(actual_idx)
            if item_id is None:
                continue
            meta = {key: val for key, val in self._metadata[item_id].items() if key != "_idx"}
            results.append(SearchResult(id=item_id, score=float(scores[local_idx]), metadata=meta))

        return results

    def all_ids(self) -> list[str]:
        """Return all stored IDs."""
        return list(self._id_to_idx.keys())

    def all_vectors(self) -> dict[str, np.ndarray]:
        """Return all vectors for graph building."""
        if self._vectors is None:
            return {}
        return {id: self._vectors[idx] for id, idx in self._id_to_idx.items()}

    def save(self) -> None:
        """Persist to disk."""
        if not self._dirty:
            return

        # Compact: rebuild arrays without deleted entries
        if self._id_to_idx:
            ids = list(self._id_to_idx.keys())
            old_indices = [self._id_to_idx[id] for id in ids]

            if self._vectors is not None:
                new_vectors = self._vectors[old_indices]
                np.save(self.path / "vectors.npy", new_vectors)
                self._vectors = new_vectors

            # Rebuild index mappings
            new_id_to_idx = {id: i for i, id in enumerate(ids)}
            new_metadata = {}
            for id in ids:
                meta = {k: v for k, v in self._metadata[id].items() if k != "_idx"}
                new_metadata[id] = {**meta, "_idx": new_id_to_idx[id]}

            # Update internal state
            self._id_to_idx = new_id_to_idx
            self._idx_to_id = {v: k for k, v in new_id_to_idx.items()}
            self._metadata = new_metadata

        # Save metadata
        meta_serializable = {id: dict(meta.items()) for id, meta in self._metadata.items()}
        with open(self.path / "metadata.json", "w") as f:
            json.dump(meta_serializable, f, indent=2, default=str)

        # Save index mappings
        with open(self.path / "index.json", "w") as f:
            json.dump(
                {
                    "id_to_idx": self._id_to_idx,
                    "count": len(self._id_to_idx),
                },
                f,
                indent=2,
            )

        self._dirty = False

    def load(self) -> None:
        """Load from disk."""
        vectors_path = self.path / "vectors.npy"
        metadata_path = self.path / "metadata.json"
        index_path = self.path / "index.json"

        if not vectors_path.exists():
            return  # Empty store

        self._vectors = np.load(vectors_path)

        with open(metadata_path) as f:
            self._metadata = json.load(f)

        with open(index_path) as f:
            index_data = json.load(f)
            self._id_to_idx = {k: int(v) for k, v in index_data["id_to_idx"].items()}

        self._idx_to_id = {v: k for k, v in self._id_to_idx.items()}
        self._dirty = False
