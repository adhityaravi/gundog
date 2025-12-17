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
    direct: list[dict[str, Any]]
    related: list[dict[str, Any]]


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

        self.store.load()
        self.graph.load()
        if config.hybrid.enabled:
            self.bm25.load()

    @staticmethod
    def _rescale_score(raw_score: float, baseline: float = 0.5) -> float:
        """Rescale raw cosine similarity so baseline becomes 0%."""
        if raw_score <= baseline:
            return 0.0
        return (raw_score - baseline) / (1 - baseline)

    def _fuse_results(
        self,
        vector_results: list[SearchResult],
        bm25_results: list[tuple[str, float]],
        top_k: int,
    ) -> list[SearchResult]:
        """Fuse vector and BM25 results using Reciprocal Rank Fusion."""
        k = 60
        rrf_scores: dict[str, float] = defaultdict(float)
        vector_scores: dict[str, float] = {}
        metadata_map: dict[str, dict[str, Any]] = {}

        for rank, result in enumerate(vector_results):
            rrf_scores[result.id] += self.config.hybrid.vector_weight / (k + rank)
            vector_scores[result.id] = result.score
            metadata_map[result.id] = result.metadata

        for rank, (doc_id, _) in enumerate(bm25_results):
            rrf_scores[doc_id] += self.config.hybrid.bm25_weight / (k + rank)
            if doc_id not in metadata_map:
                result = self.store.get(doc_id)
                metadata_map[doc_id] = result[1] if result else {}

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        return [
            SearchResult(
                id=doc_id,
                score=vector_scores.get(doc_id, 0.0),
                metadata=metadata_map.get(doc_id, {}),
            )
            for doc_id in sorted_ids[:top_k]
        ]

    def _deduplicate_chunks(self, results: list[SearchResult]) -> list[SearchResult]:
        """Keep only the highest-scoring chunk per file."""
        if not self.config.chunking.enabled:
            return results

        best_by_file: dict[str, SearchResult] = {}

        for result in results:
            parent_file, chunk_idx = parse_chunk_id(result.id)

            if parent_file not in best_by_file or result.score > best_by_file[parent_file].score:
                if chunk_idx is not None:
                    result.metadata["_chunk_index"] = chunk_idx
                    result.metadata["_parent_file"] = parent_file
                best_by_file[parent_file] = result

        return list(best_by_file.values())

    def _vector_search(self, query_text: str, top_k: int, min_score: float) -> list[SearchResult]:
        """Perform vector search with optional BM25 fusion."""
        query_vector = self.embedder.embed_text(query_text)
        vector_results = self.store.search(query_vector, top_k=top_k * 2)
        vector_results = [r for r in vector_results if r.score >= min_score]

        if self.config.hybrid.enabled and not self.bm25.is_empty and vector_results:
            bm25_results = self.bm25.search(query_text, top_k=top_k * 2)
            valid_ids = {r.id for r in vector_results}
            bm25_results = [(id, s) for id, s in bm25_results if id in valid_ids]
            return self._fuse_results(vector_results, bm25_results, top_k * 2)

        return vector_results

    def _format_direct_result(self, result: SearchResult) -> dict[str, Any]:
        """Format a single search result for output."""
        parent_file, chunk_idx = parse_chunk_id(result.id)

        entry: dict[str, Any] = {
            "path": parent_file,
            "type": result.metadata.get("type", "unknown"),
            "score": round(self._rescale_score(result.score), 4),
        }

        if chunk_idx is not None:
            entry["chunk"] = chunk_idx

        if result.metadata.get("start_line"):
            entry["lines"] = f"{result.metadata['start_line']}-{result.metadata['end_line']}"

        if result.metadata.get("git_url"):
            entry["git_url"] = result.metadata["git_url"]
            entry["git_branch"] = result.metadata["git_branch"]
            entry["git_relative_path"] = result.metadata["git_relative_path"]

        return entry

    def _expand_graph(
        self,
        seed_results: list[SearchResult],
        expand_depth: int | None,
        type_filter: str | None,
    ) -> list[dict[str, Any]]:
        """Expand results via graph traversal."""
        if not seed_results:
            return []

        seed_ids = [r.id for r in seed_results]
        depth = expand_depth or self.config.graph.max_expand_depth

        expanded = self.graph.expand(
            seed_ids=seed_ids,
            min_weight=self.config.graph.expand_threshold,
            max_depth=depth,
        )

        direct_ids = set(seed_ids)
        direct_parent_files = {parse_chunk_id(sid)[0] for sid in seed_ids}
        seen_parent_files: set[str] = set()

        # First pass: collect node_ids that need metadata lookup
        nodes_to_fetch: list[tuple[str, str, int | None, dict[str, Any]]] = []
        for node_id, info in expanded.items():
            if node_id in direct_ids:
                continue

            parent_file, chunk_idx = parse_chunk_id(node_id)

            if parent_file in direct_parent_files or parent_file in seen_parent_files:
                continue
            seen_parent_files.add(parent_file)

            if type_filter and info["type"] != type_filter:
                continue

            nodes_to_fetch.append((node_id, parent_file, chunk_idx, info))

        # Batch fetch metadata for all nodes at once
        node_ids_to_fetch = [n[0] for n in nodes_to_fetch]
        metadata_batch = self.store.get_batch(node_ids_to_fetch)

        # Build results with fetched metadata
        related: list[dict[str, Any]] = []
        for node_id, parent_file, chunk_idx, info in nodes_to_fetch:
            via_parent, _ = parse_chunk_id(info["via"])
            entry: dict[str, Any] = {
                "path": parent_file,
                "type": info["type"],
                "via": via_parent,
                "edge_weight": round(info["edge_weight"], 4),
                "depth": info["depth"],
            }
            if chunk_idx is not None:
                entry["chunk"] = chunk_idx

            # Add git metadata from batch lookup
            if node_id in metadata_batch:
                _, metadata = metadata_batch[node_id]
                if metadata.get("git_url"):
                    entry["git_url"] = metadata["git_url"]
                    entry["git_branch"] = metadata["git_branch"]
                    entry["git_relative_path"] = metadata["git_relative_path"]

            related.append(entry)

        related.sort(key=lambda x: -x["edge_weight"])
        return related

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
            type_filter: Filter results by type
            min_score: Minimum cosine similarity threshold

        Returns:
            QueryResult with direct matches and related files
        """
        # Phase 1: Vector search
        search_results = self._vector_search(query_text, top_k, min_score)
        search_results = self._deduplicate_chunks(search_results)

        if type_filter:
            search_results = [r for r in search_results if r.metadata.get("type") == type_filter]

        search_results.sort(key=lambda r: r.score, reverse=True)
        search_results = search_results[:top_k]

        # Format direct results
        direct = [self._format_direct_result(r) for r in search_results]

        # Phase 2: Graph expansion
        related: list[dict[str, Any]] = []
        if expand:
            related = self._expand_graph(search_results, expand_depth, type_filter)

        return QueryResult(query=query_text, direct=direct, related=related)

    def to_json(self, result: QueryResult) -> dict[str, Any]:
        """Convert QueryResult to JSON-serializable dict."""
        return {
            "query": result.query,
            "direct": result.direct,
            "related": result.related,
        }
