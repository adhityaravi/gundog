"""LanceDB vector store backend for better performance at scale."""

from pathlib import Path
from typing import Any

import numpy as np

from gundog._store._base import SearchResult


class LanceStore:
    """
    Vector store using LanceDB for scalable vector search.

    Better performance than NumpyStore for large corpora (>10k documents).
    Requires optional dependency: pip install gundog[lance]

    Storage format:
        .gundog/index/lance/  # LanceDB database directory
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._db: Any = None
        self._table: Any = None
        self._table_name = "vectors"
        self._dirty = False

    def _ensure_db(self) -> None:
        """Ensure database connection is established."""
        if self._db is None:
            try:
                import lancedb  # type: ignore[import-not-found]
            except ImportError as e:
                raise ImportError(
                    "LanceDB is not installed. Install with: pip install gundog[lance]"
                ) from e

            self.path.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(self.path))

            # Check if table exists
            if self._table_name in self._db.table_names():
                self._table = self._db.open_table(self._table_name)

    def upsert(self, id: str, vector: np.ndarray, metadata: dict) -> None:
        """Insert or update a vector."""
        self._ensure_db()

        vector = np.asarray(vector, dtype=np.float32)

        # Prepare record
        record = {
            "id": id,
            "vector": vector.tolist(),
            **{f"meta_{k}": v for k, v in metadata.items()},
        }

        if self._table is None:
            # Create table with first record
            self._table = self._db.create_table(self._table_name, [record])
        else:
            # Check if ID exists
            existing = self._table.search().where(f"id = '{id}'").limit(1).to_list()
            if existing:
                # Delete and re-add (LanceDB doesn't have native upsert)
                self._table.delete(f"id = '{id}'")
            self._table.add([record])

        self._dirty = True

    def get(self, id: str) -> tuple[np.ndarray, dict] | None:
        """Get vector and metadata by ID."""
        self._ensure_db()

        if self._table is None:
            return None

        results = self._table.search().where(f"id = '{id}'").limit(1).to_list()
        if not results:
            return None

        row = results[0]
        vector = np.array(row["vector"], dtype=np.float32)
        metadata = {k[5:]: v for k, v in row.items() if k.startswith("meta_")}

        return vector, metadata

    def get_batch(self, ids: list[str]) -> dict[str, tuple[np.ndarray, dict]]:
        """Get multiple vectors and metadata by IDs in a single query."""
        self._ensure_db()

        if self._table is None or not ids:
            return {}

        # Build OR filter for all IDs
        id_filter = " OR ".join(f"id = '{id}'" for id in ids)
        results = self._table.search().where(id_filter).limit(len(ids)).to_list()

        result_map = {}
        for row in results:
            vector = np.array(row["vector"], dtype=np.float32)
            metadata = {k[5:]: v for k, v in row.items() if k.startswith("meta_")}
            result_map[row["id"]] = (vector, metadata)

        return result_map

    def delete(self, id: str) -> bool:
        """Delete vector by ID."""
        self._ensure_db()

        if self._table is None:
            return False

        # Check if exists
        existing = self._table.search().where(f"id = '{id}'").limit(1).to_list()
        if not existing:
            return False

        self._table.delete(f"id = '{id}'")
        self._dirty = True
        return True

    def search(self, query_vector: np.ndarray, top_k: int = 10) -> list[SearchResult]:
        """Find top-k most similar vectors using cosine similarity."""
        self._ensure_db()

        if self._table is None:
            return []

        query_vector = np.asarray(query_vector, dtype=np.float32)

        # Use cosine distance - returns (1 - cosine_similarity)
        results = self._table.search(query_vector.tolist()).metric("cosine").limit(top_k).to_list()

        return [
            SearchResult(
                id=row["id"],
                score=1 - row.get("_distance", 0),  # cosine_distance to similarity
                metadata={k[5:]: v for k, v in row.items() if k.startswith("meta_")},
            )
            for row in results
        ]

    def all_ids(self) -> list[str]:
        """Return all stored IDs."""
        self._ensure_db()

        if self._table is None:
            return []

        # Use to_arrow() to avoid pandas dependency
        table = self._table.to_arrow()
        return table.column("id").to_pylist()

    def all_vectors(self) -> dict[str, np.ndarray]:
        """Return all vectors for graph building."""
        self._ensure_db()

        if self._table is None:
            return {}

        # Use to_arrow() to avoid pandas dependency
        table = self._table.to_arrow()
        ids = table.column("id").to_pylist()
        vectors = table.column("vector").to_pylist()

        return {id: np.array(vec, dtype=np.float32) for id, vec in zip(ids, vectors, strict=True)}

    def save(self) -> None:
        """Persist to disk - LanceDB auto-persists."""
        self._dirty = False

    def load(self) -> None:
        """Load from disk - establishes connection."""
        self._ensure_db()
