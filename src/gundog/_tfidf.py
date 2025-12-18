"""Per-line TF-IDF scoring for fine-grained result ranking."""

import math
import pickle
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from gundog._utils import tokenize


@dataclass
class LineScore:
    """Score for a single line within a chunk."""

    line_idx: int  # 0-based index within chunk
    absolute_line: int  # 1-based line number in file
    score: float
    matching_terms: list[str]


class LineTFIDFIndex:
    """
    Pre-computed TF-IDF scores for individual lines within chunks.

    Enables Stage 2 fine-grained ranking to identify the most relevant
    lines within candidate chunks returned by coarse retrieval.

    Storage format:
        .gundog/index/line_tfidf.pkl
        {
            "version": "1.0",
            "idf_scores": {term: float, ...},
            "chunk_lines": {
                chunk_id: {
                    "lines": [line1, line2, ...],
                    "tokens": [[tok1, tok2], ...],
                    "start_line": int,  # 1-based absolute line number
                }
            }
        }
    """

    VERSION = "1.0"

    def __init__(self, path: Path | None = None):
        self.path = path
        self._idf_scores: dict[str, float] = {}
        self._chunk_lines: dict[str, dict] = {}
        self._total_lines: int = 0

    def build(self, chunks: dict[str, tuple[str, int]]) -> None:
        """
        Build TF-IDF index from chunk content.

        Args:
            chunks: Mapping of chunk_id to (content, start_line) tuples
                    where start_line is the 1-based line number in the file
        """
        if not chunks:
            self._idf_scores = {}
            self._chunk_lines = {}
            self._total_lines = 0
            return

        # Phase 1: Collect all lines and compute document frequencies
        doc_freq: dict[str, int] = defaultdict(int)
        all_lines_data: list[tuple[str, list[str]]] = []  # (chunk_id, line_tokens)

        for chunk_id, (content, start_line) in chunks.items():
            lines = content.split("\n")
            chunk_data = {
                "lines": lines,
                "tokens": [],
                "start_line": start_line,
            }

            for line in lines:
                tokens = tokenize(line)
                chunk_data["tokens"].append(tokens)

                # Count unique terms per line for IDF
                unique_terms = set(tokens)
                for term in unique_terms:
                    doc_freq[term] += 1

                all_lines_data.append((chunk_id, tokens))

            self._chunk_lines[chunk_id] = chunk_data

        # Phase 2: Compute IDF scores
        self._total_lines = len(all_lines_data)
        if self._total_lines > 0:
            for term, df in doc_freq.items():
                # Standard IDF formula: log(N/df) + 1
                self._idf_scores[term] = math.log(self._total_lines / df) + 1

    def score_lines(self, query: str, chunk_id: str, top_k: int | None = None) -> list[LineScore]:
        """
        Score lines within a chunk for relevance to query.

        Args:
            query: Query text
            chunk_id: ID of the chunk to score
            top_k: Maximum number of results (None = all)

        Returns:
            List of LineScore objects sorted by score descending
        """
        if chunk_id not in self._chunk_lines:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        chunk_data = self._chunk_lines[chunk_id]
        start_line = chunk_data["start_line"]
        results = []

        for line_idx, line_tokens in enumerate(chunk_data["tokens"]):
            if not line_tokens:
                continue

            # Compute TF-IDF score for this line
            score = 0.0
            matching_terms = []
            term_freq = defaultdict(int)

            for token in line_tokens:
                term_freq[token] += 1

            for query_term in query_tokens:
                if query_term in term_freq:
                    # TF: term frequency in this line
                    tf = term_freq[query_term] / len(line_tokens)
                    # IDF: from pre-computed scores
                    idf = self._idf_scores.get(query_term, 1.0)
                    score += tf * idf
                    matching_terms.append(query_term)

            if score > 0:
                results.append(
                    LineScore(
                        line_idx=line_idx,
                        absolute_line=start_line + line_idx,
                        score=score,
                        matching_terms=matching_terms,
                    )
                )

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)

        if top_k is not None:
            results = results[:top_k]

        return results

    def get_best_line(self, query: str, chunk_id: str) -> tuple[int, float] | None:
        """
        Get the best matching line for a query within a chunk.

        Args:
            query: Query text
            chunk_id: ID of the chunk

        Returns:
            Tuple of (absolute_line_number, score) or None if no match
        """
        scores = self.score_lines(query, chunk_id, top_k=1)
        if scores:
            return (scores[0].absolute_line, scores[0].score)
        return None

    def get_line_content(self, chunk_id: str, line_idx: int) -> str | None:
        """Get content of a specific line in a chunk."""
        if chunk_id not in self._chunk_lines:
            return None

        lines = self._chunk_lines[chunk_id]["lines"]
        if 0 <= line_idx < len(lines):
            return lines[line_idx]
        return None

    def save(self) -> None:
        """Save index to disk."""
        if self.path is None:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.VERSION,
            "idf_scores": self._idf_scores,
            "chunk_lines": self._chunk_lines,
            "total_lines": self._total_lines,
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

            # Version check
            if data.get("version") != self.VERSION:
                return False

            self._idf_scores = data["idf_scores"]
            self._chunk_lines = data["chunk_lines"]
            self._total_lines = data.get("total_lines", 0)

            return True
        except Exception:
            return False

    @property
    def is_empty(self) -> bool:
        """Check if index is empty."""
        return len(self._chunk_lines) == 0

    @property
    def chunk_count(self) -> int:
        """Number of indexed chunks."""
        return len(self._chunk_lines)

    @property
    def line_count(self) -> int:
        """Total number of indexed lines."""
        return self._total_lines
