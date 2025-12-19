"""Shared data types for gundog.

These types are used across all gundog packages for:
- Search results (direct and graph-expanded)
- Graph visualization data
- Index metadata
"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A direct search result.

    Attributes:
        path: Relative path to the file within the index.
        score: Similarity score (0.0 to 1.0).
        type: Content type - "code", "docs", or "config".
        lines: Optional line range (start, end) for the match.
        chunk_index: Optional chunk index within the file.
        content_preview: Optional preview of matching content.
    """

    path: str
    score: float
    type: str = "code"
    lines: tuple[int, int] | None = None
    chunk_index: int | None = None
    content_preview: str | None = None


@dataclass(frozen=True, slots=True)
class RelatedHit:
    """A graph-expanded related result.

    These are files discovered through the similarity graph,
    connected to direct matches.

    Attributes:
        path: Relative path to the file.
        via: Path of the connecting node (how we found this).
        edge_weight: Similarity weight of the connecting edge.
        depth: Graph traversal depth from direct match.
        type: Content type - "code", "docs", or "config".
    """

    path: str
    via: str
    edge_weight: float
    depth: int
    type: str = "code"


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A node in the similarity graph.

    Attributes:
        id: Node identifier (typically file path).
        type: Content type - "code", "docs", or "config".
        score: Optional relevance score for this node.
    """

    id: str
    type: str = "code"
    score: float | None = None


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """An edge in the similarity graph.

    Attributes:
        source: Source node ID.
        target: Target node ID.
        weight: Similarity weight (0.0 to 1.0).
    """

    source: str
    target: str
    weight: float


@dataclass(frozen=True, slots=True)
class GraphData:
    """Graph data for visualization.

    Contains nodes and edges for rendering the similarity graph.
    """

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class QueryResponse:
    """Complete response from a semantic search query.

    Attributes:
        direct: List of direct matches from vector search.
        related: List of related matches from graph expansion.
        graph: Optional graph data for visualization.
        timing_ms: Query execution time in milliseconds.
        total_matches: Total number of matches found.
    """

    direct: list[SearchHit]
    related: list[RelatedHit]
    graph: GraphData | None = None
    timing_ms: float = 0.0
    total_matches: int = 0


@dataclass(frozen=True, slots=True)
class IndexInfo:
    """Information about an available index.

    Attributes:
        name: Index name (used in queries).
        path: Path to the index directory.
        file_count: Number of files in the index.
        is_active: Whether this is the currently active index.
        local_path: Optional client-side path mapping for file preview.
    """

    name: str
    path: str
    file_count: int = 0
    is_active: bool = False
    local_path: str | None = None
