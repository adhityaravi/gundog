"""Query execution with graph expansion."""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gundog._bm25 import BM25Index
from gundog._chunker import parse_chunk_id
from gundog._config import GundogConfig
from gundog._embedder import Embedder
from gundog._graph import SimilarityGraph
from gundog._store import SearchResult, create_store


@dataclass
class QueryResult:
    """Result of a query with expansion."""

    query: str
    direct: list[dict[str, Any]]  # Direct matches from vector search
    related: list[dict[str, Any]]  # Related files from graph expansion


class QueryEngine:
    """
    Executes semantic queries with graph expansion.

    Two-phase retrieval:
    1. Vector search (+ optional BM25 fusion) for direct matches
    2. Graph traversal for related documents
    """

    def __init__(self, config: GundogConfig):
        self.config = config
        self.embedder = Embedder(config.embedding.model)
        self.store = create_store(config.storage.backend, config.storage.path)
        self.graph = SimilarityGraph(Path(config.storage.path) / "graph.json")
        self.bm25 = BM25Index(Path(config.storage.path) / "bm25.pkl")

        # Load from disk
        self.store.load()
        self.graph.load()
        if config.hybrid.enabled:
            self.bm25.load()

    def _fuse_results(
        self,
        vector_results: list[SearchResult],
        bm25_results: list[tuple[str, float]],
        top_k: int,
    ) -> list[SearchResult]:
        """
        Fuse vector and BM25 results using Reciprocal Rank Fusion (RRF).

        RRF score = sum(1 / (k + rank)) where k=60 is a constant
        Returns results with original cosine similarity as the score.
        """
        k = 60  # RRF constant (standard value from literature)
        rrf_scores: dict[str, float] = defaultdict(float)
        vector_scores: dict[str, float] = {}
        metadata_map: dict[str, dict[str, Any]] = {}

        # Score from vector results (keep original similarity)
        for rank, result in enumerate(vector_results):
            rrf_scores[result.id] += self.config.hybrid.vector_weight / (k + rank)
            vector_scores[result.id] = result.score  # Original cosine similarity
            metadata_map[result.id] = result.metadata

        # Score from BM25 results
        for rank, (doc_id, _) in enumerate(bm25_results):
            rrf_scores[doc_id] += self.config.hybrid.bm25_weight / (k + rank)
            # Get metadata if not already present
            if doc_id not in metadata_map:
                result = self.store.get(doc_id)
                if result:
                    metadata_map[doc_id] = result[1]
                else:
                    metadata_map[doc_id] = {}

        # Sort by RRF score for ranking
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        # Return with original cosine similarity as score (more meaningful)
        fused = []
        for doc_id in sorted_ids[:top_k]:
            fused.append(
                SearchResult(
                    id=doc_id,
                    score=vector_scores.get(doc_id, 0.0),  # Original similarity
                    metadata=metadata_map.get(doc_id, {}),
                )
            )

        return fused

    def _deduplicate_chunks(self, results: list[SearchResult]) -> list[SearchResult]:
        """
        Deduplicate results by parent file, keeping the highest-scoring chunk.

        When chunking is enabled, multiple chunks from the same file may match.
        This keeps only the best-scoring chunk per file.
        """
        if not self.config.chunking.enabled:
            return results

        best_by_file: dict[str, SearchResult] = {}

        for result in results:
            parent_file, chunk_idx = parse_chunk_id(result.id)

            # For chunks, use parent file as key; for whole files, use the ID
            file_key = parent_file

            if file_key not in best_by_file or result.score > best_by_file[file_key].score:
                # Store with parent file info in metadata for display
                if chunk_idx is not None:
                    result.metadata["_chunk_index"] = chunk_idx
                    result.metadata["_parent_file"] = parent_file
                best_by_file[file_key] = result

        return list(best_by_file.values())

    @staticmethod
    def _rescale_score(raw_score: float, baseline: float = 0.5) -> float:
        """
        Rescale raw cosine similarity to intuitive relevance score.

        Embedding models have high baseline similarity (~0.4-0.5) even for
        unrelated text. This rescales so baseline becomes 0% and 1.0 becomes 100%.
        """
        if raw_score <= baseline:
            return 0.0
        return (raw_score - baseline) / (1 - baseline)

    def query(
        self,
        query_text: str,
        top_k: int = 10,
        expand: bool = True,
        expand_depth: int | None = None,
        type_filter: str | None = None,
        min_score: float = 0.5,
    ) -> QueryResult:
        """
        Execute a semantic query.

        Args:
            query_text: Natural language query
            top_k: Number of direct matches to return
            expand: Whether to expand results via graph
            expand_depth: Override config's max_expand_depth
            type_filter: Filter results by type ("adr", "code", etc.)
            min_score: Minimum cosine similarity threshold (0-1)

        Returns:
            QueryResult with direct matches and related files
        """
        # Phase 1: Vector search (with optional BM25 hybrid)
        query_vector = self.embedder.embed_text(query_text)
        vector_results = self.store.search(
            query_vector, top_k=top_k * 2
        )  # Get extra for filtering/fusion

        # Filter by minimum cosine similarity first
        vector_results = [r for r in vector_results if r.score >= min_score]

        # Hybrid search: fuse vector and BM25 results
        if self.config.hybrid.enabled and not self.bm25.is_empty:
            # Only fuse if we have vector results above threshold
            if vector_results:
                bm25_results = self.bm25.search(query_text, top_k=top_k * 2)
                # Only include BM25 results for docs that passed vector threshold
                valid_ids = {r.id for r in vector_results}
                bm25_results = [(id, s) for id, s in bm25_results if id in valid_ids]
                search_results = self._fuse_results(vector_results, bm25_results, top_k * 2)
            else:
                search_results = []
        else:
            search_results = vector_results

        # Deduplicate chunks (keeps best chunk per file)
        search_results = self._deduplicate_chunks(search_results)

        # Apply type filter if specified
        if type_filter:
            search_results = [r for r in search_results if r.metadata.get("type") == type_filter]

        # Re-sort after deduplication (scores may have changed order)
        search_results.sort(key=lambda r: r.score, reverse=True)

        # Take top_k after filtering
        search_results = search_results[:top_k]

        # Format direct results
        direct: list[dict[str, Any]] = []
        for r in search_results:
            parent_file, chunk_idx = parse_chunk_id(r.id)
            result_entry: dict[str, Any] = {
                "path": parent_file,  # Always show parent file path
                "type": r.metadata.get("type", "unknown"),
                "score": round(self._rescale_score(r.score), 4),
            }
            # Add chunk info if applicable
            if chunk_idx is not None:
                result_entry["chunk"] = chunk_idx
            # Add line numbers if available
            if r.metadata.get("start_line"):
                result_entry["lines"] = f"{r.metadata['start_line']}-{r.metadata['end_line']}"
            direct.append(result_entry)

        # Phase 2: Graph expansion
        related: list[dict[str, Any]] = []
        if expand and search_results:
            seed_ids = [r.id for r in search_results]
            depth = expand_depth or self.config.graph.max_expand_depth

            expanded = self.graph.expand(
                seed_ids=seed_ids,
                min_weight=self.config.graph.expand_threshold,
                max_depth=depth,
            )

            # Format expanded results, excluding direct matches
            direct_ids = set(seed_ids)
            # Also track parent files for deduplication
            direct_parent_files = {parse_chunk_id(sid)[0] for sid in seed_ids}
            seen_parent_files: set[str] = set()

            for node_id, info in expanded.items():
                if node_id in direct_ids:
                    continue

                parent_file, chunk_idx = parse_chunk_id(node_id)

                # Skip if we've already included this parent file
                if parent_file in direct_parent_files or parent_file in seen_parent_files:
                    continue
                seen_parent_files.add(parent_file)

                # Apply type filter to expanded results too
                if type_filter and info["type"] != type_filter:
                    continue

                via_parent, _ = parse_chunk_id(info["via"])
                related_entry: dict[str, Any] = {
                    "path": parent_file,
                    "type": info["type"],
                    "via": via_parent,
                    "edge_weight": round(info["edge_weight"], 4),
                    "depth": info["depth"],
                }
                if chunk_idx is not None:
                    related_entry["chunk"] = chunk_idx
                related.append(related_entry)

            # Sort by edge weight
            related.sort(key=lambda x: -x["edge_weight"])

        return QueryResult(
            query=query_text,
            direct=direct,
            related=related,
        )

    def to_json(self, result: QueryResult) -> dict[str, Any]:
        """Convert QueryResult to JSON-serializable dict."""
        return {
            "query": result.query,
            "direct": result.direct,
            "related": result.related,
        }
