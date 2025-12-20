"""Similarity graph construction and traversal."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class GraphEdge:
    """Edge in the similarity graph."""

    source: str
    target: str
    weight: float  # Similarity score


@dataclass
class GraphNode:
    """Node in the similarity graph."""

    id: str
    type: str | None = None  # optional user-defined category
    neighbors: dict[str, float] = field(default_factory=dict)  # neighbor_id -> weight


class SimilarityGraph:
    """
    Graph of document relationships based on embedding similarity.

    Built during indexing, used during query expansion.

    Storage format:
        .gundog/index/graph.json
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._dirty = False

    def build(
        self,
        vectors: dict[str, np.ndarray],
        metadata: dict[str, dict[str, Any]],
        threshold: float = 0.65,
    ) -> None:
        """
        Build similarity graph from vectors.

        Creates edges between all document pairs with similarity > threshold.

        Args:
            vectors: Dict mapping file paths to embedding vectors
            metadata: Dict mapping file paths to metadata (must include 'type')
            threshold: Minimum cosine similarity for creating an edge
        """
        self.nodes.clear()
        self.edges.clear()

        # Create nodes
        for node_id, meta in metadata.items():
            self.nodes[node_id] = GraphNode(
                id=node_id,
                type=meta.get("type", "unknown"),
            )

        if not vectors:
            return

        # Compute pairwise similarities and create edges
        ids = list(vectors.keys())
        vecs = np.array([vectors[id] for id in ids])

        # Similarity matrix (vectors are normalized, so dot product = cosine)
        similarity_matrix = vecs @ vecs.T

        # Create edges for pairs above threshold
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                sim = float(similarity_matrix[i, j])
                if sim >= threshold:
                    source, target = ids[i], ids[j]

                    # Add edge
                    self.edges.append(GraphEdge(source=source, target=target, weight=sim))

                    # Update node neighbors (bidirectional)
                    self.nodes[source].neighbors[target] = sim
                    self.nodes[target].neighbors[source] = sim

        self._dirty = True

    def get_neighbors(
        self,
        node_id: str,
        min_weight: float = 0.0,
    ) -> list[tuple[str, float]]:
        """
        Get neighbors of a node.

        Args:
            node_id: ID of node to get neighbors for
            min_weight: Minimum edge weight to include

        Returns:
            List of (neighbor_id, weight) tuples, sorted by weight descending
        """
        if node_id not in self.nodes:
            return []

        neighbors = [
            (nid, weight)
            for nid, weight in self.nodes[node_id].neighbors.items()
            if weight >= min_weight
        ]
        return sorted(neighbors, key=lambda x: -x[1])

    def expand(
        self,
        seed_ids: list[str],
        min_weight: float = 0.60,
        max_depth: int = 1,
    ) -> dict[str, dict[str, Any]]:
        """
        Expand from seed nodes to find related documents.

        Performs BFS from seed nodes up to max_depth.

        Args:
            seed_ids: Starting node IDs (e.g., direct query matches)
            min_weight: Minimum edge weight to traverse
            max_depth: Maximum hops from seed nodes

        Returns:
            Dict mapping discovered node IDs to expansion info:
            {
                "path/to/file.md": {
                    "via": "path/to/seed.md",  # How we got here
                    "edge_weight": 0.72,        # Edge weight from 'via'
                    "depth": 1,                 # Hops from seed
                }
            }
        """
        discovered: dict[str, dict[str, Any]] = {}
        visited = set(seed_ids)

        # BFS frontier: (node_id, via_node, edge_weight, depth)
        frontier: list[tuple[str, str | None, float, int]] = [
            (sid, None, 1.0, 0) for sid in seed_ids
        ]

        while frontier:
            current_id, via_id, edge_weight, depth = frontier.pop(0)

            if depth > 0:  # Don't include seeds in discovered
                node_type = "unknown"
                if current_id in self.nodes:
                    node_type = self.nodes[current_id].type
                discovered[current_id] = {
                    "via": via_id,
                    "edge_weight": edge_weight,
                    "depth": depth,
                    "type": node_type,
                }

            if depth >= max_depth:
                continue

            # Add unvisited neighbors to frontier
            for neighbor_id, weight in self.get_neighbors(current_id, min_weight):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    frontier.append((neighbor_id, current_id, weight, depth + 1))

        return discovered

    def save(self) -> None:
        """Persist graph to disk."""
        if not self._dirty:
            return

        data = {
            "nodes": {
                id: {"type": node.type, "neighbors": node.neighbors}
                for id, node in self.nodes.items()
            },
            "edges": [
                {"source": e.source, "target": e.target, "weight": e.weight} for e in self.edges
            ],
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

        self._dirty = False

    def load(self) -> None:
        """Load graph from disk."""
        if not self.path.exists():
            return

        with open(self.path) as f:
            data = json.load(f)

        self.nodes = {
            id: GraphNode(id=id, type=n["type"], neighbors=n["neighbors"])
            for id, n in data["nodes"].items()
        }

        self.edges = [
            GraphEdge(source=e["source"], target=e["target"], weight=e["weight"])
            for e in data["edges"]
        ]

        self._dirty = False

    def to_dict(self) -> dict:
        """Export graph as dictionary for JSON serialization."""
        return {
            "nodes": [{"id": n.id, "type": n.type} for n in self.nodes.values()],
            "edges": [
                {"source": e.source, "target": e.target, "weight": e.weight} for e in self.edges
            ],
        }

    def to_dot(self) -> str:
        """Export graph in Graphviz DOT format."""
        lines = ["graph G {"]
        lines.append("  layout=neato;")
        lines.append("  overlap=false;")

        # Node styling by type
        type_colors = {"adr": "lightblue", "code": "lightgreen", "doc": "lightyellow"}

        for node in self.nodes.values():
            color = type_colors.get(node.type or "unknown", "white")
            label = Path(node.id).name  # Just filename for readability
            lines.append(f'  "{node.id}" [label="{label}", fillcolor={color}, style=filled];')

        for edge in self.edges:
            lines.append(f'  "{edge.source}" -- "{edge.target}" [weight={edge.weight:.2f}];')

        lines.append("}")
        return "\n".join(lines)
