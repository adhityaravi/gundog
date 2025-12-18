"""BM25 keyword search index for hybrid retrieval."""

import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

from gundog._utils import tokenize


class BM25Index:
    """
    BM25 keyword search index.

    Stores tokenized documents and supports keyword-based retrieval
    to complement vector search.
    """

    def __init__(self, path: Path | None = None):
        self.path = path
        self._bm25: BM25Okapi | None = None
        self._doc_ids: list[str] = []
        self._corpus: list[list[str]] = []

    def build(self, documents: dict[str, str]) -> None:
        """
        Build BM25 index from documents.

        Args:
            documents: Mapping of document ID to text content
        """
        if not documents:
            self._doc_ids = []
            self._corpus = []
            self._bm25 = None
            return

        self._doc_ids = list(documents.keys())
        self._corpus = [tokenize(doc) for doc in documents.values()]
        self._bm25 = BM25Okapi(self._corpus)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Search for documents matching query.

        Args:
            query: Search query text
            top_k: Number of results to return

        Returns:
            List of (doc_id, score) tuples, sorted by score descending
        """
        if self._bm25 is None or not self._doc_ids:
            return []

        tokens = tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)

        # Get top-k indices
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_indices = indexed_scores[:top_k]

        # Return (doc_id, score) pairs for non-zero scores
        results = []
        for idx, score in top_indices:
            if score > 0:
                results.append((self._doc_ids[idx], float(score)))

        return results

    def save(self) -> None:
        """Save index to disk."""
        if self.path is None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "doc_ids": self._doc_ids,
            "corpus": self._corpus,
        }

        with open(self.path, "wb") as f:
            pickle.dump(data, f)

    def load(self) -> bool:
        """
        Load index from disk.

        Returns:
            True if loaded successfully, False if no index found
        """
        if self.path is None or not self.path.exists():
            return False

        try:
            with open(self.path, "rb") as f:
                data = pickle.load(f)

            self._doc_ids = data["doc_ids"]
            self._corpus = data["corpus"]

            if self._corpus:
                self._bm25 = BM25Okapi(self._corpus)

            return True
        except Exception:
            return False

    @property
    def is_empty(self) -> bool:
        """Check if index is empty."""
        return len(self._doc_ids) == 0
