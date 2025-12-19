"""HNSW vector store using hnswlib for fast approximate nearest neighbor search."""

import json
from pathlib import Path
from typing import Any

import numpy as np

from gundog._store._base import SearchResult


class HNSWStore:
    """
    Vector store using HNSW (Hierarchical Navigable Small World) algorithm.

    Provides ~1ms search time vs ~40ms for brute force at similar recall.
    Best for datasets >1k vectors where search speed matters.

    Storage format:
        .gundog/index/
        ├── vectors.hnsw       # hnswlib binary index
        ├── hnsw_metadata.json # id -> {metadata, _idx}
        └── hnsw_config.json   # {dimensions, M, ef_construction, max_elements}
    """

    # HNSW build parameters (tunable for speed/quality tradeoff)
    M = 16  # Number of connections per layer (higher = better recall, more memory)
    EF_CONSTRUCTION = 200  # Build-time search depth (higher = better quality, slower build)
    EF_SEARCH = 50  # Query-time search depth (higher = better recall, slower query)
    INITIAL_MAX_ELEMENTS = 10000  # Initial capacity (auto-resizes)

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

        self._index: Any = None  # hnswlib.Index
        self._metadata: dict[str, dict[str, Any]] = {}  # id -> {meta, _idx}
        self._id_to_idx: dict[str, int] = {}  # id -> HNSW internal index
        self._idx_to_id: dict[int, str] = {}  # HNSW internal index -> id
        self._dimensions: int | None = None
        self._next_idx: int = 0
        self._dirty = False

    def _ensure_index(self, dimensions: int) -> None:
        """Initialize HNSW index if not already created."""
        if self._index is not None:
            return

        try:
            import hnswlib
        except ImportError as e:
            raise ImportError(
                "hnswlib is not installed. Install with: pip install gundog[hnsw]"
            ) from e

        self._dimensions = dimensions
        self._index = hnswlib.Index(space="cosine", dim=dimensions)
        self._index.init_index(
            max_elements=self.INITIAL_MAX_ELEMENTS,
            ef_construction=self.EF_CONSTRUCTION,
            M=self.M,
        )
        self._index.set_ef(self.EF_SEARCH)

    def _resize_if_needed(self) -> None:
        """Resize index if capacity is exceeded."""
        if self._index is None:
            return

        current_count = self._index.get_current_count()
        max_elements = self._index.get_max_elements()

        if current_count >= max_elements:
            # Double capacity
            new_max = max_elements * 2
            self._index.resize_index(new_max)

    def upsert(self, id: str, vector: np.ndarray, metadata: dict) -> None:
        """Insert or update a vector with metadata."""
        vector = np.asarray(vector, dtype=np.float32)

        # Initialize index on first vector
        self._ensure_index(vector.shape[0])

        if id in self._id_to_idx:
            # Update existing - HNSW doesn't support in-place update, so we mark and re-add
            idx = self._id_to_idx[id]
            # hnswlib allows overwriting at same index
            self._index.add_items(vector.reshape(1, -1), np.array([idx]))
            self._metadata[id] = {**metadata, "_idx": idx}
        else:
            # Insert new
            self._resize_if_needed()
            idx = self._next_idx
            self._next_idx += 1

            self._index.add_items(vector.reshape(1, -1), np.array([idx]))
            self._id_to_idx[id] = idx
            self._idx_to_id[idx] = id
            self._metadata[id] = {**metadata, "_idx": idx}

        self._dirty = True

    def get(self, id: str) -> tuple[np.ndarray, dict] | None:
        """Get vector and metadata by ID."""
        if id not in self._id_to_idx or self._index is None:
            return None

        idx = self._id_to_idx[id]
        vector = self._index.get_items([idx])[0]
        meta = {k: v for k, v in self._metadata[id].items() if k != "_idx"}
        return np.array(vector, dtype=np.float32), meta

    def get_batch(self, ids: list[str]) -> dict[str, tuple[np.ndarray, dict]]:
        """Get multiple vectors and metadata by IDs."""
        if self._index is None or not ids:
            return {}

        result = {}
        valid_ids = [item_id for item_id in ids if item_id in self._id_to_idx]

        if valid_ids:
            indices = [self._id_to_idx[item_id] for item_id in valid_ids]
            vectors = self._index.get_items(indices)

            for i, item_id in enumerate(valid_ids):
                meta = {k: v for k, v in self._metadata[item_id].items() if k != "_idx"}
                result[item_id] = (np.array(vectors[i], dtype=np.float32), meta)

        return result

    def delete(self, id: str) -> bool:
        """
        Delete vector by ID.

        Note: HNSW doesn't support true deletion. We mark as deleted
        and exclude from searches. Full cleanup requires rebuild.
        """
        if id not in self._id_to_idx:
            return False

        idx = self._id_to_idx[id]

        # Mark as deleted in hnswlib
        if self._index is not None:
            self._index.mark_deleted(idx)

        del self._metadata[id]
        del self._id_to_idx[id]
        del self._idx_to_id[idx]
        self._dirty = True
        return True

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[SearchResult]:
        """
        Find top-k most similar vectors using HNSW approximate nearest neighbor.

        Returns cosine similarity scores (0-1, higher is better).
        """
        if self._index is None or len(self._id_to_idx) == 0:
            return []

        query_vector = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)

        # Adjust top_k to not exceed available vectors
        k = min(top_k, len(self._id_to_idx))

        # HNSW search returns (indices, distances)
        # For cosine space: distance = 1 - cosine_similarity
        indices, distances = self._index.knn_query(query_vector, k=k)

        results = []
        for idx, dist in zip(indices[0], distances[0], strict=True):
            id = self._idx_to_id.get(int(idx))
            if id is None:
                continue
            # Convert cosine distance to similarity
            score = 1.0 - float(dist)
            meta = {k: v for k, v in self._metadata[id].items() if k != "_idx"}
            results.append(SearchResult(id=id, score=score, metadata=meta))

        return results

    def all_ids(self) -> list[str]:
        """Return all stored IDs."""
        return list(self._id_to_idx.keys())

    def all_vectors(self) -> dict[str, np.ndarray]:
        """Return all vectors for graph building."""
        if self._index is None:
            return {}

        result = {}
        for item_id, idx in self._id_to_idx.items():
            vector = self._index.get_items([idx])[0]
            result[item_id] = np.array(vector, dtype=np.float32)
        return result

    def save(self) -> None:
        """Persist to disk."""
        if not self._dirty or self._index is None:
            return

        # Save HNSW index
        self._index.save_index(str(self.path / "vectors.hnsw"))

        # Save metadata
        meta_serializable = {id: dict(meta.items()) for id, meta in self._metadata.items()}
        with open(self.path / "hnsw_metadata.json", "w") as f:
            json.dump(meta_serializable, f, indent=2, default=str)

        # Save config for reload
        config = {
            "dimensions": self._dimensions,
            "M": self.M,
            "ef_construction": self.EF_CONSTRUCTION,
            "ef_search": self.EF_SEARCH,
            "max_elements": self._index.get_max_elements(),
            "next_idx": self._next_idx,
            "id_to_idx": self._id_to_idx,
        }
        with open(self.path / "hnsw_config.json", "w") as f:
            json.dump(config, f, indent=2)

        self._dirty = False

    def load(self) -> None:
        """Load from disk."""
        index_path = self.path / "vectors.hnsw"
        config_path = self.path / "hnsw_config.json"
        metadata_path = self.path / "hnsw_metadata.json"

        if not index_path.exists():
            return  # Empty store

        try:
            import hnswlib
        except ImportError as e:
            raise ImportError(
                "hnswlib is not installed. Install with: pip install gundog[hnsw]"
            ) from e

        # Load config
        with open(config_path) as f:
            config = json.load(f)

        self._dimensions = config["dimensions"]
        self._next_idx = config["next_idx"]
        self._id_to_idx = {k: int(v) for k, v in config["id_to_idx"].items()}
        self._idx_to_id = {v: k for k, v in self._id_to_idx.items()}

        # Load HNSW index
        assert self._dimensions is not None, "dimensions must be set in config"
        self._index = hnswlib.Index(space="cosine", dim=self._dimensions)
        self._index.load_index(str(index_path), max_elements=config["max_elements"])
        self._index.set_ef(config.get("ef_search", self.EF_SEARCH))

        # Load metadata
        with open(metadata_path) as f:
            self._metadata = json.load(f)

        self._dirty = False

    def set_ef_search(self, ef: int) -> None:
        """
        Adjust search quality/speed tradeoff at runtime.

        Higher ef = better recall but slower search.
        Typical values: 10 (fastest), 50 (balanced), 200 (best quality)
        """
        if self._index is not None:
            self._index.set_ef(ef)
